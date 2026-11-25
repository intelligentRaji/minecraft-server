#!/usr/bin/env python3
"""One-way deterministic configuration placement for Dynamic Trees.

Places static configuration from `mods/dynamictrees/configs/` into `data/`:
- `config/dynamictrees-common.toml` -> `data/config/dynamictrees-common.toml`
- `world/serverconfig/dynamictrees-server.toml` -> `data/world/serverconfig/dynamictrees-server.toml`

Validates schema types, exact table/root keys, enum values, numeric bounds,
runtime state isolation, and secret guards before touching `data/`.
"""

from __future__ import annotations

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

COMMON_REL_PATH = "config/dynamictrees-common.toml"
SERVER_REL_PATH = "world/serverconfig/dynamictrees-server.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    COMMON_REL_PATH: ("config", "dynamictrees-common.toml"),
    SERVER_REL_PATH: ("world", "serverconfig", "dynamictrees-server.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "mods",
    "region",
    "DIM1",
    "DIM-1",
    "playerdata",
    "entities",
    "poi",
    "level.dat",
    "session.lock",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

SWAMP_OAKS_MODES: frozenset[str] = frozenset({"ROOTED", "SUNK", "DISABLED"})
AXE_DAMAGE_MODES: frozenset[str] = frozenset({"VANILLA", "THICKNESS", "VOLUME"})

COMMON_TABLES: dict[str, tuple[str, ...]] = {
    "vanilla": (
        "replaceVanillaSapling",
        "replaceNyliumFungi",
        "cancelVanillaVillageTrees",
    ),
    "misc": (
        "generateDirtBucketRecipes",
        "generateMegaSeedRecipe",
        "biocharBrewingBase",
    ),
    "integration": (
        "preferredSeasonMod",
        "enableSeasonalSeedDropFactor",
        "enableSeasonalGrowthFactor",
        "enableSeasonalFruitProductionFactor",
    ),
}

SERVER_ROOT_KEYS: tuple[str, ...] = (
    "growthFolding",
    "seeds",
    "trees",
    "interaction",
    "world",
    "debug",
)

SERVER_TABLES: dict[str, tuple[str, ...]] = {
    "seeds": (
        "leavesSeedDropRate",
        "voluntarySeedDropRate",
        "seedPlantRate",
        "timeToLive",
        "seedOnlyForest",
        "seedMinForestness",
    ),
    "trees": (
        "growthMultiplier",
        "harvestMultiplier",
        "maxTreeHardness",
        "treeHardnessMultiplier",
        "growthFolding",
        "dropSticks",
        "scaleBiomeGrowthRate",
        "diseaseChance",
        "maxBranchRotRadius",
        "rootyBlockHardnessMultiplier",
        "swampOaksInWater",
        "boneMealGrowthPulses",
    ),
    "interaction": (
        "isLeavesPassable",
        "vanillaLeavesCollision",
        "enableBranchClimbling",
        "canopyCrash",
        "axeDamageMode",
        "enableFallingTrees",
        "enableFallingTreeDamage",
        "fallingTreeDamageMultiplier",
        "dirtBucketPlacesDirt",
        "sloppyBreakDrops",
        "minRadiusForStrip",
        "enableStripRadiusReduction",
        "canBoneMealFruit",
        "canBoneMealPods",
        "dynamicSaplingDrops",
    ),
    "world": (
        "podzolGen",
        "worldGen",
        "dimensionsBlacklist",
    ),
    "debug": ("debug",),
}

SEEDS_FLOAT_RANGES: dict[str, tuple[float, float]] = {
    "leavesSeedDropRate": (0.0, 64.0),
    "voluntarySeedDropRate": (0.0, 1.0),
    "seedPlantRate": (0.0, 1.0),
    "seedMinForestness": (0.0, 1.0),
}

TREES_FLOAT_RANGES: dict[str, tuple[float, float]] = {
    "growthMultiplier": (0.0, 16.0),
    "harvestMultiplier": (0.0, 128.0),
    "maxTreeHardness": (1.0, 200.0),
    "treeHardnessMultiplier": (0.0078125, 32.0),
    "scaleBiomeGrowthRate": (0.0, 1.0),
    "diseaseChance": (0.0, 1.0),
    "rootyBlockHardnessMultiplier": (0.0, 128.0),
}

TREES_INT_RANGES: dict[str, tuple[int, int]] = {
    "growthFolding": (1, 8),
    "maxBranchRotRadius": (0, 24),
    "boneMealGrowthPulses": (1, 512),
}

INTERACTION_BOOL_KEYS: tuple[str, ...] = (
    "isLeavesPassable",
    "vanillaLeavesCollision",
    "enableBranchClimbling",
    "canopyCrash",
    "enableFallingTrees",
    "enableFallingTreeDamage",
    "dirtBucketPlacesDirt",
    "sloppyBreakDrops",
    "enableStripRadiusReduction",
    "canBoneMealFruit",
    "canBoneMealPods",
    "dynamicSaplingDrops",
)


def _check_bools(
    table: dict[str, Any],
    label: str,
    keys: tuple[str, ...],
    rationale: str,
) -> list[str]:
    errors: list[str] = []
    for key in keys:
        if key not in table:
            continue
        value = table[key]
        if not isinstance(value, bool):
            errors.append(
                f"{label}.{key} invariant violation: must be a boolean "
                f"(got {type(value).__name__}: {value!r}) because {rationale}."
            )
    return errors


def _check_int_range(
    table: dict[str, Any],
    label: str,
    key: str,
    min_val: int,
    max_val: int,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    value = table[key]
    if not is_strict_int(value) or not (min_val <= value <= max_val):
        return [
            f"{label}.{key} invariant violation: must be an integer in "
            f"[{min_val}, {max_val}] (got {type(value).__name__}: {value!r}) "
            f"because {rationale}."
        ]
    return []


def _check_number_range(
    table: dict[str, Any],
    label: str,
    key: str,
    min_val: float,
    max_val: float,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    value = table[key]
    if not is_finite_number(value) or not (min_val <= value <= max_val):
        return [
            f"{label}.{key} invariant violation: must be a finite number in "
            f"[{min_val}, {max_val}] (got {type(value).__name__}: {value!r}) "
            f"because {rationale}."
        ]
    return []


def _check_nonempty_str(
    table: dict[str, Any],
    label: str,
    key: str,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        return [
            f"{label}.{key} invariant violation: must be a non-empty string "
            f"(got {type(value).__name__}: {value!r}) because {rationale}."
        ]
    return []


def _check_enum(
    table: dict[str, Any],
    label: str,
    key: str,
    allowed: frozenset[str],
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    value = table[key]
    if not isinstance(value, str) or value not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        return [
            f"{label}.{key} invariant violation: must be one of {{{allowed_list}}} "
            f"(got {type(value).__name__}: {value!r}) because {rationale}."
        ]
    return []


def validate_common(data: object) -> list[str]:
    """Validate schema and types for `config/dynamictrees-common.toml`."""
    if not isinstance(data, dict):
        return [
            f"{COMMON_REL_PATH} invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so Dynamic Trees can load [vanilla], [misc], "
            "and [integration] sections."
        ]

    errors = [
        f"{err} (Dynamic Trees common config must declare only [vanilla], [misc], "
        "and [integration] so no unvalidated or runtime keys are placed into data/config/)."
        for err in check_table_keys(data, COMMON_REL_PATH, COMMON_TABLES.keys())
    ]

    for table_name, expected_keys in COMMON_TABLES.items():
        if table_name not in data:
            continue
        table = data[table_name]
        if not isinstance(table, dict):
            errors.append(
                f"{COMMON_REL_PATH} invariant violation: [{table_name}] must be a TOML table "
                f"(got {type(table).__name__}) so Dynamic Trees can read {table_name} settings."
            )
            continue
        errors.extend(
            f"{err} (Dynamic Trees [{table_name}] must contain only its static Forge config "
            "keys so common settings remain deterministic across restarts)."
            for err in check_table_keys(
                table,
                f"{COMMON_REL_PATH} [{table_name}]",
                expected_keys,
            )
        )

    if isinstance(data.get("vanilla"), dict):
        errors.extend(
            _check_bools(
                data["vanilla"],
                f"{COMMON_REL_PATH} [vanilla]",
                COMMON_TABLES["vanilla"],
                "Dynamic Trees reads vanilla tree/sapling replacement flags as strict booleans",
            )
        )

    if isinstance(data.get("misc"), dict):
        misc = data["misc"]
        errors.extend(
            _check_bools(
                misc,
                f"{COMMON_REL_PATH} [misc]",
                ("generateDirtBucketRecipes", "generateMegaSeedRecipe"),
                "Dynamic Trees reads recipe generation toggles as strict booleans",
            )
        )
        errors.extend(
            _check_nonempty_str(
                misc,
                f"{COMMON_REL_PATH} [misc]",
                "biocharBrewingBase",
                "Dynamic Trees resolves biocharBrewingBase as a potion registry name",
            )
        )

    if isinstance(data.get("integration"), dict):
        integration = data["integration"]
        errors.extend(
            _check_nonempty_str(
                integration,
                f"{COMMON_REL_PATH} [integration]",
                "preferredSeasonMod",
                "Dynamic Trees expects a mod ID, '*', or '!' for season mod selection",
            )
        )
        errors.extend(
            _check_bools(
                integration,
                f"{COMMON_REL_PATH} [integration]",
                (
                    "enableSeasonalSeedDropFactor",
                    "enableSeasonalGrowthFactor",
                    "enableSeasonalFruitProductionFactor",
                ),
                "Dynamic Trees reads seasonal integration flags as strict booleans",
            )
        )

    return errors


def validate_server(data: object) -> list[str]:
    """Validate schema, enums, and numeric ranges for `world/serverconfig/dynamictrees-server.toml`."""
    if not isinstance(data, dict):
        return [
            f"{SERVER_REL_PATH} invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so Dynamic Trees can load serverconfig settings."
        ]

    errors = [
        f"{err} (Dynamic Trees serverconfig must declare only its static root key and "
        "sections so runtime world state is never mixed into versioned configs)."
        for err in check_table_keys(data, SERVER_REL_PATH, SERVER_ROOT_KEYS)
    ]

    errors.extend(
        _check_int_range(
            data,
            SERVER_REL_PATH,
            "growthFolding",
            0,
            4096,
            "Forge bounds root falling-tree leaf particle limit to 0..4096 to prevent server lag",
        )
    )

    for table_name, expected_keys in SERVER_TABLES.items():
        if table_name not in data:
            continue
        table = data[table_name]
        if not isinstance(table, dict):
            errors.append(
                f"{SERVER_REL_PATH} invariant violation: [{table_name}] must be a TOML table "
                f"(got {type(table).__name__}) so Dynamic Trees can read {table_name} settings."
            )
            continue
        errors.extend(
            f"{err} (Dynamic Trees [{table_name}] must contain only its static Forge config "
            "keys so server behavior remains deterministic)."
            for err in check_table_keys(
                table,
                f"{SERVER_REL_PATH} [{table_name}]",
                expected_keys,
            )
        )

    if isinstance(data.get("seeds"), dict):
        seeds = data["seeds"]
        seed_label = f"{SERVER_REL_PATH} [seeds]"
        for key, (lo, hi) in SEEDS_FLOAT_RANGES.items():
            errors.extend(
                _check_number_range(
                    seeds,
                    seed_label,
                    key,
                    lo,
                    hi,
                    "Forge enforces bounded seed drop/plant probability and rate ranges",
                )
            )
        errors.extend(
            _check_int_range(
                seeds,
                seed_label,
                "timeToLive",
                0,
                6000,
                "Forge bounds seed entity TTL to 0..6000 ticks (up to 5 minutes)",
            )
        )
        errors.extend(
            _check_bools(
                seeds,
                seed_label,
                ("seedOnlyForest",),
                "Dynamic Trees reads seedOnlyForest as a strict true/false toggle",
            )
        )

    if isinstance(data.get("trees"), dict):
        trees = data["trees"]
        trees_label = f"{SERVER_REL_PATH} [trees]"
        for key, (lo, hi) in TREES_FLOAT_RANGES.items():
            errors.extend(
                _check_number_range(
                    trees,
                    trees_label,
                    key,
                    lo,
                    hi,
                    "Forge enforces bounded tree growth, hardness, and rot multipliers",
                )
            )
        for key, (lo, hi) in TREES_INT_RANGES.items():
            errors.extend(
                _check_int_range(
                    trees,
                    trees_label,
                    key,
                    lo,
                    hi,
                    "Forge enforces bounded integer growth/rot/bonemeal parameters",
                )
            )
        errors.extend(
            _check_bools(
                trees,
                trees_label,
                ("dropSticks",),
                "Dynamic Trees reads dropSticks as a strict true/false toggle",
            )
        )
        errors.extend(
            _check_enum(
                trees,
                trees_label,
                "swampOaksInWater",
                SWAMP_OAKS_MODES,
                "Dynamic Trees only supports ROOTED, SUNK, or DISABLED for swamp oak generation",
            )
        )

    if isinstance(data.get("interaction"), dict):
        interaction = data["interaction"]
        inter_label = f"{SERVER_REL_PATH} [interaction]"
        errors.extend(
            _check_bools(
                interaction,
                inter_label,
                INTERACTION_BOOL_KEYS,
                "Dynamic Trees reads interaction flags as strict true/false Forge config toggles",
            )
        )
        errors.extend(
            _check_enum(
                interaction,
                inter_label,
                "axeDamageMode",
                AXE_DAMAGE_MODES,
                "Dynamic Trees only supports VANILLA, THICKNESS, or VOLUME for axe durability damage",
            )
        )
        errors.extend(
            _check_number_range(
                interaction,
                inter_label,
                "fallingTreeDamageMultiplier",
                0.0,
                100.0,
                "Forge bounds falling tree entity damage multiplier to 0.0..100.0",
            )
        )
        errors.extend(
            _check_int_range(
                interaction,
                inter_label,
                "minRadiusForStrip",
                0,
                24,
                "Forge bounds branch stripping minimum radius to 0..24",
            )
        )

    if isinstance(data.get("world"), dict):
        world = data["world"]
        world_label = f"{SERVER_REL_PATH} [world]"
        errors.extend(
            _check_bools(
                world,
                world_label,
                ("podzolGen", "worldGen"),
                "Dynamic Trees reads worldgen toggles as strict true/false flags",
            )
        )
        if "dimensionsBlacklist" in world:
            blacklist = world["dimensionsBlacklist"]
            if not isinstance(blacklist, list) or not all(
                isinstance(item, str) and bool(item.strip()) for item in blacklist
            ):
                errors.append(
                    f"{world_label}.dimensionsBlacklist invariant violation: must be a list "
                    f"of non-empty dimension registry name strings (got {blacklist!r}) because "
                    "Dynamic Trees matches each entry against ResourceLocation dimension IDs."
                )

    if isinstance(data.get("debug"), dict):
        errors.extend(
            _check_bools(
                data["debug"],
                f"{SERVER_REL_PATH} [debug]",
                ("debug",),
                "Dynamic Trees reads [debug].debug as a strict true/false toggle",
            )
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/dynamictrees/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            COMMON_REL_PATH: validate_common,
            SERVER_REL_PATH: validate_server,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Dynamic Trees static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "dynamictrees",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Dynamic Trees static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
