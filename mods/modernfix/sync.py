#!/usr/bin/env python3
"""One-way deterministic configuration placement for ModernFix.

Places static configuration from `mods/modernfix/configs/` into `data/`:
- `modernfix-common.toml` -> `data/config/modernfix-common.toml`
- `modernfix-mixins.properties` -> `data/config/modernfix-mixins.properties`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
Never reads, copies, or modifies excluded runtime directories (`data/logs/`, `data/world/`,
`data/mods/`).
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    check_forbidden_entries,
    collect_config_files,
    run_sync_cli,
    scan_mapping_for_secrets,
    scan_text_for_secrets,
    sync_static_file as bridge_sync_static_file,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "modernfix-common.toml": ("config", "modernfix-common.toml"),
    "modernfix-mixins.properties": ("config", "modernfix-mixins.properties"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bak",
    ".tmp",
    ".lock",
    ".db",
    ".jar",
)

EXPECTED_COMMON_KEYS: frozenset[str] = frozenset({
    "blacklist_async_jei_plugins",
})

VALID_STABILITY_LEVELS: frozenset[str] = frozenset({
    "GA",
    "BETA",
    "ALPHA",
})

VALID_PROPERTY_BOOLEANS: frozenset[str] = frozenset({
    "true",
    "false",
})


def validate_modernfix_common(data: Any) -> list[str]:
    """Validate architectural and operational invariants for `modernfix-common.toml`."""
    if not isinstance(data, dict):
        return [
            f"modernfix-common.toml invariant violation: root TOML value must be a table "
            f"(got {type(data).__name__}) so ModernFix can deserialize its common configuration schema."
        ]

    errors: list[str] = []

    unknown_keys = sorted(set(data.keys()) - EXPECTED_COMMON_KEYS)
    if unknown_keys:
        errors.append(
            f"modernfix-common.toml invariant violation: unexpected keys {unknown_keys} "
            "(mods/modernfix/configs/modernfix-common.toml must contain only ModernFix's static "
            "common schema and never embed unvalidated or secret fields)."
        )

    blacklist = data.get("blacklist_async_jei_plugins")
    if not isinstance(blacklist, list) or any(
        not isinstance(item, str) or not item.strip() for item in blacklist
    ):
        errors.append(
            f"modernfix-common.toml invariant violation: blacklist_async_jei_plugins must be a "
            f"list of non-empty strings (got {blacklist!r}) so ModernFix knows which JEI plugins "
            "must be loaded on the main thread."
        )

    return errors


def validate_modernfix_mixins(raw_text: str, rel: str) -> list[str]:
    """Validate syntax, allowed keys, and secret guards for `modernfix-mixins.properties`."""
    errors: list[str] = []
    parsed_props: dict[str, str] = {}

    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue

        if "=" not in raw_line:
            errors.append(
                f"{rel}:{line_no} invariant violation: non-comment line must be a 'key=value' "
                f"assignment (got {raw_line!r}) so ModernFix's Java Properties parser can load it cleanly."
            )
            continue

        raw_key, raw_val = raw_line.split("=", 1)
        key = raw_key.strip()
        value = raw_val.strip()

        if not key:
            errors.append(
                f"{rel}:{line_no} invariant violation: property key must be non-empty "
                "(blank keys are invalid in ModernFix's mixin override properties)."
            )
            continue

        parsed_props[key] = value

        if key == "stability_level":
            if value not in VALID_STABILITY_LEVELS:
                errors.append(
                    f"{rel}:{line_no} invariant violation: stability_level must be one of "
                    f"{sorted(VALID_STABILITY_LEVELS)} (got {value!r}) so ModernFix enables only "
                    "recognized feature stability tiers."
                )
        elif key.startswith("mixin.") and len(key) > len("mixin."):
            if value not in VALID_PROPERTY_BOOLEANS:
                errors.append(
                    f"{rel}:{line_no} invariant violation: {key} must be 'true' or 'false' "
                    f"(got {value!r}) so ModernFix can deterministically toggle the mixin rule."
                )
        else:
            errors.append(
                f"{rel}:{line_no} invariant violation: unexpected property key {key!r} "
                "(only 'mixin.*' boolean flags and 'stability_level' are permitted in "
                "modernfix-mixins.properties so unvalidated or secret keys are never committed)."
            )

    errors.extend(scan_mapping_for_secrets(parsed_props, rel))
    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/modernfix/configs/` before placement."""
    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    errors = check_forbidden_entries(CONFIGS_DIR, FORBIDDEN_NAMES, FORBIDDEN_SUFFIXES)
    config_files, collect_errors = collect_config_files(CONFIGS_DIR)
    errors.extend(collect_errors)

    expected_files = set(STATIC_FILES.keys())
    actual_files = set(config_files.keys())

    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing:
        errors.append(f"Missing expected config files in configs/: {', '.join(missing)}")
    if unexpected:
        errors.append(f"Unexpected files in configs/: {', '.join(unexpected)}")

    loaded_bytes: dict[str, bytes] = {}
    for rel in sorted(actual_files & expected_files):
        raw_bytes = config_files[rel].read_bytes()
        loaded_bytes[rel] = raw_bytes
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{rel}: invalid UTF-8 ({exc})")
            continue

        errors.extend(scan_text_for_secrets(raw_text, rel))

        if rel == "modernfix-common.toml":
            try:
                parsed_toml = tomllib.loads(raw_text)
            except Exception as exc:
                errors.append(f"{rel}: invalid TOML ({exc})")
                continue

            errors.extend(scan_mapping_for_secrets(parsed_toml, rel))
            errors.extend(validate_modernfix_common(parsed_toml))
        elif rel == "modernfix-mixins.properties":
            errors.extend(validate_modernfix_mixins(raw_text, rel))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated ModernFix static files into `DATA_DIR`."""
    changed = 0
    unchanged = 0
    for rel in STATIC_FILES:
        dst_path = DATA_DIR.joinpath(*STATIC_FILES[rel])
        if bridge_sync_static_file(dst_path, loaded_bytes[rel], dry_run=dry_run):
            action = "Would update (static)" if dry_run else "Updated (static)"
            print(f"  [{action}] {rel} -> {dst_path.relative_to(DATA_DIR).as_posix()}")
            changed += 1
        else:
            unchanged += 1
    return changed, unchanged


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "modernfix",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place ModernFix static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
