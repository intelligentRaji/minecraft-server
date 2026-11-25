#!/usr/bin/env python3
"""Unit and integration tests for mods/simplebackups/sync.py."""

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
    spec = importlib.util.spec_from_file_location("simplebackups_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class SimpleBackupsSyncTest(unittest.TestCase):
    """Verify Simple Backups config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "simplebackups" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/simplebackups/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"simplebackups-common.toml", "simplebackups-server.toml"},
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places both TOML files; second run is idempotent; updates preserve target file mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "simplebackups-common.toml"
        server_target = self.data_dir / "world" / "serverconfig" / "simplebackups-server.toml"
        self.assertTrue(common_target.is_file(), "Missing simplebackups-common.toml in config/")
        self.assertTrue(server_target.is_file(), "Missing simplebackups-server.toml in world/serverconfig/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(common_target, 0o600)
        common_src = self.configs_dir / "simplebackups-common.toml"
        common_src.write_text(
            common_src.read_text(encoding="utf-8").replace("timer = 120", "timer = 60"),
            encoding="utf-8",
        )

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(common_target.stat().st_mode & 0o777, 0o600)
        self.assertIn("timer = 60", common_target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_and_dirs_rejected(self) -> None:
        """Forbidden backup archives, directories, and runtime files must fail pre-flight validation."""
        for forbidden_dir in ("simplebackups", "logs", "world"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden file/directory present in configs/: {forbidden_dir}", str(ctx.exception))
            dpath.rmdir()

        for suffix_file in ("backup-2026.zip", "backup.tar.gz", "state.db", "mod.jar", "run.lock"):
            fpath = self.configs_dir / suffix_file
            fpath.write_bytes(b"artifact")
            with self.assertRaises(ValueError) as ctx_file:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden archive/runtime file present in configs/: {suffix_file}", str(ctx_file.exception))
            fpath.unlink()

    def test_missing_and_unexpected_files_rejected(self) -> None:
        """Missing expected files or unexpected files in configs/ must fail validation."""
        unexpected = self.configs_dir / "unexpected.toml"
        unexpected.write_text("foo = 1\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Unexpected files in configs/: unexpected.toml", str(ctx.exception))
        unexpected.unlink()

        (self.configs_dir / "simplebackups-server.toml").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: simplebackups-server.toml",
            str(ctx_missing.exception),
        )

    def test_invariant_output_path_must_be_simplebackups(self) -> None:
        """outputPath traversal, absolute paths, or non-default paths must fail with data/ isolation rationale."""
        common_path = self.configs_dir / "simplebackups-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        for bad_path in ("../escape", "/tmp/backups", "custom_backups"):
            common_path.write_text(
                orig.replace('outputPath = "simplebackups"', f'outputPath = "{bad_path}"'),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            msg = str(ctx.exception)
            self.assertIn('outputPath must be "simplebackups"', msg)
            self.assertIn("data/simplebackups/", msg)

    def test_invariant_backup_type_validated(self) -> None:
        """Invalid backupType values must fail validation."""
        common_path = self.configs_dir / "simplebackups-common.toml"
        orig = common_path.read_text(encoding="utf-8")
        common_path.write_text(
            orig.replace('backupType = "FULL_BACKUPS"', 'backupType = "INCREMENTAL"'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("backupType must be one of", str(ctx.exception))

    def test_invariant_integer_ranges_validated(self) -> None:
        """Out-of-range or boolean values for integer settings must fail with explanatory rationale."""
        common_path = self.configs_dir / "simplebackups-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        cases = [
            ("backupsToKeep = 10", "backupsToKeep = 0", "backupsToKeep must be an integer in 1..32767"),
            ("backupsToKeep = 10", "backupsToKeep = 32768", "backupsToKeep must be an integer in 1..32767"),
            ("backupsToKeep = 10", "backupsToKeep = true", "backupsToKeep must be an integer in 1..32767"),
            ("timer = 120", "timer = 0", "timer must be an integer in 1..32767"),
            ("timer = 120", "timer = 32768", "timer must be an integer in 1..32767"),
            ("fullBackupTimer = 525960", "fullBackupTimer = 0", "fullBackupTimer must be an integer in 1..5259600"),
            (
                "fullBackupTimer = 525960",
                "fullBackupTimer = 5259601",
                "fullBackupTimer must be an integer in 1..5259600",
            ),
            ("compressionLevel = -1", "compressionLevel = -2", "compressionLevel must be an integer in -1..9"),
            ("compressionLevel = -1", "compressionLevel = 10", "compressionLevel must be an integer in -1..9"),
        ]
        for old, new, expected_msg in cases:
            self.assertIn(old, orig)
            common_path.write_text(orig.replace(old, new, 1), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {new}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

    def test_invariant_max_disk_size_validated(self) -> None:
        """Malformed maxDiskSize strings must fail validation."""
        common_path = self.configs_dir / "simplebackups-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        for bad_size in ("25GB", "25 PB", "abc GB"):
            common_path.write_text(
                orig.replace('maxDiskSize = "25 GB"', f'maxDiskSize = "{bad_size}"'),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn("maxDiskSize must match", str(ctx.exception))

    def test_invariant_server_toml_validated(self) -> None:
        """commandsCheatsDisabled = true or non-bool messagesForEveryone must fail with multiplayer rationale."""
        server_path = self.configs_dir / "simplebackups-server.toml"
        orig = server_path.read_text(encoding="utf-8")

        server_path.write_text(
            orig.replace("commandsCheatsDisabled = false", "commandsCheatsDisabled = true"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("commandsCheatsDisabled must be false", msg)
        self.assertIn("non-OP players", msg)

        server_path.write_text(
            orig.replace("messagesForEveryone = true", 'messagesForEveryone = "yes"'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_msg:
            self.sync.validate_configs()
        self.assertIn("messagesForEveryone must be a boolean", str(ctx_msg.exception))

    def test_secret_guards_rejected(self) -> None:
        """Secret patterns and secret key names in TOML files must fail validation."""
        common_path = self.configs_dir / "simplebackups-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        common_path.write_text(
            orig + '\n[secrets]\nwebhookUrl = "https://discord.com/api/webhooks/123456789/abcdef-token"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_webhook:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_webhook.exception))
        self.assertIn("non-empty secret key 'secrets.webhookUrl'", str(ctx_webhook.exception))

        common_path.write_text(
            orig + '\n[auth]\npassword = "supersecret"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_pw:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'auth.password'", str(ctx_pw.exception))


if __name__ == "__main__":
    unittest.main()
