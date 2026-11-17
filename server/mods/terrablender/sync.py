#!/usr/bin/env python3
"""One-way deterministic configuration placement for TerraBlender.

Places static configuration from `mods/terrablender/configs/` into `data/`:
- `config/terrablender.toml` -> `data/config/terrablender.toml`

Validates schema types, range invariants, runtime state isolation, and
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

TARGET_REL_PATH = "config/terrablender.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "terrablender.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

ROOT_KEYS: tuple[str, ...] = ("general", "generation_settings")

GENERATION_INT_BOUNDS: dict[str, tuple[int, int, str]] = {
    "overworld_region_size": (
        2,
        6,
        "TerraBlender enforces overworld biome region size in [2, 6] to keep "
        "multi-mod biome distribution grid scaling valid during worldgen",
    ),
    "nether_region_size": (
        2,
        6,
        "TerraBlender enforces nether biome region size in [2, 6] to keep "
        "multi-mod Nether biome distribution grid scaling valid during worldgen",
    ),
    "vanilla_overworld_region_weight": (
        0,
        2147483647,
        "TerraBlender reads vanilla_overworld_region_weight as a non-negative "
        "32-bit signed integer [0, 2147483647] when weighting vanilla regions",
    ),
    "vanilla_nether_region_weight": (
        0,
        2147483647,
        "TerraBlender reads vanilla_nether_region_weight as a non-negative "
        "32-bit signed integer [0, 2147483647] when weighting vanilla regions",
    ),
}


def validate_terrablender_toml(data: Any) -> list[str]:
    """Validate schema, types, and range invariants for `config/terrablender.toml`."""
    errors = check_table_keys(
        data,
        f"{TARGET_REL_PATH} root",
        ROOT_KEYS,
    )
    if not isinstance(data, dict):
        return [
            f"{err} (TerraBlender expects a root TOML table with 'general' and "
            "'generation_settings' sections so Forge's NightConfig parser can load it)"
            for err in errors
        ]

    if errors:
        errors = [
            f"{err} (config/terrablender.toml must declare only 'general' and "
            "'generation_settings' so static worldgen parameters remain deterministic)"
            for err in errors
        ]

    if "general" in data:
        general = data["general"]
        if not isinstance(general, dict):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: 'general' must be an empty "
                f"TOML table (got {type(general).__name__}: {general!r}) because "
                "TerraBlender defines 'general' as an empty category header in Forge config"
            )
        elif general:
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: 'general' must be an empty "
                f"TOML table with 0 keys (got {sorted(general.keys())}) because "
                "TerraBlender does not expose any settings under 'general' and unexpected "
                "keys indicate unvalidated or misplaced configuration"
            )

    if "generation_settings" in data:
        gen = data["generation_settings"]
        gen_errors = check_table_keys(
            gen,
            f"{TARGET_REL_PATH} [generation_settings]",
            GENERATION_INT_BOUNDS.keys(),
        )
        if gen_errors:
            errors.extend(
                f"{err} (all four TerraBlender region size and vanilla weight fields "
                "must be explicitly declared to prevent silent worldgen drift)"
                for err in gen_errors
            )

        if isinstance(gen, dict):
            for key, (min_val, max_val, rationale) in GENERATION_INT_BOUNDS.items():
                if key not in gen:
                    continue
                value = gen[key]
                if not is_strict_int(value):
                    errors.append(
                        f"{TARGET_REL_PATH} invariant violation: generation_settings.{key} "
                        f"must be a strict integer (got {type(value).__name__}: {value!r}) "
                        f"because {rationale}"
                    )
                elif not (min_val <= value <= max_val):
                    errors.append(
                        f"{TARGET_REL_PATH} invariant violation: generation_settings.{key} "
                        f"must be in range [{min_val}, {max_val}] (got {value}) because "
                        f"{rationale}"
                    )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/terrablender/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_terrablender_toml},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated TerraBlender static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "terrablender",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place TerraBlender static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
