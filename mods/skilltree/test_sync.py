#!/usr/bin/env python3
"""Unit and integration tests for mods/skilltree/sync.py."""

from __future__ import annotations

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


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("skilltree_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillTreeSyncTest(unittest.TestCase):
    """Verify Passive Skill Tree config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "skilltree" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/skilltree/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"skilltree-common.toml", "skilltree-server.toml"},
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places both TOML files; second run is idempotent; updates preserve target file mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "skilltree-common.toml"
        server_target = self.data_dir / "world" / "serverconfig" / "skilltree-server.toml"
        self.assertTrue(common_target.is_file(), "Missing skilltree-common.toml in config/")
        self.assertTrue(server_target.is_file(), "Missing skilltree-server.toml in world/serverconfig/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(common_target, 0o600)
        common_src = self.configs_dir / "skilltree-common.toml"
        common_src.write_text(
            common_src.read_text(encoding="utf-8").replace(
                '"Base drop chance" = 0.15', '"Base drop chance" = 0.25'
            ),
            encoding="utf-8",
        )

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(common_target.stat().st_mode & 0o777, 0o600)
        self.assertIn('"Base drop chance" = 0.25', common_target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_and_dirs_rejected(self) -> None:
        """Forbidden runtime directories and archive/database files must fail pre-flight validation."""
        for forbidden_dir in ("world", "playerdata", "logs", "mods"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden file/directory present in configs/: {forbidden_dir}", str(ctx.exception))
            dpath.rmdir()

        for suffix_file in ("backup.zip", "world.tar.gz", "player.db", "mod.jar", "run.lock"):
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

        (self.configs_dir / "skilltree-server.toml").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("Missing expected config files in configs/: skilltree-server.toml", str(ctx_missing.exception))

    def test_invariant_common_skill_points_validated(self) -> None:
        """Invalid skill point bounds, types, or Levelup costs lengths in common TOML must fail with rationale."""
        common_path = self.configs_dir / "skilltree-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        cases = [
            ('"Maximum skill points" = 85', '"Maximum skill points" = 0', "must be an integer in 1..1000"),
            ('"Maximum skill points" = 85', '"Maximum skill points" = 1001', "must be an integer in 1..1000"),
            ('"Maximum skill points" = 85', '"Maximum skill points" = true', "must be an integer in 1..1000"),
            ('"First skill point cost" = 15', '"First skill point cost" = 0', '"First skill point cost" must be an integer > 0'),
            ('"First skill point cost" = 15', '"First skill point cost" = false', '"First skill point cost" must be an integer > 0'),
            ('"Last skill point cost" = 1400', '"Last skill point cost" = 0', '"Last skill point cost" must be an integer > 0'),
            ('"Use skill points costs array" = false', '"Use skill points costs array" = "yes"', '"Use skill points costs array" must be a boolean'),
            ('"Show chat messages" = true', '"Show chat messages" = 1', '"Show chat messages" must be a boolean'),
            ('"Enable exprerience exchange for skill points" = true', '"Enable exprerience exchange for skill points" = "true"', '"Enable exprerience exchange for skill points" must be a boolean'),
            ('"Levelup costs" = [15,', '"Levelup costs" = [0,', '"Levelup costs"[0] must be an integer > 0'),
            ('"Levelup costs" = [15, 19,', '"Levelup costs" = [15,', '"Levelup costs" length (84) must equal "Maximum skill points" (85)'),
        ]
        for old, new, expected_msg in cases:
            self.assertIn(old, orig)
            common_path.write_text(orig.replace(old, new, 1), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {new}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

    def test_invariant_common_gems_equipment_amnesia_xp_mixtures_validated(self) -> None:
        """Invalid Gems, Equipment, Amnesia Scroll, Experience, and Mixtures values must fail with rationale."""
        common_path = self.configs_dir / "skilltree-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        cases = [
            ('"Base drop chance" = 0.15', '"Base drop chance" = -0.1', '"Base drop chance" must be a number in 0.0..1.0'),
            ('"Base drop chance" = 0.15', '"Base drop chance" = 1.1', '"Base drop chance" must be a number in 0.0..1.0'),
            ('"Base drop chance" = 0.15', '"Base drop chance" = true', '"Base drop chance" must be a number in 0.0..1.0'),
            ('"Base drop chance" = 0.15', '"Base drop chance" = nan', '"Base drop chance" must be a number in 0.0..1.0'),
            ('"IDs of items that shouldn\'t have sockets" = []', '"IDs of items that shouldn\'t have sockets" = [""]', "must be a list of non-empty strings"),
            ('"IDs of items that shouldn\'t have sockets" = []', '"IDs of items that shouldn\'t have sockets" = "minecraft:stick"', "must be a list of non-empty strings"),
            ('"Amnesia scroll penalty" = 0.2', '"Amnesia scroll penalty" = 1.5', '"Amnesia scroll penalty" must be a number in 0.0..1.0'),
            ('"Drop amnesia scrolls from the Ender Dragon" = true', '"Drop amnesia scrolls from the Ender Dragon" = 0', '"Drop amnesia scrolls from the Ender Dragon" must be a boolean'),
            ('"Grindstone experience multiplier" = 0.1', '"Grindstone experience multiplier" = -0.05', '"Grindstone experience multiplier" must be a number in 0.0..1.0'),
            ('"Effects duration multiplier" = 1.0', '"Effects duration multiplier" = 2.1', '"Effects duration multiplier" must be a number in 0.0..2.0'),
            ('"Effects strength multiplier" = 1.0', '"Effects strength multiplier" = -0.1', '"Effects strength multiplier" must be a number in 0.0..2.0'),
        ]
        for old, new, expected_msg in cases:
            self.assertIn(old, orig)
            common_path.write_text(orig.replace(old, new, 1), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {new}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

        for socket_key in self.sync.EQUIPMENT_SOCKET_KEYS:
            default_val = 0 if socket_key == "Default Leggings Sockets" else 1
            old_line = f'"{socket_key}" = {default_val}'
            self.assertIn(old_line, orig)
            for bad_val in (-1, 5, "true"):
                new_line = f'"{socket_key}" = {bad_val}'
                common_path.write_text(orig.replace(old_line, new_line, 1), encoding="utf-8")
                with self.assertRaises(ValueError, msg=f"Expected ValueError for {new_line}") as ctx:
                    self.sync.validate_configs()
                self.assertIn(f'"{socket_key}" must be an integer in 0..4', str(ctx.exception))

    def test_invariant_server_toml_validated(self) -> None:
        """Invalid skilltree-server.toml bounds and types must fail with explanatory rationale."""
        server_path = self.configs_dir / "skilltree-server.toml"
        orig = server_path.read_text(encoding="utf-8")

        cases = [
            ('"Maximum skill points" = 100', '"Maximum skill points" = 1', "must be an integer > 1"),
            ('"Maximum skill points" = 100', '"Maximum skill points" = true', "must be an integer > 1"),
            ('"First skill point cost" = 15', '"First skill point cost" = 0', '"First skill point cost" must be an integer > 0'),
            ('"Last skill point cost" = 1400', '"Last skill point cost" = -1', '"Last skill point cost" must be an integer > 0'),
            ('"Levelup costs" = [15, 19,', '"Levelup costs" = [15,', '"Levelup costs" length (99) must equal "Maximum skill points" (100)'),
            ('"Amnesia scroll penalty" = 0.2', '"Amnesia scroll penalty" = 1.2', '"Amnesia scroll penalty" must be a number in 0.0..1.0'),
            ('"Grindstone experience multiplier" = 0.1', '"Grindstone experience multiplier" = 1.5', '"Grindstone experience multiplier" must be a number in 0.0..1.0'),
        ]
        for old, new, expected_msg in cases:
            self.assertIn(old, orig)
            server_path.write_text(orig.replace(old, new, 1), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {new}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

    def test_secret_guards_rejected(self) -> None:
        """Secret patterns and secret key names in TOML files must fail validation."""
        common_path = self.configs_dir / "skilltree-common.toml"
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
