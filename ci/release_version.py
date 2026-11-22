"""Release version resolution and release/build gating."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .artifact_reuse import find_release_run
from .github_env import GitHubContext, tag_exists

CLIENT_PYPROJECT_PATH = Path("client/pyproject.toml")
RELEASE_TAG_PREFIX = "client-v"


@dataclass(frozen=True)
class ReleasePlan:
    """Outputs produced by prepare-release for downstream release jobs."""

    app_version: str
    tag_name: str
    should_release: bool
    artifact_run_id: str
    needs_build: bool

    def to_outputs(self) -> dict[str, str]:
        return {
            "app_version": self.app_version,
            "tag_name": self.tag_name,
            "should_release": "true" if self.should_release else "false",
            "artifact_run_id": self.artifact_run_id,
            "needs_build": "true" if self.needs_build else "false",
        }


def read_client_version(pyproject_path: Path = CLIENT_PYPROJECT_PATH) -> str:
    """Return the package version declared in client/pyproject.toml."""
    with pyproject_path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"]).strip()


def resolve_release_plan(
    ctx: GitHubContext,
    *,
    pyproject_path: Path = CLIENT_PYPROJECT_PATH,
) -> ReleasePlan:
    """Determine version, tag, artifact reuse, and whether release build/E2E must run."""
    if ctx.ref.startswith(f"refs/tags/{RELEASE_TAG_PREFIX}"):
        app_version = ctx.ref_name.removeprefix(RELEASE_TAG_PREFIX)
        tag_name = ctx.ref_name
        should_release = True
        is_tag_push = True
    else:
        app_version = read_client_version(pyproject_path)
        tag_name = f"{RELEASE_TAG_PREFIX}{app_version}"
        is_tag_push = False
        if ctx.event_name == "workflow_dispatch":
            should_release = ctx.dispatch_publish_release
        elif tag_exists(tag_name):
            print(f"Tag {tag_name} already exists; skipping release.")
            should_release = False
        else:
            print(f"New version {app_version} detected on main; will publish {tag_name}.")
            should_release = True

    artifact_run_id = ""
    if should_release and ctx.event_name != "workflow_dispatch" and not is_tag_push:
        artifact_run_id = find_release_run(
            commit_sha=ctx.sha,
            repo=ctx.repository,
            expected_version=app_version,
        )

    needs_build = (not artifact_run_id) and (
        should_release or ctx.event_name == "workflow_dispatch"
    )
    return ReleasePlan(
        app_version=app_version,
        tag_name=tag_name,
        should_release=should_release,
        artifact_run_id=artifact_run_id,
        needs_build=needs_build,
    )
