#!/usr/bin/env python3
"""One-way deterministic configuration placement for Vanilla Backport.

Places static configuration from `mods/vanillabackport/configs/` into `data/`:
- `config/vanillabackport-common.toml` -> `data/config/vanillabackport-common.toml`

Validates schema types, exact TOML tables and keys, enum/range/cross-key
invariants, runtime state isolation, and secret guards before touching `data/`.
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
    is_finite_number,
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

TARGET_REL_PATH = "config/vanillabackport-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "vanillabackport-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

RECIPE_MODES: frozenset[str] = frozenset({"APPEND", "REPLACE", "IGNORE"})

# Field kinds:
# - "bool": strict boolean
# - "recipe": string in {"APPEND", "REPLACE", "IGNORE"}
# - "rgb": strict int in [0, 0xFFFFFF]
# - "chance": finite number in [0.0, 1.0]
# - "non_neg_float": finite number >= 0.0
# - "pos_int": strict int > 0
# - "gt1_int": strict int > 1
TABLE_SCHEMAS: dict[str, dict[str, str]] = {
    "Tricky Trials": {
        "tuff_blocks": "bool",
        "copper_blockset": "bool",
    },
    "Armored Paws": {
        "armadillo": "bool",
        "wolf_variants": "bool",
        "updated_wolf_spawns": "bool",
    },
    "Bundles of Bravery": {
        "has_updated_bundles": "bool",
        "bundle_loot": "bool",
        "has_dyeable_bundle_recipe": "bool",
        "inverted_bundle_controls": "bool",
        "bundle_recipe": "recipe",
    },
    "The Garden Awakens": {
        "resin": "bool",
        "resin_loot": "bool",
        "creaking": "bool",
        "pale_garden": "bool",
        "pale_trades": "bool",
        "creaking_particle_color": "rgb",
        "creaking_particle_reverse_color": "rgb",
        "do_creaking_hearts_work_on_day": "bool",
        "lead_recipe": "recipe",
        "saddle_recipe": "recipe",
    },
    "Spring to Life": {
        "bushes": "bool",
        "firefly_bushes": "bool",
        "wildflowers": "bool",
        "dry_grass": "bool",
        "fallen_trees": "bool",
        "leaf_litter": "bool",
        "cactus_flowers": "bool",
        "farm_animal_variants": "bool",
        "wolf_sound_variants": "bool",
        "camel_spawns": "bool",
        "spring_trades": "bool",
        "lodestone_loot": "bool",
        "mob_variants_spawn_chance": "chance",
        "cactus_flower_spawn_chance": "chance",
        "lodestone_recipe": "recipe",
    },
    "Chase the Skies": {
        "dried_ghasts": "bool",
        "leash_drop_connections": "bool",
        "tears_music_disc": "bool",
        "happy_ghast_speed_modifier": "non_neg_float",
        "modern_leashes": "bool",
    },
    "Hot as Lava": {
        "lava_chicken_music_disc": "bool",
    },
    "Copper Age": {
        "has_copper_horse_armor_loot": "bool",
        "has_copper_golems": "bool",
        "golem_weathering_tick_from": "pos_int",
        "golem_weathering_tick_to": "pos_int",
        "golem_item_carry_amount": "gt1_int",
        "has_copper_nuggets": "bool",
        "has_copper_toolset": "bool",
        "has_weathering_lightning_rods": "bool",
    },
    "Mounts of Mayhem": {
        "has_parched_skeletons": "bool",
        "has_camel_husks": "bool",
        "has_nautilus": "bool",
        "has_zombie_horses": "bool",
        "zombie_nautilus_spawn_chance": "chance",
        "has_nautilus_armor_loot": "bool",
        "has_spears": "bool",
        "can_mounts_float_while_ridden": "bool",
    },
    "Chaos Cubed": {
        "has_sulfur_caves": "bool",
        "has_sulfur_springs": "bool",
        "do_geysers_erupt": "bool",
        "has_sulfur_cubes": "bool",
        "do_sulfur_cubes_explode": "bool",
        "do_sulfur_cubes_damage": "bool",
        "do_merchant_trade_chaos_cubed_contents": "bool",
        "has_bounce_music_disc": "bool",
    },
    "Wilderness Bound": {
        "has_dappled_forest": "bool",
    },
}


def _validate_field(table_name: str, key: str, value: object, kind: str) -> str | None:
    """Validate a single Vanilla Backport config field and return an explanatory error or None."""
    fq_key = f'["{table_name}"].{key}'

    if kind == "bool":
        if not isinstance(value, bool):
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be a boolean "
                f"(got {type(value).__name__}: {value!r}) because Forge's ConfigValue<Boolean> "
                "requires a strict true/false toggle at mod-loading time."
            )
        return None

    if kind == "recipe":
        if not isinstance(value, str) or value not in RECIPE_MODES:
            allowed = ", ".join(sorted(RECIPE_MODES))
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be one of {{{allowed}}} "
                f"(got {type(value).__name__}: {value!r}) because Vanilla Backport's Forge "
                "EnumValue recipe mode parser rejects unknown recipe strategies."
            )
        return None

    if kind == "rgb":
        if not is_strict_int(value) or not (0 <= value <= 0xFFFFFF):
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be a strict integer in "
                f"0..16777215 (0x000000..0xFFFFFF) (got {type(value).__name__}: {value!r}) "
                "because Creaking Heart trail particle colors are packed 24-bit RGB integers."
            )
        return None

    if kind == "chance":
        if not is_finite_number(value) or not (0.0 <= float(value) <= 1.0):
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be a finite number in "
                f"0.0..1.0 (got {type(value).__name__}: {value!r}) because Forge probability "
                "sliders clamp spawn chances to the unit interval."
            )
        return None

    if kind == "non_neg_float":
        if not is_finite_number(value) or float(value) < 0.0:
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be a finite number >= 0.0 "
                f"(got {type(value).__name__}: {value!r}) because negative movement speed "
                "multipliers would invert or stall Happy Ghast steering."
            )
        return None

    if kind == "pos_int":
        if not is_strict_int(value) or value <= 0:
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be a strict integer > 0 "
                f"(got {type(value).__name__}: {value!r}) because Forge's IntValue (> 0) rejects "
                "zero or negative Copper Golem weathering tick bounds."
            )
        return None

    if kind == "gt1_int":
        if not is_strict_int(value) or value <= 1:
            return (
                f"{TARGET_REL_PATH} invariant violation: {fq_key} must be a strict integer > 1 "
                f"(got {type(value).__name__}: {value!r}) because Forge's IntValue (> 1) requires "
                "Copper Golems to carry at least 2 items per transfer cycle."
            )
        return None

    raise AssertionError(f"Unhandled schema kind: {kind!r}")


def validate_vanillabackport_common(data: object) -> list[str]:
    """Validate schema, types, ranges, and cross-key invariants for `config/vanillabackport-common.toml`."""
    if not isinstance(data, dict):
        return [
            f"{TARGET_REL_PATH} invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so Forge can parse Vanilla Backport's 11 update sections."
        ]

    errors = [
        f"{err} (Vanilla Backport requires the exact 11 update sections in "
        "vanillabackport-common.toml so server/client feature flags stay synchronized and "
        "unvalidated or runtime keys are never placed into data/config/)."
        for err in check_table_keys(data, TARGET_REL_PATH, TABLE_SCHEMAS.keys())
    ]

    for table_name, field_specs in TABLE_SCHEMAS.items():
        if table_name not in data:
            continue
        table = data[table_name]
        if not isinstance(table, dict):
            errors.append(
                f'{TARGET_REL_PATH} invariant violation: ["{table_name}"] must be a TOML table '
                f"(got {type(table).__name__}) so Forge can read {table_name} feature flags."
            )
            continue

        errors.extend(
            f'{err} (Vanilla Backport ["{table_name}"] must declare only its static Forge '
            "config keys so server behavior remains deterministic across restarts)."
            for err in check_table_keys(
                table,
                f'{TARGET_REL_PATH} ["{table_name}"]',
                field_specs.keys(),
            )
        )

        for key, kind in field_specs.items():
            if key not in table:
                continue
            err = _validate_field(table_name, key, table[key], kind)
            if err is not None:
                errors.append(err)

    copper_age = data.get("Copper Age")
    if isinstance(copper_age, dict):
        tick_from = copper_age.get("golem_weathering_tick_from")
        tick_to = copper_age.get("golem_weathering_tick_to")
        if (
            is_strict_int(tick_from)
            and is_strict_int(tick_to)
            and tick_from > 0
            and tick_to > 0
            and tick_from > tick_to
        ):
            errors.append(
                f'{TARGET_REL_PATH} invariant violation: ["Copper Age"].golem_weathering_tick_from '
                f"({tick_from}) must be <= golem_weathering_tick_to ({tick_to}) because Copper "
                "Golem oxidation samples a random tick interval [from, to] and an inverted range "
                "breaks Forge's uniform random bound."
            )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/vanillabackport/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_vanillabackport_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Vanilla Backport static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "vanillabackport",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Vanilla Backport static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
