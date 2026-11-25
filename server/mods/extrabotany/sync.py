#!/usr/bin/env python3
"""One-way deterministic configuration placement for ExtraBotany.

Places static configuration from `mods/extrabotany/configs/` into `data/`:
- `config/extrabotany-common.toml` -> `data/config/extrabotany-common.toml`

Validates TOML schema, value types, ranges, cross-field invariants, runtime
state isolation, and secret guards before touching `data/`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    check_table_keys,
    is_finite_number,
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
)

SERVER_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = SERVER_ROOT / "data"

TARGET_REL_PATH = "config/extrabotany-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "extrabotany-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
    "extrabotany-client.toml",
    "extrabotany-server.toml",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

INT32_MAX = 2_147_483_647
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

EXPECTED_ROOT_KEYS: tuple[str, ...] = ("server",)
EXPECTED_SERVER_KEYS: tuple[str, ...] = ("telemetry", "gaia", "fakePlayer", "flower")
EXPECTED_TELEMETRY_KEYS: tuple[str, ...] = ("enableTelemetry", "telemetryUUID")
EXPECTED_GAIA_KEYS: tuple[str, ...] = ("disableGaiaDisarm", "gaiaSpawnUnCheckList")
EXPECTED_FAKE_PLAYER_KEYS: tuple[str, ...] = ("fakePlayerId",)


class _IntSpec:
    __slots__ = ("max_val", "min_val", "rationale")

    def __init__(
        self,
        min_val: int = 1,
        max_val: int = INT32_MAX,
        rationale: str = (
            "ExtraBotany ForgeConfigSpec defines this mana, timing, or cap setting as a "
            "bounded 32-bit integer within its valid operational range."
        ),
    ) -> None:
        self.min_val = min_val
        self.max_val = max_val
        self.rationale = rationale


class _FloatSpec:
    __slots__ = ("max_val", "min_val", "rationale")

    def __init__(self, min_val: float, max_val: float, rationale: str) -> None:
        self.min_val = min_val
        self.max_val = max_val
        self.rationale = rationale


class _IntListSpec:
    __slots__ = ("length", "max_val", "min_val", "rationale")

    def __init__(
        self,
        length: int,
        min_val: int = 0,
        max_val: int = INT32_MAX,
        rationale: str = (
            "ExtraBotany ForgeConfigSpec defines this range setting as a fixed-length "
            "tuple of non-negative 32-bit integers."
        ),
    ) -> None:
        self.length = length
        self.min_val = min_val
        self.max_val = max_val
        self.rationale = rationale


FieldSpec = _IntSpec | _FloatSpec | _IntListSpec

FLOWER_SCHEMA: dict[str, dict[str, FieldSpec]] = {
    "tradeOrchid": {
        "maxMana": _IntSpec(),
        "manaCost": _IntSpec(),
        "cooldown": _IntSpec(),
        "discountPercentage": _FloatSpec(
            0.0,
            1.0,
            "Trade Orchid discountPercentage must be a finite fraction in [0.0, 1.0] "
            "so villager trade discounts do not become negative or invert prices.",
        ),
    },
    "woodienia": {
        "maxMana": _IntSpec(),
        "workManaCost": _IntSpec(),
        "range": _IntListSpec(
            length=3,
            min_val=0,
            max_val=INT32_MAX,
            rationale=(
                "Woodienia range must be exactly 3 non-negative 32-bit integers "
                "(±X, +Y, ±Z) defining its log-harvesting search volume."
            ),
        ),
        "cooldown": _IntSpec(),
    },
    "reikarlily": {
        "maxMana": _IntSpec(),
        "produceCooldown": _IntSpec(),
        "produceMana": _IntSpec(),
        "passiveGenerateTime": _IntSpec(),
        "passiveGenerateMana": _IntSpec(),
        "spawnLightningCooldown": _IntSpec(),
    },
    "bellflower": {
        "maxMana": _IntSpec(),
        "generateModify": _FloatSpec(
            0.0,
            float(INT32_MAX),
            "Bellflower generateModify must be a finite multiplier in "
            "[0.0, 2147483647.0] for wind-based mana generation.",
        ),
    },
    "annoyingflower": {
        "maxMana": _IntSpec(),
        "fishingCost": _IntSpec(),
        "cooldown": _IntSpec(),
        "foodBoostMax": _IntSpec(),
        "foodBoostPerEat": _IntSpec(),
        "foodBoostCooldownMultiplier": _FloatSpec(
            0.0,
            1.0,
            "Annoying Flower foodBoostCooldownMultiplier must be a finite multiplier "
            "in [0.0, 1.0] so food boosts reduce cooldown without negative or "
            "inflated intervals.",
        ),
    },
    "stonesia": {
        "maxMana": _IntSpec(),
        "cooldown": _IntSpec(),
    },
    "edelweiss": {
        "maxMana": _IntSpec(),
        "cooldown": _IntSpec(),
    },
    "resoncund": {
        "maxMana": _IntSpec(),
        "lossPerHeard": _IntSpec(),
    },
    "sunshineLily": {
        "maxMana": _IntSpec(),
        "produceMana": _IntSpec(),
    },
    "moonlightLily": {
        "maxMana": _IntSpec(),
        "produceMana": _IntSpec(),
    },
    "twinstar": {
        "maxMana": _IntSpec(),
        "maxTemperatureCap": _IntSpec(),
        "minTemperatureCap": _IntSpec(
            min_val=0,
            max_val=INT32_MAX,
            rationale=(
                "Twinstar minTemperatureCap must be a non-negative 32-bit integer in "
                "[0, 2147483647] representing the lowest accepted fluid temperature."
            ),
        ),
    },
    "omniviolet": {
        "maxMana": _IntSpec(),
    },
    "tinkle": {
        "maxMana": _IntSpec(),
        "produceMana": _IntSpec(),
    },
    "bloodEnchantress": {
        "maxMana": _IntSpec(),
        "produceMana": _IntSpec(),
    },
    "serenitian": {
        "range": _IntSpec(
            min_val=1,
            max_val=16,
            rationale=(
                "Serenitian working range is bounded by ForgeConfigSpec to [1, 16] "
                "blocks to prevent excessive chunk and flower scanning."
            ),
        ),
    },
    "mirrowtunia": {
        "maxMana": _IntSpec(),
        "effectCost": _IntSpec(),
    },
    "necrofleur": {
        "maxMana": _IntSpec(),
    },
    "manalink": {
        "transferSpeed": _IntSpec(),
    },
    "enchanter": {
        "transformCost": _IntSpec(),
        "consumeSpeed": _IntSpec(),
    },
}


def _check_section_keys(
    table: object,
    expected_keys: tuple[str, ...],
    section_label: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Verify `table` is a mapping with exact `expected_keys` and attach rationale."""
    raw_errors = check_table_keys(
        table,
        f"{TARGET_REL_PATH} ({section_label})",
        expected_keys,
    )
    if raw_errors:
        rationale = (
            "all ExtraBotany common config sections and keys must be explicitly declared "
            "without extra or missing fields so ForgeConfigSpec bindings remain deterministic "
            "and unvalidated or secret keys never reach data/."
        )
        return None if not isinstance(table, dict) else table, [
            f"{err} ({rationale})" for err in raw_errors
        ]
    assert isinstance(table, dict)
    return table, []


