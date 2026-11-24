"""Unit tests for ci.client_build."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ci import client_build


class ClientBuildTests(unittest.TestCase):
    def test_sync_client_version_writes_expected_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_file = Path(tmp) / "__init__.py"
            client_build.sync_client_version(" 0.1.4 ", init_path=init_file)
            self.assertEqual(
                init_file.read_text(encoding="utf-8"),
                '"""ModSync background client package."""\n\n__version__ = "0.1.4"\n',
            )

    def test_windows_defender_exclusion_paths_deduplicates(self) -> None:
        env = {
            "GITHUB_WORKSPACE": "/ws",
            "TEMP": "/tmp/runner",
            "TMP": "/tmp/runner",
            "LOCALAPPDATA": "/local",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            paths = client_build.windows_defender_exclusion_paths()
        self.assertEqual(paths, ["/ws", "/tmp/runner"])

    def test_exclude_windows_defender_paths_warns_without_raising(self) -> None:
        failed = mock.Mock(returncode=1, stdout="", stderr="access denied")
        with mock.patch.object(client_build.subprocess, "run", return_value=failed) as run_mock:
            client_build.exclude_windows_defender_paths(["C:\\workspace"])
        run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
