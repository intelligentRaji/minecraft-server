#!/usr/bin/env python3
"""Unit and integration tests for mods/doubledoors/sync.py."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

CONFIG_REL_PATH = "config/serilum/doubledoors.json"

BOOLEAN_KEYS: tuple[str, ...] = (
    "Enable Double Doors",
    "enableRecursiveOpening",
    "enableDoors",
    "enableFenceGates",
    "enableTrapdoors",
    "enableModIncompatibilityCheck",
)


def load_sync_module() -> SyncModuleProtocol:
    """Dynamically load `mods/doubledoors/sync.py`."""
    spec = importlib.util.spec_from_file_location("doubledoors_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class DoubleDoorsSyncTest(unittest.TestCase):
    """Verify Double Doors config validation, invariants, sibling isolation, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "doubledoors" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.sync.CONFIGS_DIR = MOD_DIR / "configs"
        self.sync.DATA_DIR = MOD_DIR.parent.parent / "data"
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "serilum" / "doubledoors.json"

    def _load_valid_config(self) -> dict[str, object]:
        return json.loads(self._config_path().read_text(encoding="utf-8"))

    def _write_config(self, payload: object) -> None:
        self._config_path().write_text(json.dumps(payload, indent="\t"), encoding="utf-8")

    def test_committed_configs_pass_validation(self) -> None:
        """Committed configs in mods/doubledoors/configs/ must pass validate_configs()."""
        loaded = self.sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {CONFIG_REL_PATH})

    def test_static_placement_idempotency_and_sibling_preservation(self) -> None:
        """Placement must write doubledoors.json, preserve collective.json, and be idempotent."""
        sibling_path = self.data_dir / "config" / "serilum" / "collective.json"
        sibling_path.parent.mkdir(parents=True, exist_ok=True)
        sibling_bytes = b'{"sibling":"collective-state"}\n'
        sibling_path.write_bytes(sibling_bytes)

        loaded = self.sync.validate_configs()
        changed, unchanged = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual(changed, 1)
        self.assertEqual(unchanged, 0)

        target_path = self.data_dir / "config" / "serilum" / "doubledoors.json"
        self.assertTrue(target_path.is_file())
        self.assertEqual(target_path.read_bytes(), loaded[CONFIG_REL_PATH])
        self.assertEqual(sibling_path.read_bytes(), sibling_bytes)

        changed_second, unchanged_second = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual(changed_second, 0)
        self.assertEqual(unchanged_second, 1)
        self.assertEqual(sibling_path.read_bytes(), sibling_bytes)

    def test_file_permission_preservation(self) -> None:
        """Existing target file mode (0600) must be preserved upon update."""
        target_path = self.data_dir / "config" / "serilum" / "doubledoors.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("{}", encoding="utf-8")
        os.chmod(target_path, 0o600)

        loaded = self.sync.validate_configs()
        self.sync.apply_configs(loaded, dry_run=False)

        self.assertEqual(stat.S_IMODE(target_path.stat().st_mode), 0o600)

    def test_dry_run_leaves_target_untouched(self) -> None:
        """CLI with --dry-run must leave DATA_DIR untouched."""
        exit_code = self.sync.main(["--dry-run"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(list(self.data_dir.rglob("*")), [])

    def test_root_schema_violations_raise_value_error(self) -> None:
        """Non-dict root, missing/extra keys, and non-string root '//' must raise ValueError."""
        base = self._load_valid_config()

        self._write_config(["not", "a", "dict"])
        with self.assertRaises(ValueError) as ctx_list:
            self.sync.validate_configs()
        self.assertIn("expected a mapping/table", str(ctx_list.exception))
        self.assertIn("Double Doors config must declare exactly", str(ctx_list.exception))

        missing = copy.deepcopy(base)
        del missing["enableDoors"]
        self._write_config(missing)
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['enableDoors']", str(ctx_missing.exception))

        extra = copy.deepcopy(base)
        extra["rogueSetting"] = {"value": True}
        self._write_config(extra)
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['rogueSetting']", str(ctx_extra.exception))

        bad_comment = copy.deepcopy(base)
        bad_comment["//"] = 42
        self._write_config(bad_comment)
        with self.assertRaises(ValueError) as ctx_comment:
            self.sync.validate_configs()
        self.assertIn("[root].// invariant violation", str(ctx_comment.exception))
        self.assertIn("plain string metadata", str(ctx_comment.exception))

    def test_setting_entry_schema_violations_raise_value_error(self) -> None:
        """Setting entries must be dicts with 'value', optional string '//', and no extra keys."""
        base = self._load_valid_config()

        not_dict = copy.deepcopy(base)
        not_dict["enableDoors"] = True
        self._write_config(not_dict)
        with self.assertRaises(ValueError) as ctx_type:
            self.sync.validate_configs()
        self.assertIn("expected a mapping/table", str(ctx_type.exception))
        self.assertIn("Serilum object with a 'value' key", str(ctx_type.exception))

        missing_val = copy.deepcopy(base)
        missing_val["enableDoors"] = {"//": "missing value"}
        self._write_config(missing_val)
        with self.assertRaises(ValueError) as ctx_missing_val:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['value']", str(ctx_missing_val.exception))

        extra_key = copy.deepcopy(base)
        cast("dict[str, object]", extra_key["enableDoors"])["extra"] = 1
        self._write_config(extra_key)
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra']", str(ctx_extra_key.exception))

        bad_entry_comment = copy.deepcopy(base)
        cast("dict[str, object]", bad_entry_comment["enableDoors"])["//"] = ["bad"]
        self._write_config(bad_entry_comment)
        with self.assertRaises(ValueError) as ctx_entry_comment:
            self.sync.validate_configs()
        self.assertIn("[enableDoors].// invariant violation", str(ctx_entry_comment.exception))

    def test_boolean_settings_require_strict_bool(self) -> None:
        """All 6 boolean settings must reject strings, ints, and null."""
        base = self._load_valid_config()
        for key in BOOLEAN_KEYS:
            for bad_val in ("true", 1, 0, None):
                with self.subTest(key=key, bad_val=bad_val):
                    cfg = copy.deepcopy(base)
                    cast("dict[str, object]", cfg[key])["value"] = bad_val
                    self._write_config(cfg)
                    with self.assertRaises(ValueError) as ctx:
                        self.sync.validate_configs()
                    msg = str(ctx.exception)
                    self.assertIn(f"[{key}].value invariant violation", msg)
                    self.assertIn("strict JSON boolean", msg)
                    self.assertIn("Serilum Collective deserializes", msg)

    def test_recursive_distance_requires_strict_int_in_bounds(self) -> None:
        """recursiveOpeningMaxBlocksDistance must be strict int in [1, 64]."""
        base = self._load_valid_config()
        for valid_val in (1, 10, 64):
            with self.subTest(valid_val=valid_val):
                cfg = copy.deepcopy(base)
                cast("dict[str, object]", cfg["recursiveOpeningMaxBlocksDistance"])["value"] = valid_val
                self._write_config(cfg)
                self.sync.validate_configs()

        for bad_val in (True, False, 10.5, "10", 0, -5, 65):
            with self.subTest(bad_val=bad_val):
                cfg = copy.deepcopy(base)
                cast("dict[str, object]", cfg["recursiveOpeningMaxBlocksDistance"])["value"] = bad_val
                self._write_config(cfg)
                with self.assertRaises(ValueError) as ctx:
                    self.sync.validate_configs()
                msg = str(ctx.exception)
                self.assertIn("[recursiveOpeningMaxBlocksDistance].value invariant violation", msg)
                self.assertIn("strict integer in [1, 64]", msg)
                self.assertIn("server tick stalls", msg)

    def test_door_block_blacklist_validation(self) -> None:
        """doorBlockBlacklist must be empty or valid comma-separated namespace:path IDs."""
        base = self._load_valid_config()
        for valid_val in ("", "create:andesite_door, supplementaries:gold_door", "minecraft:oak_door"):
            with self.subTest(valid_val=valid_val):
                cfg = copy.deepcopy(base)
                cast("dict[str, object]", cfg["doorBlockBlacklist"])["value"] = valid_val
                self._write_config(cfg)
                self.sync.validate_configs()

        bad_blacklists: tuple[object, ...] = (
            ["minecraft:oak_door"],
            123,
            "   ",
            "minecraft:oak_door,",
            ",minecraft:oak_door",
            "oak_door",
            "Minecraft:oak_door",
        )
        for bad_val in bad_blacklists:
            with self.subTest(bad_val=bad_val):
                cfg = copy.deepcopy(base)
                cast("dict[str, object]", cfg["doorBlockBlacklist"])["value"] = bad_val
                self._write_config(cfg)
                with self.assertRaises(ValueError) as ctx:
                    self.sync.validate_configs()
                msg = str(ctx.exception)
                self.assertIn("[doorBlockBlacklist].value invariant violation", msg)

    def test_forbidden_files_dirs_and_symlinks_raise_value_error(self) -> None:
        """Forbidden files/dirs (collective.json, playerdata, .zip, symlink) must fail pre-flight."""
        sibling_in_configs = self.configs_dir / "config" / "serilum" / "collective.json"
        sibling_in_configs.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_collective:
            self.sync.validate_configs()
        self.assertIn(
            "Forbidden file/directory present in configs/: config/serilum/collective.json",
            str(ctx_collective.exception),
        )
        sibling_in_configs.unlink()

        (self.configs_dir / "playerdata").mkdir()
        with self.assertRaises(ValueError) as ctx_dir:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: playerdata", str(ctx_dir.exception))
        (self.configs_dir / "playerdata").rmdir()

        (self.configs_dir / "backup.zip").write_text("dummy", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_zip:
            self.sync.validate_configs()
        self.assertIn("Forbidden archive/runtime file present in configs/: backup.zip", str(ctx_zip.exception))
        (self.configs_dir / "backup.zip").unlink()

        symlink_path = self.configs_dir / "config" / "serilum" / "link.json"
        os.symlink(self._config_path(), symlink_path)
        with self.assertRaises(ValueError) as ctx_link:
            self.sync.validate_configs()
        self.assertIn("Symlinks are forbidden in configs/: config/serilum/link.json", str(ctx_link.exception))
        symlink_path.unlink()

    def test_secret_guards_reject_credentials_and_patterns(self) -> None:
        """Secret keys and webhook patterns in configs/ must fail validation."""
        cfg = self._load_valid_config()
        cfg["password"] = "supersecret"
        self._write_config(cfg)
        with self.assertRaises(ValueError) as ctx_key:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'password'", str(ctx_key.exception))

        shutil.copy2(MOD_DIR / "configs" / CONFIG_REL_PATH, self._config_path())
        cfg_webhook = self._load_valid_config()
        cfg_webhook["//"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        self._write_config(cfg_webhook)
        with self.assertRaises(ValueError) as ctx_pattern:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_pattern.exception))


if __name__ == "__main__":
    unittest.main()