def _validate_bool(table: dict[str, Any], field_path: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, bool):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a boolean "
            f"(got {type(val).__name__}: {val!r}) because ExtraBotany binds this setting "
            "as a strict true/false ForgeConfigSpec toggle."
        ]
    return []


def _validate_uuid(table: dict[str, Any], field_path: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, str) or not UUID_PATTERN.fullmatch(val):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a non-empty "
            f"canonical UUID string in 8-4-4-4-12 hex format (got {val!r}) so ExtraBotany "
            "telemetry uses a valid instance identifier."
        ]
    return []


def _validate_non_empty_str(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, str) or not val.strip():
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a non-empty "
            f"string (got {val!r}) because {rationale}"
        ]
    return []


def _validate_non_empty_str_list(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, list):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a list of "
            f"non-empty strings (got {type(val).__name__}) because {rationale}"
        ]
    errors: list[str] = []
    for idx, item in enumerate(val):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: '{field_path}[{idx}]' must be "
                f"a non-empty string (got {item!r}) because {rationale}"
            )
    return errors


def _validate_int_range(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    min_val: int,
    max_val: int = INT32_MAX,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not is_strict_int(val):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be an integer "
            f"(got {type(val).__name__}: {val!r}) because {rationale}"
        ]
    if val < min_val or val > max_val:
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be in "
            f"[{min_val}, {max_val}] (got {val}) because {rationale}"
        ]
    return []


def _validate_float_range(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    min_val: float,
    max_val: float,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not is_finite_number(val):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a finite "
            f"number (got {type(val).__name__}: {val!r}) because {rationale}"
        ]
    numeric = float(val)
    if numeric < min_val or numeric > max_val:
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be in "
            f"[{min_val}, {max_val}] (got {val}) because {rationale}"
        ]
    return []


def _validate_int_list(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    expected_len: int,
    min_val: int,
    max_val: int = INT32_MAX,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, list):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a list of "
            f"{expected_len} integers (got {type(val).__name__}) because {rationale}"
        ]
    if len(val) != expected_len:
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must contain "
            f"exactly {expected_len} integers (got {len(val)}: {val!r}) because {rationale}"
        ]
    errors: list[str] = []
    for idx, item in enumerate(val):
        if not is_strict_int(item):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: '{field_path}[{idx}]' must be "
                f"an integer (got {type(item).__name__}: {item!r}) because {rationale}"
            )
        elif item < min_val or item > max_val:
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: '{field_path}[{idx}]' must be "
                f"in [{min_val}, {max_val}] (got {item}) because {rationale}"
            )
    return errors


