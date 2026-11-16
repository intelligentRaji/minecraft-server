#!/usr/bin/env python3
"""Unit and integration tests for project-root sync_mod_configurations.py."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

import sync_mod_configurations


class SyncModConfigurationsTest(unittest.TestCase):
    """Verify mod sync script discovery, --mod filtering, --dry-run forwarding, and fail-fast exit codes."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.mods_dir = self.root / "mods"
        self.mods_dir.mkdir(parents=True, exist_ok=True)

        self.orig_repo_root = sync_mod_configurations.REPO_ROOT
        self.orig_mods_dir = sync_mod_configurations.MODS_DIR
        sync_mod_configurations.REPO_ROOT = self.root
        sync_mod_configurations.MODS_DIR = self.mods_dir

    def tearDown(self) -> None:
        sync_mod_configurations.REPO_ROOT = self.orig_repo_root
        sync_mod_configurations.MODS_DIR = self.orig_mods_dir
        self.tmp_dir.cleanup()

    def _create_mod_sync(self, slug: str, code: str) -> Path:
        mod_dir = self.mods_dir / slug
        mod_dir.mkdir(parents=True, exist_ok=True)
        script = mod_dir / "sync.py"
        script.write_text(textwrap.dedent(code), encoding="utf-8")
        return script

    def test_discover_sorted_sync_scripts(self) -> None:
        s_b = self._create_mod_sync("beta", "import sys; sys.exit(0)\n")
        s_a = self._create_mod_sync("alpha", "import sys; sys.exit(0)\n")
        discovered = sync_mod_configurations.discover_sync_scripts(None)
        self.assertEqual(discovered, [s_a, s_b])

    def test_missing_targeted_mod_returns_error(self) -> None:
        rc = sync_mod_configurations.main(["--mod", "nonexistent"])
        self.assertEqual(rc, 1)

    def test_forwards_dry_run_and_succeeds(self) -> None:
        marker = self.root / "marker.txt"
        self._create_mod_sync(
            "alpha",
            f"""\
            import sys
            from pathlib import Path
            Path({str(marker)!r}).write_text(" ".join(sys.argv[1:]), encoding="utf-8")
            """,
        )
        rc = sync_mod_configurations.main(["--dry-run", "--mod", "alpha"])
        self.assertEqual(rc, 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "--dry-run")

    def test_fails_fast_when_mod_sync_returns_nonzero(self) -> None:
        marker = self.root / "beta_ran.txt"
        self._create_mod_sync("alpha", "import sys; sys.exit(2)\n")
        self._create_mod_sync(
            "beta",
            f"""\
            from pathlib import Path
            Path({str(marker)!r}).write_text("ran", encoding="utf-8")
            """,
        )
        rc = sync_mod_configurations.main([])
        self.assertEqual(rc, 2)
        self.assertFalse(marker.exists(), "Subsequent mod scripts must not run after a failure")


if __name__ == "__main__":
    unittest.main()
