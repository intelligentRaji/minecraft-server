#!/usr/bin/env python3
"""One-way deterministic configuration placement for Just Enough Resources (JER).

Places static configuration from `mods/jeresources/configs/` into `data/`:
- `config/jeresources-common.toml` -> `data/config/jeresources-common.toml`
- `config/jeresources.toml` -> `data/config/jeresources.toml`

Validates schema types, integer bounds, list element types, and secret/forbidden
entry guards before touching `data/`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import partial
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

COMMON_REL_PATH = "config/jeresources-common.toml"
MAIN_REL_PATH = "config/jeresources.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    COMMON_REL_PATH: ("config", "jeresources-common.toml"),
    MAIN_REL_PATH: ("config", "jeresources.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

EXPECTED_KEYS: tuple[str, ...] = (
    "itemsPerColumn",
    "itemsPerRow",
    "diyData",
    "showDevData",
    "enchantsBlacklist",
    "hiddenTabs",
    "dimensionsBlacklist",
    "disableLootManagerReloading",
)

BOOL_KEYS: tuple[str, ...] = (
    "diyData",
    "showDevData",
    "disableLootManagerReloading",
)

GRID_INT_KEYS: tuple[str, ...] = (
    "itemsPerColumn",
    "itemsPerRow",
)

STR_LIST_KEYS: tuple[str, ...] = (
    "enchantsBlacklist",
    "hiddenTabs",
)


def _validate_str_list(rel_path: str, key: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [
            f"{rel_path} invariant violation: '{key}' must be a list of strings "
            f"(got {value!r}) because JER filters enchantment names and JEI tab IDs "
            "by exact string identifier."
        ]
    return []


def _validate_int_list(rel_path: str, key: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(is_strict_int(item) for item in value):
        return [
            f"{rel_path} invariant violation: '{key}' must be a list of integers "
            f"(got {value!r}) because JER matches dimension blacklist entries against "
            "numeric Forge dimension IDs (booleans are rejected)."
        ]
    return []


def validate_jeresources_toml(rel_path: str, data: Any) -> list[str]:
    """Validate schema, types, and bounds for a Just Enough Resources TOML file."""
    key_errors = check_table_keys(data, rel_path, EXPECTED_KEYS)
    if key_errors:
        return [
            f"{err} (both JER config files must declare all 8 static keys and never "
            "embed unvalidated, runtime, or secret fields)"
            for err in key_errors
        ]

    errors: list[str] = []

    for key in GRID_INT_KEYS:
        value = data[key]
        if not is_strict_int(value) or not (1 <= value <= 4):
            errors.append(
                f"{rel_path} invariant violation: '{key}' must be an integer in range 1..4 "
                f"(got {type(value).__name__}: {value!r}) because JER's JEI recipe/drop "
                "grid layout clamps column and row counts between 1 and 4."
            )

    for key in BOOL_KEYS:
        value = data[key]
        if not isinstance(value, bool):
            errors.append(
                f"{rel_path} invariant violation: '{key}' must be a boolean "
                f"(got {type(value).__name__}: {value!r}) because JER reads '{key}' as a "
                "strict true/false toggle when loading loot and worldgen data."
            )

    for key in STR_LIST_KEYS:
        errors.extend(_validate_str_list(rel_path, key, data[key]))

    errors.extend(
        _validate_int_list(rel_path, "dimensionsBlacklist", data["dimensionsBlacklist"])
    )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/jeresources/configs/` before placement."""
    validators: dict[str, Callable[[Any], list[str]]] = {
        rel_path: partial(validate_jeresources_toml, rel_path)
        for rel_path in STATIC_FILES
    }
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        validators,
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Just Enough Resources static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "jeresources",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Just Enough Resources static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