def _validate_field_spec(
    table: dict[str, Any],
    field_path: str,
    key: str,
    spec: FieldSpec,
) -> list[str]:
    if isinstance(spec, _IntSpec):
        return _validate_int_range(
            table,
            field_path,
            key,
            min_val=spec.min_val,
            max_val=spec.max_val,
            rationale=spec.rationale,
        )
    if isinstance(spec, _FloatSpec):
        return _validate_float_range(
            table,
            field_path,
            key,
            min_val=spec.min_val,
            max_val=spec.max_val,
            rationale=spec.rationale,
        )
    return _validate_int_list(
        table,
        field_path,
        key,
        expected_len=spec.length,
        min_val=spec.min_val,
        max_val=spec.max_val,
        rationale=spec.rationale,
    )


def _validate_flowers(flower_table: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for flower_name, field_specs in FLOWER_SCHEMA.items():
        if flower_name not in flower_table:
            continue
        section_path = f"server.flower.{flower_name}"
        flower_entry, entry_errors = _check_section_keys(
            flower_table[flower_name],
            tuple(field_specs.keys()),
            section_path,
        )
        errors.extend(entry_errors)
        if flower_entry is None:
            continue

        for field_name, spec in field_specs.items():
            errors.extend(
                _validate_field_spec(
                    flower_entry,
                    f"{section_path}.{field_name}",
                    field_name,
                    spec,
                )
            )

        if flower_name == "twinstar":
            min_temp = flower_entry.get("minTemperatureCap")
            max_temp = flower_entry.get("maxTemperatureCap")
            if (
                is_strict_int(min_temp)
                and is_strict_int(max_temp)
                and isinstance(min_temp, int)
                and isinstance(max_temp, int)
                and min_temp > max_temp
            ):
                errors.append(
                    f"{TARGET_REL_PATH} invariant violation: "
                    f"'server.flower.twinstar.minTemperatureCap' ({min_temp}) must be <= "
                    f"'server.flower.twinstar.maxTemperatureCap' ({max_temp}) because an "
                    "inverted temperature range prevents Twinstar from accepting any fluid."
                )

    return errors


def validate_extrabotany_common(data: object) -> list[str]:
    """Validate schema, types, ranges, and invariants for `config/extrabotany-common.toml`."""
    root, errors = _check_section_keys(data, EXPECTED_ROOT_KEYS, "root")
    if root is None:
        return errors

    if "server" not in root:
        return errors

    server_table, server_errors = _check_section_keys(
        root["server"],
        EXPECTED_SERVER_KEYS,
        "server",
    )
    errors.extend(server_errors)
    if server_table is None:
        return errors

    if "telemetry" in server_table:
        telemetry, telemetry_errors = _check_section_keys(
            server_table["telemetry"],
            EXPECTED_TELEMETRY_KEYS,
            "server.telemetry",
        )
        errors.extend(telemetry_errors)
        if telemetry is not None:
            errors.extend(
                _validate_bool(telemetry, "server.telemetry.enableTelemetry", "enableTelemetry")
            )
            errors.extend(
                _validate_uuid(telemetry, "server.telemetry.telemetryUUID", "telemetryUUID")
            )

    if "gaia" in server_table:
        gaia, gaia_errors = _check_section_keys(
            server_table["gaia"],
            EXPECTED_GAIA_KEYS,
            "server.gaia",
        )
        errors.extend(gaia_errors)
        if gaia is not None:
            errors.extend(
                _validate_bool(gaia, "server.gaia.disableGaiaDisarm", "disableGaiaDisarm")
            )
            errors.extend(
                _validate_non_empty_str_list(
                    gaia,
                    "server.gaia.gaiaSpawnUnCheckList",
                    "gaiaSpawnUnCheckList",
                    rationale=(
                        "ExtraBotany Gaia III spawn checks match each entry as a non-empty "
                        "mod ID or namespace:item identifier."
                    ),
                )
            )

    if "fakePlayer" in server_table:
        fake_player, fake_player_errors = _check_section_keys(
            server_table["fakePlayer"],
            EXPECTED_FAKE_PLAYER_KEYS,
            "server.fakePlayer",
        )
        errors.extend(fake_player_errors)
        if fake_player is not None:
            errors.extend(
                _validate_non_empty_str(
                    fake_player,
                    "server.fakePlayer.fakePlayerId",
                    "fakePlayerId",
                    rationale=(
                        "ExtraBotany uses fakePlayerId as the Forge GameProfile name for "
                        "permission and claim-protection checks."
                    ),
                )
            )

    if "flower" in server_table:
        flower_table, flower_errors = _check_section_keys(
            server_table["flower"],
            tuple(FLOWER_SCHEMA.keys()),
            "server.flower",
        )
        errors.extend(flower_errors)
        if flower_table is not None:
            errors.extend(_validate_flowers(flower_table))

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/extrabotany/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_extrabotany_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated ExtraBotany static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "extrabotany",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place ExtraBotany static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
