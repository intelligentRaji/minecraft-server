"""Unit tests for `mods/_bridge/secrets.py`."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODS_DIR = Path(__file__).resolve().parent.parent.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge.secrets import scan_mapping_for_secrets, scan_text_for_secrets  # noqa: E402


class BridgeSecretsTest(unittest.TestCase):
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
        errors = scan_mapping_for_secrets(payload, "test.json")
        self.assertEqual(len(errors), 3)
        self.assertTrue(any("apiKey" in e for e in errors))
        self.assertTrue(any("Discord Webhook URL" in e for e in errors))
        self.assertTrue(any("Private Key" in e for e in errors))

    def test_scan_text_for_secrets_detects_patterns(self) -> None:
        text = 'url = "https://canary.discord.com/api/webhooks/999/tok-123"\n'
        errors = scan_text_for_secrets(text, "raw.conf")
        self.assertEqual(len(errors), 1)
        self.assertIn("Discord Webhook URL", errors[0])


if __name__ == "__main__":
    unittest.main()
