"""GitHub Actions environment, event payload, Git, and GitHub CLI client helpers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode


@dataclass(frozen=True)
class GitHubContext:
    """Resolved GitHub Actions workflow context from environment and event JSON."""

    event_name: str
    repository: str
    sha: str
    ref: str
    ref_name: str
    base_ref: str
    output_path: Path | None
    event_payload: dict[str, Any]

    @property
    def before_sha(self) -> str:
        return str(self.event_payload.get("before") or "")

    @property
    def pr_head_sha(self) -> str:
        pr = self.event_payload.get("pull_request") or {}
        head = pr.get("head") or {}
        return str(head.get("sha") or "")

    @property
    def pr_head_repo(self) -> str:
        pr = self.event_payload.get("pull_request") or {}
        head = pr.get("head") or {}
        repo = head.get("repo") or {}
        return str(repo.get("full_name") or "")

    @property
    def dispatch_publish_release(self) -> bool:
        inputs = self.event_payload.get("inputs") or {}
        val = inputs.get("publish_release", False)
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() == "true"

    @classmethod
    def from_env(cls) -> GitHubContext:
        event_path_raw = os.environ.get("GITHUB_EVENT_PATH", "").strip()
        payload: dict[str, Any] = {}
        if event_path_raw:
            event_file = Path(event_path_raw)
            if event_file.is_file():
                payload = json.loads(event_file.read_text(encoding="utf-8"))
        output_raw = os.environ.get("GITHUB_OUTPUT", "").strip()
        return cls(
            event_name=os.environ.get("GITHUB_EVENT_NAME", "").strip(),
            repository=os.environ.get("GITHUB_REPOSITORY", "").strip(),
            sha=os.environ.get("GITHUB_SHA", "").strip(),
            ref=os.environ.get("GITHUB_REF", "").strip(),
            ref_name=os.environ.get("GITHUB_REF_NAME", "").strip(),
            base_ref=os.environ.get("GITHUB_BASE_REF", "").strip(),
            output_path=Path(output_raw) if output_raw else None,
            event_payload=payload,
        )


def write_github_outputs(output_path: Path | None, values: dict[str, str]) -> None:
    """Append key=value outputs to GITHUB_OUTPUT (or stdout when running locally)."""
    if output_path is None:
        for key, val in values.items():
            print(f"{key}={val}")
        return
    with output_path.open("a", encoding="utf-8") as handle:
        for key, val in values.items():
            handle.write(f"{key}={val}\n")


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute a git command and return its captured output."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def ref_exists(ref: str) -> bool:
    """Return True if a Git ref resolves to a commit locally."""
    res = run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], check=False)
    return res.returncode == 0


def tag_exists(tag_name: str) -> bool:
    """Return True if a Git tag exists in refs/tags/."""
    res = run_git(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag_name}"], check=False)
    return res.returncode == 0


def gh_api_json(endpoint: str) -> object:
    """Query the GitHub REST API via gh CLI and parse JSON."""
    res = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(res.stdout)


class GitHubClientProtocol(Protocol):
    """Typed boundary for GitHub Actions REST and artifact metadata queries."""

    def list_ci_runs(
        self,
        repo: str,
        *,
        event: str | None = None,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, Any]]: ...

    def get_run(self, repo: str, run_id: int) -> dict[str, Any]: ...

    def list_run_artifacts(self, repo: str, run_id: int) -> list[dict[str, Any]]: ...

    def list_commit_pulls(self, repo: str, commit_sha: str) -> list[dict[str, Any]]: ...

    def download_run_metadata(
        self,
        repo: str,
        run_id: int,
        *,
        artifact_name: str = "build-meta",
        filename: str = "build-meta.json",
    ) -> dict[str, Any] | None: ...


class GhCliGitHubClient:
    """Production GitHub Actions client backed by the preinstalled gh CLI."""

    def list_ci_runs(
        self,
        repo: str,
        *,
        event: str | None = None,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        query: dict[str, str | int] = {"per_page": per_page}
        if event:
            query["event"] = event
        if head_sha:
            query["head_sha"] = head_sha
        if status:
            query["status"] = status
        endpoint = f"repos/{repo}/actions/workflows/ci.yml/runs?{urlencode(query)}"
        payload = gh_api_json(endpoint)
        assert isinstance(payload, dict)
        return list(payload.get("workflow_runs", []))

    def get_run(self, repo: str, run_id: int) -> dict[str, Any]:
        payload = gh_api_json(f"repos/{repo}/actions/runs/{run_id}")
        assert isinstance(payload, dict)
        return dict(payload)

    def list_run_artifacts(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        payload = gh_api_json(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")
        assert isinstance(payload, dict)
        return list(payload.get("artifacts", []))

    def list_commit_pulls(self, repo: str, commit_sha: str) -> list[dict[str, Any]]:
        payload = gh_api_json(f"repos/{repo}/commits/{commit_sha}/pulls")
        assert isinstance(payload, list)
        return list(payload)

    def download_run_metadata(
        self,
        repo: str,
        run_id: int,
        *,
        artifact_name: str = "build-meta",
        filename: str = "build-meta.json",
    ) -> dict[str, Any] | None:
        with tempfile.TemporaryDirectory() as tmpdir:
            res = subprocess.run(
                ["gh", "run", "download", str(run_id), "-R", repo, "-n", artifact_name, "-D", tmpdir],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                return None
            meta_file = Path(tmpdir) / filename
            if not meta_file.is_file():
                return None
            return json.loads(meta_file.read_text(encoding="utf-8"))
