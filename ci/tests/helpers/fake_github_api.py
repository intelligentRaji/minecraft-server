"""In-memory fake GitHub client implementing GitHubClientProtocol for CI unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ci import artifact_reuse


@dataclass
class FakeGitHubApi:
    """In-memory GitHubActions client storing workflow runs, PR associations, artifacts, and metadata."""

    repo: str = "org/minecraft-server"
    runs: dict[int, dict[str, Any]] = field(default_factory=dict)
    run_polls: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    prs_by_commit: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    artifacts_by_run: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    meta_by_run: dict[int, dict[str, Any]] = field(default_factory=dict)

    def add_run(
        self,
        run_id: int,
        *,
        event: str = "push",
        head_sha: str = "abc",
        head_repo: str | None = None,
        status: str = "completed",
        conclusion: str | None = "success",
        created_at: str = "2026-11-22T00:00:00Z",
        artifacts: list[str | dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Register a workflow run and optional artifacts/build-meta."""
        self.runs[run_id] = {
            "id": run_id,
            "event": event,
            "head_sha": head_sha,
            "head_repository": {"full_name": head_repo or self.repo},
            "status": status,
            "conclusion": conclusion,
            "created_at": created_at,
        }
        if artifacts is not None:
            self.artifacts_by_run[run_id] = [
                {"name": item, "expired": False} if isinstance(item, str) else item
                for item in artifacts
            ]
        elif meta is not None:
            self.artifacts_by_run[run_id] = [
                {"name": name, "expired": False} for name in artifact_reuse.REQUIRED_ARTIFACTS
            ]
        if meta is not None:
            self.meta_by_run[run_id] = meta

    def queue_run_poll(
        self,
        run_id: int,
        *,
        status: str = "completed",
        conclusion: str | None = "success",
    ) -> None:
        """Queue a subsequent status snapshot returned when polling get_run()."""
        updated = dict(self.runs[run_id])
        updated.update({"status": status, "conclusion": conclusion})
        self.run_polls.setdefault(run_id, []).append(updated)

    def add_pr_for_commit(
        self,
        commit_sha: str,
        *,
        pr_head_sha: str,
        pr_repo: str | None = None,
    ) -> None:
        """Associate a commit SHA (e.g. a merge commit on main) with a pull request head."""
        self.prs_by_commit.setdefault(commit_sha, []).append(
            {
                "head": {
                    "sha": pr_head_sha,
                    "repo": {"full_name": pr_repo or self.repo},
                }
            }
        )

    def list_ci_runs(
        self,
        repo: str,
        *,
        event: str | None = None,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        if repo != self.repo:
            return []

        def _matches(run: dict[str, Any]) -> bool:
            if event is not None and run.get("event") != event:
                return False
            if head_sha is not None and run.get("head_sha") != head_sha:
                return False
            if status == "success":
                return run.get("conclusion") == "success"
            if status is not None:
                return run.get("status") == status
            return True

        return [run for run in self.runs.values() if _matches(run)][:per_page]

    def get_run(self, repo: str, run_id: int) -> dict[str, Any]:
        assert repo == self.repo, f"Unexpected repo {repo!r}"
        queued = self.run_polls.get(run_id)
        if queued:
            self.runs[run_id] = queued.pop(0)
        return self.runs[run_id]

    def list_run_artifacts(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        return self.artifacts_by_run.get(run_id, []) if repo == self.repo else []

    def list_commit_pulls(self, repo: str, commit_sha: str) -> list[dict[str, Any]]:
        return self.prs_by_commit.get(commit_sha, []) if repo == self.repo else []

    def download_run_metadata(
        self,
        repo: str,
        run_id: int,
        *,
        artifact_name: str = "build-meta",
        filename: str = "build-meta.json",
    ) -> dict[str, Any] | None:
        del artifact_name, filename
        return self.meta_by_run.get(run_id) if repo == self.repo else None
