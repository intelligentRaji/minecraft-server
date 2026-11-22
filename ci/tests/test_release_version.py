"""Unit tests for ci.release_version."""

from __future__ import annotations

import unittest
from unittest import mock

from ci import release_version
from ci.github_env import GitHubContext


class ReleaseVersionTests(unittest.TestCase):
    def _ctx(
        self,
        *,
        event_name: str = "push",
        ref: str = "refs/heads/main",
        ref_name: str = "main",
        payload: dict | None = None,
    ) -> GitHubContext:
        return GitHubContext(
            event_name=event_name,
            repository="org/minecraft-server",
            sha="deadbeef",
            ref=ref,
            ref_name=ref_name,
            base_ref="",
            output_path=None,
            event_payload=payload or {},
        )

    def test_tag_push_triggers_build_without_artifact_reuse(self) -> None:
        plan = release_version.resolve_release_plan(
            self._ctx(
                event_name="push",
                ref="refs/tags/client-v0.1.4",
                ref_name="client-v0.1.4",
            )
        )
        self.assertEqual(plan.app_version, "0.1.4")
        self.assertEqual(plan.tag_name, "client-v0.1.4")
        self.assertTrue(plan.should_release)
        self.assertEqual(plan.artifact_run_id, "")
        self.assertTrue(plan.needs_build)

    def test_main_push_promotes_verified_ci_run_and_skips_build(self) -> None:
        with (
            mock.patch.object(release_version, "read_client_version", return_value="0.1.4"),
            mock.patch.object(release_version, "tag_exists", return_value=False),
            mock.patch.object(release_version, "find_release_run", return_value="777"),
        ):
            plan = release_version.resolve_release_plan(self._ctx())
        self.assertTrue(plan.should_release)
        self.assertEqual(plan.artifact_run_id, "777")
        self.assertFalse(plan.needs_build)

    def test_main_push_with_existing_tag_skips_release_and_build(self) -> None:
        with (
            mock.patch.object(release_version, "read_client_version", return_value="0.1.3"),
            mock.patch.object(release_version, "tag_exists", return_value=True),
        ):
            plan = release_version.resolve_release_plan(self._ctx())
        self.assertFalse(plan.should_release)
        self.assertEqual(plan.artifact_run_id, "")
        self.assertFalse(plan.needs_build)

    def test_workflow_dispatch_without_publish_still_runs_build(self) -> None:
        with mock.patch.object(release_version, "read_client_version", return_value="0.1.3"):
            plan = release_version.resolve_release_plan(
                self._ctx(
                    event_name="workflow_dispatch",
                    payload={"inputs": {"publish_release": False}},
                )
            )
        self.assertFalse(plan.should_release)
        self.assertTrue(plan.needs_build)


if __name__ == "__main__":
    unittest.main()
