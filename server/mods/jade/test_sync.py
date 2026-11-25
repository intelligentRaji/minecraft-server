#!/usr/bin/env python3
"""Unit and integration tests for mods/jade/sync.py."""

from __future__ import annotations

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


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("jade_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class JadeSyncTest(unittest.TestCase):
    """Verify Jade config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "jade" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.sync.CONFIGS_DIR = MOD_DIR / "configs"
        self.sync.DATA_DIR = MOD_DIR.parent.parent / "data"
        self.tmp_dir.cleanup()

    def _overrides_path(self) -> Path:
        return self.configs_dir / "server-plugin-overrides.json"

    def _sort_order_path(self) -> Path:
        return self.configs_dir / "sort-order.json"

    def _write_overrides(self, text: str) -> None:
        self._overrides_path().write_text(text, encoding="utf-8")

    def _write_sort_order(self, text: str) -> None:
        self._sort_order_path().write_text(text, encoding="utf-8")

    def test_committed_configs_pass_validation(self) -> None:
        """Committed configs in mods/jade/configs/ must pass validate_configs()."""
        loaded = self.sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"server-plugin-overrides.json", "sort-order.json"},
        )

    def test_valid_non_empty_overrides_and_numeric_sort_order_pass(self) -> None:
        """Non-empty plugin overrides and numeric sort-order priorities must validate cleanly."""
        self._write_overrides(
            json.dumps(
                {
                    "minecraft:furnace": True,
                    "jade:object_name.display_mode": "ICON",
                    "minecraft:item_storage.normal_amount": 54,
                    "custom:nested": {"enabled": False, "tags": ["a", "b"]},
                }
            )
        )
        self._write_sort_order(
            json.dumps(
                {
                    "jade:object_name": -1000,
                    "minecraft:furnace": 1.5,
                    "minecraft:redstone": None,
                }
            )
        )
        loaded = self.sync.validate_configs()
        self.assertEqual(len(loaded), 2)

    def test_static_file_placement_permissions_and_idempotency(self) -> None:
        """Files must be placed into DATA_DIR, preserve existing mode, and be idempotent."""
        target_overrides = (
            self.data_dir / "config" / "jade" / "server-plugin-overrides.json"
        )
        target_sort_order = self.data_dir / "config" / "jade" / "sort-order.json"
        target_overrides.parent.mkdir(parents=True, exist_ok=True)
        target_overrides.write_text('{"stale": true}', encoding="utf-8")
        os.chmod(target_overrides, 0o640)

        loaded = self.sync.validate_configs()
        changed, unchanged = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual(changed, 2)
        self.assertEqual(unchanged, 0)

        self.assertTrue(target_overrides.is_file())
        self.assertTrue(target_sort_order.is_file())
        self.assertEqual(target_overrides.read_bytes(), loaded["server-plugin-overrides.json"])
        self.assertEqual(target_sort_order.read_bytes(), loaded["sort-order.json"])
        self.assertEqual(stat.S_IMODE(target_overrides.stat().st_mode), 0o640)

        changed_2, unchanged_2 = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual(changed_2, 0)
        self.assertEqual(unchanged_2, 2)

    def test_dry_run_leaves_target_untouched(self) -> None:
        """Running main(['--dry-run']) must not create or modify files in DATA_DIR."""
        exit_code = self.sync.main(["--dry-run"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_overrides_root_not_object_raises(self) -> None:
        """server-plugin-overrides.json with non-object root must raise ValueError."""
        self._write_overrides("[]")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("JSON object", str(ctx.exception))

    def test_overrides_empty_key_raises(self) -> None:
        """server-plugin-overrides.json with empty or whitespace key must raise ValueError."""
        self._write_overrides(json.dumps({"  ": True}))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("non-empty string", str(ctx.exception))

    def test_overrides_non_finite_float_raises(self) -> None:
        """server-plugin-overrides.json with NaN/Infinity must raise ValueError."""
        self._write_overrides('{"minecraft:furnace.scale": NaN}')
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("finite", str(ctx.exception))

    def test_overrides_nested_empty_key_raises(self) -> None:
        """Nested dict in server-plugin-overrides.json with empty key must raise ValueError."""
        self._write_overrides(json.dumps({"minecraft:furnace": {"": 1}}))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("non-empty strings", str(ctx.exception))

    def test_sort_order_root_not_object_raises(self) -> None:
        """sort-order.json with non-object root must raise ValueError."""
        self._write_sort_order('["jade:object_name"]')
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("JSON object", str(ctx.exception))

    def test_sort_order_empty_key_raises(self) -> None:
        """sort-order.json with empty provider ID key must raise ValueError."""
        self._write_sort_order(json.dumps({"": None}))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("non-empty string", str(ctx.exception))

    def test_sort_order_bool_priority_raises(self) -> None:
        """sort-order.json with boolean priority must raise ValueError."""
        self._write_sort_order(json.dumps({"jade:object_name": True}))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("null", str(ctx.exception))
        self.assertIn("finite number", str(ctx.exception))

    def test_sort_order_string_priority_raises(self) -> None:
        """sort-order.json with string priority must raise ValueError."""
        self._write_sort_order(json.dumps({"jade:object_name": "high"}))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("finite number", str(ctx.exception))

    def test_sort_order_non_finite_priority_raises(self) -> None:
        """sort-order.json with Infinity priority must raise ValueError."""
        self._write_sort_order('{"jade:object_name": Infinity}')
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("finite number", str(ctx.exception))

    def test_forbidden_client_files_and_dirs_raise(self) -> None:
        """Client-only Jade files/dirs and forbidden suffixes must raise ValueError."""
        for name in ("jade.json", "disabled_plugins.json", "hide-blocks.json", "state.db"):
            path = self.configs_dir / name
            path.write_text("{}", encoding="utf-8")
            try:
                with self.assertRaises(ValueError):
                    self.sync.validate_configs()
            finally:
                path.unlink()

        profiles_dir = self.configs_dir / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "default.json").write_text("{}", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                self.sync.validate_configs()
        finally:
            shutil.rmtree(profiles_dir)

    def test_unexpected_and_missing_files_raise(self) -> None:
        """Unexpected extra files or missing expected files must raise ValueError."""
        extra = self.configs_dir / "extra.json"
        extra.write_text("{}", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                self.sync.validate_configs()
        finally:
            extra.unlink()

        self._sort_order_path().unlink()
        with self.assertRaises(ValueError):
            self.sync.validate_configs()

    def test_symlink_raises(self) -> None:
        """Symlinks inside configs/ must raise ValueError."""
        link_path = self.configs_dir / "link.json"
        link_path.symlink_to(self._sort_order_path())
        try:
            with self.assertRaises(ValueError):
                self.sync.validate_configs()
        finally:
            link_path.unlink()

    def test_secret_guard_raises(self) -> None:
        """Secret keys or token patterns in configs/ must raise ValueError."""
        self._write_overrides(json.dumps({"password": "supersecret123"}))
        with self.assertRaises(ValueError):
            self.sync.validate_configs()

        self._write_overrides(
            json.dumps(
                {"webhook": "https://discord.com/api/webhooks/123456789/abcdef_ghijk"}
            )
        )
        with self.assertRaises(ValueError):
            self.sync.validate_configs()


if __name__ == "__main__":
    unittest.main()
