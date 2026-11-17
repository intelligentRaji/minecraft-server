#!/usr/bin/env python3
"""Unit and integration tests for mods/attributefix/sync.py."""

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
    spec = importlib.util.spec_from_file_location("attributefix_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AttributeFixSyncTest(unittest.TestCase):
    """Verify AttributeFix config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "attributefix" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/attributefix/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"attributefix.json"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places static file; second run is idempotent; updates preserve file mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "attributefix.json"
        self.assertTrue(target.is_file(), "Missing attributefix.json in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)
        src = self.configs_dir / "attributefix.json"
        updated = json.loads(src.read_text(encoding="utf-8"))
        updated["attributes"]["minecraft:generic.max_health"]["max"]["value"] = 2048
        src.write_text(json.dumps(updated, indent=2), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            json.loads(target.read_text(encoding="utf-8"))["attributes"][
                "minecraft:generic.max_health"
            ]["max"]["value"],
            2048,
        )

    def test_dry_run_leaves_data_dir_untouched(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf.getvalue())
        self.assertFalse((self.data_dir / "config" / "attributefix.json").exists())

    def test_forbidden_dirs_suffixes_and_inventory_rejected(self) -> None:
        """Forbidden directories, archive/runtime suffixes, and missing/unexpected files must fail."""
        for forbidden_dir in ("logs", "world"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx_dir:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden file/directory present in configs/: {forbidden_dir}",
                str(ctx_dir.exception),
            )
            dpath.rmdir()

        for suffix_file in ("backup.zip", "state.db", "mod.jar", "run.lock", "latest.log"):
            fpath = self.configs_dir / suffix_file
            fpath.write_bytes(b"artifact")
            with self.assertRaises(ValueError) as ctx_file:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden archive/runtime file present in configs/: {suffix_file}",
                str(ctx_file.exception),
            )
            fpath.unlink()

        unexpected = self.configs_dir / "extra.json"
        unexpected.write_text('{"foo": 1}\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_unexpected:
            self.sync.validate_configs()
        self.assertIn("Unexpected files in configs/: extra.json", str(ctx_unexpected.exception))
        unexpected.unlink()

        (self.configs_dir / "attributefix.json").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: attributefix.json",
            str(ctx_missing.exception),
        )

    def test_secret_guard_rejects_secrets(self) -> None:
        """Secret patterns or credential keys embedded in attributefix.json must fail."""
        cfg_path = self.configs_dir / "attributefix.json"
        orig = json.loads(cfg_path.read_text(encoding="utf-8"))
        mutated = dict(orig)
        mutated["api_token"] = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        cfg_path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Pre-flight validation failed", str(ctx.exception))

    def test_schema_and_range_invariants_validated(self) -> None:
        """Schema violations and invalid min > max bounds must raise ValueError with rationale."""
        cfg_path = self.configs_dir / "attributefix.json"
        orig = json.loads(cfg_path.read_text(encoding="utf-8"))

        # 1. Non-dict root
        cfg_path.write_text('["not", "an", "object"]', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_root:
            self.sync.validate_configs()
        self.assertIn("expected a mapping/table", str(ctx_root.exception))

        # 2. Unexpected top-level key
        bad_top = dict(orig)
        bad_top["runtime_players"] = {}
        cfg_path.write_text(json.dumps(bad_top), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_top:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['runtime_players']", str(ctx_top.exception))

        # 3. Non-dict attributes
        cfg_path.write_text(json.dumps({"attributes": []}), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_attrs_type:
            self.sync.validate_configs()
        self.assertIn("'attributes' must be a JSON object", str(ctx_attrs_type.exception))

        # 4. Empty attribute ID key
        cfg_path.write_text(
            json.dumps(
                {
                    "attributes": {
                        "   ": {
                            "enabled": True,
                            "min": {"default": 0, "value": 0},
                            "max": {"default": 1, "value": 1},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_empty_key:
            self.sync.validate_configs()
        self.assertIn("must be a non-empty string resource-location ID", str(ctx_empty_key.exception))

        # 5. Non-bool enabled (strict bool check rejects int 1)
        cfg_path.write_text(
            json.dumps(
                {
                    "attributes": {
                        "minecraft:generic.max_health": {
                            "enabled": 1,
                            "min": {"default": 1, "value": 1},
                            "max": {"default": 1024, "value": 1000000},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("expected a strict boolean", str(ctx_bool.exception))

        # 6. Non-numeric bound field (bool True rejected by is_finite_number)
        cfg_path.write_text(
            json.dumps(
                {
                    "attributes": {
                        "minecraft:generic.max_health": {
                            "enabled": True,
                            "min": {"default": True, "value": 1},
                            "max": {"default": 1024, "value": 1000000},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_num:
            self.sync.validate_configs()
        self.assertIn("expected a finite number", str(ctx_num.exception))

        # 7. min.default > max.default
        cfg_path.write_text(
            json.dumps(
                {
                    "attributes": {
                        "minecraft:generic.max_health": {
                            "enabled": True,
                            "min": {"default": 2000, "value": 1},
                            "max": {"default": 1024, "value": 1000000},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_min_default:
            self.sync.validate_configs()
        self.assertIn("min.default (2000) > max.default (1024)", str(ctx_min_default.exception))
        self.assertIn("breaks AttributeFix's attribute range enforcement", str(ctx_min_default.exception))

        # 8. min.value > max.value
        cfg_path.write_text(
            json.dumps(
                {
                    "attributes": {
                        "minecraft:generic.max_health": {
                            "enabled": True,
                            "min": {"default": 1, "value": 2000000},
                            "max": {"default": 1024, "value": 1000000},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_min_value:
            self.sync.validate_configs()
        self.assertIn("min.value (2000000) > max.value (1000000)", str(ctx_min_value.exception))
        self.assertIn("breaks AttributeFix's attribute range enforcement", str(ctx_min_value.exception))


if __name__ == "__main__":
    unittest.main()
