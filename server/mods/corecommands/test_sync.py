#!/usr/bin/env python3
"""Unit and integration tests for mods/corecommands/sync.py."""

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

RUNTIME_STATE_FILES: tuple[str, ...] = (
    "afkstatus.json",
    "deathlocation.json",
    "homes.json",
    "lastlocation.json",
    "lastmessagerecipient.json",
    "logoutposition.json",
    "playerjoinstatus.json",
    "spawn.json",
    "tparequests.json",
    "warps.json",
)


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("corecommands_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CoreCommandsSyncTest(unittest.TestCase):
    """Verify CoreCommands config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "corecommands" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/corecommands/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config.json", "rules.json"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places static files, repeats cleanly, preserves mode, and leaves runtime files untouched."""
        cc_dir = self.data_dir / "config" / "corecommands"
        cc_dir.mkdir(parents=True, exist_ok=True)
        homes_file = cc_dir / "homes.json"
        warps_file = cc_dir / "warps.json"
        spawn_file = cc_dir / "spawn.json"
        homes_file.write_text('{"player-uuid": {"home": {"x": 10}}}', encoding="utf-8")
        warps_file.write_text('{"hub": {"x": 0, "y": 64, "z": 0}}', encoding="utf-8")
        spawn_file.write_text('{"x": 0, "y": 70, "z": 0}', encoding="utf-8")

        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        config_target = cc_dir / "config.json"
        rules_target = cc_dir / "rules.json"
        self.assertTrue(config_target.is_file(), "Missing config.json in data/config/corecommands/")
        self.assertTrue(rules_target.is_file(), "Missing rules.json in data/config/corecommands/")
        self.assertEqual(
            homes_file.read_text(encoding="utf-8"),
            '{"player-uuid": {"home": {"x": 10}}}',
        )
        self.assertEqual(
            warps_file.read_text(encoding="utf-8"),
            '{"hub": {"x": 0, "y": 64, "z": 0}}',
        )
        self.assertEqual(
            spawn_file.read_text(encoding="utf-8"),
            '{"x": 0, "y": 70, "z": 0}',
        )

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(config_target, 0o600)
        config_src = self.configs_dir / "config.json"
        updated = json.loads(config_src.read_text(encoding="utf-8"))
        updated["backCommandEnabled"] = False
        config_src.write_text(json.dumps(updated), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(config_target.stat().st_mode & 0o777, 0o600)
        self.assertIs(json.loads(config_target.read_text(encoding="utf-8"))["backCommandEnabled"], False)

    def test_dry_run_does_not_write_or_touch_runtime_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        cc_dir = self.data_dir / "config" / "corecommands"
        cc_dir.mkdir(parents=True, exist_ok=True)
        pre_existing = {
            "homes.json": '{"uuid": {}}',
            "warps.json": '{"spawn": {}}',
            "spawn.json": '{"x": 1}',
        }
        for name, content in pre_existing.items():
            (cc_dir / name).write_text(content, encoding="utf-8")

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertFalse((cc_dir / "config.json").exists())
        self.assertFalse((cc_dir / "rules.json").exists())
        for name, content in pre_existing.items():
            self.assertEqual((cc_dir / name).read_text(encoding="utf-8"), content)

    def test_forbidden_runtime_files_dirs_and_suffixes_rejected(self) -> None:
        """All 10 runtime state filenames, forbidden directories, and archive/runtime suffixes must fail validation."""
        for runtime_name in RUNTIME_STATE_FILES:
            fpath = self.configs_dir / runtime_name
            fpath.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden file/directory present in configs/: {runtime_name}", str(ctx.exception))
            fpath.unlink()

        for forbidden_dir in ("logs", "world"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx_dir:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden file/directory present in configs/: {forbidden_dir}", str(ctx_dir.exception))
            dpath.rmdir()

        for suffix_file in ("backup-2026.zip", "state.db", "mod.jar", "run.lock", "latest.log"):
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

        (self.configs_dir / "rules.json").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("Missing expected config files in configs/: rules.json", str(ctx_missing.exception))

    def test_config_json_invariants_validated(self) -> None:
        """Invalid root type, unexpected keys, non-bool backCommandEnabled, or non-str comment_backCommand must fail."""
        config_path = self.configs_dir / "config.json"
        orig = json.loads(config_path.read_text(encoding="utf-8"))

        config_path.write_text('["not", "an", "object"]', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_root:
            self.sync.validate_configs()
        self.assertIn("root JSON value must be an object", str(ctx_root.exception))

        mutated = dict(orig)
        mutated["homes"] = {"uuid": {}}
        config_path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['homes']", str(ctx_key.exception))

        for bad_bool in ("true", 1, 0, None):
            mutated = dict(orig)
            mutated["backCommandEnabled"] = bad_bool
            config_path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_bool:
                self.sync.validate_configs()
            self.assertIn("backCommandEnabled must be a boolean", str(ctx_bool.exception))

        for bad_comment in (123, True, ["a"], None):
            mutated = dict(orig)
            mutated["comment_backCommand"] = bad_comment
            config_path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_comment:
                self.sync.validate_configs()
            self.assertIn("comment_backCommand must be a string", str(ctx_comment.exception))

    def test_rules_json_invariants_validated(self) -> None:
        """Invalid root type, empty string, or non-string items in rules.json must fail with explanatory rationale."""
        rules_path = self.configs_dir / "rules.json"

        rules_path.write_text('{"rules": ["1. Be nice"]}', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_root:
            self.sync.validate_configs()
        self.assertIn("root JSON value must be a list of rule strings", str(ctx_root.exception))

        for bad_rules in ([""], ["1. Valid", "   "], ["1. Valid", 42], [None]):
            rules_path.write_text(json.dumps(bad_rules), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx_item:
                self.sync.validate_configs()
            self.assertIn("must be a non-empty string", str(ctx_item.exception))

    def test_secret_guards_rejected(self) -> None:
        """Secret key names and secret patterns in config.json or rules.json must fail validation."""
        config_path = self.configs_dir / "config.json"
        orig = json.loads(config_path.read_text(encoding="utf-8"))

        mutated = dict(orig)
        mutated["webhookUrl"] = "https://discord.com/api/webhooks/123456789/abcdef-token"
        config_path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_webhook:
            self.sync.validate_configs()
        msg = str(ctx_webhook.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'webhookUrl'", msg)

        config_path.write_text(json.dumps(orig), encoding="utf-8")
        rules_path = self.configs_dir / "rules.json"
        rules_path.write_text(
            json.dumps(["1. Secret webhook https://discord.com/api/webhooks/123456789/abcdef-token"]),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_rules_secret:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_rules_secret.exception))


if __name__ == "__main__":
    unittest.main()
