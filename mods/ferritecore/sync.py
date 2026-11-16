#!/usr/bin/env python3
"""One-way deterministic configuration placement for FerriteCore.

Places static configuration from `mods/ferritecore/configs/` into `data/`:
- `config/ferritecore-mixin.toml` -> `data/config/ferritecore-mixin.toml`

Validates schema types, dependency invariants, runtime state isolation, and
secret guards before touching `data/`.
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

FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".jar",
    ".db",
    ".sqlite",
    ".log",
    ".gz",
    ".zip",
    ".tar",
    ".tgz",
    ".bak",
    ".tmp",
    ".lock",
)

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


def validate_ferritecore_mixin(data: Any) -> list[str]:
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
        errors.append(
            f"Missing expected config files in configs/: {', '.join(missing)} "
            "(all static FerriteCore configs must be present for deterministic server placement)."
        )
    if unexpected:
        errors.append(
            f"Unexpected files in configs/: {', '.join(unexpected)} "
            "(only config/ferritecore-mixin.toml is permitted so runtime state or unvalidated "
            "files are never synced into data/)."
        )

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

        try:
            parsed_toml = tomllib.loads(raw_text)
        except Exception as exc:
            errors.append(f"{rel}: invalid TOML ({exc})")
            continue

        errors.extend(scan_mapping_for_secrets(parsed_toml, rel))
        errors.extend(validate_ferritecore_mixin(parsed_toml))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated FerriteCore static files into `DATA_DIR`."""
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
        "ferritecore",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place FerriteCore static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
