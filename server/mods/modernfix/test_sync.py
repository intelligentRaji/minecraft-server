#!/usr/bin/env python3
"""Unit and integration tests for mods/modernfix/sync.py."""

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


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("modernfix_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class ModernFixSyncTest(unittest.TestCase):
    """Verify ModernFix config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "modernfix" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/modernfix/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"modernfix-common.toml", "modernfix-mixins.properties"},
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places both static files; second run is idempotent; updates preserve target file mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "modernfix-common.toml"
        mixins_target = self.data_dir / "config" / "modernfix-mixins.properties"
        self.assertTrue(common_target.is_file(), "Missing modernfix-common.toml in data/config/")
        self.assertTrue(mixins_target.is_file(), "Missing modernfix-mixins.properties in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(common_target, 0o600)
        os.chmod(mixins_target, 0o640)

        common_src = self.configs_dir / "modernfix-common.toml"
        common_src.write_text(
            'blacklist_async_jei_plugins = ["jepb:jei_plugin", "example:plugin"]\n',
            encoding="utf-8",
        )
        mixins_src = self.configs_dir / "modernfix-mixins.properties"
        mixins_src.write_text(
            mixins_src.read_text(encoding="utf-8") + "\nmixin.perf.dynamic_resources=true\nstability_level=BETA\n",
            encoding="utf-8",
        )

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("2 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(common_target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(mixins_target.stat().st_mode & 0o777, 0o640)
        self.assertIn("example:plugin", common_target.read_text(encoding="utf-8"))
        self.assertIn("stability_level=BETA", mixins_target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_dirs_and_symlinks_rejected(self) -> None:
        """Forbidden runtime directories, archive/runtime suffixes, and symlinks must fail pre-flight validation."""
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

        for suffix_file in ("backup.zip", "world.tar.gz", "state.db", "mod.jar", "run.lock"):
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
        link_path.symlink_to(self.configs_dir / "modernfix-common.toml")
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

        (self.configs_dir / "modernfix-common.toml").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: modernfix-common.toml",
            str(ctx_missing.exception),
        )

    def test_common_toml_invariants_validated(self) -> None:
        """Invalid TOML, wrong types, empty strings, and unexpected keys in modernfix-common.toml must fail."""
        common_path = self.configs_dir / "modernfix-common.toml"

        common_path.write_text("blacklist_async_jei_plugins = [\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("modernfix-common.toml: invalid TOML", str(ctx_toml.exception))

        bad_values = [
            'blacklist_async_jei_plugins = "jepb:jei_plugin"\n',
            "blacklist_async_jei_plugins = [123]\n",
            'blacklist_async_jei_plugins = [""]\n',
            'blacklist_async_jei_plugins = ["   "]\n',
        ]
        for content in bad_values:
            common_path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_val:
                self.sync.validate_configs()
            self.assertIn(
                "blacklist_async_jei_plugins must be a list of non-empty strings",
                str(ctx_val.exception),
            )

        common_path.write_text(
            'blacklist_async_jei_plugins = ["jepb:jei_plugin"]\nextra_key = true\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_unknown:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extra_key']", str(ctx_unknown.exception))

    def test_mixins_properties_invariants_validated(self) -> None:
        """Invalid lines, non-boolean mixin.* flags, invalid stability_level, and unknown keys must fail."""
        mixins_path = self.configs_dir / "modernfix-mixins.properties"
        base = mixins_path.read_text(encoding="utf-8")

        mixins_path.write_text(base + "\nnot_an_assignment\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_line:
            self.sync.validate_configs()
        self.assertIn("non-comment line must be a 'key=value' assignment", str(ctx_line.exception))

        mixins_path.write_text(base + "\nmixin.perf.dynamic_resources=yes\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("mixin.perf.dynamic_resources must be 'true' or 'false'", str(ctx_bool.exception))

        mixins_path.write_text(base + "\nstability_level=NIGHTLY\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_stab:
            self.sync.validate_configs()
        self.assertIn(
            "stability_level must be one of ['ALPHA', 'BETA', 'GA']",
            str(ctx_stab.exception),
        )

        mixins_path.write_text(base + "\nunknown_setting=123\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_unknown:
            self.sync.validate_configs()
        self.assertIn("unexpected property key 'unknown_setting'", str(ctx_unknown.exception))

    def test_secret_guards_rejected(self) -> None:
        """Secret key names and secret patterns in TOML or properties must fail validation."""
        common_path = self.configs_dir / "modernfix-common.toml"
        common_path.write_text(
            'blacklist_async_jei_plugins = ["https://discord.com/api/webhooks/123456789/abcdef-token"]\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_webhook:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_webhook.exception))

        common_path.write_text(
            'blacklist_async_jei_plugins = ["jepb:jei_plugin"]\npassword = "supersecret"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_pw:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'password'", str(ctx_pw.exception))

        common_path.write_text('blacklist_async_jei_plugins = ["jepb:jei_plugin"]\n', encoding="utf-8")
        mixins_path = self.configs_dir / "modernfix-mixins.properties"
        mixins_path.write_text(
            mixins_path.read_text(encoding="utf-8")
            + "\n! -----BEGIN RSA PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_key:
            self.sync.validate_configs()
        self.assertIn("Private Key", str(ctx_key.exception))


if __name__ == "__main__":
    unittest.main()
