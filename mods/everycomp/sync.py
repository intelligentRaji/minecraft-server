#!/usr/bin/env python3
"""One-way deterministic configuration placement for Every Compat (Wood Good).

Places static configuration from `mods/everycomp/configs/` into `data/`:
- `config/everycomp-common.toml` -> `data/config/everycomp-common.toml`
- `config/everycomp-entries.toml` -> `data/config/everycomp-entries.toml`
- `config/everycomp-hazardous.toml` -> `data/config/everycomp-hazardous.toml`

Validates TOML schema, value types, regex syntax, runtime state isolation, and
secret guards before touching `data/`.
"""

from __future__ import annotations

import re
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
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

COMMON_REL_PATH = "config/everycomp-common.toml"
ENTRIES_REL_PATH = "config/everycomp-entries.toml"
HAZARDOUS_REL_PATH = "config/everycomp-hazardous.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    COMMON_REL_PATH: ("config", "everycomp-common.toml"),
    ENTRIES_REL_PATH: ("config", "everycomp-entries.toml"),
    HAZARDOUS_REL_PATH: ("config", "everycomp-hazardous.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({"logs", "world", "mods", "debug"})
FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

COMMON_GENERAL_BOOL_KEYS: tuple[str, ...] = (
    "generate_dynamic_assets",
    "creative_tab",
    "tab_item_search",
    "no_mod_creative_tab",
    "generate_blocktype_tags",
    "save_debug_resources",
    "mod_version_check_packet",
    "debug_packet",
)
COMMON_GENERAL_KEYS: tuple[str, ...] = COMMON_GENERAL_BOOL_KEYS + ("tooltips",)
COMMON_TOOLTIPS_KEYS: tuple[str, ...] = (
    "mod_origin_enabled",
    "block_type_enabled",
    "show_on_advanced_tooltips",
)

HAZARDOUS_REGEX_SECTIONS: tuple[str, ...] = (
    "woodtype",
    "leavestype",
    "block",
    "entryset",
    "module",
)
HAZARDOUS_ROOT_KEYS: tuple[str, ...] = HAZARDOUS_REGEX_SECTIONS + ("other",)


def _check_keys_with_rationale(
    table: Any,
    rel_path: str,
    section_label: str,
    required_keys: tuple[str, ...],
    rationale: str,
    optional_keys: tuple[str, ...] = (),
) -> tuple[dict[str, Any] | None, list[str]]:
    raw_errors = check_table_keys(
        table,
        f"{rel_path} ({section_label})",
        required_keys,
        optional_keys=optional_keys,
    )
    if raw_errors:
        return None if not isinstance(table, dict) else table, [
            f"{err} ({rationale})" for err in raw_errors
        ]
    return table, []


def _validate_strict_bool(
    table: dict[str, Any],
    rel_path: str,
    field_path: str,
    key: str,
    rationale: str,
) -> list[str]:
    if key not in table:
        return []
    val = table[key]
    if not isinstance(val, bool):
        return [
            f"{rel_path} invariant violation: '{field_path}' must be a strict boolean "
            f"(got {type(val).__name__}: {val!r}) because {rationale}"
        ]
    return []


def validate_everycomp_common(data: Any) -> list[str]:
    """Validate schema and strict boolean types for `config/everycomp-common.toml`."""
    schema_rationale = (
        "all Every Compat common config sections and keys must be explicitly declared "
        "without extra or missing fields so dynamic asset generation and client-server "
        "packet settings remain deterministic and unvalidated keys never reach data/."
    )
    bool_rationale = (
        "Every Compat binds common settings as strict true/false ForgeConfigSpec booleans "
        "to control dynamic asset generation, creative tabs, and version-check packets."
    )

    root, errors = _check_keys_with_rationale(
        data, COMMON_REL_PATH, "root", ("general",), schema_rationale
    )
    if root is None or "general" not in root:
        return errors

    general, gen_errors = _check_keys_with_rationale(
        root["general"], COMMON_REL_PATH, "general", COMMON_GENERAL_KEYS, schema_rationale
    )
    errors.extend(gen_errors)
    if general is None:
        return errors

    for key in COMMON_GENERAL_BOOL_KEYS:
        errors.extend(
            _validate_strict_bool(
                general, COMMON_REL_PATH, f"general.{key}", key, bool_rationale
            )
        )

    if "tooltips" in general:
        tooltips, tt_errors = _check_keys_with_rationale(
            general["tooltips"],
            COMMON_REL_PATH,
            "general.tooltips",
            COMMON_TOOLTIPS_KEYS,
            schema_rationale,
        )
        errors.extend(tt_errors)
        if tooltips is not None:
            for key in COMMON_TOOLTIPS_KEYS:
                errors.extend(
                    _validate_strict_bool(
                        tooltips,
                        COMMON_REL_PATH,
                        f"general.tooltips.{key}",
                        key,
                        bool_rationale,
                    )
                )

    return errors


def _validate_modid_bool_map(
    category_table: Any,
    section_path: str,
) -> list[str]:
    if not isinstance(category_table, dict):
        return [
            f"{ENTRIES_REL_PATH} invariant violation: '{section_path}' must be a TOML "
            f"table mapping mod IDs to entry toggles (got {type(category_table).__name__}) "
            "so Every Compat can resolve per-mod wood/leaves registrations."
        ]

    errors: list[str] = []
    for modid, entries in category_table.items():
        if not isinstance(modid, str) or not modid.strip():
            errors.append(
                f"{ENTRIES_REL_PATH} invariant violation: '{section_path}' contains an "
                f"invalid mod ID key {modid!r}; non-empty mod ID strings are required."
            )
            continue
        if not isinstance(entries, dict):
            errors.append(
                f"{ENTRIES_REL_PATH} invariant violation: '{section_path}.{modid}' must be "
                f"a TOML table of entry toggles (got {type(entries).__name__}) so each "
                "registered type or block entry has an explicit boolean state."
            )
            continue
        for entry_name in entries:
            errors.extend(
                _validate_strict_bool(
                    entries,
                    ENTRIES_REL_PATH,
                    f"{section_path}.{modid}.{entry_name}",
                    entry_name,
                    "Every Compat entry toggles are strict true/false flags controlling "
                    "recipe and creative-tab visibility.",
                )
            )
    return errors


def validate_everycomp_entries(data: Any) -> list[str]:
    """Validate schema and nested mod-entry booleans for `config/everycomp-entries.toml`."""
    schema_rationale = (
        "everycomp-entries.toml must contain only [types] and [entries] tables with valid "
        "wood_type/leaves_type categories so recipe and tab toggles stay well-formed."
    )
    root, errors = _check_keys_with_rationale(
        data, ENTRIES_REL_PATH, "root", ("types", "entries"), schema_rationale
    )
    if root is None:
        return errors

    if "types" in root:
        types_table, types_errors = _check_keys_with_rationale(
            root["types"],
            ENTRIES_REL_PATH,
            "types",
            ("wood_type", "leaves_type"),
            schema_rationale,
        )
        errors.extend(types_errors)
        if types_table is not None:
            for category in ("wood_type", "leaves_type"):
                if category in types_table:
                    errors.extend(
                        _validate_modid_bool_map(types_table[category], f"types.{category}")
                    )

    if "entries" in root:
        entries_table, entries_errors = _check_keys_with_rationale(
            root["entries"],
            ENTRIES_REL_PATH,
            "entries",
            ("wood_type",),
            schema_rationale,
            optional_keys=("leaves_type",),
        )
        errors.extend(entries_errors)
        if entries_table is not None:
            for category in ("wood_type", "leaves_type"):
                if category in entries_table:
                    errors.extend(
                        _validate_modid_bool_map(
                            entries_table[category], f"entries.{category}"
                        )
                    )

    return errors


def validate_everycomp_hazardous(data: Any) -> list[str]:
    """Validate schema, regex compilation, and booleans for `config/everycomp-hazardous.toml`."""
    schema_rationale = (
        "everycomp-hazardous.toml controls conditional block/module registration that must "
        "match between server and client; exact section and key structure prevents silent "
        "registry mismatches that would block players from joining."
    )
    root, errors = _check_keys_with_rationale(
        data, HAZARDOUS_REL_PATH, "root", HAZARDOUS_ROOT_KEYS, schema_rationale
    )
    if root is None:
        return errors

    for section in HAZARDOUS_REGEX_SECTIONS:
        if section not in root:
            continue
        sec_table, sec_errors = _check_keys_with_rationale(
            root[section], HAZARDOUS_REL_PATH, section, ("blacklist",), schema_rationale
        )
        errors.extend(sec_errors)
        if sec_table is None or "blacklist" not in sec_table:
            continue

        blacklist = sec_table["blacklist"]
        if not isinstance(blacklist, list):
            errors.append(
                f"{HAZARDOUS_REL_PATH} invariant violation: '{section}.blacklist' must be "
                f"a list of regex strings (got {type(blacklist).__name__}) so Every Compat "
                "can evaluate conditional registration exclusions."
            )
            continue

        for idx, pattern in enumerate(blacklist):
            if not isinstance(pattern, str) or not pattern.strip():
                errors.append(
                    f"{HAZARDOUS_REL_PATH} invariant violation: "
                    f"'{section}.blacklist[{idx}]' must be a non-empty regex string "
                    f"(got {pattern!r}) so empty patterns do not unintentionally match all entries."
                )
                continue
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(
                    f"{HAZARDOUS_REL_PATH} invariant violation: "
                    f"'{section}.blacklist[{idx}]' ({pattern!r}) is not a valid regex "
                    f"({exc}); invalid regexes can break conditional registration on startup."
                )

    if "other" in root:
        other_table, other_errors = _check_keys_with_rationale(
            root["other"],
            HAZARDOUS_REL_PATH,
            "other",
            ("include_all_wood_modules",),
            schema_rationale,
        )
        errors.extend(other_errors)
        if other_table is not None:
            errors.extend(
                _validate_strict_bool(
                    other_table,
                    HAZARDOUS_REL_PATH,
                    "other.include_all_wood_modules",
                    "include_all_wood_modules",
                    "Every Compat requires a strict boolean for include_all_wood_modules "
                    "to keep server and client wood-module registries aligned.",
                )
            )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/everycomp/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            COMMON_REL_PATH: validate_everycomp_common,
            ENTRIES_REL_PATH: validate_everycomp_entries,
            HAZARDOUS_REL_PATH: validate_everycomp_hazardous,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Every Compat static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "everycomp",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Every Compat static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
