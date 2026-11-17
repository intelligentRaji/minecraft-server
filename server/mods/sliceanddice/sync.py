#!/usr/bin/env python3
"""One-way deterministic configuration placement for Create Slice & Dice.

Places static configuration from `mods/sliceanddice/configs/` into `data/`:
- `config/sliceanddice-common.toml` -> `data/config/sliceanddice-common.toml`

Validates TOML schema, value types, enum/range invariants, runtime state isolation,
and secret guards before touching `data/`.
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
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

TARGET_REL_PATH = "config/sliceanddice-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "sliceanddice-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

EXPECTED_TABLES: dict[str, tuple[str, ...]] = {
    "harvester": ("uses_knife",),
    "slicer": (
        "consume_tool_durability",
        "ignore_rotation",
        "jei_show_converted_recipes",
    ),
    "basin_cooking": (
        "enabled",
        "replace_fluid_containers",
        "heat_condition",
    ),
    "sprinkler": (
        "fluid_capacity",
        "fluid_per_use",
        "horizontal_range",
    ),
}

BOOL_KEYS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "harvester": ("uses_knife",),
    "slicer": (
        "consume_tool_durability",
        "ignore_rotation",
        "jei_show_converted_recipes",
    ),
    "basin_cooking": (
        "enabled",
        "replace_fluid_containers",
    ),
}

ALLOWED_HEAT_CONDITIONS: tuple[str, ...] = ("NONE", "HEATED", "SUPERHEATED")

INT_RANGES: dict[tuple[str, str], tuple[int, int]] = {
    ("sprinkler", "fluid_capacity"): (10, 2048),
    ("sprinkler", "fluid_per_use"): (0, 2048),
    ("sprinkler", "horizontal_range"): (1, 32),
}


def _validate_bool(table: dict[str, Any], table_label: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, bool):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{table_label}.{key}' must be a boolean "
            f"(got {type(val).__name__}: {val!r}) because ForgeConfigSpec binds this option "
            "as a strict true/false toggle."
        ]
    return []


def _validate_int_range(
    table: dict[str, Any],
    table_label: str,
    key: str,
    min_val: int,
    max_val: int,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not is_strict_int(val) or not (min_val <= val <= max_val):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{table_label}.{key}' must be an integer "
            f"in [{min_val}, {max_val}] (got {type(val).__name__}: {val!r}) so Create Slice & Dice "
            "sprinkler mechanics stay within ForgeConfigSpec bounds."
        ]
    return []


def validate_sliceanddice_common(data: Any) -> list[str]:
    """Validate schema, types, and invariants for `config/sliceanddice-common.toml`."""
    errors = check_table_keys(
        data,
        f"{TARGET_REL_PATH} [root]",
        tuple(EXPECTED_TABLES.keys()),
    )
    if not isinstance(data, dict):
        return errors

    tables: dict[str, dict[str, Any]] = {}
    for table_name, expected_keys in EXPECTED_TABLES.items():
        if table_name not in data:
            continue
        section = data[table_name]
        errors.extend(
            check_table_keys(
                section,
                f"{TARGET_REL_PATH} [{table_name}]",
                expected_keys,
            )
        )
        if isinstance(section, dict):
            tables[table_name] = section

    for table_name, bool_keys in BOOL_KEYS_BY_TABLE.items():
        table = tables.get(table_name)
        if table is None:
            continue
        for key in bool_keys:
            errors.extend(_validate_bool(table, table_name, key))

    basin_cooking = tables.get("basin_cooking")
    if basin_cooking is not None and "heat_condition" in basin_cooking:
        heat = basin_cooking["heat_condition"]
        if not isinstance(heat, str) or heat not in ALLOWED_HEAT_CONDITIONS:
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: 'basin_cooking.heat_condition' must be "
                f"one of {list(ALLOWED_HEAT_CONDITIONS)} (got {heat!r}) because Create's "
                "HeatCondition enum rejects unrecognized heat levels at recipe registration."
            )

    for (table_name, key), (min_val, max_val) in INT_RANGES.items():
        table = tables.get(table_name)
        if table is not None:
            errors.extend(_validate_int_range(table, table_name, key, min_val, max_val))

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/sliceanddice/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_sliceanddice_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Create Slice & Dice static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "sliceanddice",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Create Slice & Dice static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
