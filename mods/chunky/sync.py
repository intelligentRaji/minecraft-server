#!/usr/bin/env python3
"""One-way deterministic configuration placement for Chunky.

Places static configuration from `mods/chunky/configs/` into `data/`:
- `config.json` -> `data/config/chunky/config.json`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
Never reads, copies, or modifies excluded live chunk pre-generation task state or runtime
directories (`data/config/chunky/tasks/`, `data/logs/`, `data/world/`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    check_forbidden_entries,
    collect_config_files,
    is_strict_int,
    run_sync_cli,
    scan_mapping_for_secrets,
    scan_text_for_secrets,
    sync_static_file as bridge_sync_static_file,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "config.json": ("config", "chunky", "config.json"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "tasks",
    "logs",
    "world",
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

EXPECTED_CONFIG_KEYS: frozenset[str] = frozenset({
    "version",
    "language",
    "continueOnRestart",
    "forceLoadExistingChunks",
    "silent",
    "updateInterval",
})


def validate_chunky_config(data: Any) -> list[str]:
    """Validate architectural and operational invariants for Chunky `config.json`."""
    if not isinstance(data, dict):
        return [
            f"config.json invariant violation: root JSON value must be an object "
            f"(got {type(data).__name__}) so Chunky can deserialize its configuration schema."
        ]

    errors: list[str] = []

    unknown_keys = sorted(set(data.keys()) - EXPECTED_CONFIG_KEYS)
    if unknown_keys:
        errors.append(
            f"config.json invariant violation: unexpected keys {unknown_keys} "
            "(mods/chunky/configs/config.json must contain only Chunky's static configuration schema "
            "and never embed runtime task state or unvalidated/secret fields)."
        )

    version = data.get("version")
    if not is_strict_int(version) or version < 1:
        errors.append(
            f"config.json invariant violation: version must be an integer >= 1 "
            f"(got {version!r}) so Chunky can identify and migrate its configuration schema on startup."
        )

    language = data.get("language")
    if not isinstance(language, str) or not language.strip():
        errors.append(
            f"config.json invariant violation: language must be a non-empty string "
            f"(got {language!r}) so Chunky can load a valid server localization bundle."
        )

    bool_keys: tuple[tuple[str, str], ...] = (
        (
            "continueOnRestart",
            "control deterministically whether interrupted tasks in data/config/chunky/tasks/ resume on server restart",
        ),
        (
            "forceLoadExistingChunks",
            "control deterministically whether already-generated chunks are re-processed during pre-generation",
        ),
        (
            "silent",
            "control deterministically whether Chunky suppresses progress broadcasts during pre-generation",
        ),
    )
    for key, rationale in bool_keys:
        val = data.get(key)
        if not isinstance(val, bool):
            errors.append(
                f"config.json invariant violation: {key} must be a boolean "
                f"(got {val!r}) to {rationale}."
            )

    update_interval = data.get("updateInterval")
    if not is_strict_int(update_interval) or update_interval < 1:
        errors.append(
            f"config.json invariant violation: updateInterval must be an integer >= 1 "
            f"(got {update_interval!r}) to prevent zero/negative status-reporting intervals in seconds."
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/chunky/configs/` before placement."""
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

        try:
            parsed = json.loads(raw_text)
        except Exception as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
            continue

        errors.extend(scan_mapping_for_secrets(parsed, rel))

        if rel == "config.json":
            errors.extend(validate_chunky_config(parsed))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Chunky static files into `DATA_DIR`."""
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
        "chunky",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Chunky static config into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
