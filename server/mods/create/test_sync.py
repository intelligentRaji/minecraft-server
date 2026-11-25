#!/usr/bin/env python3
"""Unit and integration tests for mods/create/sync.py."""

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
    spec = importlib.util.spec_from_file_location("create_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CreateSyncTest(unittest.TestCase):
    """Verify Create config validation, invariant errors, secret guards, and atomic placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "create" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/create/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(
            set(loaded.keys()),
            {"config/create-common.toml", "world/serverconfig/create-server.toml"},
        )

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places both TOML files; second run is idempotent; updates preserve target file mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("2 changed, 0 unchanged", buf1.getvalue())

        common_target = self.data_dir / "config" / "create-common.toml"
        server_target = self.data_dir / "world" / "serverconfig" / "create-server.toml"
        self.assertTrue(common_target.is_file(), "Missing create-common.toml in config/")
        self.assertTrue(
            server_target.is_file(),
            "Missing create-server.toml in world/serverconfig/",
        )

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 2 unchanged", buf2.getvalue())

        os.chmod(common_target, 0o600)
        common_src = self.configs_dir / "config" / "create-common.toml"
        common_src.write_text(
            common_src.read_text(encoding="utf-8").replace(
                "disableWorldGen = false", "disableWorldGen = true"
            ),
            encoding="utf-8",
        )

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 1 unchanged", buf3.getvalue())
        self.assertEqual(common_target.stat().st_mode & 0o777, 0o600)
        self.assertIn(
            "disableWorldGen = true", common_target.read_text(encoding="utf-8")
        )

    def test_dry_run_does_not_write_files(self) -> None:
        """--dry-run validates and previews without creating or modifying files in DATA_DIR."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN: 2 changed, 0 unchanged", buf.getvalue())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    def test_forbidden_files_and_dirs_rejected(self) -> None:
        """Forbidden runtime directories and archive/database/NBT/JSON files must fail validation."""
        for forbidden_dir in ("schematics", "data", "playerdata", "region", "logs", "mods"):
            dpath = self.configs_dir / forbidden_dir
            dpath.mkdir()
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden file/directory present in configs/: {forbidden_dir}",
                str(ctx.exception),
            )
            dpath.rmdir()

        for suffix_file in (
            "schematic.nbt",
            "create_trains.dat",
            "state.json",
            "player.db",
            "world.sqlite",
            "backup.zip",
            "mod.jar",
        ):
            fpath = self.configs_dir / suffix_file
            fpath.write_bytes(b"artifact")
            with self.assertRaises(ValueError) as ctx_file:
                self.sync.validate_configs()
            self.assertIn(
                f"Forbidden archive/runtime file present in configs/: {suffix_file}",
                str(ctx_file.exception),
            )
            fpath.unlink()

    def test_missing_and_unexpected_files_rejected(self) -> None:
        """Missing expected files or unexpected files in configs/ must fail validation."""
        unexpected = self.configs_dir / "config" / "unexpected.toml"
        unexpected.write_text("foo = 1\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn(
            "Unexpected files in configs/: config/unexpected.toml",
            str(ctx.exception),
        )
        unexpected.unlink()

        (self.configs_dir / "world" / "serverconfig" / "create-server.toml").unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "Missing expected config files in configs/: world/serverconfig/create-server.toml",
            str(ctx_missing.exception),
        )

    def test_invalid_toml_syntax_rejected(self) -> None:
        """Malformed TOML syntax must fail pre-flight validation."""
        common_path = self.configs_dir / "config" / "create-common.toml"
        common_path.write_text("[worldgen\ndisableWorldGen = false\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.sync.validate_configs()
        self.assertIn("invalid TOML", str(ctx.exception))

    def test_invariant_common_toml_validated(self) -> None:
        """Invalid [worldgen] types or missing section in create-common.toml must fail with rationale."""
        common_path = self.configs_dir / "config" / "create-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        common_path.write_text(
            orig.replace("disableWorldGen = false", 'disableWorldGen = "false"'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_type:
            self.sync.validate_configs()
        self.assertIn(
            "[worldgen].disableWorldGen must be a boolean", str(ctx_type.exception)
        )
        self.assertIn("world generation", str(ctx_type.exception))

        common_path.write_text("# empty\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn(
            "[worldgen] table must be present", str(ctx_missing.exception)
        )

    def test_invariant_server_toml_ranges_types_enums_validated(self) -> None:
        """Out-of-range values, wrong types, invalid enums, and missing sections must fail with rationale."""
        server_path = self.configs_dir / "world" / "serverconfig" / "create-server.toml"
        orig = server_path.read_text(encoding="utf-8")

        cases = [
            (
                "tickrateSyncTimer = 20",
                "tickrateSyncTimer = 5",
                "[infrastructure].tickrateSyncTimer must be an integer > 5",
            ),
            (
                "tickrateSyncTimer = 20",
                "tickrateSyncTimer = true",
                "[infrastructure].tickrateSyncTimer must be an integer > 5",
            ),
            ("bulkPressing = false", 'bulkPressing = "no"', "[recipes].bulkPressing must be a boolean"),
            (
                "maxFireworkIngredientsInCrafter = 9",
                "maxFireworkIngredientsInCrafter = 1",
                "[recipes].maxFireworkIngredientsInCrafter must be an integer > 1",
            ),
            ("maxBeltLength = 20", "maxBeltLength = 5", "[kinetics].maxBeltLength must be an integer > 5"),
            ("maxRotationSpeed = 256", "maxRotationSpeed = 64", "[kinetics].maxRotationSpeed must be an integer > 64"),
            (
                'ignoreDeployerAttacks = "CREEPERS"',
                'ignoreDeployerAttacks = "ZOMBIES"',
                "[kinetics].ignoreDeployerAttacks must be one of {ALL, CREEPERS, NONE}",
            ),
            (
                "crankHungerMultiplier = 0.009999999776482582",
                "crankHungerMultiplier = 1.5",
                "[kinetics].crankHungerMultiplier must be a finite number in 0.0..1.0",
            ),
            (
                "fanPushDistance = 20",
                "fanPushDistance = 5",
                "[kinetics.encasedFan].fanPushDistance must be an integer > 5",
            ),
            (
                'movableSpawners = "NO_PICKUP"',
                'movableSpawners = "DESTROY"',
                "[kinetics.contraptions].movableSpawners must be one of {MOVABLE, NO_PICKUP, UNMOVABLE}",
            ),
            (
                "mediumSpeed = 30.0",
                "mediumSpeed = 5000.0",
                "[kinetics.stats].mediumSpeed must be a finite number in 0.0..4096.0",
            ),
            (
                "crushing_wheel = 8.0",
                "crushing_wheel = -1.0",
                "[kinetics.stressValues.v2.impact].crushing_wheel must be a non-negative finite number",
            ),
            (
                "steam_engine = 1024.0",
                "steam_engine = nan",
                "[kinetics.stressValues.v2.capacity].steam_engine must be a non-negative finite number",
            ),
            (
                "hosePulleyBlockThreshold = 10000",
                "hosePulleyBlockThreshold = -2",
                "[fluids].hosePulleyBlockThreshold must be an integer >= -1",
            ),
            (
                'bottomlessFluidMode = "ALLOW_BY_TAG"',
                'bottomlessFluidMode = "INVALID"',
                "[fluids].bottomlessFluidMode must be one of {ALLOW_ALL, ALLOW_BY_TAG, DENY_ALL, DENY_BY_TAG}",
            ),
            ("vaultCapacity = 20", "vaultCapacity = 2049", "[logistics].vaultCapacity must be an integer in 1..2048"),
            (
                "brassTunnelTimer = 10",
                "brassTunnelTimer = 11",
                "[logistics].brassTunnelTimer must be an integer in 1..10",
            ),
            (
                "maxSchematicPacketSize = 1024",
                "maxSchematicPacketSize = 128",
                "[schematics].maxSchematicPacketSize must be an integer in 256..32767",
            ),
            (
                "schematicannonDelay = 10",
                "schematicannonDelay = 1",
                "[schematics.schematicannon].schematicannonDelay must be an integer > 1",
            ),
            (
                "maxSymmetryWandRange = 50",
                "maxSymmetryWandRange = 10",
                "[equipment].maxSymmetryWandRange must be an integer > 10",
            ),
            (
                "maxTrackPlacementLength = 32",
                "maxTrackPlacementLength = 15",
                "[trains].maxTrackPlacementLength must be an integer in 16..128",
            ),
            (
                "trainTopSpeed = 28.0",
                "trainTopSpeed = -0.1",
                "[trains.trainStats].trainTopSpeed must be a finite number >= 0.0",
            ),
            (
                "poweredTrainAcceleration = 3.0",
                "poweredTrainAcceleration = inf",
                "[trains.poweredTrainStats].poweredTrainAcceleration must be a finite number >= 0.0",
            ),
        ]

        for old, new, expected_msg in cases:
            self.assertIn(old, orig, f"Test fixture missing {old!r}")
            server_path.write_text(orig.replace(old, new, 1), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {new!r}") as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

        server_path.write_text("[infrastructure]\ntickrateSyncTimer = 20\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_sec:
            self.sync.validate_configs()
        self.assertIn("[trains] table must be present", str(ctx_sec.exception))

    def test_secret_guard_rejects_tokens_and_secret_keys(self) -> None:
        """Secret patterns or credential keys injected into configs must fail pre-flight validation."""
        common_path = self.configs_dir / "config" / "create-common.toml"
        orig = common_path.read_text(encoding="utf-8")

        common_path.write_text(
            orig + '\n# -----BEGIN PRIVATE KEY-----\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_pat:
            self.sync.validate_configs()
        self.assertIn("detected Private Key", str(ctx_pat.exception))

        common_path.write_text(
            orig + '\n[auth]\npassword = "hunter2"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_key:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'auth.password'", str(ctx_key.exception))


if __name__ == "__main__":
    unittest.main()
