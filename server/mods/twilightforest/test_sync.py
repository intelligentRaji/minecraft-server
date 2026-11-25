#!/usr/bin/env python3
"""Unit and integration tests for mods/twilightforest/sync.py."""

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
    "originDimension": "minecraft:overworld",
    "allowPortalsInOtherDimensions": False,
    "adminOnlyPortals": False,
    "disablePortalCreation": False,
    "checkPortalDestination": False,
    "portalLightning": False,
    "shouldReturnPortalBeUsable": True,
    "portalUnlockedByAdvancement": "",
    "maxPortalSize": 64,
    "uuid_locking": False,
    "skull_candles": False,
    "default_item_enchantments": True,
    "boss_drop_chests": True,
    "cloudBlockPrecipitationDistance": 32,
    "Dimension Settings": {
        "newPlayersSpawnInTF": False,
        "portalForNewPlayer": False,
    },
    "Uncrafting Table": {
        "uncraftingXpCostMultiplier": 1.0,
        "repairingXpCostMultiplier": 1.0,
        "disableUncraftingRecipes": ["twilightforest:giant_log_to_oak_planks"],
        "flipRecipeList": False,
        "blacklistedUncraftingModIds": [],
        "flipIdList": False,
        "enableShapelessCrafting": False,
        "disableUncrafting": False,
        "disableUncraftingTable": False,
    },
    "Magic Trees": {
        "disableTimeCore": False,
        "timeCoreRange": 16,
        "disableTransformationCore": False,
        "transformationCoreRange": 16,
        "disableMiningCore": False,
        "miningCoreRange": 16,
        "disableSortingCore": False,
        "sortingCoreRange": 16,
    },
    "Shield Parrying": {
        "parryNonTwilightAttacks": False,
        "shieldParryTicksArrow": 40,
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
    """Serialize a Twilight Forest config dict (top-level keys + tables) into TOML."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, object]]] = []
    for key, value in config.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_format_value(value)}")
    lines.append("")
    for section, values in tables:
        lines.append(f'["{section}"]')
        for key, value in values.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")
    return "\n".join(lines)


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("twilightforest_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class TwilightForestSyncTest(unittest.TestCase):
    """Verify Twilight Forest config validation, invariants, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "twilightforest" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "twilightforest-common.toml"

    def _write_config(self, cfg: dict[str, object]) -> None:
        self._config_path().write_text(format_toml(cfg), encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/twilightforest/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/twilightforest-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "twilightforest-common.toml"
        self.assertTrue(target.is_file(), "Missing twilightforest-common.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)
        cfg = copy.deepcopy(VALID_CONFIG)
        cfg["maxPortalSize"] = 32
        self._write_config(cfg)

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("maxPortalSize = 32", target.read_text(encoding="utf-8"))

    def test_dry_run_leaves_target_untouched(self) -> None:
        """Running with --dry-run must report planned changes without mutating data/."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN", buf.getvalue())
        self.assertFalse((self.data_dir / "config" / "twilightforest-common.toml").exists())

    def test_missing_and_unexpected_keys_rejected(self) -> None:
        """Missing required keys or unexpected keys must raise ValueError with rationale."""
        cfg_missing_root = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_root["uuid_locking"]
        self._write_config(cfg_missing_root)
        with self.assertRaisesRegex(ValueError, "missing required keys.*uuid_locking"):
            self.sync.validate_configs()

        cfg_extra_root = copy.deepcopy(VALID_CONFIG)
        cfg_extra_root["unexpectedFlag"] = True
        self._write_config(cfg_extra_root)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*unexpectedFlag"):
            self.sync.validate_configs()

        cfg_missing_table = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_table["Magic Trees"]["timeCoreRange"]  # type: ignore[index]
        self._write_config(cfg_missing_table)
        with self.assertRaisesRegex(ValueError, "missing required keys.*timeCoreRange"):
            self.sync.validate_configs()

        cfg_extra_table = copy.deepcopy(VALID_CONFIG)
        cfg_extra_table["Shield Parrying"]["extraKey"] = 42  # type: ignore[index]
        self._write_config(cfg_extra_table)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*extraKey"):
            self.sync.validate_configs()

    def test_resource_location_invariants(self) -> None:
        """originDimension and portalUnlockedByAdvancement must obey ResourceLocation rules."""
        for bad_origin in (123, "", "overworld", "minecraft:"):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["originDimension"] = bad_origin
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "originDimension"):
                self.sync.validate_configs()

        for bad_adv in (False, "story/mine_diamond", "minecraft:"):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["portalUnlockedByAdvancement"] = bad_adv
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "portalUnlockedByAdvancement"):
                self.sync.validate_configs()

        cfg_valid_adv = copy.deepcopy(VALID_CONFIG)
        cfg_valid_adv["portalUnlockedByAdvancement"] = "minecraft:story/mine_diamond"
        self._write_config(cfg_valid_adv)
        self.assertIn("config/twilightforest-common.toml", self.sync.validate_configs())

    def test_bool_type_invariants(self) -> None:
        """Non-boolean values for boolean flags must raise ValueError."""
        for key in (
            "allowPortalsInOtherDimensions",
            "adminOnlyPortals",
            "disablePortalCreation",
            "checkPortalDestination",
            "portalLightning",
            "shouldReturnPortalBeUsable",
            "uuid_locking",
            "skull_candles",
            "default_item_enchantments",
            "boss_drop_chests",
        ):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg[key] = "true"
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, f"'{key}' must be a boolean"):
                self.sync.validate_configs()

        for section, key in (
            ("Dimension Settings", "newPlayersSpawnInTF"),
            ("Dimension Settings", "portalForNewPlayer"),
            ("Uncrafting Table", "flipRecipeList"),
            ("Uncrafting Table", "flipIdList"),
            ("Uncrafting Table", "enableShapelessCrafting"),
            ("Uncrafting Table", "disableUncrafting"),
            ("Uncrafting Table", "disableUncraftingTable"),
            ("Magic Trees", "disableTimeCore"),
            ("Magic Trees", "disableTransformationCore"),
            ("Magic Trees", "disableMiningCore"),
            ("Magic Trees", "disableSortingCore"),
            ("Shield Parrying", "parryNonTwilightAttacks"),
        ):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg[section][key] = 1  # type: ignore[index]
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, f"'{section}.{key}' must be a boolean"):
                self.sync.validate_configs()

    def test_strict_int_and_range_invariants(self) -> None:
        """Strict int and range bounds for numeric keys must be enforced."""
        for bad in (True, 4.0, 3, -1):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["maxPortalSize"] = bad
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "maxPortalSize"):
                self.sync.validate_configs()

        for bad in (False, 1.5, -1):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["cloudBlockPrecipitationDistance"] = bad
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "cloudBlockPrecipitationDistance"):
                self.sync.validate_configs()

        for range_key in (
            "timeCoreRange",
            "transformationCoreRange",
            "miningCoreRange",
            "sortingCoreRange",
        ):
            for bad in (True, 16.0, 0, -5, 129):
                cfg = copy.deepcopy(VALID_CONFIG)
                cfg["Magic Trees"][range_key] = bad  # type: ignore[index]
                self._write_config(cfg)
                with self.assertRaisesRegex(ValueError, f"Magic Trees.{range_key}"):
                    self.sync.validate_configs()

        for bad in (False, 40.5, -1):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["Shield Parrying"]["shieldParryTicksArrow"] = bad  # type: ignore[index]
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "Shield Parrying.shieldParryTicksArrow"):
                self.sync.validate_configs()

    def test_uncrafting_multiplier_and_list_invariants(self) -> None:
        """XP cost multipliers must be finite >= 0.0 and lists must contain non-empty strings."""
        for mult_key in ("uncraftingXpCostMultiplier", "repairingXpCostMultiplier"):
            for bad in (True, "1.0", -0.1):
                cfg = copy.deepcopy(VALID_CONFIG)
                cfg["Uncrafting Table"][mult_key] = bad  # type: ignore[index]
                self._write_config(cfg)
                with self.assertRaisesRegex(ValueError, f"Uncrafting Table.{mult_key}"):
                    self.sync.validate_configs()

            toml_text = format_toml(VALID_CONFIG).replace(
                f"{mult_key} = 1.0", f"{mult_key} = nan"
            )
            self._config_path().write_text(toml_text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, f"Uncrafting Table.{mult_key}"):
                self.sync.validate_configs()

        for list_key in ("disableUncraftingRecipes", "blacklistedUncraftingModIds"):
            cfg_not_list = copy.deepcopy(VALID_CONFIG)
            cfg_not_list["Uncrafting Table"][list_key] = "twilightforest"  # type: ignore[index]
            self._write_config(cfg_not_list)
            with self.assertRaisesRegex(
                ValueError, f"Uncrafting Table.{list_key}.*list of non-empty strings"
            ):
                self.sync.validate_configs()

            for bad_elem in (123, "", "   "):
                cfg_bad_elem = copy.deepcopy(VALID_CONFIG)
                cfg_bad_elem["Uncrafting Table"][list_key] = [bad_elem]  # type: ignore[index]
                self._write_config(cfg_bad_elem)
                with self.assertRaisesRegex(
                    ValueError, rf"Uncrafting Table\.{list_key}\[0\].*non-empty string"
                ):
                    self.sync.validate_configs()

    def test_invalid_toml_rejected(self) -> None:
        """Malformed TOML syntax must raise ValueError."""
        self._config_path().write_text("maxPortalSize = [unclosed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid TOML"):
            self.sync.validate_configs()

    def test_forbidden_files_and_secrets_rejected(self) -> None:
        """Forbidden runtime/client files, suffixes, and secret patterns must raise ValueError."""
        for forbidden_name in ("twilightforest-client.toml", "twilightforest-server.toml"):
            bad_cfg = self.configs_dir / "config" / forbidden_name
            bad_cfg.write_text("flag = false\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Forbidden file/directory"):
                self.sync.validate_configs()
            bad_cfg.unlink()

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
