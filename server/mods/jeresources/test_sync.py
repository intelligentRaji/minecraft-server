#!/usr/bin/env python3
"""Unit and integration tests for mods/jeresources/sync.py."""

from __future__ import annotations

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

VALID_JER_CONFIG: dict[str, object] = {
    "itemsPerColumn": 4,
    "itemsPerRow": 4,
    "diyData": True,
    "showDevData": False,
    "enchantsBlacklist": ["flimflam", "soulBound"],
    "hiddenTabs": [],
    "dimensionsBlacklist": [-11],
    "disableLootManagerReloading": False,
}


def format_toml(values: dict[str, object]) -> str:
    lines: list[str] = []
    for key, value in values.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, list):
            formatted_items: list[str] = []
            for item in value:
                if isinstance(item, bool):
                    formatted_items.append("true" if item else "false")
                elif isinstance(item, str):
                    formatted_items.append(f'"{item}"')
                else:
                    formatted_items.append(repr(item))
            lines.append(f"{key} = [{', '.join(formatted_items)}]")
        else:
            lines.append(f"{key} = {value!r}")
    return "\n".join(lines) + "\n"


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("jeresources_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class JeResourcesSyncTest(unittest.TestCase):
    """Verify JER config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "jeresources" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _common_path(self) -> Path:
        return self.configs_dir / "config" / "jeresources-common.toml"

    def _main_path(self) -> Path:
        return self.configs_dir / "config" / "jeresources.toml"

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/jeresources/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"config/jeresources-common.toml", "config/jeresources.toml"},
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places both static files; second run is idempotent; updates preserve mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "jeresources-common.toml"
        main_target = self.data_dir / "config" / "jeresources.toml"
        self.assertTrue(common_target.is_file(), "Missing jeresources-common.toml in data/config/")
        self.assertTrue(main_target.is_file(), "Missing jeresources.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(common_target, 0o600)

        updated = dict(VALID_JER_CONFIG)
        updated["itemsPerRow"] = 3
        self._common_path().write_text(format_toml(updated), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(common_target.stat().st_mode & 0o777, 0o600)
        self.assertIn("itemsPerRow = 3", common_target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
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
        link_path.symlink_to(self._common_path())
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

        self._main_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: config/jeresources.toml",
            str(ctx_missing.exception),
        )

    def test_schema_keys_and_invalid_toml_rejected(self) -> None:
        """Invalid TOML, missing keys, and unknown keys must raise ValueError with rationale."""
        common_path = self._common_path()

        common_path.write_text("itemsPerColumn = [not valid\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        missing_key = dict(VALID_JER_CONFIG)
        del missing_key["disableLootManagerReloading"]
        common_path.write_text(format_toml(missing_key), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['disableLootManagerReloading']", str(ctx_missing.exception))
        self.assertIn("all 8 static keys", str(ctx_missing.exception))

        extra_key = dict(VALID_JER_CONFIG)
        extra_key["extraSetting"] = True
        common_path.write_text(format_toml(extra_key), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extraSetting']", str(ctx_extra.exception))
        self.assertIn("all 8 static keys", str(ctx_extra.exception))

    def test_grid_bounds_and_strict_types_enforced(self) -> None:
        """Out-of-range grid ints, bool-as-int, and wrong types must raise ValueError with rationale."""
        main_path = self._main_path()

        for grid_key in ("itemsPerColumn", "itemsPerRow"):
            for bad_val in (0, 5, True, "4"):
                bad_cfg = dict(VALID_JER_CONFIG)
                bad_cfg[grid_key] = bad_val
                main_path.write_text(format_toml(bad_cfg), encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    self.sync.validate_configs()
                msg = str(ctx.exception)
                self.assertIn(f"'{grid_key}' must be an integer in range 1..4", msg)
                self.assertIn("grid layout", msg)

        for bool_key in ("diyData", "showDevData", "disableLootManagerReloading"):
            bad_cfg = dict(VALID_JER_CONFIG)
            bad_cfg[bool_key] = 1
            main_path.write_text(format_toml(bad_cfg), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"'{bool_key}' must be a boolean", str(ctx.exception))

        for str_list_key in ("enchantsBlacklist", "hiddenTabs"):
            bad_cfg = dict(VALID_JER_CONFIG)
            bad_cfg[str_list_key] = [123]
            main_path.write_text(format_toml(bad_cfg), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"'{str_list_key}' must be a list of strings", str(ctx.exception))

        for bad_dims in ([True], ["minecraft:the_nether"], -11):
            bad_cfg = dict(VALID_JER_CONFIG)
            bad_cfg["dimensionsBlacklist"] = bad_dims
            main_path.write_text(format_toml(bad_cfg), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            msg = str(ctx.exception)
            self.assertIn("'dimensionsBlacklist' must be a list of integers", msg)
            self.assertIn("booleans are rejected", msg)

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        common_path = self._common_path()

        with_secret = dict(VALID_JER_CONFIG)
        with_secret["secret"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        common_path.write_text(format_toml(with_secret), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'secret'", msg)


if __name__ == "__main__":
    unittest.main()
