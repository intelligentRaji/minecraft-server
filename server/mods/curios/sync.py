#!/usr/bin/env python3
"""One-way deterministic configuration placement for Curios.

Places static configuration from `mods/curios/configs/` into `data/`:
- `config/curios-common.toml` -> `data/config/curios-common.toml`
- `world/serverconfig/curios-server.toml` -> `data/world/serverconfig/curios-server.toml`

Per-player curio inventories and runtime tags live in `data/world/playerdata/`
and are never touched by this bridge.
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

COMMON_REL_PATH = "config/curios-common.toml"
SERVER_REL_PATH = "world/serverconfig/curios-server.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    COMMON_REL_PATH: ("config", "curios-common.toml"),
    SERVER_REL_PATH: ("world", "serverconfig", "curios-server.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "mods",
    "playerdata",
    "region",
    "entities",
    "poi",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

KEEP_CURIOS_VALUES: frozenset[str] = frozenset({"ON", "DEFAULT", "OFF"})


def _check_exact_keys(
    table: Any,
    label: str,
    required_keys: tuple[str, ...],
    rationale: str,
) -> list[str]:
    """Wrap `check_table_keys` with an architectural rationale for why exact keys are enforced."""
    base_errors = check_table_keys(table, label, required_keys)
    return [f"{err} ({rationale})" for err in base_errors]


def _validate_int_range(
    table: dict[str, Any],
    label: str,
    key: str,
    min_val: int,
    max_val: int,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not is_strict_int(val) or not (min_val <= val <= max_val):
        return [
            f"{label}.{key} invariant violation: must be an integer in [{min_val}, {max_val}] "
            f"(got {type(val).__name__}: {val!r}) because {rationale}"
        ]
    return []


def validate_curios_common(data: Any) -> list[str]:
    """Validate schema and types for `config/curios-common.toml`."""
    errors = _check_exact_keys(
        data,
        COMMON_REL_PATH,
        ("slots",),
        "Curios common config must declare only the documented 'slots' key so ForgeConfigSpec "
        "loads deterministic slot definitions without unvalidated or secret fields.",
    )
    if not isinstance(data, dict) or "slots" not in data:
        return errors

    slots = data["slots"]
    if not isinstance(slots, list) or not all(isinstance(item, str) for item in slots):
        errors.append(
            f"{COMMON_REL_PATH} invariant violation: 'slots' must be a list of strings "
            f"(got {type(slots).__name__}: {slots!r}) because Curios parses each entry as a "
            "slot configuration string during mod initialization."
        )
    return errors


def validate_curios_server(data: Any) -> list[str]:
    """Validate schema, types, and ranges for `world/serverconfig/curios-server.toml`."""
    errors = _check_exact_keys(
        data,
        SERVER_REL_PATH,
        ("keepCurios", "menu"),
        "Curios server config must explicitly declare all root keys so death-retention and "
        "menu behavior remain deterministic across server restarts.",
    )
    if not isinstance(data, dict):
        return errors

    if "keepCurios" in data:
        keep_curios = data["keepCurios"]
        if not isinstance(keep_curios, str) or keep_curios not in KEEP_CURIOS_VALUES:
            errors.append(
                f"{SERVER_REL_PATH} invariant violation: 'keepCurios' must be one of "
                f"{sorted(KEEP_CURIOS_VALUES)} (got {keep_curios!r}) because Curios binds this "
                "setting to a strict enum controlling whether curio items are kept on death."
            )

    if "menu" in data:
        menu = data["menu"]
        errors.extend(
            _check_exact_keys(
                menu,
                f"{SERVER_REL_PATH} [menu]",
                ("enableLegacyMenu", "experimental"),
                "Curios [menu] section must declare both 'enableLegacyMenu' and 'experimental' "
                "so ForgeConfigSpec binds all server menu options cleanly.",
            )
        )
        if isinstance(menu, dict):
            if "enableLegacyMenu" in menu:
                legacy = menu["enableLegacyMenu"]
                if not isinstance(legacy, bool):
                    errors.append(
                        f"{SERVER_REL_PATH} invariant violation: 'menu.enableLegacyMenu' must be "
                        f"a boolean (got {type(legacy).__name__}: {legacy!r}) because "
                        "ForgeConfigSpec reads this flag as a strict true/false toggle."
                    )

            if "experimental" in menu:
                exp = menu["experimental"]
                errors.extend(
                    _check_exact_keys(
                        exp,
                        f"{SERVER_REL_PATH} [menu.experimental]",
                        ("minimumColumns", "maxSlotsPerPage"),
                        "Curios [menu.experimental] section must declare both 'minimumColumns' and "
                        "'maxSlotsPerPage' to bound the experimental Curios screen layout.",
                    )
                )
                if isinstance(exp, dict):
                    errors.extend(
                        _validate_int_range(
                            exp,
                            f"{SERVER_REL_PATH} [menu.experimental]",
                            "minimumColumns",
                            1,
                            8,
                            "Curios clamps the experimental menu grid to 1..8 columns inclusive.",
                        )
                    )
                    errors.extend(
                        _validate_int_range(
                            exp,
                            f"{SERVER_REL_PATH} [menu.experimental]",
                            "maxSlotsPerPage",
                            1,
                            48,
                            "Curios limits paged curio inventories to 1..48 slots per page so "
                            "they fit within a single screen container.",
                        )
                    )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/curios/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            COMMON_REL_PATH: validate_curios_common,
            SERVER_REL_PATH: validate_curios_server,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Curios static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "curios",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Curios static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
