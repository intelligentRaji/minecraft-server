"""Unit tests for `mods/_bridge/validation.py`."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

MODS_DIR = Path(__file__).resolve().parent.parent.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge.validation import validate_static_configs  # noqa: E402


class BridgeValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_validate_static_configs_success_and_invalid_toml(self) -> None:
        configs = self.root / "configs"
        configs.mkdir()
        (configs / "settings.toml").write_text("enabled = true\n", encoding="utf-8")
        (configs / "rules.json").write_text('["rule 1"]\n', encoding="utf-8")

        static_files = {
            "settings.toml": ("config", "settings.toml"),
            "rules.json": ("config", "rules.json"),
        }
        validators = {
            "settings.toml": lambda d: [] if d.get("enabled") is True else ["must be true"],
            "rules.json": lambda d: [] if isinstance(d, list) else ["must be list"],
        }

        loaded = validate_static_configs(
            configs,
            static_files,
            validators,
            forbidden_names=("world",),
        )
        self.assertEqual(set(loaded.keys()), {"settings.toml", "rules.json"})

        (configs / "settings.toml").write_text("enabled = [unclosed\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            validate_static_configs(configs, static_files, validators)
        self.assertIn("invalid TOML", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
