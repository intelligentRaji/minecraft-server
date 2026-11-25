#!/usr/bin/env python3
"""Unit and integration tests for mods/chunky/sync.py."""

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
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("chunky_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class ChunkySyncTest(unittest.TestCase):
    """Verify Chunky config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "chunky" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/chunky/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config.json"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places config.json, repeats cleanly, and preserves mode and tasks/."""
        tasks_dir = self.data_dir / "config" / "chunky" / "tasks" / "minecraft"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        live_task = tasks_dir / "overworld.json"
        live_task.write_text('{"world": "minecraft:overworld", "progress": 42}', encoding="utf-8")

        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        config_target = self.data_dir / "config" / "chunky" / "config.json"
        self.assertTrue(config_target.is_file(), "Missing config.json in data/config/chunky/")
        self.assertEqual(
            live_task.read_text(encoding="utf-8"),
            '{"world": "minecraft:overworld", "progress": 42}',
        )

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(config_target, 0o600)
        config_src = self.configs_dir / "config.json"
        updated = json.loads(config_src.read_text(encoding="utf-8"))
        updated["updateInterval"] = 5
        config_src.write_text(json.dumps(updated, indent=2), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(config_target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(config_target.read_text(encoding="utf-8"))["updateInterval"], 5)

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_and_dirs_rejected(self) -> None:
        """Forbidden runtime dirs (tasks, logs, world) and archive/runtime suffixes fail validation."""
        for forbidden_dir in ("tasks", "logs", "world"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden file/directory present in configs/: {forbidden_dir}", str(ctx.exception))
            dpath.rmdir()

        for suffix_file in ("backup-2026.zip", "tasks.tar.gz", "state.db", "mod.jar", "run.lock"):
            fpath = self.configs_dir / suffix_file
            fpath.write_bytes(b"artifact")
            with self.assertRaises(ValueError) as ctx_file:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden archive/runtime file present in configs/: {suffix_file}", str(ctx_file.exception))
            fpath.unlink()

    def test_missing_and_unexpected_files_rejected(self) -> None:
        """Missing expected files or unexpected files in configs/ must fail validation."""
        unexpected = self.configs_dir / "unexpected.json"
        unexpected.write_text('{"foo": 1}\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Unexpected files in configs/: unexpected.json", str(ctx.exception))
        unexpected.unlink()

        (self.configs_dir / "config.json").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("Missing expected config files in configs/: config.json", str(ctx_missing.exception))

    def test_invariant_version_and_update_interval_validated(self) -> None:
        """Out-of-range or boolean values for version and updateInterval must fail with explanatory rationale."""
        config_path = self.configs_dir / "config.json"
        orig = json.loads(config_path.read_text(encoding="utf-8"))

        cases = [
            ("version", 0, "version must be an integer >= 1"),
            ("version", -1, "version must be an integer >= 1"),
            ("version", True, "version must be an integer >= 1"),
            ("version", "2", "version must be an integer >= 1"),
            ("updateInterval", 0, "updateInterval must be an integer >= 1"),
            ("updateInterval", -5, "updateInterval must be an integer >= 1"),
            ("updateInterval", False, "updateInterval must be an integer >= 1"),
            ("updateInterval", "1", "updateInterval must be an integer >= 1"),
        ]
        for key, bad_val, expected_msg in cases:
            mutated = dict(orig)
            mutated[key] = bad_val
            config_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {key}={bad_val!r}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

    def test_invariant_language_and_booleans_validated(self) -> None:
        """Empty/non-string language and non-boolean flags must fail with explanatory rationale."""
        config_path = self.configs_dir / "config.json"
        orig = json.loads(config_path.read_text(encoding="utf-8"))

        for bad_lang in ("", "   ", 123, None):
            mutated = dict(orig)
            mutated["language"] = bad_lang
            config_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn("language must be a non-empty string", str(ctx.exception))

        for bool_key in ("continueOnRestart", "forceLoadExistingChunks", "silent"):
            for bad_bool in ("false", 0, 1, None):
                mutated = dict(orig)
                mutated[bool_key] = bad_bool
                config_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    self.sync.validate_configs()
                self.assertIn(f"{bool_key} must be a boolean", str(ctx.exception))

    def test_unexpected_keys_and_secret_guards_rejected(self) -> None:
        """Unexpected keys, secret key names, and secret patterns in config.json must fail validation."""
        config_path = self.configs_dir / "config.json"
        orig = json.loads(config_path.read_text(encoding="utf-8"))

        mutated = dict(orig)
        mutated["tasks"] = {"overworld": {"radius": 5000}}
        config_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_unknown:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['tasks']", str(ctx_unknown.exception))

        mutated = dict(orig)
        mutated["webhookUrl"] = "https://discord.com/api/webhooks/123456789/abcdef-token"
        config_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_webhook:
            self.sync.validate_configs()
        msg = str(ctx_webhook.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'webhookUrl'", msg)

        mutated = dict(orig)
        mutated["password"] = "supersecret"
        config_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_pw:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'password'", str(ctx_pw.exception))


if __name__ == "__main__":
    unittest.main()
