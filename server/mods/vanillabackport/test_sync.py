#!/usr/bin/env python3
"""Unit and integration tests for mods/vanillabackport/sync.py."""

from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vanillabackport_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VanillaBackportSyncTest(unittest.TestCase):
    """Verify Vanilla Backport config validation, invariants, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "vanillabackport" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "vanillabackport-common.toml"

    def _replace_toml_kv(self, key: str, raw_value: str) -> None:
        text = self._config_path().read_text(encoding="utf-8")
        pattern = rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$"
        updated, count = re.subn(pattern, rf"\g<1>{raw_value}", text, count=1)
        self.assertEqual(count, 1, f"Expected to replace key {key!r} once")
        self._config_path().write_text(updated, encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/vanillabackport/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/vanillabackport-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the config; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "vanillabackport-common.toml"
        self.assertTrue(target.is_file(), f"Missing {target} after sync")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)
        self._replace_toml_kv("tuff_blocks", "false")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("tuff_blocks = false", target.read_text(encoding="utf-8"))

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
            "Missing expected config files in configs/: config/vanillabackport-common.toml",
            str(ctx_missing.exception),
        )

    def test_table_and_key_structure_enforced(self) -> None:
        """Invalid TOML, missing/unexpected tables or keys, and non-table sections must fail."""
        cfg = self._config_path()
        original = cfg.read_text(encoding="utf-8")

        cfg.write_text('["Tricky Trials"\ntuff_blocks = true\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        wilderness_block = (
            '["Wilderness Bound"]\n'
            "\t#allow Dappled Forest biomes to generate\n"
            "\thas_dappled_forest = false\n"
        )
        without_wilderness = original.replace(wilderness_block, "")
        cfg.write_text(without_wilderness, encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_table:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['Wilderness Bound']", str(ctx_missing_table.exception))

        cfg.write_text(original + '\n["Extra Update"]\n\tenabled = true\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra_table:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['Extra Update']", str(ctx_extra_table.exception))

        hot_lava_block = (
            '["Hot as Lava"]\n'
            "\t#allow Chicken jockeys to drop the Lava Chicken music disc\n"
            "\tlava_chicken_music_disc = true\n"
        )
        cfg.write_text(
            '"Hot as Lava" = true\n' + original.replace(hot_lava_block, ""),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_non_table:
            self.sync.validate_configs()
        self.assertIn('["Hot as Lava"] must be a TOML table', str(ctx_non_table.exception))

        cfg.write_text(original.replace("\ttuff_blocks = true\n", ""), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_key:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['tuff_blocks']", str(ctx_missing_key.exception))

        cfg.write_text(original + "\textra_flag = false\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra_flag']", str(ctx_extra_key.exception))

    def test_field_types_enums_and_ranges_enforced(self) -> None:
        """All field types, recipe enums, RGB bounds, chances, speeds, and Copper Age ticks must validate."""
        original = self._config_path().read_text(encoding="utf-8")

        # Strict bool
        for bad_bool in ("1", '"true"'):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("tuff_blocks", bad_bool)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn('["Tricky Trials"].tuff_blocks must be a boolean', str(ctx.exception))

        # Recipe enum
        for bad_recipe in ('"OVERWRITE"', "123", "true"):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("bundle_recipe", bad_recipe)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                '["Bundles of Bravery"].bundle_recipe must be one of {APPEND, IGNORE, REPLACE}',
                str(ctx.exception),
            )

        # RGB colors (0..0xFFFFFF)
        for bad_color in ("-1", "16777216", "true", "12.5", '"#ffffff"'):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("creaking_particle_color", bad_color)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                '["The Garden Awakens"].creaking_particle_color must be a strict integer in 0..16777215',
                str(ctx.exception),
            )

        # Probability chances (0.0..1.0)
        for bad_chance in ("-0.01", "1.01", "nan", "inf", "true", '"0.5"'):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("mob_variants_spawn_chance", bad_chance)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                '["Spring to Life"].mob_variants_spawn_chance must be a finite number in 0.0..1.0',
                str(ctx.exception),
            )

        # Non-negative speed modifier (>= 0.0)
        for bad_speed in ("-0.1", "nan", "inf", "false", '"1.0"'):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("happy_ghast_speed_modifier", bad_speed)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                '["Chase the Skies"].happy_ghast_speed_modifier must be a finite number >= 0.0',
                str(ctx.exception),
            )

        # Copper Age positive ints and carry amount > 1
        for bad_tick in ("0", "-10", "true", "1.5"):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("golem_weathering_tick_from", bad_tick)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                '["Copper Age"].golem_weathering_tick_from must be a strict integer > 0',
                str(ctx.exception),
            )

        for bad_carry in ("1", "0", "-1", "true", "2.5"):
            self._config_path().write_text(original, encoding="utf-8")
            self._replace_toml_kv("golem_item_carry_amount", bad_carry)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                '["Copper Age"].golem_item_carry_amount must be a strict integer > 1',
                str(ctx.exception),
            )

        # Cross-key invariant: golem_weathering_tick_from <= golem_weathering_tick_to
        self._config_path().write_text(original, encoding="utf-8")
        self._replace_toml_kv("golem_weathering_tick_from", "600000")
        self._replace_toml_kv("golem_weathering_tick_to", "500000")
        with self.assertRaises(ValueError) as ctx_cross:
            self.sync.validate_configs()
        self.assertIn(
            '["Copper Age"].golem_weathering_tick_from (600000) must be <= golem_weathering_tick_to (500000)',
            str(ctx_cross.exception),
        )

        # Valid boundary values
        self._config_path().write_text(original, encoding="utf-8")
        self._replace_toml_kv("creaking_particle_color", "0")
        self._replace_toml_kv("creaking_particle_reverse_color", "16777215")
        self._replace_toml_kv("mob_variants_spawn_chance", "0.0")
        self._replace_toml_kv("cactus_flower_spawn_chance", "1.0")
        self._replace_toml_kv("happy_ghast_speed_modifier", "0.0")
        self._replace_toml_kv("golem_weathering_tick_from", "1")
        self._replace_toml_kv("golem_weathering_tick_to", "1")
        self._replace_toml_kv("golem_item_carry_amount", "2")
        loaded = self.sync.validate_configs()
        self.assertIn("config/vanillabackport-common.toml", loaded)

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        cfg = self._config_path()
        cfg.write_text(
            cfg.read_text(encoding="utf-8")
            + '\nsecret = "https://discord.com/api/webhooks/123456789/abcdef_token"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'Wilderness Bound.secret'", msg)


if __name__ == "__main__":
    unittest.main()
