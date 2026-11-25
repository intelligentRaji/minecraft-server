#!/usr/bin/env python3
"""One-way deterministic configuration placement for The Twilight Forest.

Places static configuration from `mods/twilightforest/configs/` into `data/`:
- `config/twilightforest-common.toml` -> `data/config/twilightforest-common.toml`

Validates TOML schema, value types, ranges, resource locations, runtime state
isolation, and secret guards before touching `data/`.
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

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

TARGET_REL_PATH = "config/twilightforest-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "twilightforest-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
    "twilightforest-client.toml",
    "twilightforest-server.toml",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

RESOURCE_LOCATION_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")

TOP_LEVEL_BOOL_KEYS: tuple[str, ...] = (
    "allowPortalsInOtherDimensions",
    "adminOnlyPortals",
    "disablePortalCreation",
    "checkPortalDestination",
    "portalLightning",
    "shouldReturnPortalBeUsable",
    "uuid_locking",
    "skull_candles",
    "default_item_enchantments",
    "boss_drop_chests",
)

TOP_LEVEL_SCALAR_KEYS: tuple[str, ...] = (
    "originDimension",
    "allowPortalsInOtherDimensions",
    "adminOnlyPortals",
    "disablePortalCreation",
    "checkPortalDestination",
    "portalLightning",
    "shouldReturnPortalBeUsable",
    "portalUnlockedByAdvancement",
    "maxPortalSize",
    "uuid_locking",
    "skull_candles",
    "default_item_enchantments",
    "boss_drop_chests",
    "cloudBlockPrecipitationDistance",
)

EXPECTED_TABLES: dict[str, tuple[str, ...]] = {
    "Dimension Settings": (
        "newPlayersSpawnInTF",
        "portalForNewPlayer",
    ),
    "Uncrafting Table": (
        "uncraftingXpCostMultiplier",
        "repairingXpCostMultiplier",
        "disableUncraftingRecipes",
        "flipRecipeList",
        "blacklistedUncraftingModIds",
        "flipIdList",
        "enableShapelessCrafting",
        "disableUncrafting",
        "disableUncraftingTable",
    ),
    "Magic Trees": (
        "disableTimeCore",
        "timeCoreRange",
        "disableTransformationCore",
        "transformationCoreRange",
        "disableMiningCore",
        "miningCoreRange",
        "disableSortingCore",
        "sortingCoreRange",
    ),
    "Shield Parrying": (
        "parryNonTwilightAttacks",
        "shieldParryTicksArrow",
    ),
}

EXPECTED_ROOT_KEYS: tuple[str, ...] = TOP_LEVEL_SCALAR_KEYS + tuple(EXPECTED_TABLES.keys())


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
            "all Twilight Forest common config sections and keys must be explicitly declared "
            "without extra or missing fields so dimension, portal, and progression rules "
            "remain deterministic and unvalidated or secret keys never reach data/."
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
            f"(got {type(val).__name__}: {val!r}) because Twilight Forest binds this setting "
            "as a strict true/false ForgeConfigSpec toggle."
        ]
    return []


def _validate_int_range(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    min_val: int,
    max_val: int | None = None,
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
    if val < min_val or (max_val is not None and val > max_val):
        bounds = f"[{min_val}, {max_val}]" if max_val is not None else f">= {min_val}"
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be {bounds} "
            f"(got {val}) because {rationale}"
        ]
    return []


def _validate_non_negative_number(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not is_finite_number(val) or val < 0.0:
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a finite "
            f"non-negative number >= 0.0 (got {type(val).__name__}: {val!r}) because {rationale}"
        ]
    return []


def _validate_resource_location(
    table: dict[str, Any],
    field_path: str,
    key: str,
    *,
    allow_empty: bool,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, str):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a string "
            f"(got {type(val).__name__}: {val!r}) because {rationale}"
        ]
    if allow_empty and val == "":
        return []
    if not RESOURCE_LOCATION_RE.match(val):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a valid "
            f"resource location 'namespace:path' (got {val!r}) because {rationale}"
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
                f"{TARGET_REL_PATH} invariant violation: '{field_path}[{idx}]' must be a "
                f"non-empty string (got {type(item).__name__}: {item!r}) because {rationale}"
            )
    return errors


def validate_twilightforest_common(data: object) -> list[str]:
    """Validate schema, types, and invariants for `config/twilightforest-common.toml`."""
    root, errors = _check_section_keys(data, EXPECTED_ROOT_KEYS, "root")
    if root is None:
        return errors

    errors.extend(
        _validate_resource_location(
            root,
            "originDimension",
            "originDimension",
            allow_empty=False,
            rationale=(
                "Twilight Forest resolves the origin/return dimension via a non-empty "
                "Minecraft ResourceLocation (e.g. 'minecraft:overworld')."
            ),
        )
    )
    errors.extend(
        _validate_resource_location(
            root,
            "portalUnlockedByAdvancement",
            "portalUnlockedByAdvancement",
            allow_empty=True,
            rationale=(
                "portal progression gating requires either an empty string (unlocked) or "
                "a valid Minecraft advancement ResourceLocation ('namespace:path')."
            ),
        )
    )

    for key in TOP_LEVEL_BOOL_KEYS:
        errors.extend(_validate_bool(root, key, key))

    errors.extend(
        _validate_int_range(
            root,
            "maxPortalSize",
            "maxPortalSize",
            min_val=4,
            rationale=(
                "a valid Twilight Forest portal requires at least a 2x2 water pool "
                "(>= 4 blocks) to form."
            ),
        )
    )
    errors.extend(
        _validate_int_range(
            root,
            "cloudBlockPrecipitationDistance",
            "cloudBlockPrecipitationDistance",
            min_val=0,
            rationale=(
                "cloud precipitation scan distance must be >= 0 blocks (0 disables "
                "cloud weather logic)."
            ),
        )
    )

    tables: dict[str, dict[str, Any]] = {}
    for table_name, expected_keys in EXPECTED_TABLES.items():
        if table_name not in root:
            continue
        parsed_table, table_errors = _check_section_keys(
            root[table_name],
            expected_keys,
            table_name,
        )
        errors.extend(table_errors)
        if parsed_table is not None:
            tables[table_name] = parsed_table

    dim_settings = tables.get("Dimension Settings")
    if dim_settings is not None:
        errors.extend(
            _validate_bool(
                dim_settings,
                "Dimension Settings.newPlayersSpawnInTF",
                "newPlayersSpawnInTF",
            )
        )
        errors.extend(
            _validate_bool(
                dim_settings,
                "Dimension Settings.portalForNewPlayer",
                "portalForNewPlayer",
            )
        )

    uncrafting = tables.get("Uncrafting Table")
    if uncrafting is not None:
        errors.extend(
            _validate_non_negative_number(
                uncrafting,
                "Uncrafting Table.uncraftingXpCostMultiplier",
                "uncraftingXpCostMultiplier",
                rationale=(
                    "Twilight Forest multiplies uncrafting XP costs by a non-negative "
                    "finite factor (0.0 disables XP cost)."
                ),
            )
        )
        errors.extend(
            _validate_non_negative_number(
                uncrafting,
                "Uncrafting Table.repairingXpCostMultiplier",
                "repairingXpCostMultiplier",
                rationale=(
                    "Twilight Forest multiplies repairing XP costs by a non-negative "
                    "finite factor (0.0 disables XP cost)."
                ),
            )
        )
        errors.extend(
            _validate_non_empty_str_list(
                uncrafting,
                "Uncrafting Table.disableUncraftingRecipes",
                "disableUncraftingRecipes",
                rationale=(
                    "every disabled uncrafting recipe entry must be a non-empty recipe ID string."
                ),
            )
        )
        errors.extend(
            _validate_non_empty_str_list(
                uncrafting,
                "Uncrafting Table.blacklistedUncraftingModIds",
                "blacklistedUncraftingModIds",
                rationale=(
                    "every blacklisted uncrafting mod entry must be a non-empty mod ID string."
                ),
            )
        )
        for bool_key in (
            "flipRecipeList",
            "flipIdList",
            "enableShapelessCrafting",
            "disableUncrafting",
            "disableUncraftingTable",
        ):
            errors.extend(
                _validate_bool(uncrafting, f"Uncrafting Table.{bool_key}", bool_key)
            )

    magic_trees = tables.get("Magic Trees")
    if magic_trees is not None:
        for bool_key, range_key in (
            ("disableTimeCore", "timeCoreRange"),
            ("disableTransformationCore", "transformationCoreRange"),
            ("disableMiningCore", "miningCoreRange"),
            ("disableSortingCore", "sortingCoreRange"),
        ):
            errors.extend(_validate_bool(magic_trees, f"Magic Trees.{bool_key}", bool_key))
            errors.extend(
                _validate_int_range(
                    magic_trees,
                    f"Magic Trees.{range_key}",
                    range_key,
                    min_val=1,
                    max_val=128,
                    rationale=(
                        "Twilight Forest enforces Magic Tree core radius within [1, 128] "
                        "blocks to prevent chunk-scan lag or invalid zero ranges."
                    ),
                )
            )

    shield_parrying = tables.get("Shield Parrying")
    if shield_parrying is not None:
        errors.extend(
            _validate_bool(
                shield_parrying,
                "Shield Parrying.parryNonTwilightAttacks",
                "parryNonTwilightAttacks",
            )
        )
        errors.extend(
            _validate_int_range(
                shield_parrying,
                "Shield Parrying.shieldParryTicksArrow",
                "shieldParryTicksArrow",
                min_val=0,
                rationale=(
                    "shield parry tick window must be >= 0 ticks."
                ),
            )
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/twilightforest/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_twilightforest_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Twilight Forest static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "twilightforest",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Twilight Forest static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
