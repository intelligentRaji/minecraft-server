#!/usr/bin/env python3
"""Unit and integration tests for mods/everycomp/sync.py."""

from __future__ import annotations

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


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("everycomp_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EveryCompSyncTest(unittest.TestCase):
    """Verify Every Compat config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "everycomp" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self, filename: str) -> Path:
        return self.configs_dir / "config" / filename

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/everycomp/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {
                "config/everycomp-common.toml",
                "config/everycomp-entries.toml",
                "config/everycomp-hazardous.toml",
            },
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places all 3 static files; second run is idempotent; updates preserve mode."""
        loaded = self.sync.validate_configs()
        changed, unchanged = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual((changed, unchanged), (3, 0))

        for filename in (
            "everycomp-common.toml",
            "everycomp-entries.toml",
            "everycomp-hazardous.toml",
        ):
            target = self.data_dir / "config" / filename
            self.assertTrue(target.is_file())
            self.assertEqual(
                target.read_bytes(),
                self._config_path(filename).read_bytes(),
            )

        changed2, unchanged2 = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual((changed2, unchanged2), (0, 3))

        common_target = self.data_dir / "config" / "everycomp-common.toml"
        os.chmod(common_target, 0o600)
        text = self._config_path("everycomp-common.toml").read_text(encoding="utf-8")
        self._config_path("everycomp-common.toml").write_text(
            text.replace("debug_packet = false", "debug_packet = true"),
            encoding="utf-8",
        )
        loaded_updated = self.sync.validate_configs()
        changed3, unchanged3 = self.sync.apply_configs(loaded_updated, dry_run=False)
        self.assertEqual((changed3, unchanged3), (1, 2))
        self.assertEqual(os.stat(common_target).st_mode & 0o777, 0o600)

    def test_dry_run_leaves_target_untouched(self) -> None:
        """Running with --dry-run must not create or modify any file in DATA_DIR."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = self.sync.main(["--dry-run"])
        self.assertEqual(exit_code, 0)
        self.assertIn("DRY-RUN: 3 changed, 0 unchanged", stdout.getvalue())
        self.assertFalse((self.data_dir / "config").exists())

    def test_common_missing_and_extra_keys_rejected(self) -> None:
        path = self._config_path("everycomp-common.toml")
        original = path.read_text(encoding="utf-8")

        path.write_text(
            original.replace("debug_packet = false\n", ""),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("missing required keys", str(ctx.exception))
        self.assertIn("deterministic", str(ctx.exception))

        path.write_text(original + "\textra_key = true\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("unexpected keys", str(ctx.exception))

    def test_common_non_bool_rejected(self) -> None:
        path = self._config_path("everycomp-common.toml")
        original = path.read_text(encoding="utf-8")

        path.write_text(
            original.replace("creative_tab = true", "creative_tab = 1"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("strict boolean", str(ctx.exception))
        self.assertIn("ForgeConfigSpec", str(ctx.exception))

        path.write_text(
            original.replace("mod_origin_enabled = true", 'mod_origin_enabled = "yes"'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("general.tooltips.mod_origin_enabled", str(ctx.exception))

    def test_entries_schema_and_non_bool_rejected(self) -> None:
        path = self._config_path("everycomp-entries.toml")
        original = path.read_text(encoding="utf-8")

        path.write_text(original + "\n[extra_section]\nfoo = true\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("unexpected keys", str(ctx.exception))

        path.write_text(
            original.replace("fir = true", "fir = 1", 1),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("strict boolean", str(ctx.exception))

        path.write_text(
            "[types.wood_type]\nbotania = true\n[types.leaves_type]\n[entries.wood_type]\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("TOML table of entry toggles", str(ctx.exception))

    def test_hazardous_schema_regex_and_bool_rejected(self) -> None:
        path = self._config_path("everycomp-hazardous.toml")
        original = path.read_text(encoding="utf-8")

        # Valid regexes should pass
        path.write_text(
            original.replace("blacklist = []", 'blacklist = ["biomesoplenty:.*fireproof.*"]', 1),
            encoding="utf-8",
        )
        self.sync.validate_configs()

        # Invalid regex must fail with rationale
        path.write_text(
            original.replace("blacklist = []", 'blacklist = ["[unclosed"]', 1),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("not a valid regex", str(ctx.exception))
        self.assertIn("conditional registration", str(ctx.exception))

        # Empty regex string must fail
        path.write_text(
            original.replace("blacklist = []", 'blacklist = ["  "]', 1),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("non-empty regex string", str(ctx.exception))

        # Non-bool include_all_wood_modules must fail
        path.write_text(
            original.replace("include_all_wood_modules = true", "include_all_wood_modules = 1"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("other.include_all_wood_modules", str(ctx.exception))
        self.assertIn("strict boolean", str(ctx.exception))

        # Missing top-level table must fail
        missing_other = (
            "[other]\n"
            "\t#Disable all of Supported Mods on EveryCompat's side. "
            "This feature is same as Library-Section which do not have any Wood Modules.\n"
            "\t#WARNING: If the config between CLIENT & SERVER are not the same, "
            "then you won't able to join a server\n"
            "\tinclude_all_wood_modules = true\n"
        )
        path.write_text(original.replace(missing_other, ""), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("missing required keys", str(ctx.exception))

    def test_forbidden_files_and_secrets_rejected(self) -> None:
        (self.configs_dir / "debug").mkdir()
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory", str(ctx.exception))
        shutil.rmtree(self.configs_dir / "debug")

        (self.configs_dir / "config" / "state.db").write_text("sqlite", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Forbidden archive/runtime file", str(ctx.exception))
        (self.configs_dir / "config" / "state.db").unlink()

        common_path = self._config_path("everycomp-common.toml")
        common_path.write_text(
            common_path.read_text(encoding="utf-8")
            + '\npassword = "super-secret-value"\n'
            + '# https://discord.com/api/webhooks/123456789012345678/abcDEF123_xyz\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key", str(ctx.exception))
        self.assertIn("Discord Webhook URL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
