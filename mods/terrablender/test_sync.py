#!/usr/bin/env python3
"""Unit and integration tests for mods/terrablender/sync.py."""

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

VALID_GENERATION_SETTINGS: dict[str, object] = {
    "overworld_region_size": 4,
    "nether_region_size": 2,
    "vanilla_overworld_region_weight": 10,
    "vanilla_nether_region_weight": 10,
}


def format_terrablender_toml(
    general: dict[str, object] | object = None,
    generation_settings: dict[str, object] | object = None,
    *,
    include_general: bool = True,
    include_generation: bool = True,
    extra_root: dict[str, object] | None = None,
) -> str:
    """Serialize a TerraBlender TOML document for test cases."""
    lines: list[str] = []
    if include_general:
        if general is None:
            lines.append("general = {}")
        elif isinstance(general, dict):
            if not general:
                lines.append("general = {}")
            else:
                lines.append("[general]")
                for k, v in general.items():
                    lines.append(f"{k} = {_format_toml_value(v)}")
        else:
            lines.append(f"general = {_format_toml_value(general)}")

    if extra_root:
        for k, v in extra_root.items():
            lines.append(f"{k} = {_format_toml_value(v)}")

    if include_generation:
        if generation_settings is None:
            gen_map = VALID_GENERATION_SETTINGS
        elif isinstance(generation_settings, dict):
            gen_map = generation_settings
        else:
            lines.append(f"generation_settings = {_format_toml_value(generation_settings)}")
            return "\n".join(lines) + "\n"

        lines.append("[generation_settings]")
        for k, v in gen_map.items():
            lines.append(f"{k} = {_format_toml_value(v)}")

    return "\n".join(lines) + "\n"


def _format_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("terrablender_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TerraBlenderSyncTest(unittest.TestCase):
    """Verify TerraBlender config validation, invariant errors, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "terrablender" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _toml_path(self) -> Path:
        return self.configs_dir / "config" / "terrablender.toml"

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/terrablender/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/terrablender.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "terrablender.toml"
        self.assertTrue(target.is_file(), "Missing terrablender.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)

        updated = dict(VALID_GENERATION_SETTINGS)
        updated["overworld_region_size"] = 5
        self._toml_path().write_text(
            format_terrablender_toml(generation_settings=updated),
            encoding="utf-8",
        )

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("overworld_region_size = 5", target.read_text(encoding="utf-8"))

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
        link_path.symlink_to(self._toml_path())
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

        self._toml_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: config/terrablender.toml",
            str(ctx_missing.exception),
        )

    def test_invalid_toml_and_root_keys_rejected(self) -> None:
        """Invalid TOML syntax and missing/extra root keys must raise ValueError with rationale."""
        toml_path = self._toml_path()

        toml_path.write_text("general = [unclosed\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        toml_path.write_text(format_terrablender_toml(include_general=False), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_root:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['general']", str(ctx_missing_root.exception))

        toml_path.write_text(
            format_terrablender_toml(extra_root={"unexpected_root": 1}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_extra_root:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['unexpected_root']", str(ctx_extra_root.exception))

    def test_general_must_be_empty_table(self) -> None:
        """Non-table or non-empty `general` section must raise ValueError with rationale."""
        toml_path = self._toml_path()

        toml_path.write_text(format_terrablender_toml(general=True), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_type:
            self.sync.validate_configs()
        self.assertIn("'general' must be an empty TOML table", str(ctx_type.exception))

        toml_path.write_text(
            format_terrablender_toml(general={"debug": True}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_nonempty:
            self.sync.validate_configs()
        self.assertIn("'general' must be an empty TOML table with 0 keys", str(ctx_nonempty.exception))

    def test_generation_settings_keys_and_types_rejected(self) -> None:
        """Missing/extra keys and non-strict-int types (including bool) must raise ValueError."""
        toml_path = self._toml_path()

        toml_path.write_text(
            format_terrablender_toml(generation_settings="invalid"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_not_table:
            self.sync.validate_configs()
        self.assertIn("expected a mapping/table", str(ctx_not_table.exception))

        missing = dict(VALID_GENERATION_SETTINGS)
        del missing["nether_region_size"]
        toml_path.write_text(
            format_terrablender_toml(generation_settings=missing),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['nether_region_size']", str(ctx_missing.exception))

        extra = dict(VALID_GENERATION_SETTINGS)
        extra["extra_setting"] = 1
        toml_path.write_text(
            format_terrablender_toml(generation_settings=extra),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra_setting']", str(ctx_extra.exception))

        for key in VALID_GENERATION_SETTINGS:
            for bad_val in (True, False, 4.0, "4"):
                bad = dict(VALID_GENERATION_SETTINGS)
                bad[key] = bad_val
                toml_path.write_text(
                    format_terrablender_toml(generation_settings=bad),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError, msg=f"Expected ValueError for {key}={bad_val!r}") as ctx_type:
                    self.sync.validate_configs()
                self.assertIn(f"generation_settings.{key} must be a strict integer", str(ctx_type.exception))

    def test_generation_settings_ranges_enforced(self) -> None:
        """Out-of-range region sizes and vanilla weights must raise ValueError with rationale."""
        toml_path = self._toml_path()

        out_of_range_cases = [
            ("overworld_region_size", 1, "[2, 6]"),
            ("overworld_region_size", 7, "[2, 6]"),
            ("nether_region_size", 1, "[2, 6]"),
            ("nether_region_size", 7, "[2, 6]"),
            ("vanilla_overworld_region_weight", -1, "[0, 2147483647]"),
            ("vanilla_overworld_region_weight", 2147483648, "[0, 2147483647]"),
            ("vanilla_nether_region_weight", -1, "[0, 2147483647]"),
            ("vanilla_nether_region_weight", 2147483648, "[0, 2147483647]"),
        ]
        for key, bad_val, expected_range in out_of_range_cases:
            bad = dict(VALID_GENERATION_SETTINGS)
            bad[key] = bad_val
            toml_path.write_text(
                format_terrablender_toml(generation_settings=bad),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {key}={bad_val}") as ctx:
                self.sync.validate_configs()
            self.assertIn(
                f"generation_settings.{key} must be in range {expected_range}",
                str(ctx.exception),
            )

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        toml_path = self._toml_path()

        toml_path.write_text(
            format_terrablender_toml(
                extra_root={"secret": "https://discord.com/api/webhooks/123456789/abcdef_token"},
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'secret'", msg)


if __name__ == "__main__":
    unittest.main()
