"""Unit tests for `mods/_bridge/files.py`."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

MODS_DIR = Path(__file__).resolve().parent.parent.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge.files import (  # noqa: E402
    apply_static_files,
    check_forbidden_entries,
    sync_static_file,
)


class BridgeFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_check_forbidden_entries_rejects_names_suffixes_and_symlinks(self) -> None:
        configs = self.root / "configs"
        configs.mkdir()
        (configs / "tasks").mkdir()
        (configs / "backup.zip").write_bytes(b"zip")
        (configs / "link.json").symlink_to(configs / "backup.zip")

        errors = check_forbidden_entries(
            configs,
            forbidden_names=("tasks",),
            forbidden_suffixes=(".zip",),
        )
        self.assertTrue(any("tasks" in e for e in errors))
        self.assertTrue(any("backup.zip" in e for e in errors))
        self.assertTrue(any("Symlinks are forbidden" in e for e in errors))

    def test_sync_static_file_atomic_mode_preservation_and_idempotency(self) -> None:
        target = self.root / "data" / "config.json"
        self.assertTrue(sync_static_file(target, b'{"a": 1}\n', dry_run=True))
        self.assertFalse(target.exists())

        self.assertTrue(sync_static_file(target, b'{"a": 1}\n', dry_run=False))
        self.assertTrue(target.exists())
        self.assertFalse(sync_static_file(target, b'{"a": 1}\n', dry_run=False))

        target.chmod(0o640)
        self.assertTrue(sync_static_file(target, b'{"a": 2}\n', dry_run=False))
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertEqual(target.read_bytes(), b'{"a": 2}\n')

    def test_apply_static_files_dry_run_apply_and_idempotency(self) -> None:
        data_dir = self.root / "data"
        static_files = {
            "settings.toml": ("config", "settings.toml"),
            "rules.json": ("config", "rules.json"),
        }
        loaded = {
            "settings.toml": b"enabled = true\n",
            "rules.json": b'["rule 1"]\n',
        }

        self.assertEqual(apply_static_files(static_files, data_dir, loaded, dry_run=True), (2, 0))
        self.assertFalse((data_dir / "config" / "settings.toml").exists())

        self.assertEqual(apply_static_files(static_files, data_dir, loaded, dry_run=False), (2, 0))
        self.assertTrue((data_dir / "config" / "settings.toml").exists())
        self.assertEqual(apply_static_files(static_files, data_dir, loaded, dry_run=False), (0, 2))


if __name__ == "__main__":
    unittest.main()
