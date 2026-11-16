#!/usr/bin/env python3
"""One-way deterministic configuration placement for CoreCommands.

Places static configuration from `mods/corecommands/configs/` into `data/`:
- `config.json` -> `data/config/corecommands/config.json`
- `rules.json` -> `data/config/corecommands/rules.json`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
Never reads, copies, or modifies excluded live player/world runtime state files in
`data/config/corecommands/` (`afkstatus.json`, `deathlocation.json`, `homes.json`,
`lastlocation.json`, `lastmessagerecipient.json`, `logoutposition.json`,
`playerjoinstatus.json`, `spawn.json`, `tparequests.json`, `warps.json`) or
runtime directories (`data/logs/`, `data/world/`).
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
    run_sync_cli,
    scan_mapping_for_secrets,
    scan_text_for_secrets,
    sync_static_file as bridge_sync_static_file,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "config.json": ("config", "corecommands", "config.json"),
    "rules.json": ("config", "corecommands", "rules.json"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "afkstatus.json",
    "deathlocation.json",
    "homes.json",
    "lastlocation.json",
    "lastmessagerecipient.json",
    "logoutposition.json",
    "playerjoinstatus.json",
    "spawn.json",
    "tparequests.json",
    "warps.json",
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
    ".log",
)

EXPECTED_CONFIG_KEYS: frozenset[str] = frozenset({
    "backCommandEnabled",
    "comment_backCommand",
})


def validate_corecommands_config(data: Any) -> list[str]:
    """Validate architectural and operational invariants for CoreCommands `config.json`."""
    if not isinstance(data, dict):
        return [
            f"config.json invariant violation: root JSON value must be an object "
            f"(got {type(data).__name__}) so CoreCommands can deserialize its configuration schema."
        ]

    errors: list[str] = []

    unknown_keys = sorted(set(data.keys()) - EXPECTED_CONFIG_KEYS)
    if unknown_keys:
        errors.append(
            f"config.json invariant violation: unexpected keys {unknown_keys} "
            "(mods/corecommands/configs/config.json must contain only CoreCommands' static "
            "configuration schema and never embed runtime player/world state or unvalidated fields)."
        )

    back_enabled = data.get("backCommandEnabled")
    if not isinstance(back_enabled, bool):
        errors.append(
            f"config.json invariant violation: backCommandEnabled must be a boolean "
            f"(got {back_enabled!r}) to deterministically enable or disable the /back command on the server."
        )

    if "comment_backCommand" in data:
        comment = data["comment_backCommand"]
        if not isinstance(comment, str):
            errors.append(
                f"config.json invariant violation: comment_backCommand must be a string "
                f"(got {comment!r}) to preserve CoreCommands' inline schema documentation."
            )

    return errors


def validate_corecommands_rules(data: Any) -> list[str]:
    """Validate architectural and operational invariants for CoreCommands `rules.json`."""
    if not isinstance(data, list):
        return [
            f"rules.json invariant violation: root JSON value must be a list of rule strings "
            f"(got {type(data).__name__}) so CoreCommands can render /rules lines in order."
        ]

    errors: list[str] = []
    for idx, item in enumerate(data):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                f"rules.json invariant violation: rule entry at index {idx} must be a non-empty string "
                f"(got {item!r}) so /rules never displays blank or non-text entries to players."
            )
    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/corecommands/configs/` before placement."""
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
            errors.extend(validate_corecommands_config(parsed))
        elif rel == "rules.json":
            errors.extend(validate_corecommands_rules(parsed))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated CoreCommands static files into `DATA_DIR`."""
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
        "corecommands",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place CoreCommands static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
