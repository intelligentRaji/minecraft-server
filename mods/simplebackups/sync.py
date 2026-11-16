#!/usr/bin/env python3
"""One-way deterministic configuration placement for Simple Backups.

Places static configurations from `mods/simplebackups/configs/` into `data/`:
- `simplebackups-common.toml` -> `data/config/simplebackups-common.toml`
- `simplebackups-server.toml` -> `data/world/serverconfig/simplebackups-server.toml`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
Never reads, copies, or modifies excluded backup archives or runtime directories (`data/simplebackups/`,
`data/logs/`, `data/world/` level/region data).
"""

from __future__ import annotations

import re
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
    "simplebackups-common.toml": ("config", "simplebackups-common.toml"),
    "simplebackups-server.toml": ("world", "serverconfig", "simplebackups-server.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "simplebackups",
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

VALID_BACKUP_TYPES: frozenset[str] = frozenset({
    "FULL_BACKUPS",
    "MODIFIED_SINCE_LAST",
    "MODIFIED_SINCE_FULL",
})

MAX_DISK_SIZE_RE = re.compile(r"^\d+\s+(B|KB|MB|GB|TB)$")


def validate_common_toml(data: dict[str, Any]) -> list[str]:
    """Validate architectural and operational invariants for `simplebackups-common.toml`."""
    errors: list[str] = []

    output_path = data.get("outputPath")
    if output_path != "simplebackups":
        errors.append(
            f"simplebackups-common.toml invariant violation: outputPath must be \"simplebackups\" "
            f"(got {output_path!r}) as a relative path inside data/ with no '..' or leading '/', "
            "ensuring backup archives stay inside data/simplebackups/ and never escape the server data volume."
        )

    backup_type = data.get("backupType")
    if backup_type not in VALID_BACKUP_TYPES:
        errors.append(
            f"simplebackups-common.toml invariant violation: backupType must be one of "
            f"{sorted(VALID_BACKUP_TYPES)} (got {backup_type!r}) so Simple Backups creates valid, "
            "restorable archive chains."
        )

    int_ranges: tuple[tuple[str, int, int, str], ...] = (
        ("backupsToKeep", 1, 32767, "retain at least 1 backup while staying within Forge's 16-bit config bound"),
        ("timer", 1, 32767, "prevent zero/negative backup intervals and stay within Forge's 16-bit config bound"),
        ("fullBackupTimer", 1, 5259600, "bound full-backup cadence between 1 minute and 10 years"),
        ("compressionLevel", -1, 9, "match zlib/zip compression levels (-1 default through 9 maximum)"),
    )
    for key, low, high, rationale in int_ranges:
        val = data.get(key)
        if not is_strict_int(val) or val < low or val > high:
            errors.append(
                f"simplebackups-common.toml invariant violation: {key} must be an integer in {low}..{high} "
                f"(got {val!r}) to {rationale}."
            )

    max_disk_size = data.get("maxDiskSize")
    if not isinstance(max_disk_size, str) or not MAX_DISK_SIZE_RE.match(max_disk_size):
        errors.append(
            f"simplebackups-common.toml invariant violation: maxDiskSize must match '<number> <B|KB|MB|GB|TB>' "
            f"(got {max_disk_size!r}) so Forge/Simple Backups can parse the storage quota and prune old archives."
        )

    return errors


def validate_server_toml(data: dict[str, Any]) -> list[str]:
    """Validate multiplayer permission invariants for `simplebackups-server.toml`."""
    errors: list[str] = []

    commands_cheats_disabled = data.get("commandsCheatsDisabled")
    if commands_cheats_disabled is not False:
        errors.append(
            f"simplebackups-server.toml invariant violation: commandsCheatsDisabled must be false "
            f"(got {commands_cheats_disabled!r}) because on a multiplayer server setting it to true allows "
            "non-OP players without cheats or permissions to trigger /simplebackups commands."
        )

    messages_for_everyone = data.get("messagesForEveryone")
    if not isinstance(messages_for_everyone, bool):
        errors.append(
            f"simplebackups-server.toml invariant violation: messagesForEveryone must be a boolean "
            f"(got {messages_for_everyone!r}) so Simple Backups can deterministically route backup status broadcasts."
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/simplebackups/configs/` before placement."""
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
        raw_text = raw_bytes.decode("utf-8")

        errors.extend(scan_text_for_secrets(raw_text, rel))

        try:
            parsed = tomllib.loads(raw_text)
        except Exception as exc:
            errors.append(f"{rel}: invalid TOML ({exc})")
            continue

        errors.extend(scan_mapping_for_secrets(parsed, rel))

        if rel == "simplebackups-common.toml":
            errors.extend(validate_common_toml(parsed))
        elif rel == "simplebackups-server.toml":
            errors.extend(validate_server_toml(parsed))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Simple Backups static files into `DATA_DIR`."""
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
        "simplebackups",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Simple Backups static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
