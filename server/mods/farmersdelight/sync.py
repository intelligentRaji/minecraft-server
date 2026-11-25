#!/usr/bin/env python3
"""One-way deterministic configuration placement for Farmer's Delight.

Places static configuration from `mods/farmersdelight/configs/` into `data/`:
- `config/farmersdelight-common.toml` -> `data/config/farmersdelight-common.toml`

Validates TOML schema, value types, ranges, dye/resource-location invariants,
runtime state isolation, and secret guards before touching `data/`.
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
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

TARGET_REL_PATH = "config/farmersdelight-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "farmersdelight-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

MINECRAFT_DYE_COLORS: frozenset[str] = frozenset({
    "white",
    "orange",
    "magenta",
    "light_blue",
    "yellow",
    "lime",
    "pink",
    "gray",
    "light_gray",
    "cyan",
    "purple",
    "blue",
    "brown",
    "green",
    "red",
    "black",
})

RESOURCE_LOCATION_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")

EXPECTED_TABLES: dict[str, tuple[str, ...]] = {
    "settings": (
        "enableFarmerFDTrades",
        "enableWanderingTraderFDTrades",
        "enableRopeReeling",
        "canvasSignDarkBackgroundList",
    ),
    "farming": (
        "richSoilBoostChance",
        "enableTomatoVineClimbingTaggedRopes",
        "defaultTomatoVineRope",
    ),
    "crafting": (
        "enableCookingPotRecipeBook",
        "enableVanillaCropCrates",
        "cuttingBoardFortuneBonus",
    ),
    "overrides": (
        "enableVanillaSoupExtraEffects",
        "enableRabbitStewJumpBoost",
        "enablePumpkinPieSneakToPlace",
        "enableCuttingBoardDispenserBehavior",
        "stack_size",
    ),
    "world": (
        "generateFDChestLoot",
        "generateVillageCompostHeaps",
        "generateFDCropsOnVillageFarms",
    ),
    "debug": (
        "enableTomatoRopePermanence",
    ),
}

EXPECTED_STACK_SIZE_KEYS: tuple[str, ...] = (
    "enableStackableSoupItems",
    "soupItemList",
)

BOOL_KEYS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "settings": (
        "enableFarmerFDTrades",
        "enableWanderingTraderFDTrades",
        "enableRopeReeling",
    ),
    "farming": ("enableTomatoVineClimbingTaggedRopes",),
    "crafting": (
        "enableCookingPotRecipeBook",
        "enableVanillaCropCrates",
    ),
    "overrides": (
        "enableVanillaSoupExtraEffects",
        "enableRabbitStewJumpBoost",
        "enablePumpkinPieSneakToPlace",
        "enableCuttingBoardDispenserBehavior",
    ),
    "world": (
        "generateFDChestLoot",
        "generateVillageCompostHeaps",
        "generateFDCropsOnVillageFarms",
    ),
    "debug": ("enableTomatoRopePermanence",),
}

UNIT_FLOAT_KEYS: tuple[tuple[str, str], ...] = (
    ("farming", "richSoilBoostChance"),
    ("crafting", "cuttingBoardFortuneBonus"),
)


def _check_table_keys(
    table: object,
    expected_keys: tuple[str, ...],
    table_label: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Verify `table` is a dict with exact `expected_keys`, returning `(table, errors)`."""
    if not isinstance(table, dict):
        return None, [
            f"{TARGET_REL_PATH} invariant violation: '{table_label}' must be a TOML table "
            f"(got {type(table).__name__}) so Farmer's Delight can bind its ForgeConfigSpec section."
        ]

    errors: list[str] = []
    expected_set = set(expected_keys)
    actual_set = set(table.keys())

    missing = sorted(expected_set - actual_set)
    if missing:
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: '{table_label}' is missing required keys "
            f"{missing} (all Farmer's Delight common config keys must be explicitly declared so "
            "server gameplay and worldgen behavior remain deterministic across restarts)."
        )

    unexpected = sorted(actual_set - expected_set)
    if unexpected:
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: '{table_label}' contains unexpected keys "
            f"{unexpected} (only documented Farmer's Delight keys are permitted so unvalidated "
            "or secret fields are never synced into data/)."
        )

    return table, errors


