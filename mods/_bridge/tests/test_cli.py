"""Unit tests for `mods/_bridge/cli.py`."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

MODS_DIR = Path(__file__).resolve().parent.parent.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge.cli import run_sync_cli  # noqa: E402


class BridgeCliTest(unittest.TestCase):
    def test_run_sync_cli_dry_run_and_validation_error(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = run_sync_cli(
                "demo",
                lambda: {"a.toml": b"k = 1\n"},
                lambda data, dry_run: (1, 2),
                argv=["--dry-run"],
            )
        self.assertEqual(rc, 0)
        self.assertIn("[demo/sync.py] DRY-RUN: 1 changed, 2 unchanged (total 3 files verified).", stdout.getvalue())

        stderr = io.StringIO()
        def _fail() -> dict[str, bytes]:
            raise ValueError("bad config")

        with contextlib.redirect_stderr(stderr):
            rc_err = run_sync_cli("demo", _fail, lambda data, dry_run: (0, 0), argv=[])
        self.assertEqual(rc_err, 1)
        self.assertIn("[demo/sync.py] ERROR: bad config", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
