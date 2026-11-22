"""Subtree verification, PR push reuse, and verified release artifact promotion."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from .github_env import GhCliGitHubClient, GitHubClientProtocol, run_git
from .path_triggers import TRIGGER_PATH_PREFIXES, has_client_changes

TRACKED_DIRS = ("ci", "client", "client-e2e", "modsync_api", ".github")
REQUIRED_ARTIFACTS = ("ModSync-windows", "ModSync-linux", "build-meta")
META_FILENAME = "build-meta.json"
ACTIVE_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})
FAILURE_CONCLUSIONS = frozenset({"failure", "timed_out", "action_required"})
POLL_INTERVAL_SECONDS = 15
MAX_POLL_WAIT_SECONDS = 900


def git_tree_sha(ref: str, subdir: str) -> str:
    """Return the Git tree SHA for a repository subdirectory at a given ref."""
    return run_git(["rev-parse", f"{ref}^{{tree}}:{subdir}"]).stdout.strip()


def collect_subtrees(ref: str = "HEAD") -> dict[str, str]:
    """Return committed Git tree SHAs for all tracked CI/client/API/E2E directories."""
    return {subdir: git_tree_sha(ref, subdir) for subdir in TRACKED_DIRS}


def build_metadata(
    *,
    version: str,
    subtrees: dict[str, str],
    source_repo: str,
    head_sha: str,
    event: str,
) -> dict[str, Any]:
    """Create the serializable build-meta payload for artifact verification."""
    return {
        "version": version,
        "subtrees": subtrees,
        "source_repo": source_repo,
        "head_sha": head_sha,
        "event": event,
    }


def metadata_matches(
    meta: dict[str, Any],
    *,
    expected_version: str,
    expected_subtrees: dict[str, str],
    expected_repo: str,
) -> bool:
    """Return True only when downloaded build-meta matches version, repo, and all subtrees."""
    return (
        meta.get("version") == expected_version
        and meta.get("source_repo") == expected_repo
        and meta.get("subtrees") == expected_subtrees
    )


def run_has_required_artifacts(
    repo: str,
    run_id: int,
    *,
    client: GitHubClientProtocol | None = None,
) -> bool:
    """Return True if a workflow run has all non-expired release + metadata artifacts."""
    gh = client or GhCliGitHubClient()
    valid_names = {
        art["name"]
        for art in gh.list_run_artifacts(repo, run_id)
        if not art.get("expired", False)
    }
    return all(name in valid_names for name in REQUIRED_ARTIFACTS)


def _latest_push_run(
    client: GitHubClientProtocol,
    repo: str,
    head_sha: str,
) -> dict[str, Any] | None:
    runs = sorted(
        client.list_ci_runs(repo, event="push", head_sha=head_sha),
        key=lambda r: r.get("created_at", ""),
        reverse=True,
    )
    return runs[0] if runs else None


def _is_trusted_repo_run(run: dict[str, Any], repo: str) -> bool:
    head_repo = run.get("head_repository")
    if isinstance(head_repo, dict) and head_repo.get("full_name"):
        return head_repo.get("full_name") == repo
    return True


def find_matching_verified_run(
    *,
    repo: str,
    expected_version: str,
    expected_subtrees: dict[str, str],
    candidate_shas: list[str] | None = None,
    client: GitHubClientProtocol | None = None,
) -> str:
    """Find a successful CI Tests run with matching build-meta and non-expired artifacts."""
    gh = client or GhCliGitHubClient()
    candidate_runs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    def _collect(runs: list[dict[str, Any]]) -> None:
        for run in runs:
            if run.get("conclusion") != "success":
                continue
            if run.get("event") not in ("push", "pull_request"):
                continue
            if not _is_trusted_repo_run(run, repo):
                continue
            run_id = int(run["id"])
            if run_id not in seen_ids:
                seen_ids.add(run_id)
                candidate_runs.append(run)

    for sha in candidate_shas or []:
        _collect(gh.list_ci_runs(repo, head_sha=sha, status="success"))
    _collect(gh.list_ci_runs(repo, status="success"))

    candidate_runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    for run in candidate_runs:
        run_id = int(run["id"])
        if not run_has_required_artifacts(repo, run_id, client=gh):
            continue
        meta = gh.download_run_metadata(repo, run_id)
        if meta and metadata_matches(
            meta,
            expected_version=expected_version,
            expected_subtrees=expected_subtrees,
            expected_repo=repo,
        ):
            return str(run_id)
    return ""


def resolve_ci_e2e(
    *,
    event: str,
    head_sha: str,
    head_repo: str,
    base_repo: str,
    app_version: str,
    base_ref: str = "",
    before_sha: str = "",
    client: GitHubClientProtocol | None = None,
) -> tuple[bool, int]:
    """Decide whether CI must run client-e2e based on path triggers and artifact reuse.

    Returns ``(run_e2e, exit_code)``.
    """
    if not has_client_changes(event=event, before_sha=before_sha, base_ref=base_ref):
        print(f"No changes in {TRIGGER_PATH_PREFIXES}; skipping client-e2e.")
        return False, 0

    if event != "pull_request":
        print("Client/API/E2E/CI paths changed on push; running client-e2e.")
        return True, 0

    if not head_repo or head_repo != base_repo:
        print("PR originates from a fork or unknown repo; running E2E.")
        return True, 0

    gh = client or GhCliGitHubClient()
    pr_subtrees = collect_subtrees("HEAD")
    head_matches_pr_tree = False
    try:
        head_matches_pr_tree = collect_subtrees(head_sha) == pr_subtrees
    except subprocess.CalledProcessError:
        head_matches_pr_tree = False

    if head_matches_pr_tree and head_sha:
        run = _latest_push_run(gh, base_repo, head_sha)
        if run is not None:
            run_id = int(run["id"])
            deadline = time.monotonic() + MAX_POLL_WAIT_SECONDS
            while run.get("status") in ACTIVE_STATUSES:
                if time.monotonic() >= deadline:
                    print(f"Timed out waiting for push CI run {run_id}; falling back to PR E2E.")
                    return True, 0
                print(f"Waiting for in-progress push CI run {run_id} ({run.get('status')})...")
                time.sleep(POLL_INTERVAL_SECONDS)
                run = gh.get_run(base_repo, run_id)

            conclusion = run.get("conclusion")
            if conclusion in FAILURE_CONCLUSIONS:
                print(f"Matching push CI run {run_id} ended with {conclusion}; failing PR check.")
                return False, 1

            if conclusion == "success" and run_has_required_artifacts(base_repo, run_id, client=gh):
                meta = gh.download_run_metadata(base_repo, run_id)
                if meta and metadata_matches(
                    meta,
                    expected_version=app_version,
                    expected_subtrees=pr_subtrees,
                    expected_repo=base_repo,
                ):
                    print(f"Reusing verified push CI run {run_id}; skipping duplicate PR E2E.")
                    return False, 0

    reused_id = find_matching_verified_run(
        repo=base_repo,
        expected_version=app_version,
        expected_subtrees=pr_subtrees,
        candidate_shas=[head_sha] if head_sha else None,
        client=gh,
    )
    if reused_id:
        print(f"Reusing verified CI run {reused_id} matching PR tree; skipping duplicate PR E2E.")
        return False, 0

    print("No matching verified CI run found; running PR E2E.")
    return True, 0


def find_release_run(
    *,
    commit_sha: str,
    repo: str,
    expected_version: str,
    client: GitHubClientProtocol | None = None,
) -> str:
    """Return a verified CI Tests run ID whose artifacts match main HEAD, or ''."""
    gh = client or GhCliGitHubClient()
    main_subtrees = collect_subtrees("HEAD")
    candidate_shas: list[str] = [commit_sha]

    for pr in gh.list_commit_pulls(repo, commit_sha):
        pr_head = pr.get("head") or {}
        pr_repo = (pr_head.get("repo") or {}).get("full_name")
        pr_sha = pr_head.get("sha")
        if pr_repo == repo and pr_sha and pr_sha not in candidate_shas:
            candidate_shas.append(pr_sha)

    run_id = find_matching_verified_run(
        repo=repo,
        expected_version=expected_version,
        expected_subtrees=main_subtrees,
        candidate_shas=candidate_shas,
        client=gh,
    )
    if run_id:
        print(f"Found verified CI Tests run {run_id} matching main HEAD.")
        return run_id

    print("No matching CI Tests artifact run found; release workflow will build from source.")
    return ""
