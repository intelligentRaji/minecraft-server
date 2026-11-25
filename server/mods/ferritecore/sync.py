#!/usr/bin/env python3
"""One-way deterministic configuration placement for FerriteCore.

Places static configuration from `mods/ferritecore/configs/` into `data/`:
- `config/ferritecore-mixin.toml` -> `data/config/ferritecore-mixin.toml`

Validates schema types, dependency invariants, runtime state isolation, and
secret guards before touching `data/`.
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
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

TARGET_REL_PATH = "config/ferritecore-mixin.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "ferritecore-mixin.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

EXPECTED_MIXIN_KEYS: tuple[str, ...] = (
    "compactFastMap",
    "useSmallThreadingDetector",
    "cacheMultipartPredicates",
    "multipartDeduplication",
    "blockstateCacheDeduplication",
    "modelResourceLocations",
    "modelSides",
    "replaceNeighborLookup",
    "populateNeighborTable",
    "replacePropertyMap",
    "bakedQuadDeduplication",
)


def validate_ferritecore_mixin(data: object) -> list[str]:
    """Validate schema, types, and dependency invariants for `config/ferritecore-mixin.toml`."""
    if not isinstance(data, dict):
        return [
            f"{TARGET_REL_PATH} invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so FerriteCore can parse its top-level mixin flags."
        ]

    errors: list[str] = []
    expected_set = set(EXPECTED_MIXIN_KEYS)
    actual_set = set(data.keys())

    missing_keys = sorted(expected_set - actual_set)
    if missing_keys:
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: missing required keys {missing_keys} "
            "(all 11 FerriteCore mixin flags must be explicitly declared so server memory "
            "optimizations remain deterministic across restarts)."
        )

    unexpected_keys = sorted(actual_set - expected_set)
    if unexpected_keys:
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: unexpected keys {unexpected_keys} "
            "(mods/ferritecore/configs/config/ferritecore-mixin.toml must contain only "
            "FerriteCore's 11 static mixin flags and never embed unvalidated or secret fields)."
        )

    for key in EXPECTED_MIXIN_KEYS:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, bool):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: '{key}' must be a boolean "
                f"(got {type(value).__name__}: {value!r}) because FerriteCore reads every "
                "mixin flag as a strict true/false toggle at Forge mod-loading time."
            )

    if (
        isinstance(data.get("multipartDeduplication"), bool)
        and isinstance(data.get("cacheMultipartPredicates"), bool)
        and data["multipartDeduplication"] is True
        and data["cacheMultipartPredicates"] is False
    ):
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: multipartDeduplication=true requires "
            "cacheMultipartPredicates=true because FerriteCore's multipart model deduplication "
            "relies on cached multipart predicate instances to safely share MultipartBakedModel "
            "objects across block states."
        )

    if (
        isinstance(data.get("replacePropertyMap"), bool)
        and isinstance(data.get("replaceNeighborLookup"), bool)
        and data["replacePropertyMap"] is True
        and data["replaceNeighborLookup"] is False
    ):
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: replacePropertyMap=true requires "
            "replaceNeighborLookup=true because FerriteCore omits per-state property maps and "
            "resolves blockstate properties directly from the replacement neighbor lookup table."
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/ferritecore/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_ferritecore_mixin},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated FerriteCore static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "ferritecore",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place FerriteCore static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
