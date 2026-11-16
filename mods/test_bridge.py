"""Unit tests for shared Mod Bridge services in mods/_bridge.py."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

MODS_DIR = Path(__file__).resolve().parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

import _bridge as bridge  # noqa: E402


class BridgeServicesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_is_strict_int_rejects_booleans(self) -> None:
        self.assertTrue(bridge.is_strict_int(0))
        self.assertTrue(bridge.is_strict_int(42))
        self.assertFalse(bridge.is_strict_int(True))
        self.assertFalse(bridge.is_strict_int(False))
        self.assertFalse(bridge.is_strict_int("42"))

    def test_scan_mapping_for_secrets_detects_keys_and_patterns(self) -> None:
        payload = {
            "nested": {
                "apiKey": "super-secret-value",
                "items": [
                    "https://discord.com/api/webhooks/123456789/abcdef_123",
                    "-----BEGIN RSA PRIVATE KEY-----",
                ],
            },
            "emptyPassword": "",
        }
        errors = bridge.scan_mapping_for_secrets(payload, "test.json")
        self.assertEqual(len(errors), 3)
        self.assertTrue(any("apiKey" in e for e in errors))
        self.assertTrue(any("Discord Webhook URL" in e for e in errors))
        self.assertTrue(any("Private Key" in e for e in errors))

    def test_scan_text_for_secrets_detects_patterns(self) -> None:
        text = 'url = "https://canary.discord.com/api/webhooks/999/tok-123"\n'
        errors = bridge.scan_text_for_secrets(text, "raw.conf")
        self.assertEqual(len(errors), 1)
        self.assertIn("Discord Webhook URL", errors[0])

    def test_check_forbidden_entries_rejects_names_suffixes_and_symlinks(self) -> None:
        configs = self.root / "configs"
        configs.mkdir()
        (configs / "tasks").mkdir()
        (configs / "backup.zip").write_bytes(b"zip")
        (configs / "link.json").symlink_to(configs / "backup.zip")

        errors = bridge.check_forbidden_entries(
            configs,
            forbidden_names=("tasks",),
            forbidden_suffixes=(".zip",),
        )
        self.assertTrue(any("tasks" in e for e in errors))
        self.assertTrue(any("backup.zip" in e for e in errors))
        self.assertTrue(any("Symlinks are forbidden" in e for e in errors))

    def test_sync_static_file_atomic_mode_preservation_and_idempotency(self) -> None:
        target = self.root / "data" / "config.json"
        self.assertTrue(bridge.sync_static_file(target, b'{"a": 1}\n', dry_run=True))
        self.assertFalse(target.exists())

        self.assertTrue(bridge.sync_static_file(target, b'{"a": 1}\n', dry_run=False))
        self.assertTrue(target.exists())
        self.assertFalse(bridge.sync_static_file(target, b'{"a": 1}\n', dry_run=False))

        target.chmod(0o640)
        self.assertTrue(bridge.sync_static_file(target, b'{"a": 2}\n', dry_run=False))
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertEqual(target.read_bytes(), b'{"a": 2}\n')


if __name__ == "__main__":
    unittest.main()
