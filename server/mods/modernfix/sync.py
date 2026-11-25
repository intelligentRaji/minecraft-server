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
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    run_sync_cli,
    scan_mapping_for_secrets,
    validate_static_configs,
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

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

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


def validate_modernfix_common(data: object) -> list[str]:
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
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            "modernfix-common.toml": validate_modernfix_common,
            "modernfix-mixins.properties": lambda raw: validate_modernfix_mixins(
                raw, "modernfix-mixins.properties"
            ),
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated ModernFix static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


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
