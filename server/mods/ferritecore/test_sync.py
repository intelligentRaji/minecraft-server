#!/usr/bin/env python3
"""Unit and integration tests for mods/ferritecore/sync.py."""

from __future__ import annotations

import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from collections.abc import Mapping
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

VALID_MIXIN_CONFIG = {
    "compactFastMap": False,
    "useSmallThreadingDetector": False,
    "cacheMultipartPredicates": True,
    "multipartDeduplication": True,
    "blockstateCacheDeduplication": True,
    "modelResourceLocations": True,
    "modelSides": True,
    "replaceNeighborLookup": True,
    "populateNeighborTable": False,
    "replacePropertyMap": True,
    "bakedQuadDeduplication": True,
}


def format_toml(values: Mapping[str, object]) -> str:
    lines: list[str] = []
    for key, value in values.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value!r}")
    return "\n".join(lines) + "\n"


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("ferritecore_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class FerriteCoreSyncTest(unittest.TestCase):
    """Verify FerriteCore config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "ferritecore" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _mixin_path(self) -> Path:
        return self.configs_dir / "config" / "ferritecore-mixin.toml"

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/ferritecore/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/ferritecore-mixin.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places the static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "ferritecore-mixin.toml"
        self.assertTrue(target.is_file(), "Missing ferritecore-mixin.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)

        updated = dict(VALID_MIXIN_CONFIG)
        updated["compactFastMap"] = True
        self._mixin_path().write_text(format_toml(updated), encoding="utf-8")

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("compactFastMap = true", target.read_text(encoding="utf-8"))

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
        link_path.symlink_to(self._mixin_path())
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

        self._mixin_path().unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: config/ferritecore-mixin.toml",
            str(ctx_missing.exception),
        )

    def test_schema_types_missing_and_unexpected_keys_rejected(self) -> None:
        """Invalid TOML, wrong types, missing keys, and unexpected keys must raise ValueError."""
        mixin_path = self._mixin_path()

        mixin_path.write_text("compactFastMap = [not valid\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        wrong_type: dict[str, object] = dict(VALID_MIXIN_CONFIG)
        wrong_type["compactFastMap"] = "true"
        mixin_path.write_text(format_toml(wrong_type), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_type:
            self.sync.validate_configs()
        self.assertIn("'compactFastMap' must be a boolean", str(ctx_type.exception))

        missing_key = dict(VALID_MIXIN_CONFIG)
        del missing_key["bakedQuadDeduplication"]
        mixin_path.write_text(format_toml(missing_key), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['bakedQuadDeduplication']", str(ctx_missing.exception))

        extra_key = dict(VALID_MIXIN_CONFIG)
        extra_key["extraToggle"] = True
        mixin_path.write_text(format_toml(extra_key), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extraToggle']", str(ctx_extra.exception))

    def test_dependency_invariants_enforced(self) -> None:
        """Both FerriteCore mixin dependency invariants must raise ValueError with rationale."""
        mixin_path = self._mixin_path()

        bad_multipart = dict(VALID_MIXIN_CONFIG)
        bad_multipart["multipartDeduplication"] = True
        bad_multipart["cacheMultipartPredicates"] = False
        mixin_path.write_text(format_toml(bad_multipart), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_multipart:
            self.sync.validate_configs()
        self.assertIn(
            "multipartDeduplication=true requires cacheMultipartPredicates=true",
            str(ctx_multipart.exception),
        )

        bad_property_map = dict(VALID_MIXIN_CONFIG)
        bad_property_map["replacePropertyMap"] = True
        bad_property_map["replaceNeighborLookup"] = False
        mixin_path.write_text(format_toml(bad_property_map), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_prop:
            self.sync.validate_configs()
        self.assertIn(
            "replacePropertyMap=true requires replaceNeighborLookup=true",
            str(ctx_prop.exception),
        )

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        mixin_path = self._mixin_path()

        with_webhook: dict[str, object] = dict(VALID_MIXIN_CONFIG)
        with_webhook["secret"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        mixin_path.write_text(format_toml(with_webhook), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'secret'", msg)


if __name__ == "__main__":
    unittest.main()
