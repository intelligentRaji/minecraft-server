#!/usr/bin/env python3
"""Unit and integration tests for mods/farmersdelight/sync.py."""

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

VALID_CONFIG: dict[str, dict[str, object]] = {
    "settings": {
        "enableFarmerFDTrades": True,
        "enableWanderingTraderFDTrades": True,
        "enableRopeReeling": True,
        "canvasSignDarkBackgroundList": ["gray", "purple", "blue", "brown", "green", "red", "black"],
    },
    "farming": {
        "richSoilBoostChance": 0.2,
        "enableTomatoVineClimbingTaggedRopes": True,
        "defaultTomatoVineRope": "farmersdelight:rope",
    },
    "crafting": {
        "enableCookingPotRecipeBook": True,
        "enableVanillaCropCrates": True,
        "cuttingBoardFortuneBonus": 0.1,
    },
    "overrides": {
        "enableVanillaSoupExtraEffects": True,
        "enableRabbitStewJumpBoost": True,
        "enablePumpkinPieSneakToPlace": False,
        "enableCuttingBoardDispenserBehavior": True,
        "stack_size": {
            "enableStackableSoupItems": True,
            "soupItemList": [
                "minecraft:mushroom_stew",
                "minecraft:beetroot_soup",
                "minecraft:rabbit_stew",
            ],
        },
    },
    "world": {
        "generateFDChestLoot": True,
        "generateVillageCompostHeaps": True,
        "generateFDCropsOnVillageFarms": True,
    },
    "debug": {
        "enableTomatoRopePermanence": True,
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


def format_toml(config: dict[str, dict[str, object]]) -> str:
    """Serialize a nested dict of Farmer's Delight tables into TOML."""
    lines: list[str] = []
    for section, values in config.items():
        lines.append(f"[{section}]")
        nested_tables: list[tuple[str, dict[str, object]]] = []
        for key, value in values.items():
            if isinstance(value, dict):
                nested_tables.append((f"{section}.{key}", value))
            else:
                lines.append(f"{key} = {_format_value(value)}")
        for sub_name, sub_values in nested_tables:
            lines.append(f"[{sub_name}]")
            for sub_key, sub_val in sub_values.items():
                lines.append(f"{sub_key} = {_format_value(sub_val)}")
        lines.append("")
    return "\n".join(lines)


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("farmersdelight_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class FarmersDelightSyncTest(unittest.TestCase):
    """Verify Farmer's Delight config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "farmersdelight" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "farmersdelight-common.toml"

    def _write_config(self, cfg: dict[str, dict[str, object]]) -> None:
        self._config_path().write_text(format_toml(cfg), encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/farmersdelight/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/farmersdelight-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "farmersdelight-common.toml"
        self.assertTrue(target.is_file(), "Missing farmersdelight-common.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)

        updated = copy.deepcopy(VALID_CONFIG)
        updated["settings"]["enableRopeReeling"] = False
        self._write_config(updated)

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("enableRopeReeling = false", target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_dirs_and_symlinks_rejected(self) -> None:
        """Forbidden runtime directories, archive/runtime suffixes, and symlinks must fail validation."""
        for forbidden_dir in ("logs", "world", "mods"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden file/directory present in configs/: {forbidden_dir}",
                str(ctx.exception),
            )
            dpath.rmdir()

        for suffix_file in ("mod.jar", "state.db", "cache.sqlite", "latest.log", "world.gz", "backup.zip"):
            fpath = self.configs_dir / suffix_file
            fpath.write_bytes(b"artifact")
            with self.assertRaises(ValueError) as ctx_file:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden archive/runtime file present in configs/: {suffix_file}",
                str(ctx_file.exception),
            )
            fpath.unlink()

        link_path = self.configs_dir / "symlink.toml"
        link_path.symlink_to(self._config_path())
        with self.assertRaises(ValueError) as ctx_link:
            self.sync.validate_configs()
        self.assertIn("Symlinks are forbidden in configs/: symlink.toml", str(ctx_link.exception))
        link_path.unlink()

    def test_missing_and_unexpected_files_rejected(self) -> None:
        """Missing expected files or unexpected files in configs/ must fail validation."""
        unexpected = self.configs_dir / "unexpected.toml"
        unexpected.write_text('foo = "bar"\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Unexpected files in configs/: unexpected.toml", str(ctx.exception))
        unexpected.unlink()

        self._config_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: config/farmersdelight-common.toml",
            str(ctx_missing.exception),
        )

    def test_invalid_toml_and_table_structure_rejected(self) -> None:
        """Invalid TOML, missing/unexpected sections, and missing/unexpected keys must raise ValueError."""
        self._config_path().write_text("[settings]\nenableRopeReeling = [broken\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        missing_section = copy.deepcopy(VALID_CONFIG)
        del missing_section["debug"]
        self._write_config(missing_section)
        with self.assertRaises(ValueError) as ctx_missing_sec:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['debug']", str(ctx_missing_sec.exception))

        extra_section = copy.deepcopy(VALID_CONFIG)
        extra_section["client"] = {"fancy": True}
        self._write_config(extra_section)
        with self.assertRaises(ValueError) as ctx_extra_sec:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['client']", str(ctx_extra_sec.exception))

        missing_nested = copy.deepcopy(VALID_CONFIG)
        stack_size = missing_nested["overrides"]["stack_size"]
        assert isinstance(stack_size, dict)
        del stack_size["soupItemList"]
        self._write_config(missing_nested)
        with self.assertRaises(ValueError) as ctx_missing_nested:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['soupItemList']", str(ctx_missing_nested.exception))

        extra_nested = copy.deepcopy(VALID_CONFIG)
        stack_size_extra = extra_nested["overrides"]["stack_size"]
        assert isinstance(stack_size_extra, dict)
        stack_size_extra["unknownFlag"] = False
        self._write_config(extra_nested)
        with self.assertRaises(ValueError) as ctx_extra_nested:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['unknownFlag']", str(ctx_extra_nested.exception))

    def test_type_and_range_invariants_enforced(self) -> None:
        """Bad types (including bool for float) and out-of-range probabilities must raise ValueError."""
        bad_bool = copy.deepcopy(VALID_CONFIG)
        bad_bool["world"]["generateFDChestLoot"] = "true"
        self._write_config(bad_bool)
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("'world.generateFDChestLoot' must be a boolean", str(ctx_bool.exception))

        bool_as_float = copy.deepcopy(VALID_CONFIG)
        bool_as_float["farming"]["richSoilBoostChance"] = True
        self._write_config(bool_as_float)
        with self.assertRaises(ValueError) as ctx_bool_float:
            self.sync.validate_configs()
        self.assertIn(
            "'farming.richSoilBoostChance' must be a number in [0.0, 1.0]",
            str(ctx_bool_float.exception),
        )

        for field_table, field_name, bad_val in (
            ("farming", "richSoilBoostChance", -0.01),
            ("farming", "richSoilBoostChance", 1.05),
            ("crafting", "cuttingBoardFortuneBonus", -0.5),
            ("crafting", "cuttingBoardFortuneBonus", 1.5),
        ):
            out_of_range = copy.deepcopy(VALID_CONFIG)
            out_of_range[field_table][field_name] = bad_val
            self._write_config(out_of_range)
            with self.assertRaises(ValueError) as ctx_range:
                self.sync.validate_configs()
            self.assertIn(
                f"'{field_table}.{field_name}' must be a number in [0.0, 1.0]",
                str(ctx_range.exception),
            )

    def test_dye_colors_and_resource_location_invariants_enforced(self) -> None:
        """Invalid dye names and invalid resource locations must raise ValueError with rationale."""
        bad_dye = copy.deepcopy(VALID_CONFIG)
        bad_dye["settings"]["canvasSignDarkBackgroundList"] = ["gray", "crimson"]
        self._write_config(bad_dye)
        with self.assertRaises(ValueError) as ctx_dye:
            self.sync.validate_configs()
        self.assertIn(
            "'settings.canvasSignDarkBackgroundList[1]' must be one of the 16 Minecraft dye colors",
            str(ctx_dye.exception),
        )

        for bad_rope in ("", "rope", "FarmersDelight:rope", "farmersdelight:rope with spaces"):
            bad_rope_cfg = copy.deepcopy(VALID_CONFIG)
            bad_rope_cfg["farming"]["defaultTomatoVineRope"] = bad_rope
            self._write_config(bad_rope_cfg)
            with self.assertRaises(ValueError) as ctx_rope:
                self.sync.validate_configs()
            self.assertIn(
                "'farming.defaultTomatoVineRope' must be a valid Minecraft resource location",
                str(ctx_rope.exception),
            )

        bad_soup = copy.deepcopy(VALID_CONFIG)
        stack_size = bad_soup["overrides"]["stack_size"]
        assert isinstance(stack_size, dict)
        stack_size["soupItemList"] = ["minecraft:mushroom_stew", "invalid_item"]
        self._write_config(bad_soup)
        with self.assertRaises(ValueError) as ctx_soup:
            self.sync.validate_configs()
        self.assertIn(
            "'overrides.stack_size.soupItemList[1]' must be a valid Minecraft resource location",
            str(ctx_soup.exception),
        )

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        with_webhook = copy.deepcopy(VALID_CONFIG)
        with_webhook["debug"]["secret"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        self._write_config(with_webhook)
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'debug.secret'", msg)


if __name__ == "__main__":
    unittest.main()
