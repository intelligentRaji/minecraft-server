"""Path-filtered CI trigger detection for push and pull_request events."""

from __future__ import annotations

from .github_env import ref_exists, run_git

TRIGGER_PATH_PREFIXES = ("ci/", "client/", "client-e2e/", "modsync_api/", ".github/")
ZERO_SHA = "0" * 40


def paths_match_client_triggers(paths: list[str]) -> bool:
    """Return True if any changed repository-relative path impacts client build, API, E2E, or CI."""
    for path in paths:
        normalized = path.strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if any(
            normalized == prefix.rstrip("/") or normalized.startswith(prefix)
            for prefix in TRIGGER_PATH_PREFIXES
        ):
            return True
    return False


def _closest_base_commit(head_ref: str = "HEAD") -> str | None:
    """Pick the nearest ancestor base among develop and main for a newly pushed branch."""
    best_base: str | None = None
    best_distance: int | None = None
    head_sha = run_git(["rev-parse", head_ref], check=False).stdout.strip()
    for candidate in ("origin/develop", "origin/main", "develop", "main"):
        if not ref_exists(candidate):
            continue
        mb = run_git(["merge-base", candidate, head_ref], check=False)
        if mb.returncode != 0:
            continue
        base_sha = mb.stdout.strip()
        if base_sha == head_sha:
            return base_sha
        dist_res = run_git(["rev-list", "--count", f"{base_sha}..{head_ref}"], check=False)
        if dist_res.returncode != 0:
            continue
        distance = int(dist_res.stdout.strip() or "0")
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_base = base_sha
    return best_base


def list_changed_files(
    *,
    event: str,
    before_sha: str = "",
    base_ref: str = "",
    head_ref: str = "HEAD",
) -> list[str] | None:
    """Return changed file paths for push/pull_request, or None when diff cannot be determined."""
    if event == "pull_request":
        candidates = [f"origin/{base_ref}", base_ref] if base_ref else ["origin/main", "main"]
        for ref in candidates:
            if ref and ref_exists(ref):
                out = run_git(["diff", "--name-only", f"{ref}...{head_ref}"]).stdout
                return [line for line in out.splitlines() if line.strip()]
        return None

    if event == "push":
        if before_sha and before_sha != ZERO_SHA and ref_exists(before_sha):
            out = run_git(["diff", "--name-only", before_sha, head_ref]).stdout
            return [line for line in out.splitlines() if line.strip()]
        base_sha = _closest_base_commit(head_ref)
        if base_sha:
            out = run_git(["diff", "--name-only", f"{base_sha}..{head_ref}"]).stdout
            return [line for line in out.splitlines() if line.strip()]
        if ref_exists(f"{head_ref}~1"):
            out = run_git(["diff", "--name-only", f"{head_ref}~1", head_ref]).stdout
            return [line for line in out.splitlines() if line.strip()]
        return None

    return None


def has_client_changes(
    *,
    event: str,
    before_sha: str = "",
    base_ref: str = "",
    head_ref: str = "HEAD",
) -> bool:
    """Return True when client/API/E2E/CI files changed (or conservatively if diff is unknown)."""
    changed = list_changed_files(
        event=event,
        before_sha=before_sha,
        base_ref=base_ref,
        head_ref=head_ref,
    )
    if changed is None:
        return True
    return paths_match_client_triggers(changed)
