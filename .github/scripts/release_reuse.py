"""Helpers for deduplicating cross-platform CI builds and reusing release artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

TRACKED_DIRS = ("client", "client-e2e", "modsync_api")
REQUIRED_ARTIFACTS = ("ModSync-windows", "ModSync-linux", "build-meta")
META_FILENAME = "build-meta.json"
ACTIVE_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})
FAILURE_CONCLUSIONS = frozenset({"failure", "timed_out", "action_required"})
POLL_INTERVAL_SECONDS = 15
MAX_POLL_WAIT_SECONDS = 900


def read_client_version(pyproject_path: Path = Path("client/pyproject.toml")) -> str:
    """Return the package version declared in client/pyproject.toml."""
    with pyproject_path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"]).strip()


def git_tree_sha(ref: str, subdir: str) -> str:
    """Return the Git tree SHA for a repository subdirectory at a given ref."""
    result = subprocess.run(
        ["git", "rev-parse", f"{ref}^{{tree}}:{subdir}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def collect_subtrees(ref: str = "HEAD") -> dict[str, str]:
    """Return committed Git tree SHAs for all client/API/E2E directories."""
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


def write_github_outputs(output_path: Path, values: dict[str, str]) -> None:
    """Append key=value outputs to the GitHub Actions GITHUB_OUTPUT file."""
    with output_path.open("a", encoding="utf-8") as handle:
        for key, val in values.items():
            handle.write(f"{key}={val}\n")


def gh_api_json(endpoint: str) -> Any:
    """Query the GitHub REST API via the preinstalled gh CLI and parse JSON."""
    res = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(res.stdout)


def run_has_required_artifacts(repo: str, run_id: int) -> bool:
    """Return True if a workflow run has all non-expired release + metadata artifacts."""
    payload = gh_api_json(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")
    valid_names = {
        art["name"]
        for art in payload.get("artifacts", [])
        if not art.get("expired", False)
    }
    return all(name in valid_names for name in REQUIRED_ARTIFACTS)


def download_run_metadata(repo: str, run_id: int) -> dict[str, Any] | None:
    """Download and parse build-meta.json from a GitHub Actions workflow run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = subprocess.run(
            ["gh", "run", "download", str(run_id), "-R", repo, "-n", "build-meta", "-D", tmpdir],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            return None
        meta_file = Path(tmpdir) / META_FILENAME
        if not meta_file.is_file():
            return None
        return json.loads(meta_file.read_text(encoding="utf-8"))


def _latest_push_run(repo: str, head_sha: str) -> dict[str, Any] | None:
    payload = gh_api_json(
        f"repos/{repo}/actions/workflows/ci.yml/runs?event=push&head_sha={head_sha}&per_page=20"
    )
    runs = sorted(
        payload.get("workflow_runs", []),
        key=lambda r: r.get("created_at", ""),
        reverse=True,
    )
    return runs[0] if runs else None


def resolve_ci_e2e(
    *,
    event: str,
    head_sha: str,
    head_repo: str,
    base_repo: str,
) -> tuple[bool, str, int]:
    """Decide whether CI must run client-e2e or can reuse an existing push CI run.

    Returns ``(run_e2e, app_version, exit_code)``.
    """
    app_version = read_client_version()
    if event != "pull_request":
        return True, app_version, 0

    if not head_repo or head_repo != base_repo:
        print("PR originates from a fork or unknown repo; running E2E.")
        return True, app_version, 0

    pr_subtrees = collect_subtrees("HEAD")
    try:
        head_subtrees = collect_subtrees(head_sha)
    except subprocess.CalledProcessError:
        print(f"Head commit {head_sha} not present locally; running E2E.")
        return True, app_version, 0

    if head_subtrees != pr_subtrees:
        print("PR merge tree differs from PR head branch in tracked directories; running E2E.")
        return True, app_version, 0

    run = _latest_push_run(base_repo, head_sha)
    if run is None:
        print(f"No push CI run found for {head_sha}; running E2E.")
        return True, app_version, 0

    run_id = int(run["id"])
    deadline = time.monotonic() + MAX_POLL_WAIT_SECONDS
    while run.get("status") in ACTIVE_STATUSES:
        if time.monotonic() >= deadline:
            print(f"Timed out waiting for push CI run {run_id}; falling back to PR E2E.")
            return True, app_version, 0
        print(f"Waiting for in-progress push CI run {run_id} ({run.get('status')})...")
        time.sleep(POLL_INTERVAL_SECONDS)
        run = gh_api_json(f"repos/{base_repo}/actions/runs/{run_id}")

    conclusion = run.get("conclusion")
    if conclusion in FAILURE_CONCLUSIONS:
        print(f"Matching push CI run {run_id} ended with {conclusion}; failing PR check.")
        return False, app_version, 1

    if conclusion != "success":
        print(f"Push CI run {run_id} ended with {conclusion}; falling back to PR E2E.")
        return True, app_version, 0

    if not run_has_required_artifacts(base_repo, run_id):
        print(f"Push CI run {run_id} is missing required artifacts; running PR E2E.")
        return True, app_version, 0

    meta = download_run_metadata(base_repo, run_id)
    if meta and metadata_matches(
        meta,
        expected_version=app_version,
        expected_subtrees=pr_subtrees,
        expected_repo=base_repo,
    ):
        print(f"Reusing verified push CI run {run_id}; skipping duplicate PR E2E.")
        return False, app_version, 0

    print(f"Push CI run {run_id} metadata mismatch; running PR E2E.")
    return True, app_version, 0


def find_release_run(
    *,
    commit_sha: str,
    repo: str,
    expected_version: str,
) -> str:
    """Return a verified CI Tests run ID whose artifacts match main HEAD, or ''."""
    main_subtrees = collect_subtrees("HEAD")
    candidate_shas: list[str] = [commit_sha]

    pulls = gh_api_json(f"repos/{repo}/commits/{commit_sha}/pulls")
    for pr in pulls:
        pr_head = pr.get("head") or {}
        pr_repo = (pr_head.get("repo") or {}).get("full_name")
        pr_sha = pr_head.get("sha")
        if pr_repo == repo and pr_sha and pr_sha not in candidate_shas:
            candidate_shas.append(pr_sha)

    candidate_runs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for sha in candidate_shas:
        payload = gh_api_json(
            f"repos/{repo}/actions/workflows/ci.yml/runs?head_sha={sha}&status=success&per_page=20"
        )
        for run in payload.get("workflow_runs", []):
            if run.get("conclusion") != "success":
                continue
            if run.get("event") not in ("push", "pull_request"):
                continue
            run_id = int(run["id"])
            if run_id not in seen_ids:
                seen_ids.add(run_id)
                candidate_runs.append(run)

    candidate_runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    for run in candidate_runs:
        run_id = int(run["id"])
        if not run_has_required_artifacts(repo, run_id):
            continue
        meta = download_run_metadata(repo, run_id)
        if meta and metadata_matches(
            meta,
            expected_version=expected_version,
            expected_subtrees=main_subtrees,
            expected_repo=repo,
        ):
            print(f"Found verified CI Tests run {run_id} matching main HEAD.")
            return str(run_id)

    print("No matching CI Tests artifact run found; release workflow will build from source.")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI artifact reuse helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_cmd = subparsers.add_parser("write-meta")
    write_cmd.add_argument("--output", required=True, type=Path)
    write_cmd.add_argument("--source-repo", required=True)
    write_cmd.add_argument("--head-sha", required=True)
    write_cmd.add_argument("--event", required=True)

    pr_cmd = subparsers.add_parser("resolve-e2e")
    pr_cmd.add_argument("--event", required=True)
    pr_cmd.add_argument("--head-sha", default="")
    pr_cmd.add_argument("--head-repo", default="")
    pr_cmd.add_argument("--base-repo", required=True)
    pr_cmd.add_argument("--github-output", required=True, type=Path)

    rel_cmd = subparsers.add_parser("find-release-run")
    rel_cmd.add_argument("--commit-sha", required=True)
    rel_cmd.add_argument("--repo", required=True)
    rel_cmd.add_argument("--expected-version", required=True)
    rel_cmd.add_argument("--github-output", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "write-meta":
        payload = build_metadata(
            version=read_client_version(),
            subtrees=collect_subtrees("HEAD"),
            source_repo=args.source_repo,
            head_sha=args.head_sha,
            event=args.event,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 0

    if args.command == "resolve-e2e":
        run_e2e, app_version, exit_code = resolve_ci_e2e(
            event=args.event,
            head_sha=args.head_sha,
            head_repo=args.head_repo,
            base_repo=args.base_repo,
        )
        write_github_outputs(
            args.github_output,
            {
                "run_e2e": "true" if run_e2e else "false",
                "app_version": app_version,
            },
        )
        return exit_code

    if args.command == "find-release-run":
        run_id = find_release_run(
            commit_sha=args.commit_sha,
            repo=args.repo,
            expected_version=args.expected_version,
        )
        write_github_outputs(args.github_output, {"artifact_run_id": run_id})
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
