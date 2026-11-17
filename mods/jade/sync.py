#!/usr/bin/env python3
"""One-way deterministic configuration placement for Jade.

Places static configuration from `mods/jade/configs/` into `data/`:
- `server-plugin-overrides.json` -> `data/config/jade/server-plugin-overrides.json`
- `sort-order.json` -> `data/config/jade/sort-order.json`

Validates JSON schemas, provider ID keys, priority/override value types,
client-only file exclusion, and secret guards before touching `data/`.
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
    is_finite_number,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

OVERRIDES_REL_PATH = "server-plugin-overrides.json"
SORT_ORDER_REL_PATH = "sort-order.json"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    OVERRIDES_REL_PATH: ("config", "jade", "server-plugin-overrides.json"),
    SORT_ORDER_REL_PATH: ("config", "jade", "sort-order.json"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "mods",
    "playerdata",
    "region",
    "entities",
    "poi",
    "jade.json",
    "disabled_plugins.json",
    "hide-blocks.json",
    "hide-entities.json",
    "hide-mob-effects.json",
    "profiles",
    "themes",
    "plugins",
    "cache",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES


def _validate_override_value(value: Any, path: str) -> list[str]:
    """Recursively validate a JSON value inside `server-plugin-overrides.json`."""
    if value is None or isinstance(value, (bool, str)):
        return []
    if isinstance(value, (int, float)):
        if is_finite_number(value):
            return []
        return [
            f"{path} invariant violation: numeric override must be finite (got {value!r}) "
            "because Jade serializes server plugin overrides as standard JSON and non-finite "
            "floats (NaN/Infinity) break Gson deserialization on the server."
        ]
    if isinstance(value, list):
        errors: list[str] = []
        for idx, item in enumerate(value):
            errors.extend(_validate_override_value(item, f"{path}[{idx}]"))
        return errors
    if isinstance(value, dict):
        errors = []
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                errors.append(
                    f"{path} invariant violation: nested override keys must be non-empty strings "
                    f"(got {key!r}) so Jade can resolve nested option paths deterministically."
                )
                continue
            errors.extend(_validate_override_value(item, f"{path}.{key}"))
        return errors
    return [
        f"{path} invariant violation: unsupported override value type {type(value).__name__} "
        "because Jade plugin overrides only support standard JSON primitives, arrays, or objects."
    ]


def validate_server_plugin_overrides(data: Any) -> list[str]:
    """Validate `server-plugin-overrides.json` structure and override values."""
    if not isinstance(data, dict):
        return [
            f"{OVERRIDES_REL_PATH} invariant violation: root must be a JSON object "
            f"(got {type(data).__name__}) mapping Jade plugin/provider resource location IDs "
            "or option keys to override values so the server can apply deterministic plugin overrides."
        ]

    errors: list[str] = []
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(
                f"{OVERRIDES_REL_PATH} invariant violation: override key must be a non-empty string "
                f"(got {key!r}) because Jade looks up plugin overrides by resource location ID or option key."
            )
            continue
        errors.extend(_validate_override_value(value, f"{OVERRIDES_REL_PATH}[{key!r}]"))
    return errors


def validate_sort_order(data: Any) -> list[str]:
    """Validate `sort-order.json` structure, provider ID keys, and priority values."""
    if not isinstance(data, dict):
        return [
            f"{SORT_ORDER_REL_PATH} invariant violation: root must be a JSON object "
            f"(got {type(data).__name__}) mapping Jade provider resource location IDs to "
            "priority weights so tooltip ordering remains deterministic across server and client."
        ]

    errors: list[str] = []
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(
                f"{SORT_ORDER_REL_PATH} invariant violation: provider ID key must be a non-empty string "
                f"(got {key!r}) because Jade indexes tooltip sort priorities by provider resource location."
            )
            continue
        if value is not None and not is_finite_number(value):
            errors.append(
                f"{SORT_ORDER_REL_PATH}[{key!r}] invariant violation: priority value must be null "
                f"(default priority) or a finite number (int/float, not bool; got {value!r}) because "
                "Jade's sort comparator requires a nullable numeric weight for deterministic ordering."
            )
    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/jade/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            OVERRIDES_REL_PATH: validate_server_plugin_overrides,
            SORT_ORDER_REL_PATH: validate_sort_order,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Jade static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "jade",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Jade static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
