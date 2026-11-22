"""Unit tests for ci.artifact_reuse."""

from __future__ import annotations

import unittest
from unittest import mock

from ci import artifact_reuse
from ci.tests.helpers.fake_github_api import FakeGitHubApi


class ResolveCiE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = "org/minecraft-server"
        self.subtrees = {
            "ci": "t0",
            "client": "t1",
            "client-e2e": "t2",
            "modsync_api": "t3",
            ".github": "t4",
        }
        self.fake = FakeGitHubApi(repo=self.repo)

    def _meta(
        self,
        *,
        version: str = "0.1.3",
        head_sha: str = "abc",
        source_repo: str | None = None,
    ) -> dict:
        return artifact_reuse.build_metadata(
            version=version,
            subtrees=self.subtrees,
            source_repo=source_repo or self.repo,
            head_sha=head_sha,
            event="push",
        )

    def test_push_without_client_changes_skips_e2e(self) -> None:
        with mock.patch.object(artifact_reuse, "has_client_changes", return_value=False):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="push",
                head_sha="abc",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (False, 0))

    def test_push_with_client_changes_runs_e2e(self) -> None:
        with mock.patch.object(artifact_reuse, "has_client_changes", return_value=True):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="push",
                head_sha="abc",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (True, 0))

    def test_pr_without_client_changes_skips_e2e(self) -> None:
        with mock.patch.object(artifact_reuse, "has_client_changes", return_value=False):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                base_ref="main",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (False, 0))

    def test_fork_pr_with_client_changes_runs_e2e(self) -> None:
        with mock.patch.object(artifact_reuse, "has_client_changes", return_value=True):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo="fork/minecraft-server",
                base_repo=self.repo,
                app_version="0.1.3",
                base_ref="main",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (True, 0))

    def test_subtree_divergence_runs_e2e_when_no_recent_match(self) -> None:
        diverged = {**self.subtrees, "client": "other"}
        with (
            mock.patch.object(artifact_reuse, "has_client_changes", return_value=True),
            mock.patch.object(
                artifact_reuse,
                "collect_subtrees",
                side_effect=[self.subtrees, diverged],
            ),
        ):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (True, 0))

    def test_reuses_completed_matching_push_run(self) -> None:
        self.fake.add_run(42, event="push", head_sha="abc", meta=self._meta())
        with (
            mock.patch.object(artifact_reuse, "has_client_changes", return_value=True),
            mock.patch.object(artifact_reuse, "collect_subtrees", return_value=self.subtrees),
        ):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (False, 0))

    def test_reuses_earlier_branch_push_run_if_last_commit_skipped_e2e(self) -> None:
        self.fake.add_run(
            41,
            event="push",
            head_sha="c1",
            created_at="2026-11-22T01:00:00Z",
            meta=self._meta(head_sha="c1"),
        )
        self.fake.add_run(
            43,
            event="push",
            head_sha="c2",
            created_at="2026-11-22T02:00:00Z",
            artifacts=[],
        )
        with (
            mock.patch.object(artifact_reuse, "has_client_changes", return_value=True),
            mock.patch.object(artifact_reuse, "collect_subtrees", return_value=self.subtrees),
        ):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="c2",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (False, 0))

    def test_waits_for_in_progress_push_run_then_fails_if_push_fails(self) -> None:
        self.fake.add_run(42, event="push", head_sha="abc", status="in_progress", conclusion=None)
        self.fake.queue_run_poll(42, status="completed", conclusion="failure")
        with (
            mock.patch.object(artifact_reuse, "has_client_changes", return_value=True),
            mock.patch.object(artifact_reuse, "collect_subtrees", return_value=self.subtrees),
            mock.patch.object(artifact_reuse.time, "sleep"),
        ):
            run_e2e, code = artifact_reuse.resolve_ci_e2e(
                event="pull_request",
                head_sha="abc",
                head_repo=self.repo,
                base_repo=self.repo,
                app_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual((run_e2e, code), (False, 1))


class FindReleaseRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = "org/minecraft-server"
        self.subtrees = {
            "ci": "t0",
            "client": "t1",
            "client-e2e": "t2",
            "modsync_api": "t3",
            ".github": "t4",
        }
        self.fake = FakeGitHubApi(repo=self.repo)

    def _meta(self, *, version: str = "0.1.3", head_sha: str = "pr-head") -> dict:
        return artifact_reuse.build_metadata(
            version=version,
            subtrees=self.subtrees,
            source_repo=self.repo,
            head_sha=head_sha,
            event="push",
        )

    def test_finds_matching_run_from_merged_pr_head_sha(self) -> None:
        self.fake.add_pr_for_commit("merge-sha", pr_head_sha="pr-head")
        self.fake.add_run(999, event="push", head_sha="pr-head", meta=self._meta())
        with mock.patch.object(artifact_reuse, "collect_subtrees", return_value=self.subtrees):
            run_id = artifact_reuse.find_release_run(
                commit_sha="merge-sha",
                repo=self.repo,
                expected_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual(run_id, "999")

    def test_skips_expired_artifacts_and_picks_newer_valid_run(self) -> None:
        self.fake.add_run(
            101,
            event="push",
            head_sha="old-sha",
            created_at="2026-11-22T01:00:00Z",
            artifacts=[{"name": name, "expired": True} for name in artifact_reuse.REQUIRED_ARTIFACTS],
            meta=self._meta(head_sha="old-sha"),
        )
        self.fake.add_run(
            102,
            event="pull_request",
            head_sha="pr-head",
            created_at="2026-11-22T02:00:00Z",
            meta=self._meta(head_sha="pr-head"),
        )
        with mock.patch.object(artifact_reuse, "collect_subtrees", return_value=self.subtrees):
            run_id = artifact_reuse.find_release_run(
                commit_sha="merge-sha",
                repo=self.repo,
                expected_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual(run_id, "102")

    def test_ignores_fork_runs_and_mismatched_version(self) -> None:
        self.fake.add_pr_for_commit("merge-sha", pr_head_sha="fork-sha", pr_repo="fork/minecraft-server")
        self.fake.add_run(
            100,
            event="push",
            head_sha="merge-sha",
            meta=self._meta(version="0.1.2", head_sha="merge-sha"),
        )
        self.fake.add_run(
            200,
            event="pull_request",
            head_sha="fork-sha",
            head_repo="fork/minecraft-server",
            meta=self._meta(version="0.1.3", head_sha="fork-sha"),
        )
        with mock.patch.object(artifact_reuse, "collect_subtrees", return_value=self.subtrees):
            run_id = artifact_reuse.find_release_run(
                commit_sha="merge-sha",
                repo=self.repo,
                expected_version="0.1.3",
                client=self.fake,
            )
        self.assertEqual(run_id, "")


if __name__ == "__main__":
    unittest.main()
