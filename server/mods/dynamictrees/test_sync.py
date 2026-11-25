#!/usr/bin/env python3
"""Unit and integration tests for mods/dynamictrees/sync.py."""

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
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("dynamictrees_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class DynamicTreesSyncTest(unittest.TestCase):
    """Verify Dynamic Trees config validation, invariants, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "dynamictrees" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _common_path(self) -> Path:
        return self.configs_dir / "config" / "dynamictrees-common.toml"

    def _server_path(self) -> Path:
        return self.configs_dir / "world" / "serverconfig" / "dynamictrees-server.toml"

    def _replace_server_line(self, key: str, new_value: str) -> None:
        text = self._server_path().read_text(encoding="utf-8")
        updated, count = re.subn(
            rf"^(\s*{re.escape(key)}\s*=\s*).*$",
            rf"\g<1>{new_value}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        self.assertEqual(count, 1, f"Expected to replace {key} once")
        self._server_path().write_text(updated, encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/dynamictrees/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {
                "config/dynamictrees-common.toml",
                "world/serverconfig/dynamictrees-server.toml",
            },
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places both files; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "dynamictrees-common.toml"
        server_target = self.data_dir / "world" / "serverconfig" / "dynamictrees-server.toml"
        self.assertTrue(common_target.is_file())
        self.assertTrue(server_target.is_file())

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(common_target, 0o600)
        common_src = self._common_path()
        common_src.write_text(
            common_src.read_text(encoding="utf-8").replace(
                "replaceVanillaSapling = false",
                "replaceVanillaSapling = true",
            ),
            encoding="utf-8",
        )

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(common_target.stat().st_mode & 0o777, 0o600)
        self.assertIn(
            "replaceVanillaSapling = true",
            common_target.read_text(encoding="utf-8"),
        )

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
        for forbidden_dir in ("logs", "mods", "region"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden file/directory present in configs/: {forbidden_dir}",
                str(ctx.exception),
            )
            dpath.rmdir()

        for suffix_file in ("mod.jar", "state.db", "cache.sqlite", "latest.log", "backup.zip"):
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

        self._server_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: world/serverconfig/dynamictrees-server.toml",
            str(ctx_missing.exception),
        )

    def test_common_schema_and_types_enforced(self) -> None:
        """Common TOML must enforce valid TOML, exact tables/keys, strict bools, and non-empty strings."""
        common_path = self._common_path()
        original = common_path.read_text(encoding="utf-8")

        common_path.write_text("[vanilla\nreplaceVanillaSapling = false\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        common_path.write_text(original + "\n[extra]\na = 1\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra_table:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra']", str(ctx_extra_table.exception))

        common_path.write_text(
            original.replace("replaceVanillaSapling = false", 'replaceVanillaSapling = "false"'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("[vanilla].replaceVanillaSapling invariant violation: must be a boolean", str(ctx_bool.exception))

        common_path.write_text(
            original.replace('biocharBrewingBase = "thick"', 'biocharBrewingBase = "   "'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_str:
            self.sync.validate_configs()
        self.assertIn(
            "[misc].biocharBrewingBase invariant violation: must be a non-empty string",
            str(ctx_str.exception),
        )

    def test_server_enums_ranges_and_types_enforced(self) -> None:
        """Server TOML must enforce root/table ranges, enum values, blacklist types, and strict bools."""
        original = self._server_path().read_text(encoding="utf-8")

        # Top-level growthFolding range (0..4096) and strict int check
        for bad_val in ("-1", "4097", "true"):
            self._server_path().write_text(original, encoding="utf-8")
            self._replace_server_line("growthFolding", bad_val)
            with self.assertRaises(ValueError) as ctx_gf:
                self.sync.validate_configs()
            self.assertIn("growthFolding invariant violation: must be an integer in [0, 4096]", str(ctx_gf.exception))

        # [seeds].leavesSeedDropRate range (0.0..64.0)
        self._server_path().write_text(original, encoding="utf-8")
        self._replace_server_line("leavesSeedDropRate", "65.0")
        with self.assertRaises(ValueError) as ctx_seed_rate:
            self.sync.validate_configs()
        self.assertIn(
            "[seeds].leavesSeedDropRate invariant violation: must be a finite number in [0.0, 64.0]",
            str(ctx_seed_rate.exception),
        )

        # [seeds].timeToLive range (0..6000)
        self._server_path().write_text(original, encoding="utf-8")
        self._replace_server_line("timeToLive", "6001")
        with self.assertRaises(ValueError) as ctx_ttl:
            self.sync.validate_configs()
        self.assertIn("[seeds].timeToLive invariant violation: must be an integer in [0, 6000]", str(ctx_ttl.exception))

        # [trees].swampOaksInWater enum
        self._server_path().write_text(original, encoding="utf-8")
        self._replace_server_line("swampOaksInWater", '"FLOATING"')
        with self.assertRaises(ValueError) as ctx_swamp:
            self.sync.validate_configs()
        self.assertIn(
            "[trees].swampOaksInWater invariant violation: must be one of {DISABLED, ROOTED, SUNK}",
            str(ctx_swamp.exception),
        )

        # [interaction].axeDamageMode enum
        self._server_path().write_text(original, encoding="utf-8")
        self._replace_server_line("axeDamageMode", '"DURABILITY"')
        with self.assertRaises(ValueError) as ctx_axe:
            self.sync.validate_configs()
        self.assertIn(
            "[interaction].axeDamageMode invariant violation: must be one of {THICKNESS, VANILLA, VOLUME}",
            str(ctx_axe.exception),
        )

        # [world].dimensionsBlacklist list of non-empty strings
        for bad_list in ('"minecraft:the_nether"', "[123]", '[""]'):
            self._server_path().write_text(original, encoding="utf-8")
            self._replace_server_line("dimensionsBlacklist", bad_list)
            with self.assertRaises(ValueError) as ctx_bl:
                self.sync.validate_configs()
            self.assertIn(
                "[world].dimensionsBlacklist invariant violation: "
                "must be a list of non-empty dimension registry name strings",
                str(ctx_bl.exception),
            )

        # [debug].debug strict bool
        self._server_path().write_text(original, encoding="utf-8")
        self._replace_server_line("debug", "1")
        with self.assertRaises(ValueError) as ctx_dbg:
            self.sync.validate_configs()
        self.assertIn("[debug].debug invariant violation: must be a boolean", str(ctx_dbg.exception))

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        common_path = self._common_path()
        original = common_path.read_text(encoding="utf-8")
        common_path.write_text(
            original + '\n[secrets]\nsecret = "https://discord.com/api/webhooks/123456789/abcdef_token"\n',
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'secrets.secret'", msg)


if __name__ == "__main__":
    unittest.main()
