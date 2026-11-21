#!/usr/bin/env python3
"""Unit and integration tests for mods/extrabotany/sync.py."""

from __future__ import annotations

import copy
import importlib.util
import io
import math
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

VALID_CONFIG: dict[str, Any] = {
    "server": {
        "telemetry": {
            "enableTelemetry": True,
            "telemetryUUID": "4ddf92ed-0894-46bf-85f3-acfa0d9e0fe1",
        },
        "gaia": {
            "disableGaiaDisarm": False,
            "gaiaSpawnUnCheckList": ["minecraft", "botania", "extrabotany"],
        },
        "fakePlayer": {
            "fakePlayerId": "[Extrabotany]",
        },
        "flower": {
            "tradeOrchid": {
                "maxMana": 10000,
                "manaCost": 1000,
                "cooldown": 40,
                "discountPercentage": 0.5,
            },
            "woodienia": {
                "maxMana": 10000,
                "workManaCost": 200,
                "range": [8, 16, 8],
                "cooldown": 10,
            },
            "reikarlily": {
                "maxMana": 12000,
                "produceCooldown": 3600,
                "produceMana": 12000,
                "passiveGenerateTime": 1500,
                "passiveGenerateMana": 45,
                "spawnLightningCooldown": 3600,
            },
            "bellflower": {
                "maxMana": 300,
                "generateModify": 1.0,
            },
            "annoyingflower": {
                "maxMana": 1000,
                "fishingCost": 300,
                "cooldown": 900,
                "foodBoostMax": 12,
                "foodBoostPerEat": 3,
                "foodBoostCooldownMultiplier": 0.4,
            },
            "stonesia": {
                "maxMana": 3200,
                "cooldown": 40,
            },
            "edelweiss": {
                "maxMana": 12800,
                "cooldown": 40,
            },
            "resoncund": {
                "maxMana": 1200,
                "lossPerHeard": 50,
            },
            "sunshineLily": {
                "maxMana": 200,
                "produceMana": 2,
            },
            "moonlightLily": {
                "maxMana": 200,
                "produceMana": 1,
            },
            "twinstar": {
                "maxMana": 1000,
                "maxTemperatureCap": 2147483647,
                "minTemperatureCap": 0,
            },
            "omniviolet": {
                "maxMana": 1500,
            },
            "tinkle": {
                "maxMana": 1000,
                "produceMana": 100,
            },
            "bloodEnchantress": {
                "maxMana": 800,
                "produceMana": 22,
            },
            "serenitian": {
                "range": 3,
            },
            "mirrowtunia": {
                "maxMana": 2000,
                "effectCost": 100,
            },
            "necrofleur": {
                "maxMana": 200,
            },
            "manalink": {
                "transferSpeed": 400,
            },
            "enchanter": {
                "transformCost": 250000,
                "consumeSpeed": 400,
            },
        },
    }
}


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_format_value(v) for v in value)
        return f"[{items}]"
    return repr(value)


