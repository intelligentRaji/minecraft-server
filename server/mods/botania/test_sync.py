#!/usr/bin/env python3
"""Unit and integration tests for mods/botania/sync.py."""

from __future__ import annotations

import copy
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

VALID_CONFIG: dict[str, object] = {
    "chargeAnimation": True,
    "flowerBindingForceCheck": True,
    "enderPickpocket": True,
    "manaEnchanter": True,
    "relics": True,
    "invertMagnetRing": False,
    "blockBreakingParticles": {
        "enabled": True,
        "toolEnabled": True,
    },
    "manaSpreaders": {
        "silent": False,
        "traceTime": 400,
    },
    "harvestLevels": {
        "weightLens": 2,
        "boreLens": 3,
    },
    "gardenOfGlass": {
        "spawnWithLexicon": True,
        "islandScaleMultiplier": 8,
    },
    "rannuncarpus": {
        "itemBlacklist": [],
        "modBlacklist": ["storagedrawers"],
    },
}


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        items = ", ".join(_format_value(v) for v in value)
        return f"[{items}]"
    return repr(value)


def format_toml(config: dict[str, object]) -> str:
    """Serialize a Botania config dict (top-level keys + tables) into TOML."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, object]]] = []
    for key, value in config.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_format_value(value)}")
    lines.append("")
    for section, values in tables:
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")
    return "\n".join(lines)


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("botania_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class BotaniaSyncTest(unittest.TestCase):
    """Verify Botania config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "botania" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "botania-common.toml"

    def _write_config(self, cfg: dict[str, object]) -> None:
        self._config_path().write_text(format_toml(cfg), encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/botania/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/botania-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "botania-common.toml"
        self.assertTrue(target.is_file(), "Missing botania-common.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)
        cfg = copy.deepcopy(VALID_CONFIG)
        cfg["manaEnchanter"] = False
        self._write_config(cfg)

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("manaEnchanter = false", target.read_text(encoding="utf-8"))

    def test_dry_run_leaves_target_untouched(self) -> None:
        """Running with --dry-run must report planned changes without mutating data/."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN", buf.getvalue())
        self.assertFalse((self.data_dir / "config" / "botania-common.toml").exists())

    def test_missing_and_unexpected_keys_rejected(self) -> None:
        """Missing required keys or unexpected keys must raise ValueError with rationale."""
        cfg_missing_root = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_root["relics"]
        self._write_config(cfg_missing_root)
        with self.assertRaisesRegex(ValueError, "missing required keys.*relics"):
            self.sync.validate_configs()

        cfg_extra_root = copy.deepcopy(VALID_CONFIG)
        cfg_extra_root["unexpectedFlag"] = True
        self._write_config(cfg_extra_root)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*unexpectedFlag"):
            self.sync.validate_configs()

        cfg_missing_table = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_table["manaSpreaders"]["traceTime"]  # type: ignore[index]
        self._write_config(cfg_missing_table)
        with self.assertRaisesRegex(ValueError, "missing required keys.*traceTime"):
            self.sync.validate_configs()

        cfg_extra_table = copy.deepcopy(VALID_CONFIG)
        cfg_extra_table["gardenOfGlass"]["extraKey"] = 42  # type: ignore[index]
        self._write_config(cfg_extra_table)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*extraKey"):
            self.sync.validate_configs()

    def test_bool_type_invariants(self) -> None:
        """Non-boolean values for boolean flags must raise ValueError."""
        for key in (
            "chargeAnimation",
            "flowerBindingForceCheck",
            "enderPickpocket",
            "manaEnchanter",
            "relics",
            "invertMagnetRing",
        ):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg[key] = "true"
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, f"'{key}' must be a boolean"):
                self.sync.validate_configs()

        for section, key in (
            ("blockBreakingParticles", "enabled"),
            ("blockBreakingParticles", "toolEnabled"),
            ("manaSpreaders", "silent"),
            ("gardenOfGlass", "spawnWithLexicon"),
        ):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg[section][key] = 1  # type: ignore[index]
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, f"'{section}.{key}' must be a boolean"):
                self.sync.validate_configs()

    def test_strict_int_and_range_invariants(self) -> None:
        """Strict int and range bounds for numeric keys must be enforced."""
        bad_trace_values: list[object] = [True, 1.5, 0, -10]
        for bad in bad_trace_values:
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["manaSpreaders"]["traceTime"] = bad  # type: ignore[index]
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "manaSpreaders.traceTime"):
                self.sync.validate_configs()

        for lens_key in ("weightLens", "boreLens"):
            for bad in (False, 2.5, -1):
                cfg = copy.deepcopy(VALID_CONFIG)
                cfg["harvestLevels"][lens_key] = bad  # type: ignore[index]
                self._write_config(cfg)
                with self.assertRaisesRegex(ValueError, f"harvestLevels.{lens_key}"):
                    self.sync.validate_configs()

        for bad in (True, 8.0, 0, -1, 513):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["gardenOfGlass"]["islandScaleMultiplier"] = bad  # type: ignore[index]
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "gardenOfGlass.islandScaleMultiplier"):
                self.sync.validate_configs()

    def test_rannuncarpus_blacklist_invariants(self) -> None:
        """Rannuncarpus blacklists must be lists of strings."""
        for key in ("itemBlacklist", "modBlacklist"):
            cfg_not_list = copy.deepcopy(VALID_CONFIG)
            cfg_not_list["rannuncarpus"][key] = "storagedrawers"  # type: ignore[index]
            self._write_config(cfg_not_list)
            with self.assertRaisesRegex(ValueError, f"rannuncarpus.{key}.*list of strings"):
                self.sync.validate_configs()

            cfg_bad_elem = copy.deepcopy(VALID_CONFIG)
            cfg_bad_elem["rannuncarpus"][key] = [123]  # type: ignore[index]
            self._write_config(cfg_bad_elem)
            with self.assertRaisesRegex(ValueError, rf"rannuncarpus\.{key}\[0\].*must be a string"):
                self.sync.validate_configs()

    def test_invalid_toml_rejected(self) -> None:
        """Malformed TOML syntax must raise ValueError."""
        self._config_path().write_text("chargeAnimation = [unclosed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid TOML"):
            self.sync.validate_configs()

    def test_forbidden_files_and_secrets_rejected(self) -> None:
        """Forbidden runtime/client files, suffixes, and secret patterns must raise ValueError."""
        client_cfg = self.configs_dir / "config" / "botania-client.toml"
        client_cfg.write_text("subtlePowerSystem = false\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Forbidden file/directory"):
            self.sync.validate_configs()
        client_cfg.unlink()

        db_file = self.configs_dir / "state.db"
        db_file.write_bytes(b"sqlite")
        with self.assertRaisesRegex(ValueError, "Forbidden archive/runtime file"):
            self.sync.validate_configs()
        db_file.unlink()

        self._config_path().write_text(
            format_toml(VALID_CONFIG)
            + '\n# webhook = "https://discord.com/api/webhooks/123456789/abcdef"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "detected Discord Webhook URL"):
            self.sync.validate_configs()

        cfg_with_secret_key = copy.deepcopy(VALID_CONFIG)
        cfg_with_secret_key["password"] = "super-secret"
        self._write_config(cfg_with_secret_key)
        with self.assertRaisesRegex(ValueError, "non-empty secret key"):
            self.sync.validate_configs()


if __name__ == "__main__":
    unittest.main()
