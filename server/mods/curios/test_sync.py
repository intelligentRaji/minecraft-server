#!/usr/bin/env python3
"""Unit and integration tests for mods/curios/sync.py."""

from __future__ import annotations

import copy
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

VALID_COMMON: dict[str, object] = {
    "slots": [],
}

VALID_SERVER: dict[str, object] = {
    "keepCurios": "DEFAULT",
    "menu": {
        "enableLegacyMenu": False,
        "experimental": {
            "minimumColumns": 1,
            "maxSlotsPerPage": 48,
        },
    },
}


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        items = ", ".join(_format_value(v) for v in value)
        return f"[{items}]"
    return repr(value)


def format_toml(data: dict[str, object]) -> str:
    """Serialize a nested dict of Curios config tables into TOML."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, object]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_format_value(value)}")
    for section, values in tables:
        lines.append(f"\n[{section}]")
        subtables: list[tuple[str, dict[str, object]]] = []
        for sub_key, sub_val in values.items():
            if isinstance(sub_val, dict):
                subtables.append((f"{section}.{sub_key}", sub_val))
            else:
                lines.append(f"{sub_key} = {_format_value(sub_val)}")
        for sub_name, sub_values in subtables:
            lines.append(f"\n[{sub_name}]")
            for k, v in sub_values.items():
                lines.append(f"{k} = {_format_value(v)}")
    lines.append("")
    return "\n".join(lines)


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("curios_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CuriosSyncTest(unittest.TestCase):
    """Verify Curios config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "curios" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _common_path(self) -> Path:
        return self.configs_dir / "config" / "curios-common.toml"

    def _server_path(self) -> Path:
        return self.configs_dir / "world" / "serverconfig" / "curios-server.toml"

    def _write_common(self, cfg: dict[str, object]) -> None:
        self._common_path().write_text(format_toml(cfg), encoding="utf-8")

    def _write_server(self, cfg: dict[str, object]) -> None:
        self._server_path().write_text(format_toml(cfg), encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/curios/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"config/curios-common.toml", "world/serverconfig/curios-server.toml"},
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places static files; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "curios-common.toml"
        server_target = self.data_dir / "world" / "serverconfig" / "curios-server.toml"
        self.assertTrue(common_target.is_file(), "Missing curios-common.toml in data/config/")
        self.assertTrue(server_target.is_file(), "Missing curios-server.toml in data/world/serverconfig/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(server_target, 0o600)

        updated_server = copy.deepcopy(VALID_SERVER)
        updated_server["keepCurios"] = "ON"
        self._write_server(updated_server)

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(server_target.stat().st_mode & 0o777, 0o600)
        self.assertIn('keepCurios = "ON"', server_target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_dirs_and_symlinks_rejected(self) -> None:
        """Forbidden runtime directories (including world/playerdata), suffixes, and symlinks fail."""
        for forbidden_rel in ("logs", "mods", "world/playerdata"):
            dpath = self.configs_dir / forbidden_rel
            dpath.mkdir(parents=True)
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden file/directory present in configs/: {forbidden_rel}",
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
            "Missing expected config files in configs/: config/curios-common.toml",
            str(ctx_missing.exception),
        )

    def test_common_config_invariants_enforced(self) -> None:
        """Invalid TOML, key mismatches, and non-list/non-string slots must raise ValueError."""
        self._common_path().write_text("slots = [broken\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_toml:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx_toml.exception))

        self._write_common({})
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['slots']", str(ctx_missing.exception))

        self._write_common({"slots": [], "extraKey": True})
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['extraKey']", str(ctx_extra.exception))

        self._write_common({"slots": "ring"})
        with self.assertRaises(ValueError) as ctx_not_list:
            self.sync.validate_configs()
        self.assertIn("'slots' must be a list of strings", str(ctx_not_list.exception))

        self._write_common({"slots": ["id=ring;size=2", 42]})
        with self.assertRaises(ValueError) as ctx_bad_elem:
            self.sync.validate_configs()
        self.assertIn("'slots' must be a list of strings", str(ctx_bad_elem.exception))

        self._write_common({"slots": ["id=ring;size=2"]})
        self.sync.validate_configs()

    def test_server_config_invariants_enforced(self) -> None:
        """Schema, enum, bool, and strict integer range invariants must raise ValueError."""
        missing_root = copy.deepcopy(VALID_SERVER)
        del missing_root["keepCurios"]
        self._write_server(missing_root)
        with self.assertRaises(ValueError) as ctx_mr:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['keepCurios']", str(ctx_mr.exception))

        extra_root = copy.deepcopy(VALID_SERVER)
        extra_root["unexpected"] = 1
        self._write_server(extra_root)
        with self.assertRaises(ValueError) as ctx_er:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['unexpected']", str(ctx_er.exception))

        for bad_keep in ("ALWAYS", 123, True):
            bad_enum = copy.deepcopy(VALID_SERVER)
            bad_enum["keepCurios"] = bad_keep
            self._write_server(bad_enum)
            with self.assertRaises(ValueError) as ctx_enum:
                self.sync.validate_configs()
            self.assertIn("'keepCurios' must be one of", str(ctx_enum.exception))

        bad_bool = copy.deepcopy(VALID_SERVER)
        menu = bad_bool["menu"]
        assert isinstance(menu, dict)
        menu["enableLegacyMenu"] = "false"
        self._write_server(bad_bool)
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("'menu.enableLegacyMenu' must be a boolean", str(ctx_bool.exception))

        for key, bad_vals in (
            ("minimumColumns", (True, 0, 9)),
            ("maxSlotsPerPage", (False, 0, 49)),
        ):
            for bad_val in bad_vals:
                bad_range = copy.deepcopy(VALID_SERVER)
                exp = bad_range["menu"]["experimental"]  # type: ignore[index]
                exp[key] = bad_val
                self._write_server(bad_range)
                with self.assertRaises(ValueError) as ctx_range:
                    self.sync.validate_configs()
                self.assertIn(f"[menu.experimental].{key} invariant violation", str(ctx_range.exception))

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        with_secret = copy.deepcopy(VALID_SERVER)
        with_secret["secret"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        self._write_server(with_secret)
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("Discord Webhook URL", msg)
        self.assertIn("non-empty secret key 'secret'", msg)


if __name__ == "__main__":
    unittest.main()
