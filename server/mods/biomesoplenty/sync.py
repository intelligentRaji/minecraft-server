#!/usr/bin/env python3
"""One-way deterministic configuration placement for Biomes O' Plenty.

Places static configuration from `mods/biomesoplenty/configs/` into `data/`:
- `config/biomesoplenty/biome_toggles.json` -> `data/config/biomesoplenty/biome_toggles.json`
- `config/biomesoplenty/gameplay.toml` -> `data/config/biomesoplenty/gameplay.toml`
- `config/biomesoplenty/generation.toml` -> `data/config/biomesoplenty/generation.toml`

Validates schema types, exact table/root keys, non-negative region weight invariants,
runtime state isolation, and secret guards before touching `data/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    check_table_keys,
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

BIOME_TOGGLES_REL_PATH = "config/biomesoplenty/biome_toggles.json"
GAMEPLAY_REL_PATH = "config/biomesoplenty/gameplay.toml"
GENERATION_REL_PATH = "config/biomesoplenty/generation.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    BIOME_TOGGLES_REL_PATH: ("config", "biomesoplenty", "biome_toggles.json"),
    GAMEPLAY_REL_PATH: ("config", "biomesoplenty", "gameplay.toml"),
    GENERATION_REL_PATH: ("config", "biomesoplenty", "generation.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

EXPECTED_BIOME_TOGGLE_KEYS: tuple[str, ...] = (
    "aspen_glade_enabled",
    "auroral_garden_enabled",
    "bayou_enabled",
    "bog_enabled",
    "cold_desert_enabled",
    "coniferous_forest_enabled",
    "crag_enabled",
    "crystalline_chasm_enabled",
    "dead_forest_enabled",
    "dryland_enabled",
    "dune_beach_enabled",
    "erupting_inferno_enabled",
    "field_enabled",
    "fir_clearing_enabled",
    "floodplain_enabled",
    "forested_field_enabled",
    "fungal_jungle_enabled",
    "glowing_grotto_enabled",
    "grassland_enabled",
    "gravel_beach_enabled",
    "highland_enabled",
    "hot_springs_enabled",
    "jacaranda_glade_enabled",
    "jade_cliffs_enabled",
    "lavender_field_enabled",
    "lush_desert_enabled",
    "lush_savanna_enabled",
    "maple_woods_enabled",
    "marsh_enabled",
    "mediterranean_forest_enabled",
    "moor_enabled",
    "muskeg_enabled",
    "mystic_grove_enabled",
    "old_growth_dead_forest_enabled",
    "old_growth_woodland_enabled",
    "ominous_woods_enabled",
    "orchard_enabled",
    "origin_valley_enabled",
    "overgrown_greens_enabled",
    "pasture_enabled",
    "prairie_enabled",
    "pumpkin_patch_enabled",
    "rainforest_enabled",
    "redwood_forest_enabled",
    "rocky_rainforest_enabled",
    "rocky_shrubland_enabled",
    "scrubland_enabled",
    "seasonal_forest_enabled",
    "shrubland_enabled",
    "snowblossom_grove_enabled",
    "snowy_coniferous_forest_enabled",
    "snowy_fir_clearing_enabled",
    "snowy_maple_woods_enabled",
    "spider_nest_enabled",
    "tropics_enabled",
    "tundra_enabled",
    "undergrowth_enabled",
    "visceral_heap_enabled",
    "volcanic_plains_enabled",
    "volcano_enabled",
    "wasteland_enabled",
    "wasteland_steppe_enabled",
    "wetland_enabled",
    "wintry_origin_valley_enabled",
    "withered_abyss_enabled",
    "woodland_enabled",
)

GAMEPLAY_TABLES: dict[str, tuple[str, ...]] = {
    "general": ("wandering_trader_trades",),
}

GENERATION_TABLES: dict[str, tuple[str, ...]] = {
    "nether": (
        "bop_nether_region_weight",
        "bop_nether_rare_region_weight",
    ),
    "overworld": (
        "bop_primary_overworld_region_weight",
        "bop_overworld_rare_region_weight",
        "bop_secondary_overworld_region_weight",
    ),
}


def validate_biome_toggles(data: object) -> list[str]:
    """Validate schema and strict boolean types for `config/biomesoplenty/biome_toggles.json`."""
    if not isinstance(data, dict):
        return [
            f"{BIOME_TOGGLES_REL_PATH} invariant violation: root JSON value must be an object "
            f"(got {type(data).__name__}) so Biomes O' Plenty can load its flat map of biome toggles."
        ]

    errors = [
        f"{err} (Biomes O' Plenty requires the exact 66 static *_enabled biome keys so worldgen "
        "biome registration remains deterministic across restarts)."
        for err in check_table_keys(data, BIOME_TOGGLES_REL_PATH, EXPECTED_BIOME_TOGGLE_KEYS)
    ]

    for key in EXPECTED_BIOME_TOGGLE_KEYS:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, bool):
            errors.append(
                f"{BIOME_TOGGLES_REL_PATH} invariant violation: '{key}' must be a boolean "
                f"(got {type(value).__name__}: {value!r}) because Biomes O' Plenty parses each "
                "biome toggle as a strict true/false flag."
            )

    return errors


def validate_gameplay(data: object) -> list[str]:
    """Validate schema and strict boolean type for `config/biomesoplenty/gameplay.toml`."""
    if not isinstance(data, dict):
        return [
            f"{GAMEPLAY_REL_PATH} invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so Biomes O' Plenty can parse its [general] section."
        ]

    errors = [
        f"{err} (Biomes O' Plenty gameplay.toml must define only the [general] table so "
        "unvalidated or runtime keys are never placed into data/config/biomesoplenty/)."
        for err in check_table_keys(data, GAMEPLAY_REL_PATH, GAMEPLAY_TABLES.keys())
    ]

    general = data.get("general")
    if "general" not in data:
        return errors

    if not isinstance(general, dict):
        errors.append(
            f"{GAMEPLAY_REL_PATH} invariant violation: [general] must be a TOML table "
            f"(got {type(general).__name__}) so Biomes O' Plenty can read gameplay flags."
        )
        return errors

    errors.extend(
        f"{err} (Biomes O' Plenty [general] must declare only 'wandering_trader_trades' so "
        "gameplay configuration remains deterministic)."
        for err in check_table_keys(
            general,
            f"{GAMEPLAY_REL_PATH} [general]",
            GAMEPLAY_TABLES["general"],
        )
    )

    if "wandering_trader_trades" in general:
        trades = general["wandering_trader_trades"]
        if not isinstance(trades, bool):
            errors.append(
                f"{GAMEPLAY_REL_PATH} invariant violation: [general].wandering_trader_trades "
                f"must be a boolean (got {type(trades).__name__}: {trades!r}) because "
                "Biomes O' Plenty reads it as a strict true/false Forge config toggle."
            )

    return errors


def validate_generation(data: object) -> list[str]:
    """Validate schema and non-negative integer invariants for `config/biomesoplenty/generation.toml`."""
    if not isinstance(data, dict):
        return [
            f"{GENERATION_REL_PATH} invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so Biomes O' Plenty can parse [nether] and [overworld]."
        ]

    errors = [
        f"{err} (Biomes O' Plenty generation.toml must define only [nether] and [overworld] "
        "tables so TerraBlender region weights remain deterministic)."
        for err in check_table_keys(data, GENERATION_REL_PATH, GENERATION_TABLES.keys())
    ]

    for table_name, expected_keys in GENERATION_TABLES.items():
        if table_name not in data:
            continue
        table = data[table_name]
        if not isinstance(table, dict):
            errors.append(
                f"{GENERATION_REL_PATH} invariant violation: [{table_name}] must be a TOML table "
                f"(got {type(table).__name__}) so Biomes O' Plenty can read {table_name} weights."
            )
            continue

        errors.extend(
            f"{err} (Biomes O' Plenty [{table_name}] must declare only its static region weight "
            "keys so world generation weights stay explicit and deterministic)."
            for err in check_table_keys(
                table,
                f"{GENERATION_REL_PATH} [{table_name}]",
                expected_keys,
            )
        )

        for key in expected_keys:
            if key not in table:
                continue
            value = table[key]
            if not is_strict_int(value) or value < 0:
                errors.append(
                    f"{GENERATION_REL_PATH} invariant violation: [{table_name}].{key} must be a "
                    f"non-negative integer >= 0 (got {type(value).__name__}: {value!r}) because "
                    "TerraBlender region weights cannot be negative, fractional, or boolean."
                )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/biomesoplenty/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            BIOME_TOGGLES_REL_PATH: validate_biome_toggles,
            GAMEPLAY_REL_PATH: validate_gameplay,
            GENERATION_REL_PATH: validate_generation,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Biomes O' Plenty static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "biomesoplenty",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Biomes O' Plenty static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
