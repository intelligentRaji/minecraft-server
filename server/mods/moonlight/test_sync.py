#!/usr/bin/env python3
"""Unit and integration tests for mods/moonlight/sync.py."""

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

VALID_GENERAL_CONFIG: dict[str, object] = {
    "clear_dynamic_resources": False,
    "multi_threaded_generation": True,
    "extra_debug": False,
    "extra_children_debug": False,
    "global_datapacks_folder": "moonlight-global-datapacks",
}


def format_toml(general: dict[str, object], extra_tables: str = "") -> str:
    lines: list[str] = ["[general]"]
    for key, value in general.items():
        if isinstance(value, bool):
            lines.append(f"    {key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    {key} = "{escaped}"')
        else:
            lines.append(f"    {key} = {value!r}")
    if extra_tables:
        lines.append("")
        lines.append(extra_tables)
    return "\n".join(lines) + "\n"


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("moonlight_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class MoonlightSyncTest(unittest.TestCase):
    """Verify Moonlight Lib config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "moonlight" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _common_path(self) -> Path:
        return self.configs_dir / "config" / "moonlight-common.toml"

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/moonlight/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/moonlight-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "moonlight-common.toml"
        self.assertTrue(target.is_file(), "Missing moonlight-common.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)

        updated = dict(VALID_GENERAL_CONFIG)
        updated["clear_dynamic_resources"] = True
        self._common_path().write_text(format_toml(updated), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("clear_dynamic_resources = true", target.read_text(encoding="utf-8"))

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
        for forbidden_dir in ("logs", "world", "mods", "moonlight-global-datapacks"):
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

        self._common_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: config/moonlight-common.toml",
            str(ctx_missing.exception),
        )

    def test_secret_guard_rejects_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must raise ValueError."""
        with_webhook = dict(VALID_GENERAL_CONFIG)
        with_webhook["global_datapacks_folder"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        self._common_path().write_text(format_toml(with_webhook), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("secret", str(ctx.exception).lower())

        self._common_path().write_text(
            format_toml(VALID_GENERAL_CONFIG) + '\n[auth]\npassword = "super-secret-value"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_key:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'auth.password'", str(ctx_key.exception))

    def test_top_level_and_general_table_schema_checks(self) -> None:
        """Missing or unexpected top-level tables or [general] keys must fail validation."""
        # Missing [general] table
        self._common_path().write_text("[other]\nflag = true\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_table:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['general']", str(ctx_missing_table.exception))

        # Unexpected top-level table
        self._common_path().write_text(
            format_toml(VALID_GENERAL_CONFIG, extra_tables="[extra]\nfoo = 1"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_extra_table:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra']", str(ctx_extra_table.exception))

        # Missing key in [general]
        missing_key = dict(VALID_GENERAL_CONFIG)
        del missing_key["global_datapacks_folder"]
        self._common_path().write_text(format_toml(missing_key), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing_key:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['global_datapacks_folder']", str(ctx_missing_key.exception))

        # Unexpected key in [general]
        extra_key = dict(VALID_GENERAL_CONFIG)
        extra_key["unknown_flag"] = False
        self._common_path().write_text(format_toml(extra_key), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['unknown_flag']", str(ctx_extra_key.exception))

    def test_type_checks_for_boolean_and_string_keys(self) -> None:
        """Non-bool values for bool keys and non-str values for global_datapacks_folder must fail."""
        for bool_key in (
            "clear_dynamic_resources",
            "multi_threaded_generation",
            "extra_debug",
            "extra_children_debug",
        ):
            bad = dict(VALID_GENERAL_CONFIG)
            bad[bool_key] = "true"
            self._common_path().write_text(format_toml(bad), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"[general].{bool_key} must be a boolean", str(ctx.exception))

        bad_folder_type = dict(VALID_GENERAL_CONFIG)
        bad_folder_type["global_datapacks_folder"] = 123
        self._common_path().write_text(format_toml(bad_folder_type), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_type:
            self.sync.validate_configs()
        self.assertIn("[general].global_datapacks_folder must be a string", str(ctx_type.exception))

    def test_global_datapacks_folder_path_invariant(self) -> None:
        """global_datapacks_folder accepts '' or safe relative path, and rejects '/' or '..'."""
        for bad_path in ("/etc/datapacks", "../escape", "sub/../../escape"):
            bad = dict(VALID_GENERAL_CONFIG)
            bad["global_datapacks_folder"] = bad_path
            self._common_path().write_text(format_toml(bad), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn("must be a relative path without '..' or a leading '/'", str(ctx.exception))

        disabled = dict(VALID_GENERAL_CONFIG)
        disabled["global_datapacks_folder"] = ""
        self._common_path().write_text(format_toml(disabled), encoding="utf-8")
        loaded = self.sync.validate_configs()
        self.assertIn("config/moonlight-common.toml", loaded)

    def test_extra_children_debug_requires_extra_debug(self) -> None:
        """extra_children_debug=true with extra_debug=false must fail with explanatory rationale."""
        invalid = dict(VALID_GENERAL_CONFIG)
        invalid["extra_debug"] = False
        invalid["extra_children_debug"] = True
        self._common_path().write_text(format_toml(invalid), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("[general].extra_children_debug=true requires [general].extra_debug=true", msg)
        self.assertIn("BlockTypes' children", msg)

        valid = dict(VALID_GENERAL_CONFIG)
        valid["extra_debug"] = True
        valid["extra_children_debug"] = True
        self._common_path().write_text(format_toml(valid), encoding="utf-8")
        loaded = self.sync.validate_configs()
        self.assertIn("config/moonlight-common.toml", loaded)


if __name__ == "__main__":
    unittest.main()
