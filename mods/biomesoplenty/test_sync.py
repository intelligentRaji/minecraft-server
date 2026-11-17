#!/usr/bin/env python3
"""Unit and integration tests for mods/biomesoplenty/sync.py."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("biomesoplenty_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def format_gameplay_toml(wandering_trader_trades: object) -> str:
    if isinstance(wandering_trader_trades, bool):
        rendered = "true" if wandering_trader_trades else "false"
    elif isinstance(wandering_trader_trades, str):
        rendered = f'"{wandering_trader_trades}"'
    else:
        rendered = repr(wandering_trader_trades)
    return f"[general]\n\twandering_trader_trades = {rendered}\n"


def format_generation_toml(
    nether_weight: object = 13,
    nether_rare_weight: object = 2,
    overworld_primary_weight: object = 10,
    overworld_rare_weight: object = 2,
    overworld_secondary_weight: object = 8,
) -> str:
    def fmt(val: object) -> str:
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, str):
            return f'"{val}"'
        return repr(val)

    return (
        "[nether]\n"
        f"\tbop_nether_region_weight = {fmt(nether_weight)}\n"
        f"\tbop_nether_rare_region_weight = {fmt(nether_rare_weight)}\n"
        "\n"
        "[overworld]\n"
        f"\tbop_primary_overworld_region_weight = {fmt(overworld_primary_weight)}\n"
        f"\tbop_overworld_rare_region_weight = {fmt(overworld_rare_weight)}\n"
        f"\tbop_secondary_overworld_region_weight = {fmt(overworld_secondary_weight)}\n"
    )


class BiomesOPlentySyncTest(unittest.TestCase):
    """Verify Biomes O' Plenty config validation, invariants, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "biomesoplenty" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _biome_toggles_path(self) -> Path:
        return self.configs_dir / "config" / "biomesoplenty" / "biome_toggles.json"

    def _gameplay_path(self) -> Path:
        return self.configs_dir / "config" / "biomesoplenty" / "gameplay.toml"

    def _generation_path(self) -> Path:
        return self.configs_dir / "config" / "biomesoplenty" / "generation.toml"

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/biomesoplenty/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {
                "config/biomesoplenty/biome_toggles.json",
                "config/biomesoplenty/gameplay.toml",
                "config/biomesoplenty/generation.toml",
            },
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places all 3 files; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("3 changed, 0 unchanged", buf1.getvalue())

        targets = [
            self.data_dir / "config" / "biomesoplenty" / "biome_toggles.json",
            self.data_dir / "config" / "biomesoplenty" / "gameplay.toml",
            self.data_dir / "config" / "biomesoplenty" / "generation.toml",
        ]
        for target in targets:
            self.assertTrue(target.is_file(), f"Missing {target} after sync")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 3 unchanged", buf2.getvalue())

        gameplay_target = self.data_dir / "config" / "biomesoplenty" / "gameplay.toml"
        os.chmod(gameplay_target, 0o600)
        self._gameplay_path().write_text(format_gameplay_toml(False), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 2 unchanged", buf3.getvalue())
        self.assertEqual(gameplay_target.stat().st_mode & 0o777, 0o600)
        self.assertIn("wandering_trader_trades = false", gameplay_target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 3 changed, 0 unchanged", buf.getvalue())
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
        link_path.symlink_to(self._gameplay_path())
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

        self._generation_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: config/biomesoplenty/generation.toml",
            str(ctx_missing.exception),
        )

    def test_biome_toggles_schema_and_types_enforced(self) -> None:
        """Invalid JSON, non-dict root, missing/unexpected keys, and non-bool values must fail."""
        toggles_path = self._biome_toggles_path()
        original = json.loads(toggles_path.read_text(encoding="utf-8"))

        toggles_path.write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_json:
            self.sync.validate_configs()
        self.assertIn("invalid JSON", str(ctx_json.exception))

        toggles_path.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_list:
            self.sync.validate_configs()
        self.assertIn("root JSON value must be an object", str(ctx_list.exception))

        missing = dict(original)
        del missing["woodland_enabled"]
        toggles_path.write_text(json.dumps(missing, indent=2), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['woodland_enabled']", str(ctx_missing.exception))

        extra = dict(original)
        extra["custom_biome_enabled"] = True
        toggles_path.write_text(json.dumps(extra, indent=2), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['custom_biome_enabled']", str(ctx_extra.exception))

        for bad_val in (1, "true"):
            wrong_type = dict(original)
            wrong_type["bayou_enabled"] = bad_val
            toggles_path.write_text(json.dumps(wrong_type, indent=2), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_type:
                self.sync.validate_configs()
            self.assertIn("'bayou_enabled' must be a boolean", str(ctx_type.exception))

    def test_gameplay_schema_and_types_enforced(self) -> None:
        """Invalid TOML, missing/unexpected tables or keys, and non-bool trade toggle must fail."""
        gameplay_path = self._gameplay_path()

        gameplay_path.write_text("[general\nwandering_trader_trades = true\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        gameplay_path.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_no_table:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['general']", str(ctx_no_table.exception))

        gameplay_path.write_text("[general]\nwandering_trader_trades = true\n[extra]\na = 1\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra_table:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra']", str(ctx_extra_table.exception))

        gameplay_path.write_text("general = true\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_non_table:
            self.sync.validate_configs()
        self.assertIn("[general] must be a TOML table", str(ctx_non_table.exception))

        gameplay_path.write_text("[general]\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_key:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['wandering_trader_trades']", str(ctx_missing_key.exception))

        gameplay_path.write_text(
            "[general]\nwandering_trader_trades = true\nextra_flag = false\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra_flag']", str(ctx_extra_key.exception))

        for bad_val in (1, "true"):
            gameplay_path.write_text(format_gameplay_toml(bad_val), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_type:
                self.sync.validate_configs()
            self.assertIn("[general].wandering_trader_trades must be a boolean", str(ctx_type.exception))

    def test_generation_schema_types_and_ranges_enforced(self) -> None:
        """Generation TOML must enforce exact tables, keys, and strict non-negative integer weights."""
        gen_path = self._generation_path()

        gen_path.write_text("[nether]\nbop_nether_region_weight = [\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        gen_path.write_text("[nether]\nbop_nether_region_weight = 13\nbop_nether_rare_region_weight = 2\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_table:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['overworld']", str(ctx_missing_table.exception))

        gen_path.write_text(
            format_generation_toml() + "\n[end]\nweight = 1\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_extra_table:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['end']", str(ctx_extra_table.exception))

        gen_path.write_text(
            "[nether]\nbop_nether_region_weight = 13\n"
            "[overworld]\nbop_primary_overworld_region_weight = 10\n"
            "bop_overworld_rare_region_weight = 2\nbop_secondary_overworld_region_weight = 8\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_missing_key:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['bop_nether_rare_region_weight']", str(ctx_missing_key.exception))

        gen_path.write_text(
            format_generation_toml() + "\textra_weight = 5\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra_weight']", str(ctx_extra_key.exception))

        for bad_weight in (-1, True, 1.5, "13"):
            gen_path.write_text(format_generation_toml(nether_weight=bad_weight), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_weight:
                self.sync.validate_configs()
            self.assertIn(
                "[nether].bop_nether_region_weight must be a non-negative integer >= 0",
                str(ctx_weight.exception),
            )

        gen_path.write_text(
            format_generation_toml(
                nether_weight=0,
                nether_rare_weight=0,
                overworld_primary_weight=0,
                overworld_rare_weight=0,
                overworld_secondary_weight=0,
            ),
            encoding="utf-8",
        )
        loaded = self.sync.validate_configs()
        self.assertIn("config/biomesoplenty/generation.toml", loaded)

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        toggles_path = self._biome_toggles_path()
        toggles = json.loads(toggles_path.read_text(encoding="utf-8"))
        toggles["secret"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        toggles_path.write_text(json.dumps(toggles, indent=2), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'secret'", msg)


if __name__ == "__main__":
    unittest.main()
