#!/usr/bin/env python3
"""One-way deterministic configuration placement for Botania.

Places static configuration from `mods/botania/configs/` into `data/`:
- `config/botania-common.toml` -> `data/config/botania-common.toml`

Validates TOML schema, value types, ranges, runtime state isolation, and
secret guards before touching `data/`.
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

TARGET_REL_PATH = "config/botania-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "botania-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
    "botania-client.toml",
    "botania-server.toml",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

TOP_LEVEL_BOOL_KEYS: tuple[str, ...] = (
    "chargeAnimation",
    "flowerBindingForceCheck",
    "enderPickpocket",
    "manaEnchanter",
    "relics",
    "invertMagnetRing",
)

EXPECTED_TABLES: dict[str, tuple[str, ...]] = {
    "blockBreakingParticles": ("enabled", "toolEnabled"),
    "manaSpreaders": ("silent", "traceTime"),
    "harvestLevels": ("weightLens", "boreLens"),
    "gardenOfGlass": ("spawnWithLexicon", "islandScaleMultiplier"),
    "rannuncarpus": ("itemBlacklist", "modBlacklist"),
}

EXPECTED_ROOT_KEYS: tuple[str, ...] = TOP_LEVEL_BOOL_KEYS + tuple(EXPECTED_TABLES.keys())


def _check_section_keys(
    table: Any,
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
            "all Botania common config sections and keys must be explicitly declared "
            "without extra or missing fields so gameplay balance remains deterministic "
            "and unvalidated or secret keys never reach data/."
        )
        return None if not isinstance(table, dict) else table, [
            f"{err} ({rationale})" for err in raw_errors
        ]
    return table, []


def _validate_bool(table: dict[str, Any], field_path: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, bool):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a boolean "
            f"(got {type(val).__name__}: {val!r}) because Botania binds this setting as "
            "a strict true/false ForgeConfigSpec toggle."
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


def _validate_str_list(table: dict[str, Any], field_path: str, key: str) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, list):
        return [
            f"{TARGET_REL_PATH} invariant violation: '{field_path}' must be a list of "
            f"strings (got {type(val).__name__}) so Botania's Rannuncarpus filter can "
            "safely iterate configured entries."
        ]
    errors: list[str] = []
    for idx, item in enumerate(val):
        if not isinstance(item, str):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: '{field_path}[{idx}]' must be "
                f"a string (got {type(item).__name__}: {item!r}) so Botania's Rannuncarpus "
                "blacklist resolves valid registry or mod IDs."
            )
    return errors


def validate_botania_common(data: Any) -> list[str]:
    """Validate schema, types, and invariants for `config/botania-common.toml`."""
    root, errors = _check_section_keys(data, EXPECTED_ROOT_KEYS, "root")
    if root is None:
        return errors

    for key in TOP_LEVEL_BOOL_KEYS:
        errors.extend(_validate_bool(root, key, key))

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

    particles = tables.get("blockBreakingParticles")
    if particles is not None:
        errors.extend(_validate_bool(particles, "blockBreakingParticles.enabled", "enabled"))
        errors.extend(
            _validate_bool(particles, "blockBreakingParticles.toolEnabled", "toolEnabled")
        )

    spreaders = tables.get("manaSpreaders")
    if spreaders is not None:
        errors.extend(_validate_bool(spreaders, "manaSpreaders.silent", "silent"))
        errors.extend(
            _validate_int_range(
                spreaders,
                "manaSpreaders.traceTime",
                "traceTime",
                min_val=1,
                rationale=(
                    "mana spreaders require a positive tick lookahead (>= 1) to predict "
                    "mana burst trajectories."
                ),
            )
        )

    harvest = tables.get("harvestLevels")
    if harvest is not None:
        errors.extend(
            _validate_int_range(
                harvest,
                "harvestLevels.weightLens",
                "weightLens",
                min_val=0,
                rationale=(
                    "Botania harvest levels are non-negative Minecraft mining tier integers (>= 0)."
                ),
            )
        )
        errors.extend(
            _validate_int_range(
                harvest,
                "harvestLevels.boreLens",
                "boreLens",
                min_val=0,
                rationale=(
                    "Botania harvest levels are non-negative Minecraft mining tier integers (>= 0)."
                ),
            )
        )

    gog = tables.get("gardenOfGlass")
    if gog is not None:
        errors.extend(
            _validate_bool(gog, "gardenOfGlass.spawnWithLexicon", "spawnWithLexicon")
        )
        errors.extend(
            _validate_int_range(
                gog,
                "gardenOfGlass.islandScaleMultiplier",
                "islandScaleMultiplier",
                min_val=1,
                max_val=512,
                rationale=(
                    "Botania enforces islandScaleMultiplier within [1, 512] to prevent "
                    "degenerate or overflowing Garden of Glass island grid coordinates."
                ),
            )
        )

    rannuncarpus = tables.get("rannuncarpus")
    if rannuncarpus is not None:
        errors.extend(
            _validate_str_list(rannuncarpus, "rannuncarpus.itemBlacklist", "itemBlacklist")
        )
        errors.extend(
            _validate_str_list(rannuncarpus, "rannuncarpus.modBlacklist", "modBlacklist")
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/botania/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_botania_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Botania static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "botania",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Botania static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
