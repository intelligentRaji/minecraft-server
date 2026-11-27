#!/usr/bin/env python3
"""One-way deterministic configuration placement for Double Doors (Serilum).

Places static configuration from `mods/doubledoors/configs/` into `data/`:
- `config/serilum/doubledoors.json` -> `data/config/serilum/doubledoors.json`

Validates Serilum JSON schema, strict value types/bounds, block ID blacklist
formatting, sibling Serilum isolation, runtime exclusions, and secret guards
before touching `data/`.
"""

from __future__ import annotations

import re
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

SERVER_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = SERVER_ROOT / "data"

CONFIG_REL_PATH = "config/serilum/doubledoors.json"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    CONFIG_REL_PATH: ("config", "serilum", "doubledoors.json"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "mods",
    "playerdata",
    "region",
    "entities",
    "poi",
    "world",
    "data",
    "collective.json",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

BOOLEAN_SETTING_KEYS: tuple[str, ...] = (
    "Enable Double Doors",
    "enableRecursiveOpening",
    "enableDoors",
    "enableFenceGates",
    "enableTrapdoors",
    "enableModIncompatibilityCheck",
)
INT_RANGE_SETTING_KEY = "recursiveOpeningMaxBlocksDistance"
RECURSIVE_MAX_DISTANCE_MIN = 1
RECURSIVE_MAX_DISTANCE_MAX = 64
BLACKLIST_SETTING_KEY = "doorBlockBlacklist"

REQUIRED_SETTING_KEYS: tuple[str, ...] = (
    *BOOLEAN_SETTING_KEYS,
    INT_RANGE_SETTING_KEY,
    BLACKLIST_SETTING_KEY,
)

BLOCK_ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


def _check_keys_with_rationale(
    table: object,
    label: str,
    required_keys: tuple[str, ...],
    optional_keys: tuple[str, ...],
    rationale: str,
) -> list[str]:
    """Wrap `check_table_keys` with an architectural rationale for exact-schema checks."""
    base_errors = check_table_keys(
        table, label, required_keys, optional_keys=optional_keys
    )
    return [f"{err} ({rationale})" for err in base_errors]


def _validate_door_blacklist(val: object) -> list[str]:
    """Validate `doorBlockBlacklist.value` as empty or comma-separated resource locations."""
    if not isinstance(val, str):
        return [
            f"{CONFIG_REL_PATH} [{BLACKLIST_SETTING_KEY}].value invariant violation: "
            f"must be a string (got {val!r}) because Serilum Collective parses "
            "doorBlockBlacklist as a comma-separated list of Minecraft block IDs."
        ]

    if val == "":
        return []

    tokens = [item.strip() for item in val.split(",")]
    if any(not token for token in tokens):
        return [
            f"{CONFIG_REL_PATH} [{BLACKLIST_SETTING_KEY}].value invariant violation: "
            f"malformed comma-separated list {val!r}; whitespace-only strings and "
            "empty/trailing comma entries are rejected so Serilum does not ingest "
            "blank block identifiers."
        ]

    invalid_tokens = [token for token in tokens if not BLOCK_ID_PATTERN.match(token)]
    if invalid_tokens:
        return [
            f"{CONFIG_REL_PATH} [{BLACKLIST_SETTING_KEY}].value invariant violation: "
            f"invalid block ID(s) {invalid_tokens}; every entry must match Minecraft "
            "'namespace:path' format (^[a-z0-9_.-]+:[a-z0-9_./-]+$) so Double Doors "
            "reliably matches target block resource locations."
        ]

    return []


def _validate_setting_entry(key: str, entry: object) -> list[str]:
    """Validate one Double Doors setting entry object and its typed `value`."""
    label = f"{CONFIG_REL_PATH} [{key}]"
    errors = _check_keys_with_rationale(
        entry,
        label,
        ("value",),
        ("//",),
        "Each Double Doors setting must be a Serilum object with a 'value' key and "
        "optional '//' comment so Collective deserializes config entries cleanly.",
    )
    if not isinstance(entry, dict):
        return errors

    if "//" in entry and not isinstance(entry["//"], str):
        errors.append(
            f"{label}.// invariant violation: comment field must be a string "
            f"(got {entry['//']!r}) because Serilum stores human-readable descriptions "
            "as plain string metadata."
        )

    if "value" not in entry:
        return errors

    val = entry["value"]
    if key in BOOLEAN_SETTING_KEYS:
        if not isinstance(val, bool):
            errors.append(
                f"{label}.value invariant violation: must be a strict JSON boolean "
                f"(got {val!r}) because Serilum Collective deserializes '{key}' as a "
                "boolean toggle controlling Double Doors behavior."
            )
    elif key == INT_RANGE_SETTING_KEY:
        if not is_strict_int(val) or not (
            RECURSIVE_MAX_DISTANCE_MIN <= val <= RECURSIVE_MAX_DISTANCE_MAX
        ):
            errors.append(
                f"{label}.value invariant violation: must be a strict integer in "
                f"[{RECURSIVE_MAX_DISTANCE_MIN}, {RECURSIVE_MAX_DISTANCE_MAX}] "
                f"(got {val!r}) because Collective enforces 1..64 bounds and unbounded "
                "recursive block searches risk server tick stalls."
            )
    elif key == BLACKLIST_SETTING_KEY:
        errors.extend(_validate_door_blacklist(val))

    return errors


def validate_doubledoors_json(data: object) -> list[str]:
    """Validate root schema, comment metadata, and setting value invariants."""
    errors = _check_keys_with_rationale(
        data,
        f"{CONFIG_REL_PATH} [root]",
        REQUIRED_SETTING_KEYS,
        ("//",),
        "Double Doors config must declare exactly the 8 documented Serilum settings "
        "(and optional '//' header comment) so Collective loads static settings "
        "without unvalidated or rogue keys.",
    )
    if not isinstance(data, dict):
        return errors

    if "//" in data and not isinstance(data["//"], str):
        errors.append(
            f"{CONFIG_REL_PATH} [root].// invariant violation: comment field must be a "
            f"string (got {data['//']!r}) because Serilum stores header documentation "
            "as plain string metadata."
        )

    for key in REQUIRED_SETTING_KEYS:
        if key in data:
            errors.extend(_validate_setting_entry(key, data[key]))

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/doubledoors/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {CONFIG_REL_PATH: validate_doubledoors_json},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Double Doors static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "doubledoors",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Double Doors static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
