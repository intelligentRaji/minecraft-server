"""Unit tests for ci.path_triggers."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from ci import path_triggers


class PathTriggerTests(unittest.TestCase):
    def test_paths_match_client_triggers(self) -> None:
        self.assertFalse(
            path_triggers.paths_match_client_triggers(
                ["server/mods/create/configs/foo.toml", "README.md"]
            )
        )
        self.assertTrue(path_triggers.paths_match_client_triggers(["ci/artifact_reuse.py"]))
        self.assertTrue(path_triggers.paths_match_client_triggers(["client/src/modsync_client/main.py"]))
        self.assertTrue(path_triggers.paths_match_client_triggers(["client-e2e/test_tray.py"]))
        self.assertTrue(path_triggers.paths_match_client_triggers(["modsync_api/app.py"]))
        self.assertTrue(path_triggers.paths_match_client_triggers([".github/workflows/ci.yml"]))
        self.assertTrue(path_triggers.paths_match_client_triggers(["./.github/workflows/ci.yml"]))

    def test_new_branch_and_push_diff_detection_in_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }

            def git(*args: str) -> str:
                return subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()

            git("init", "-b", "main")
            (repo / "README.md").write_text("init\n", encoding="utf-8")
            (repo / "client").mkdir()
            (repo / "client" / "app.py").write_text("v1\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "init")

            git("checkout", "-b", "develop")
            (repo / "client" / "app.py").write_text("v2\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "client change on develop")
            dev_sha = git("rev-parse", "HEAD")

            git("checkout", "-b", "feat/server-only")
            prev_cwd = os.getcwd()
            os.chdir(repo)
            try:
                self.assertFalse(
                    path_triggers.has_client_changes(
                        event="push",
                        before_sha=path_triggers.ZERO_SHA,
                    )
                )
                (repo / "README.md").write_text("docs\n", encoding="utf-8")
                git("add", "README.md")
                git("commit", "-m", "docs only")
                self.assertFalse(
                    path_triggers.has_client_changes(
                        event="push",
                        before_sha=dev_sha,
                    )
                )
                prev_sha = git("rev-parse", "HEAD")
                (repo / "client" / "app.py").write_text("v3\n", encoding="utf-8")
                git("add", "client/app.py")
                git("commit", "-m", "client v3")
                self.assertTrue(
                    path_triggers.has_client_changes(
                        event="push",
                        before_sha=prev_sha,
                    )
                )
            finally:
                os.chdir(prev_cwd)


if __name__ == "__main__":
    unittest.main()
