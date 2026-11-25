#!/usr/bin/env python3
"""Unit and integration tests for mods/paradigm/sync.py."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _bridge import TargetDirSyncModuleProtocol

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"


def load_sync_module() -> TargetDirSyncModuleProtocol:
    spec = importlib.util.spec_from_file_location("paradigm_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("TargetDirSyncModuleProtocol", module)


class ParadigmSyncTest(unittest.TestCase):
    """Verify Paradigm config validation, invariant errors, secret guards, and key-level merges."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "paradigm" / "configs"
        self.target_dir = self.root / "data" / "config" / "paradigm"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.target_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.TARGET_DIR = self.target_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/paradigm/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        parsed = real_sync.validate_configs()
        self.assertEqual(len(parsed), 19)

    def test_initial_placement_and_idempotency(self) -> None:
        """First run places all 19 files; second run reports 0 changes."""
        rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)

        for rel in self.sync.STATIC_FILES:
            self.assertTrue((self.target_dir / rel).is_file(), f"Missing static file {rel}")
        self.assertTrue((self.target_dir / "cooldowns.json").is_file())
        self.assertTrue((self.target_dir / "holograms.json").is_file())

        # Modify a static file's permissions in target_dir to 0600 and update source to verify mode preservation
        afk_target = self.target_dir / "afk.json"
        os.chmod(afk_target, 0o600)

        afk_src = self.configs_dir / "afk.json"
        afk_data = json.loads(afk_src.read_text(encoding="utf-8"))
        afk_data["afkTimeoutSeconds"]["value"] = 450
        afk_src.write_text(json.dumps(afk_data, indent=2), encoding="utf-8")

        rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertEqual(afk_target.stat().st_mode & 0o777, 0o600)
        placed_afk = json.loads(afk_target.read_text(encoding="utf-8"))
        self.assertEqual(placed_afk["afkTimeoutSeconds"]["value"], 450)

    def test_key_level_merge_preserves_live_cooldowns_and_holograms(self) -> None:
        """Key-level merge updates static settings while preserving live player cooldowns and holograms in data/."""
        live_cooldowns = {
            "cooldowns": {
                "419a8875-fda5-3754-b761-2b32ce8c49c0": {
                    "tpa": 1794772124642,
                    "home": 1794767533937,
                }
            },
            "commandCooldownSeconds": {"home": 999, "tpa": 999},
            "commandWarmupSeconds": {"home": 999},
        }
        live_holograms = {
            "enabled": False,
            "defaultViewDistance": 16.0,
            "defaultRefreshIntervalSeconds": 20,
            "renderMode": "legacy",
            "holograms": {
                "spawn_welcome": {
                    "world": "minecraft:overworld",
                    "x": 0.5,
                    "y": 70.0,
                    "z": 0.5,
                    "lines": ["Welcome!"],
                }
            },
        }
        (self.target_dir / "cooldowns.json").write_text(json.dumps(live_cooldowns, indent=2), encoding="utf-8")
        (self.target_dir / "holograms.json").write_text(json.dumps(live_holograms, indent=2), encoding="utf-8")

        rc = self.sync.main([])
        self.assertEqual(rc, 0)

        merged_cool = json.loads((self.target_dir / "cooldowns.json").read_text(encoding="utf-8"))
        self.assertEqual(
            merged_cool["cooldowns"],
            live_cooldowns["cooldowns"],
            "Live player UUID cooldowns must be preserved in data/",
        )
        self.assertEqual(merged_cool["commandCooldownSeconds"]["home"], 0)

        merged_holo = json.loads((self.target_dir / "holograms.json").read_text(encoding="utf-8"))
        self.assertEqual(
            merged_holo["holograms"],
            live_holograms["holograms"],
            "Live in-world holograms must be preserved in data/",
        )
        self.assertTrue(merged_holo["enabled"])
        self.assertEqual(merged_holo["defaultViewDistance"], 48.0)

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without writing to TARGET_DIR."""
        rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.target_dir.iterdir()), [])

    def test_invariant_internal_permissions_must_be_false(self) -> None:
        """Enabling internalPermissionsEnable must fail with LuckPerms rationale."""
        main_path = self.configs_dir / "main.json"
        data = json.loads(main_path.read_text(encoding="utf-8"))
        data["internalPermissionsEnable"]["value"] = True
        main_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("internalPermissionsEnable.value must be false", str(ctx.exception))
        self.assertIn("LuckPerms is the single source of truth", str(ctx.exception))

    def test_invariant_chat_and_tablist_format_must_preserve_prefix_player_suffix(self) -> None:
        """Removing {prefix}{player_name}{suffix} must fail with staff prefix & clan suffix rationale."""
        chat_path = self.configs_dir / "chat.json"
        data = json.loads(chat_path.read_text(encoding="utf-8"))
        data["customChatFormat"]["value"] = "{player_name}: {message}"
        chat_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("{prefix}{player_name}{suffix}", str(ctx.exception))
        self.assertIn("LuckPerms staff prefixes", str(ctx.exception))

    def test_runtime_keys_rejected_in_repo_configs(self) -> None:
        """Adding 'cooldowns' or 'holograms' runtime maps into repo configs/ must fail."""
        cool_path = self.configs_dir / "cooldowns.json"
        data = json.loads(cool_path.read_text(encoding="utf-8"))
        data["cooldowns"] = {"some-uuid": {"tpa": 123}}
        cool_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("runtime key 'cooldowns' must not exist in repo configs/", str(ctx.exception))

    def test_forbidden_files_and_secrets_rejected(self) -> None:
        """Forbidden files (e.g. discord.json) or embedded secrets must fail pre-flight validation."""
        (self.configs_dir / "discord.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: discord.json", str(ctx.exception))
        (self.configs_dir / "discord.json").unlink()

        motd_path = self.configs_dir / "motd.json"
        motd_data = json.loads(motd_path.read_text(encoding="utf-8"))
        motd_data["motdLines"] = ["https://discord.com/api/webhooks/123456789/abcdef-token"]
        motd_path.write_text(json.dumps(motd_data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx2:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx2.exception))


if __name__ == "__main__":
    unittest.main()
