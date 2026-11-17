#!/usr/bin/env python3
"""Unit and integration tests for mods/sliceanddice/sync.py."""

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
from types import ModuleType

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

VALID_CONFIG: dict[str, dict[str, object]] = {
    "harvester": {
        "uses_knife": True,
    },
    "slicer": {
        "consume_tool_durability": True,
        "ignore_rotation": False,
        "jei_show_converted_recipes": False,
    },
    "basin_cooking": {
        "enabled": True,
        "replace_fluid_containers": True,
        "heat_condition": "HEATED",
    },
    "sprinkler": {
        "fluid_capacity": 300,
        "fluid_per_use": 100,
        "horizontal_range": 5,
    },
}


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def format_toml(config: dict[str, dict[str, object]]) -> str:
    """Serialize a nested dict of Slice & Dice tables into TOML."""
    lines: list[str] = []
    for section, values in config.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")
    return "\n".join(lines)


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sliceanddice_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SliceAndDiceSyncTest(unittest.TestCase):
    """Verify Slice & Dice config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "sliceanddice" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "sliceanddice-common.toml"

    def _write_config(self, cfg: dict[str, dict[str, object]]) -> None:
        self._config_path().write_text(format_toml(cfg), encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/sliceanddice/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/sliceanddice-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "sliceanddice-common.toml"
        self.assertTrue(target.is_file(), "Missing sliceanddice-common.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)

        updated = copy.deepcopy(VALID_CONFIG)
        updated["slicer"]["ignore_rotation"] = True
        self._write_config(updated)

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("ignore_rotation = true", target.read_text(encoding="utf-8"))

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
            "Missing expected config files in configs/: config/sliceanddice-common.toml",
            str(ctx_missing.exception),
        )

    def test_invalid_toml_and_table_structure_rejected(self) -> None:
        """Invalid TOML, missing/unexpected sections, and missing/unexpected keys must raise ValueError."""
        self._config_path().write_text("[harvester]\nuses_knife = [broken\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        missing_section = copy.deepcopy(VALID_CONFIG)
        del missing_section["sprinkler"]
        self._write_config(missing_section)
        with self.assertRaises(ValueError) as ctx_missing_sec:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['sprinkler']", str(ctx_missing_sec.exception))

        extra_section = copy.deepcopy(VALID_CONFIG)
        extra_section["client"] = {"fancy": True}
        self._write_config(extra_section)
        with self.assertRaises(ValueError) as ctx_extra_sec:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['client']", str(ctx_extra_sec.exception))

        missing_key = copy.deepcopy(VALID_CONFIG)
        del missing_key["slicer"]["ignore_rotation"]
        self._write_config(missing_key)
        with self.assertRaises(ValueError) as ctx_missing_key:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['ignore_rotation']", str(ctx_missing_key.exception))

        extra_key = copy.deepcopy(VALID_CONFIG)
        extra_key["harvester"]["unknown_flag"] = False
        self._write_config(extra_key)
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['unknown_flag']", str(ctx_extra_key.exception))

    def test_type_enum_and_range_invariants_enforced(self) -> None:
        """Bad types (including bool for int), invalid heat_condition, and out-of-range ints must raise ValueError."""
        bad_bool = copy.deepcopy(VALID_CONFIG)
        bad_bool["harvester"]["uses_knife"] = "true"
        self._write_config(bad_bool)
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("'harvester.uses_knife' must be a boolean", str(ctx_bool.exception))

        for bad_heat in ("", "heated", "ULTRA_HEATED", 1):
            bad_heat_cfg = copy.deepcopy(VALID_CONFIG)
            bad_heat_cfg["basin_cooking"]["heat_condition"] = bad_heat
            self._write_config(bad_heat_cfg)
            with self.assertRaises(ValueError) as ctx_heat:
                self.sync.validate_configs()
            self.assertIn(
                "'basin_cooking.heat_condition' must be one of ['NONE', 'HEATED', 'SUPERHEATED']",
                str(ctx_heat.exception),
            )

        for valid_heat in ("NONE", "HEATED", "SUPERHEATED"):
            valid_heat_cfg = copy.deepcopy(VALID_CONFIG)
            valid_heat_cfg["basin_cooking"]["heat_condition"] = valid_heat
            self._write_config(valid_heat_cfg)
            self.sync.validate_configs()

        bool_as_int = copy.deepcopy(VALID_CONFIG)
        bool_as_int["sprinkler"]["horizontal_range"] = True
        self._write_config(bool_as_int)
        with self.assertRaises(ValueError) as ctx_bool_int:
            self.sync.validate_configs()
        self.assertIn(
            "'sprinkler.horizontal_range' must be an integer in [1, 32]",
            str(ctx_bool_int.exception),
        )

        for key, bad_val, min_val, max_val in (
            ("fluid_capacity", 9, 10, 2048),
            ("fluid_capacity", 2049, 10, 2048),
            ("fluid_capacity", 300.5, 10, 2048),
            ("fluid_per_use", -1, 0, 2048),
            ("fluid_per_use", 2049, 0, 2048),
            ("horizontal_range", 0, 1, 32),
            ("horizontal_range", 33, 1, 32),
        ):
            out_of_range = copy.deepcopy(VALID_CONFIG)
            out_of_range["sprinkler"][key] = bad_val
            self._write_config(out_of_range)
            with self.assertRaises(ValueError) as ctx_range:
                self.sync.validate_configs()
            self.assertIn(
                f"'sprinkler.{key}' must be an integer in [{min_val}, {max_val}]",
                str(ctx_range.exception),
            )

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        with_webhook = copy.deepcopy(VALID_CONFIG)
        with_webhook["harvester"]["secret"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        self._write_config(with_webhook)
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'harvester.secret'", msg)


if __name__ == "__main__":
    unittest.main()