def _emit_table(lines: list[str], table: dict[str, Any], prefix: str = "") -> None:
    scalars: list[tuple[str, Any]] = []
    subtables: list[tuple[str, dict[str, Any]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            subtables.append((key, value))
        else:
            scalars.append((key, value))

    if prefix and (scalars or not subtables):
        lines.append(f"[{prefix}]")
    for key, value in scalars:
        lines.append(f"{key} = {_format_value(value)}")
    if prefix and scalars:
        lines.append("")

    for key, subtable in subtables:
        next_prefix = f"{prefix}.{key}" if prefix else key
        _emit_table(lines, subtable, next_prefix)


def format_toml(config: dict[str, Any]) -> str:
    """Serialize a nested ExtraBotany config dict into TOML."""
    lines: list[str] = []
    _emit_table(lines, config)
    return "\n".join(lines) + "\n"


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("extrabotany_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtraBotanySyncTest(unittest.TestCase):
    """Verify ExtraBotany config validation, invariants, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "extrabotany" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "extrabotany-common.toml"

    def _write_config(self, cfg: dict[str, Any]) -> None:
        self._config_path().write_text(format_toml(cfg), encoding="utf-8")

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/extrabotany/configs/ directory must pass pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {"config/extrabotany-common.toml"})

    def test_initial_placement_mode_preservation_and_idempotency(self) -> None:
        """First run places static file; second run is idempotent; updates preserve target mode."""
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("1 changed, 0 unchanged", buf1.getvalue())

        target = self.data_dir / "config" / "extrabotany-common.toml"
        self.assertTrue(target.is_file(), "Missing extrabotany-common.toml in data/config/")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("0 changed, 1 unchanged", buf2.getvalue())

        os.chmod(target, 0o600)
        cfg = copy.deepcopy(VALID_CONFIG)
        cfg["server"]["gaia"]["disableGaiaDisarm"] = True
        self._write_config(cfg)

        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertIn("1 changed, 0 unchanged", buf3.getvalue())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("disableGaiaDisarm = true", target.read_text(encoding="utf-8"))

    def test_dry_run_leaves_target_untouched(self) -> None:
        """Running with --dry-run must report planned changes without mutating data/."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN", buf.getvalue())
        self.assertFalse((self.data_dir / "config" / "extrabotany-common.toml").exists())

    def test_missing_and_unexpected_keys_rejected(self) -> None:
        """Missing or unexpected keys at root, server, and flower levels must raise ValueError."""
        cfg_missing_root: dict[str, Any] = {}
        self._write_config(cfg_missing_root)
        with self.assertRaisesRegex(ValueError, "missing required keys.*server"):
            self.sync.validate_configs()

        cfg_extra_root = copy.deepcopy(VALID_CONFIG)
        cfg_extra_root["unexpectedTop"] = True
        self._write_config(cfg_extra_root)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*unexpectedTop"):
            self.sync.validate_configs()

        cfg_missing_server = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_server["server"]["fakePlayer"]
        self._write_config(cfg_missing_server)
        with self.assertRaisesRegex(ValueError, "missing required keys.*fakePlayer"):
            self.sync.validate_configs()

        cfg_extra_server = copy.deepcopy(VALID_CONFIG)
        cfg_extra_server["server"]["extraSection"] = {"x": 1}
        self._write_config(cfg_extra_server)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*extraSection"):
            self.sync.validate_configs()

        cfg_missing_flower = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_flower["server"]["flower"]["enchanter"]
        self._write_config(cfg_missing_flower)
        with self.assertRaisesRegex(ValueError, "missing required keys.*enchanter"):
            self.sync.validate_configs()

        cfg_extra_flower = copy.deepcopy(VALID_CONFIG)
        cfg_extra_flower["server"]["flower"]["unknownFlower"] = {"maxMana": 100}
        self._write_config(cfg_extra_flower)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*unknownFlower"):
            self.sync.validate_configs()

        cfg_missing_field = copy.deepcopy(VALID_CONFIG)
        del cfg_missing_field["server"]["flower"]["reikarlily"]["produceMana"]
        self._write_config(cfg_missing_field)
        with self.assertRaisesRegex(ValueError, "missing required keys.*produceMana"):
            self.sync.validate_configs()

        cfg_extra_field = copy.deepcopy(VALID_CONFIG)
        cfg_extra_field["server"]["flower"]["serenitian"]["maxMana"] = 100
        self._write_config(cfg_extra_field)
        with self.assertRaisesRegex(ValueError, "unexpected keys.*maxMana"):
            self.sync.validate_configs()

    def test_bool_and_uuid_and_string_invariants(self) -> None:
        """Telemetry, Gaia, and FakePlayer types, UUID format, and string rules must hold."""
        for section, key in (
            ("telemetry", "enableTelemetry"),
            ("gaia", "disableGaiaDisarm"),
        ):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"][section][key] = "true"
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, f"server.{section}.{key}' must be a boolean"):
                self.sync.validate_configs()

        for bad_uuid in (
            "",
            "not-a-uuid",
            "4ddf92ed089446bf85f3acfa0d9e0fe1",
            "4ddf92ed-0894-46bf-85f3-acfa0d9e0feZ",
            12345,
        ):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["telemetry"]["telemetryUUID"] = bad_uuid
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "server.telemetry.telemetryUUID"):
                self.sync.validate_configs()

        for bad_fake_id in ("", "   ", 42):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["fakePlayer"]["fakePlayerId"] = bad_fake_id
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "server.fakePlayer.fakePlayerId"):
                self.sync.validate_configs()

        cfg_not_list = copy.deepcopy(VALID_CONFIG)
        cfg_not_list["server"]["gaia"]["gaiaSpawnUnCheckList"] = "minecraft"
        self._write_config(cfg_not_list)
        with self.assertRaisesRegex(ValueError, "gaiaSpawnUnCheckList.*list of non-empty strings"):
            self.sync.validate_configs()

        for bad_elem in ("", "   ", 99):
            cfg_bad_elem = copy.deepcopy(VALID_CONFIG)
            cfg_bad_elem["server"]["gaia"]["gaiaSpawnUnCheckList"] = ["minecraft", bad_elem]
            self._write_config(cfg_bad_elem)
            with self.assertRaisesRegex(ValueError, r"gaiaSpawnUnCheckList\[1\]"):
                self.sync.validate_configs()

        cfg_empty_list = copy.deepcopy(VALID_CONFIG)
        cfg_empty_list["server"]["gaia"]["gaiaSpawnUnCheckList"] = []
        self._write_config(cfg_empty_list)
        self.sync.validate_configs()

    def test_strict_int_and_range_invariants(self) -> None:
        """Strict integer and range bounds across flower settings must be enforced."""
        int_fields_1_to_max: list[tuple[str, str]] = [
            ("tradeOrchid", "maxMana"),
            ("tradeOrchid", "manaCost"),
            ("tradeOrchid", "cooldown"),
            ("woodienia", "maxMana"),
            ("woodienia", "workManaCost"),
            ("woodienia", "cooldown"),
            ("reikarlily", "maxMana"),
            ("reikarlily", "produceCooldown"),
            ("reikarlily", "produceMana"),
            ("reikarlily", "passiveGenerateTime"),
            ("reikarlily", "passiveGenerateMana"),
            ("reikarlily", "spawnLightningCooldown"),
            ("bellflower", "maxMana"),
            ("annoyingflower", "maxMana"),
            ("annoyingflower", "fishingCost"),
            ("annoyingflower", "cooldown"),
            ("annoyingflower", "foodBoostMax"),
            ("annoyingflower", "foodBoostPerEat"),
            ("stonesia", "maxMana"),
            ("stonesia", "cooldown"),
            ("edelweiss", "maxMana"),
            ("edelweiss", "cooldown"),
            ("resoncund", "maxMana"),
            ("resoncund", "lossPerHeard"),
            ("sunshineLily", "maxMana"),
            ("sunshineLily", "produceMana"),
            ("moonlightLily", "maxMana"),
            ("moonlightLily", "produceMana"),
            ("twinstar", "maxMana"),
            ("twinstar", "maxTemperatureCap"),
            ("omniviolet", "maxMana"),
            ("tinkle", "maxMana"),
            ("tinkle", "produceMana"),
            ("bloodEnchantress", "maxMana"),
            ("bloodEnchantress", "produceMana"),
            ("mirrowtunia", "maxMana"),
            ("mirrowtunia", "effectCost"),
            ("necrofleur", "maxMana"),
            ("manalink", "transferSpeed"),
            ("enchanter", "transformCost"),
            ("enchanter", "consumeSpeed"),
        ]
        for flower, key in int_fields_1_to_max:
            for bad in (True, 1.5, 0, -1, 2_147_483_648):
                cfg = copy.deepcopy(VALID_CONFIG)
                cfg["server"]["flower"][flower][key] = bad
                self._write_config(cfg)
                with self.assertRaisesRegex(ValueError, f"server.flower.{flower}.{key}"):
                    self.sync.validate_configs()

        for bad in (True, 3.0, 0, -1, 17):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["flower"]["serenitian"]["range"] = bad
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "server.flower.serenitian.range"):
                self.sync.validate_configs()

        for valid_range in (1, 16):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["flower"]["serenitian"]["range"] = valid_range
            self._write_config(cfg)
            self.sync.validate_configs()

    def test_woodienia_range_and_float_and_twinstar_invariants(self) -> None:
        """Woodienia 3-int range, finite floats, and Twinstar temperature bounds must hold."""
        for bad_range in ("8,16,8", [8, 16], [8, 16, 8, 1]):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["flower"]["woodienia"]["range"] = bad_range
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "server.flower.woodienia.range"):
                self.sync.validate_configs()

        for bad_elem in (True, 8.5, -1, 2_147_483_648):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["flower"]["woodienia"]["range"] = [8, bad_elem, 8]
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, r"server\.flower\.woodienia\.range\[1\]"):
                self.sync.validate_configs()

        cfg_zero_range = copy.deepcopy(VALID_CONFIG)
        cfg_zero_range["server"]["flower"]["woodienia"]["range"] = [0, 0, 0]
        self._write_config(cfg_zero_range)
        self.sync.validate_configs()

        float_checks: list[tuple[str, str, float, list[Any]]] = [
            (
                "tradeOrchid",
                "discountPercentage",
                1.0,
                [True, "0.5", float("nan"), float("inf"), -0.01, 1.01],
            ),
            (
                "bellflower",
                "generateModify",
                2147483647.0,
                [False, "1.0", float("nan"), float("inf"), -0.1, 2147483648.0],
            ),
            (
                "annoyingflower",
                "foodBoostCooldownMultiplier",
                1.0,
                [True, "0.4", float("nan"), float("-inf"), -0.01, 1.01],
            ),
        ]
        for flower, key, valid_upper, bad_values in float_checks:
            for bad in bad_values:
                cfg = copy.deepcopy(VALID_CONFIG)
                cfg["server"]["flower"][flower][key] = bad
                self._write_config(cfg)
                with self.assertRaisesRegex(ValueError, f"server.flower.{flower}.{key}"):
                    self.sync.validate_configs()

            for boundary in (0.0, valid_upper):
                cfg = copy.deepcopy(VALID_CONFIG)
                cfg["server"]["flower"][flower][key] = boundary
                self._write_config(cfg)
                self.sync.validate_configs()

        for bad_min in (True, 0.5, -1, 2_147_483_648):
            cfg = copy.deepcopy(VALID_CONFIG)
            cfg["server"]["flower"]["twinstar"]["minTemperatureCap"] = bad_min
            self._write_config(cfg)
            with self.assertRaisesRegex(ValueError, "server.flower.twinstar.minTemperatureCap"):
                self.sync.validate_configs()

        cfg_inverted = copy.deepcopy(VALID_CONFIG)
        cfg_inverted["server"]["flower"]["twinstar"]["minTemperatureCap"] = 500
        cfg_inverted["server"]["flower"]["twinstar"]["maxTemperatureCap"] = 300
        self._write_config(cfg_inverted)
        with self.assertRaisesRegex(
            ValueError,
            "minTemperatureCap.*must be <=.*maxTemperatureCap",
        ):
            self.sync.validate_configs()

        cfg_equal = copy.deepcopy(VALID_CONFIG)
        cfg_equal["server"]["flower"]["twinstar"]["minTemperatureCap"] = 300
        cfg_equal["server"]["flower"]["twinstar"]["maxTemperatureCap"] = 300
        self._write_config(cfg_equal)
        self.sync.validate_configs()

    def test_invalid_toml_rejected(self) -> None:
        """Malformed TOML syntax must raise ValueError."""
        self._config_path().write_text("[server\nenableTelemetry = true\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid TOML"):
            self.sync.validate_configs()

    def test_forbidden_files_and_secrets_rejected(self) -> None:
        """Forbidden runtime/client files, suffixes, and secret patterns must raise ValueError."""
        for forbidden_name in ("extrabotany-client.toml", "extrabotany-server.toml"):
            bad_cfg = self.configs_dir / "config" / forbidden_name
            bad_cfg.write_text("placeholder = true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Forbidden file/directory"):
                self.sync.validate_configs()
            bad_cfg.unlink()

        db_file = self.configs_dir / "state.db"
        db_file.write_bytes(b"sqlite")
        with self.assertRaisesRegex(ValueError, "Forbidden archive/runtime file"):
            self.sync.validate_configs()
        db_file.unlink()

        self._config_path().write_text(
            format_toml(VALID_CONFIG)
            + '\n# webhook = "https://discord.com/api/webhooks/123456789/abcdef"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "detected Discord Webhook URL"):
            self.sync.validate_configs()

        cfg_with_secret_key = copy.deepcopy(VALID_CONFIG)
        cfg_with_secret_key["server"]["password"] = "super-secret"
        self._write_config(cfg_with_secret_key)
        with self.assertRaisesRegex(ValueError, "non-empty secret key"):
            self.sync.validate_configs()


if __name__ == "__main__":
    unittest.main()
