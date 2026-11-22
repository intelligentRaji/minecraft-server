"""Unit tests for .github/scripts/release_reuse.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_reuse


class ResolveCiE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.subtrees = {"client": "t1", "client-e2e": "t2", "modsync_api": "t3"}

    def test_push_event_always_runs_e2e(self) -> None:
        with mock.patch.object(release_reuse, "read_client_version", return_value="0.1.2"):
            run_e2e, ver, code = release_reuse.resolve_ci_e2e(
                event="push",
                head_sha="abc",
                head_repo="org/minecraft-server",
                base_repo="org/minecraft-server",
            )
        self.assertEqual((run_e2e, ver, code), (True, "0.1.2", 0))

    def test_fork_pr_always_runs_e2e(self) -> None:
        with mock.patch.object(release_reuse, "read_client_version", return_value="0.1.2"):
            run_e2e, ver, code = release_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo="fork/minecraft-server",
                base_repo="org/minecraft-server",
            )
        self.assertEqual((run_e2e, ver, code), (True, "0.1.2", 0))

    def test_subtree_divergence_runs_e2e(self) -> None:
        diverged = {"client": "other", "client-e2e": "t2", "modsync_api": "t3"}
        with (
            mock.patch.object(release_reuse, "read_client_version", return_value="0.1.2"),
            mock.patch.object(
                release_reuse,
                "collect_subtrees",
                side_effect=[self.subtrees, diverged],
            ),
        ):
            run_e2e, _, code = release_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo="org/minecraft-server",
                base_repo="org/minecraft-server",
            )
        self.assertEqual((run_e2e, code), (True, 0))

    def test_reuses_completed_matching_push_run(self) -> None:
        meta = release_reuse.build_metadata(
            version="0.1.2",
            subtrees=self.subtrees,
            source_repo="org/minecraft-server",
            head_sha="abc",
            event="push",
        )
        with (
            mock.patch.object(release_reuse, "read_client_version", return_value="0.1.2"),
            mock.patch.object(
                release_reuse,
                "collect_subtrees",
                side_effect=[self.subtrees, self.subtrees],
            ),
            mock.patch.object(
                release_reuse,
                "_latest_push_run",
                return_value={"id": 42, "status": "completed", "conclusion": "success"},
            ),
            mock.patch.object(release_reuse, "run_has_required_artifacts", return_value=True),
            mock.patch.object(release_reuse, "download_run_metadata", return_value=meta),
        ):
            run_e2e, _, code = release_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo="org/minecraft-server",
                base_repo="org/minecraft-server",
            )
        self.assertEqual((run_e2e, code), (False, 0))

    def test_waits_for_in_progress_push_run_then_fails_if_push_fails(self) -> None:
        with (
            mock.patch.object(release_reuse, "read_client_version", return_value="0.1.2"),
            mock.patch.object(
                release_reuse,
                "collect_subtrees",
                side_effect=[self.subtrees, self.subtrees],
            ),
            mock.patch.object(
                release_reuse,
                "_latest_push_run",
                return_value={"id": 42, "status": "in_progress", "conclusion": None},
            ),
            mock.patch.object(
                release_reuse,
                "gh_api_json",
                return_value={"id": 42, "status": "completed", "conclusion": "failure"},
            ),
            mock.patch.object(release_reuse.time, "sleep"),
        ):
            run_e2e, _, code = release_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo="org/minecraft-server",
                base_repo="org/minecraft-server",
            )
        self.assertEqual((run_e2e, code), (False, 1))


class FindReleaseRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.subtrees = {"client": "t1", "client-e2e": "t2", "modsync_api": "t3"}

    def test_finds_matching_run_from_merged_pr_head_sha(self) -> None:
        meta = release_reuse.build_metadata(
            version="0.1.2",
            subtrees=self.subtrees,
            source_repo="org/minecraft-server",
            head_sha="pr-head",
            event="push",
        )

        def fake_api(endpoint: str) -> object:
            if endpoint.endswith("/pulls"):
                return [
                    {
                        "head": {
                            "sha": "pr-head",
                            "repo": {"full_name": "org/minecraft-server"},
                        }
                    }
                ]
            if "head_sha=merge-sha" in endpoint:
                return {"workflow_runs": []}
            if "head_sha=pr-head" in endpoint:
                return {
                    "workflow_runs": [
                        {
                            "id": 999,
                            "event": "push",
                            "conclusion": "success",
                            "created_at": "2026-11-22T00:00:00Z",
                        }
                    ]
                }
            raise AssertionError(f"Unexpected endpoint: {endpoint}")

        with (
            mock.patch.object(release_reuse, "collect_subtrees", return_value=self.subtrees),
            mock.patch.object(release_reuse, "gh_api_json", side_effect=fake_api),
            mock.patch.object(release_reuse, "run_has_required_artifacts", return_value=True),
            mock.patch.object(release_reuse, "download_run_metadata", return_value=meta),
        ):
            run_id = release_reuse.find_release_run(
                commit_sha="merge-sha",
                repo="org/minecraft-server",
                expected_version="0.1.2",
            )
        self.assertEqual(run_id, "999")

    def test_ignores_fork_pr_and_mismatched_version(self) -> None:
        bad_meta = release_reuse.build_metadata(
            version="0.1.1",
            subtrees=self.subtrees,
            source_repo="org/minecraft-server",
            head_sha="merge-sha",
            event="push",
        )

        def fake_api(endpoint: str) -> object:
            if endpoint.endswith("/pulls"):
                return [
                    {"head": {"sha": "fork-sha", "repo": {"full_name": "fork/minecraft-server"}}}
                ]
            if "head_sha=merge-sha" in endpoint:
                return {
                    "workflow_runs": [
                        {
                            "id": 100,
                            "event": "push",
                            "conclusion": "success",
                            "created_at": "2026-11-22T00:00:00Z",
                        }
                    ]
                }
            raise AssertionError(f"Unexpected endpoint: {endpoint}")

        with (
            mock.patch.object(release_reuse, "collect_subtrees", return_value=self.subtrees),
            mock.patch.object(release_reuse, "gh_api_json", side_effect=fake_api),
            mock.patch.object(release_reuse, "run_has_required_artifacts", return_value=True),
            mock.patch.object(release_reuse, "download_run_metadata", return_value=bad_meta),
        ):
            run_id = release_reuse.find_release_run(
                commit_sha="merge-sha",
                repo="org/minecraft-server",
                expected_version="0.1.2",
            )
        self.assertEqual(run_id, "")


if __name__ == "__main__":
    unittest.main()
