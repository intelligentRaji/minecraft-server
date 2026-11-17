#!/usr/bin/env python3
"""One-way deterministic configuration placement for AttributeFix.

Places static configuration from `mods/attributefix/configs/` into `data/`:
- `attributefix.json` -> `data/config/attributefix.json`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
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
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "attributefix.json": ("config", "attributefix.json"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES


def _validate_bound(
    entry: dict[str, Any],
    attr_id: str,
    bound_name: str,
) -> tuple[dict[str, float | int] | None, list[str]]:
    """Validate a `min` or `max` bound mapping and return `(bound, errors)`."""
    label = f"attributefix.json attributes[{attr_id!r}].{bound_name}"
    key_errors = check_table_keys(entry.get(bound_name), label, ("default", "value"))
    if key_errors:
        return None, [
            f"{err} (each attribute bound must define finite 'default' and 'value' "
            "numbers so AttributeFix can enforce valid clamp limits)."
            for err in key_errors
        ]

    bound = entry[bound_name]
    errors: list[str] = []
    for field in ("default", "value"):
        val = bound[field]
        if not is_finite_number(val):
            errors.append(
                f"{label}.{field} invariant violation: expected a finite number "
                f"(got {val!r}) so AttributeFix does not receive NaN, infinity, or "
                "non-numeric clamp bounds."
            )
    if errors:
        return None, errors
    return bound, []


def validate_attributefix_config(data: Any) -> list[str]:
    """Validate schema and clamp range invariants for `attributefix.json`."""
    root_errors = check_table_keys(data, "attributefix.json", ("attributes",))
    if root_errors:
        return [
            f"{err} (attributefix.json must contain only the top-level 'attributes' "
            "mapping so static attribute overrides remain isolated from runtime state)."
            for err in root_errors
        ]

    attributes = data["attributes"]
    if not isinstance(attributes, dict):
        return [
            f"attributefix.json invariant violation: 'attributes' must be a JSON object "
            f"(got {type(attributes).__name__}) mapping resource-location attribute IDs "
            "to clamp configurations."
        ]

    errors: list[str] = []
    for attr_id, entry in attributes.items():
        if not isinstance(attr_id, str) or not attr_id.strip():
            errors.append(
                f"attributefix.json invariant violation: attribute key {attr_id!r} must be "
                "a non-empty string resource-location ID so AttributeFix can resolve the "
                "target Minecraft or modded attribute."
            )
            continue

        entry_label = f"attributefix.json attributes[{attr_id!r}]"
        entry_errors = check_table_keys(entry, entry_label, ("enabled", "min", "max"))
        if entry_errors:
            errors.extend(
                f"{err} (each attribute override requires 'enabled', 'min', and 'max' "
                "for AttributeFix deserialization)."
                for err in entry_errors
            )
            continue

        enabled = entry["enabled"]
        if not isinstance(enabled, bool):
            errors.append(
                f"{entry_label}.enabled invariant violation: expected a strict boolean "
                f"(got {enabled!r}) to deterministically enable or disable clamping for "
                "this attribute."
            )

        min_bound, min_errors = _validate_bound(entry, attr_id, "min")
        max_bound, max_errors = _validate_bound(entry, attr_id, "max")
        errors.extend(min_errors)
        errors.extend(max_errors)

        if min_bound is not None and max_bound is not None:
            if min_bound["default"] > max_bound["default"]:
                errors.append(
                    f"{entry_label} invariant violation: min.default ({min_bound['default']}) "
                    f"> max.default ({max_bound['default']}), because a minimum bound greater "
                    "than the maximum bound creates an invalid clamp interval that breaks "
                    "AttributeFix's attribute range enforcement in-game."
                )
            if min_bound["value"] > max_bound["value"]:
                errors.append(
                    f"{entry_label} invariant violation: min.value ({min_bound['value']}) "
                    f"> max.value ({max_bound['value']}), because a minimum bound greater "
                    "than the maximum bound creates an invalid clamp interval that breaks "
                    "AttributeFix's attribute range enforcement in-game."
                )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/attributefix/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {"attributefix.json": validate_attributefix_config},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated AttributeFix static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def sync(dry_run: bool = False) -> tuple[int, int]:
    """Validate and place AttributeFix static configs into `DATA_DIR`."""
    loaded_bytes = validate_configs()
    return apply_configs(loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "attributefix",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place AttributeFix static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
