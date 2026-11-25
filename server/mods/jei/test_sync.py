#!/usr/bin/env python3
"""Unit and integration tests for mods/jei/sync.py."""

from __future__ import annotations

import copy
import importlib.util
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

VALID_PERMISSIONS: dict[str, str] = {
    "enableCheatModeForOp": "true",
    "enableCheatModeForCreative": "true",
    "enableCheatModeForGive": "false",
}


def format_ini(
    permissions: dict[str, str],
    extra_sections: dict[str, dict[str, str]] | None = None,
) -> str:
    """Format a JEI server INI file string."""
    lines: list[str] = [
        "# Name: Server Cheat Permissions",
        "# Description: Choose who can use JEI cheat mode on this server.",
        "[permissions]",
    ]
    for key, value in permissions.items():
        lines.append(f"\t{key} = {value}")
    if extra_sections:
        for section, values in extra_sections.items():
            lines.append(f"\n[{section}]")
            for sub_key, sub_val in values.items():
                lines.append(f"\t{sub_key} = {sub_val}")
    lines.append("")
    return "\n".join(lines)


def load_sync_module() -> SyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("jei_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class JeiSyncTest(unittest.TestCase):
    """Verify JEI config validation, invariants, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "jei" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.sync.CONFIGS_DIR = MOD_DIR / "configs"
        self.sync.DATA_DIR = MOD_DIR.parent.parent / "data"
        self.tmp_dir.cleanup()

    def _default_path(self) -> Path:
        return (
            self.configs_dir
            / "config"
            / "jei"
            / "server"
            / "world"
            / "default"
            / "jei-server.ini"
        )

    def _server_path(self) -> Path:
        return self.configs_dir / "world" / "serverconfig" / "jei" / "jei-server.ini"

    def _write_default(self, text: str) -> None:
        self._default_path().write_text(text, encoding="utf-8")

    def _write_server(self, text: str) -> None:
        self._server_path().write_text(text, encoding="utf-8")

    def test_committed_configs_pass_validation(self) -> None:
        """Committed configs in mods/jei/configs/ must pass validate_configs()."""
        loaded = self.sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {
                "config/jei/server/world/default/jei-server.ini",
                "world/serverconfig/jei/jei-server.ini",
            },
        )

    def test_static_file_placement_and_idempotency(self) -> None:
        """Files must be placed into target DATA_DIR; second run must report 0 changed."""
        loaded = self.sync.validate_configs()
        changed, unchanged = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual(changed, 2)
        self.assertEqual(unchanged, 0)

        target_default = (
            self.data_dir
            / "config"
            / "jei"
            / "server"
            / "world"
            / "default"
            / "jei-server.ini"
        )
        target_server = (
            self.data_dir / "world" / "serverconfig" / "jei" / "jei-server.ini"
        )
        self.assertTrue(target_default.is_file())
        self.assertTrue(target_server.is_file())
        self.assertEqual(
            target_default.read_bytes(),
            loaded["config/jei/server/world/default/jei-server.ini"],
        )
        self.assertEqual(
            target_server.read_bytes(),
            loaded["world/serverconfig/jei/jei-server.ini"],
        )

        # Second run: idempotent
        changed_second, unchanged_second = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual(changed_second, 0)
        self.assertEqual(unchanged_second, 2)

    def test_file_permission_preservation(self) -> None:
        """Existing target file mode (e.g. 0600) must be preserved upon update."""
        target_server = (
            self.data_dir / "world" / "serverconfig" / "jei" / "jei-server.ini"
        )
        target_server.parent.mkdir(parents=True, exist_ok=True)
        target_server.write_text("dummy", encoding="utf-8")
        os.chmod(target_server, 0o600)

        loaded = self.sync.validate_configs()
        self.sync.apply_configs(loaded, dry_run=False)

        current_mode = stat.S_IMODE(target_server.stat().st_mode)
        self.assertEqual(current_mode, 0o600)

    def test_dry_run_leaves_target_untouched(self) -> None:
        """CLI with --dry-run must leave DATA_DIR untouched."""
        exit_code = self.sync.main(["--dry-run"])
        self.assertEqual(exit_code, 0)
        # self.data_dir was created empty in setUp; no files should be inside
        files = list(self.data_dir.rglob("*"))
        self.assertEqual(files, [])

    def test_missing_section_raises_value_error(self) -> None:
        """An INI file missing [permissions] section must raise ValueError."""
        self._write_default("# Just comments, no section\n")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("missing required keys ['permissions']", msg)
        self.assertIn("mezz_config deserializes server cheat permissions", msg)

    def test_extra_section_raises_value_error(self) -> None:
        """An INI file with an extraneous section must raise ValueError."""
        bad_ini = format_ini(VALID_PERMISSIONS, extra_sections={"rogue": {"key": "val"}})
        self._write_server(bad_ini)
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("unexpected keys ['rogue']", msg)
        self.assertIn("mezz_config deserializes server cheat permissions", msg)

    def test_missing_permission_key_raises_value_error(self) -> None:
        """A missing cheat permission key must raise ValueError."""
        bad_perms = copy.deepcopy(VALID_PERMISSIONS)
        del bad_perms["enableCheatModeForGive"]
        self._write_default(format_ini(bad_perms))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("missing required keys ['enableCheatModeForGive']", msg)
        self.assertIn("cheat mode access is explicitly and deterministically configured", msg)

    def test_extra_permission_key_raises_value_error(self) -> None:
        """An extraneous cheat permission key must raise ValueError."""
        bad_perms = copy.deepcopy(VALID_PERMISSIONS)
        bad_perms["enableCheatModeForEveryone"] = "true"
        self._write_server(format_ini(bad_perms))
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("unexpected keys ['enableCheatModeForEveryone']", msg)
        self.assertIn("cheat mode access is explicitly and deterministically configured", msg)

    def test_non_boolean_value_raises_value_error(self) -> None:
        """Cheat permission values must be strict boolean strings ('true' or 'false')."""
        for bad_val in ("yes", "1", "TRUE", "enabled", "falsey"):
            bad_perms = copy.deepcopy(VALID_PERMISSIONS)
            bad_perms["enableCheatModeForOp"] = bad_val
            self._write_default(format_ini(bad_perms))
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            msg = str(ctx.exception)
            self.assertIn("invariant violation: must be a strict boolean string ('true' or 'false')", msg)
            self.assertIn("controlling whether JEI cheat mode is granted", msg)

    def test_consistency_drift_raises_value_error(self) -> None:
        """Default template and active serverconfig having different permissions must raise ValueError."""
        # Default has enableCheatModeForOp = true, change server to false
        divergent_server = copy.deepcopy(VALID_PERMISSIONS)
        divergent_server["enableCheatModeForOp"] = "false"
        self._write_server(format_ini(divergent_server))

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        msg = str(ctx.exception)
        self.assertIn("consistency invariant violation", msg)
        self.assertIn("have divergent [permissions] settings", msg)
        self.assertIn("so default world creation and active world cheat permissions never drift", msg)

    def test_forbidden_file_or_directory_raises_value_error(self) -> None:
        """Forbidden directories or files must be rejected during pre-flight."""
        # Forbidden directory
        (self.configs_dir / "playerdata").mkdir()
        with self.assertRaises(ValueError) as ctx_dir:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: playerdata", str(ctx_dir.exception))
        (self.configs_dir / "playerdata").rmdir()

        # Forbidden file
        (self.configs_dir / "jei-client.ini").write_text("dummy", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_file:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: jei-client.ini", str(ctx_file.exception))
        (self.configs_dir / "jei-client.ini").unlink()

        # Forbidden archive suffix
        (self.configs_dir / "backup.zip").write_text("dummy", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_archive:
            self.sync.validate_configs()
        self.assertIn("Forbidden archive/runtime file present in configs/: backup.zip", str(ctx_archive.exception))
        (self.configs_dir / "backup.zip").unlink()

    def test_secret_guards_reject_credentials(self) -> None:
        """Secret patterns or credential keys in configs/ must fail validation."""
        # Inject credential key into [permissions]
        bad_perms = copy.deepcopy(VALID_PERMISSIONS)
        bad_perms["password"] = "supersecret"
        self._write_default(format_ini(bad_perms))
        with self.assertRaises(ValueError) as ctx_cred:
            self.sync.validate_configs()
        msg_cred = str(ctx_cred.exception)
        self.assertIn("non-empty secret key 'permissions.password'", msg_cred)

        # Inject webhook secret pattern in comments
        webhook_ini = (
            "# Discord webhook: https://discord.com/api/webhooks/123456789/abcdef_token\n"
            + format_ini(VALID_PERMISSIONS)
        )
        self._write_server(webhook_ini)
        with self.assertRaises(ValueError) as ctx_pattern:
            self.sync.validate_configs()
        msg_pat = str(ctx_pattern.exception)
        self.assertIn("Discord Webhook URL", msg_pat)


if __name__ == "__main__":
    unittest.main()