def _validate_bool(table: dict[str, Any], table_label: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, bool):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{table_label}.{key}' must be a boolean "
            f"(got {type(val).__name__}: {val!r}) because ForgeConfigSpec reads this flag as a "
            "strict true/false toggle."
        ]
    return []


def _validate_unit_float(table: dict[str, Any], table_label: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{table_label}.{key}' must be a number in "
            f"[0.0, 1.0] (got {type(val).__name__}: {val!r}) because Farmer's Delight interprets "
            "this value as a decimal probability."
        ]
    return []


def _validate_resource_location(value: object, field_path: str) -> list[str]:
    if not isinstance(value, str) or not RESOURCE_LOCATION_RE.match(value):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a valid Minecraft "
            f"resource location matching '^[a-z0-9_.-]+:[a-z0-9_./-]+$' (got {value!r}) so "
            "Farmer's Delight can resolve the block or item in the Forge registry."
        ]
    return []


def validate_farmersdelight_common(data: object) -> list[str]:
    """Validate schema, types, and invariants for `config/farmersdelight-common.toml`."""
    root, errors = _check_table_keys(data, tuple(EXPECTED_TABLES.keys()), "root")
    if root is None:
        return errors

    tables: dict[str, dict[str, Any]] = {}
    for table_name, expected_keys in EXPECTED_TABLES.items():
        if table_name not in root:
            continue
        parsed_table, table_errors = _check_table_keys(root[table_name], expected_keys, table_name)
        errors.extend(table_errors)
        if parsed_table is not None:
            tables[table_name] = parsed_table

    for table_name, bool_keys in BOOL_KEYS_BY_TABLE.items():
        table = tables.get(table_name)
        if table is None:
            continue
        for key in bool_keys:
            errors.extend(_validate_bool(table, table_name, key))

    for table_name, key in UNIT_FLOAT_KEYS:
        table = tables.get(table_name)
        if table is not None:
            errors.extend(_validate_unit_float(table, table_name, key))

    settings = tables.get("settings")
    if settings is not None and "canvasSignDarkBackgroundList" in settings:
        dye_list = settings["canvasSignDarkBackgroundList"]
        if not isinstance(dye_list, list):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: 'settings.canvasSignDarkBackgroundList' "
                f"must be a list of Minecraft dye color names (got {type(dye_list).__name__})."
            )
        else:
            for idx, dye in enumerate(dye_list):
                if not isinstance(dye, str) or dye not in MINECRAFT_DYE_COLORS:
                    errors.append(
                        f"{TARGET_REL_PATH} invariant violation: "
                        f"'settings.canvasSignDarkBackgroundList[{idx}]' must be one of the 16 "
                        f"Minecraft dye colors {sorted(MINECRAFT_DYE_COLORS)} (got {dye!r}) so "
                        "Canvas Sign text contrast mapping never references an unknown DyeColor."
                    )

    farming = tables.get("farming")
    if farming is not None and "defaultTomatoVineRope" in farming:
        errors.extend(
            _validate_resource_location(
                farming["defaultTomatoVineRope"],
                "farming.defaultTomatoVineRope",
            )
        )

    overrides = tables.get("overrides")
    if overrides is not None and "stack_size" in overrides:
        stack_size, ss_errors = _check_table_keys(
            overrides["stack_size"],
            EXPECTED_STACK_SIZE_KEYS,
            "overrides.stack_size",
        )
        errors.extend(ss_errors)
        if stack_size is not None:
            errors.extend(
                _validate_bool(stack_size, "overrides.stack_size", "enableStackableSoupItems")
            )
            if "soupItemList" in stack_size:
                soup_list = stack_size["soupItemList"]
                if not isinstance(soup_list, list):
                    errors.append(
                        f"{TARGET_REL_PATH} invariant violation: "
                        "'overrides.stack_size.soupItemList' must be a list of resource location "
                        f"strings (got {type(soup_list).__name__})."
                    )
                else:
                    for idx, item_id in enumerate(soup_list):
                        errors.extend(
                            _validate_resource_location(
                                item_id,
                                f"overrides.stack_size.soupItemList[{idx}]",
                            )
                        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/farmersdelight/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_farmersdelight_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Farmer's Delight static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "farmersdelight",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Farmer's Delight static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
