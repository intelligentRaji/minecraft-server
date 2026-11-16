#!/usr/bin/env python3
"""Unit and integration tests for mods/luckperms/sync.py."""

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
    spec = importlib.util.spec_from_file_location("luckperms_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LuckPermsSyncTest(unittest.TestCase):
    """Verify LuckPerms config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "luckperms" / "configs"
        self.target_dir = self.root / "data" / "config" / "luckperms"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.target_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.TARGET_DIR = self.target_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/luckperms/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"contexts.json", "luckperms.conf"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places all static files; second run is idempotent; updates preserve target file mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        for rel in self.sync.STATIC_FILES:
            self.assertTrue((self.target_dir / rel).is_file(), f"Missing static file {rel}")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        # Restrict permissions on target contexts.json and update source to verify mode preservation
        ctx_target = self.target_dir / "contexts.json"
        os.chmod(ctx_target, 0o600)

        ctx_src = self.configs_dir / "contexts.json"
        ctx_data = json.loads(ctx_src.read_text(encoding="utf-8"))
        ctx_data["static-contexts"] = {"world": "overworld"}
        ctx_src.write_text(json.dumps(ctx_data, indent=2), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(ctx_target.stat().st_mode & 0o777, 0o600)
        placed_ctx = json.loads(ctx_target.read_text(encoding="utf-8"))
        self.assertEqual(placed_ctx["static-contexts"], {"world": "overworld"})

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without writing to TARGET_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.target_dir.iterdir()), [])

    def test_forbidden_files_and_dirs_rejected(self) -> None:
        """Forbidden databases, JARs, and runtime directories must fail pre-flight validation."""
        (self.configs_dir / "luckperms-h2-v2.mv.db").write_bytes(b"h2-db")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: luckperms-h2-v2.mv.db", str(ctx.exception))
        (self.configs_dir / "luckperms-h2-v2.mv.db").unlink()

        (self.configs_dir / "libs").mkdir()
        with self.assertRaises(ValueError) as ctx_libs:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: libs", str(ctx_libs.exception))
        (self.configs_dir / "libs").rmdir()

        (self.configs_dir / "extra.jar").write_bytes(b"jar")
        with self.assertRaises(ValueError) as ctx_jar:
            self.sync.validate_configs()
        self.assertIn("Forbidden binary/database file present in configs/: extra.jar", str(ctx_jar.exception))
        (self.configs_dir / "extra.jar").unlink()

    def test_missing_and_unexpected_files_rejected(self) -> None:
        """Missing expected files or unexpected files in configs/ must fail validation."""
        (self.configs_dir / "unexpected.txt").write_text("oops", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Unexpected files in configs/: unexpected.txt", str(ctx.exception))
        (self.configs_dir / "unexpected.txt").unlink()

        (self.configs_dir / "contexts.json").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("Missing expected config files in configs/: contexts.json", str(ctx_missing.exception))

    def test_contexts_json_structure_and_secrets_validated(self) -> None:
        """contexts.json must be a JSON object with static-contexts & default-contexts dicts and no secrets."""
        ctx_path = self.configs_dir / "contexts.json"
        ctx_path.write_text(json.dumps({"static-contexts": {}}), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("'default-contexts' must be a JSON object", str(ctx.exception))

        ctx_path.write_text(
            json.dumps({
                "static-contexts": {"webhook": "https://discord.com/api/webhooks/123456789/abcdef-token"},
                "default-contexts": {},
            }),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_secret:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_secret.exception))

    def test_invariant_storage_method_must_be_h2(self) -> None:
        """Changing storage-method away from h2 must fail with H2 database rationale."""
        conf_path = self.configs_dir / "luckperms.conf"
        text = conf_path.read_text(encoding="utf-8")
        conf_path.write_text(text.replace('storage-method = "h2"', 'storage-method = "yaml"'), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn('storage-method must be "h2"', str(ctx.exception))
        self.assertIn("luckperms-h2-v2.mv.db", str(ctx.exception))

    def test_invariant_meta_formatting_must_be_highest(self) -> None:
        """Changing meta-formatting prefix or suffix format must fail with staff prefix & clan suffix rationale."""
        conf_path = self.configs_dir / "luckperms.conf"
        orig = conf_path.read_text(encoding="utf-8")

        # Mutate first occurrence (prefix)
        conf_path.write_text(orig.replace('"highest"', '"lowest"', 1), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn('meta-formatting.prefix.format must be ["highest"]', str(ctx.exception))
        self.assertIn("FCM Clans priority-100 suffixes", str(ctx.exception))

        # Mutate second occurrence (suffix)
        parts = orig.rsplit('"highest"', 1)
        conf_path.write_text('"lowest"'.join(parts), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_suffix:
            self.sync.validate_configs()
        self.assertIn('meta-formatting.suffix.format must be ["highest"]', str(ctx_suffix.exception))

    def test_luckperms_conf_secret_guards(self) -> None:
        """Non-empty database/redis passwords, mongo URIs, non-default rabbitmq, or private keys must fail."""
        conf_path = self.configs_dir / "luckperms.conf"
        orig = conf_path.read_text(encoding="utf-8")

        cases = [
            ('  password = ""', '  password = "supersecret"', "data.password"),
            ('  mongodb-connection-uri = ""', '  mongodb-connection-uri = "mongodb://user:pass@host/db"', "data.mongodb-connection-uri"),
            ('  password = "guest"', '  password = "custom-rabbit-pass"', "rabbitmq.password"),
            ('  enabled = false\n  address = "localhost"\n  vhost = "/"', '  enabled = true\n  address = "localhost"\n  vhost = "/"', "rabbitmq.password"),
        ]
        for old, new, expected_msg in cases:
            self.assertIn(old, orig)
            conf_path.write_text(orig.replace(old, new, 1), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {expected_msg}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

        # Redis password (second occurrence of `  password = ""` after data.password)
        parts = orig.rsplit('  password = ""', 1)
        conf_path.write_text('  password = "redis-secret"'.join(parts), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_redis:
            self.sync.validate_configs()
        self.assertIn("redis.password", str(ctx_redis.exception))

        # Private key anywhere in luckperms.conf
        conf_path.write_text(orig + "\n# -----BEGIN RSA PRIVATE KEY-----\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_pk:
            self.sync.validate_configs()
        self.assertIn("Private Key", str(ctx_pk.exception))


if __name__ == "__main__":
    unittest.main()
