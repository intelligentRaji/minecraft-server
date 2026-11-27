#!/usr/bin/env python3
"""One-way deterministic configuration placement for Collective (Serilum).

Places static configuration from `mods/collective/configs/` into `data/`:
- `config/serilum/collective.json` -> `data/config/serilum/collective.json`

Shared-directory and runtime isolation invariants:
- `data/config/serilum/` is shared with sibling Serilum mods (e.g. `doubledoors.json`);
  this script manages only `config/serilum/collective.json` and never touches siblings.
- Never reads, copies, or modifies runtime caches (`data/serilum/`) or live world state
  (`world/data/collective/itemnametranslation.txt`).
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

SERVER_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = SERVER_ROOT / "data"

REL_PATH = "config/serilum/collective.json"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    REL_PATH: ("config", "serilum", "collective.json"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "doubledoors.json",
    "itemnametranslation.txt",
    "cache",
    "data",
    "world",
    "logs",
    "mods",
    "playerdata",
    "region",
    "entities",
    "poi",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = (*DEFAULT_FORBIDDEN_SUFFIXES, ".dat", ".txt")

BOOL_KEYS: frozenset[str] = frozenset({
    "enableUpdateChecker",
    "transferItemsBetweenReplacedEntities",
    "enablePatronPets",
    "commandsAskForConfirmation",
    "downloadNonEnglishTranslations",
    "pushTranslationResourcePack",
    "requireTranslationResourcePack",
    "updateMinecraftWindowTitleInDevMode",
})

INT_RANGE_SPECS: dict[str, tuple[int, int]] = {
    "findABlockCheckAroundEntitiesDelayMs": (0, 3_600_000),
    "configScreenGuiScale": (0, 10),
}

ITEM_NAME_TRANSLATION_MODES: frozenset[str] = frozenset({"auto", "server", "client"})
LOCALE_RE: re.Pattern[str] = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")

REQUIRED_KEYS: tuple[str, ...] = (
    "disabledSerilumMods",
    "enableUpdateChecker",
    "transferItemsBetweenReplacedEntities",
    "findABlockCheckAroundEntitiesDelayMs",
    "enablePatronPets",
    "commandsAskForConfirmation",
    "downloadNonEnglishTranslations",
    "pushTranslationResourcePack",
    "requireTranslationResourcePack",
    "serverLanguage",
    "itemNameTranslationMode",
    "configScreenGuiScale",
    "updateMinecraftWindowTitleInDevMode",
)


def _check_keys_with_rationale(
    table: object,
    label: str,
    required_keys: tuple[str, ...],
    optional_keys: tuple[str, ...],
    rationale: str,
) -> list[str]:
    """Wrap `check_table_keys` so schema errors embed their architectural rationale."""
    return [
        f"{err} ({rationale})"
        for err in check_table_keys(
            table,
            label,
            required_keys,
            optional_keys=optional_keys,
        )
    ]


def _validate_setting_value(key: str, value: object) -> str | None:
    """Validate the `"value"` field for one Collective configuration entry."""
    if key in BOOL_KEYS:
        if not isinstance(value, bool):
            return (
                f"{REL_PATH} [{key}].value invariant violation: must be a strict JSON boolean "
                f"(got {value!r} of type {type(value).__name__}) because Collective deserializes "
                "this flag into a boolean configuration field."
            )
        return None

    if key in INT_RANGE_SPECS:
        min_val, max_val = INT_RANGE_SPECS[key]
        if not is_strict_int(value) or not (min_val <= value <= max_val):
            return (
                f"{REL_PATH} [{key}].value invariant violation: must be a strict integer in "
                f"[{min_val}, {max_val}] (got {value!r} of type {type(value).__name__}) so "
                "Collective's bounded timing/GUI settings remain safe and well-defined on server startup."
            )
        return None

    if key == "disabledSerilumMods":
        if not isinstance(value, str):
            return (
                f"{REL_PATH} [{key}].value invariant violation: must be a string "
                f"(got {value!r} of type {type(value).__name__}) because Collective parses "
                "this field as a disabled Serilum mod list string."
            )
        return None

    if key == "serverLanguage":
        if not isinstance(value, str) or not LOCALE_RE.fullmatch(value):
            return (
                f"{REL_PATH} [{key}].value invariant violation: must be a non-empty Minecraft "
                "locale code matching '^[a-z0-9]+(_[a-z0-9]+)*$' such as 'en_us' or 'de_de' "
                f"(got {value!r}) so Collective resolves server-side Serilum mod translations "
                "deterministically."
            )
        return None

    if key == "itemNameTranslationMode":
        if not isinstance(value, str) or value not in ITEM_NAME_TRANSLATION_MODES:
            return (
                f"{REL_PATH} [{key}].value invariant violation: must be one of "
                f"{sorted(ITEM_NAME_TRANSLATION_MODES)} (got {value!r}) because Collective "
                "only supports 'auto', 'server', and 'client' item name translation modes."
            )
        return None

    return None


def validate_collective_json(data: object) -> list[str]:
    """Validate root structure, entry objects, comments, and value types for `collective.json`."""
    errors = _check_keys_with_rationale(
        data,
        f"{REL_PATH} [root]",
        REQUIRED_KEYS,
        ("//",),
        "Collective JSON root must declare all 13 documented setting objects plus optional '//' "
        "comment so Serilum's config parser loads deterministic server behavior without rogue keys.",
    )
    if not isinstance(data, dict):
        return errors

    if "//" in data and not isinstance(data["//"], str):
        errors.append(
            f"{REL_PATH} [root].'//' invariant violation: optional comment key '//' must be a string "
            f"(got {data['//']!r} of type {type(data['//']).__name__}) so Serilum's JSON comment "
            "metadata remains valid."
        )

    for key in REQUIRED_KEYS:
        if key not in data:
            continue
        entry = data[key]
        errors.extend(
            _check_keys_with_rationale(
                entry,
                f"{REL_PATH} [{key}]",
                ("value",),
                ("//",),
                "Each Collective setting entry must be a JSON object with a required 'value' key "
                "and optional '//' comment so Serilum's config schema deserializes cleanly.",
            )
        )
        if not isinstance(entry, dict):
            continue

        if "//" in entry and not isinstance(entry["//"], str):
            errors.append(
                f"{REL_PATH} [{key}].'//' invariant violation: optional comment key '//' must be a string "
                f"(got {entry['//']!r} of type {type(entry['//']).__name__}) so Serilum's JSON comment "
                "metadata remains valid."
            )

        if "value" in entry:
            val_error = _validate_setting_value(key, entry["value"])
            if val_error is not None:
                errors.append(val_error)

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/collective/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {REL_PATH: validate_collective_json},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Collective static config into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for synchronizing Collective static configuration."""
    return run_sync_cli(
        "collective",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Collective static config into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
