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
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
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

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

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
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            "simplebackups-common.toml": validate_common_toml,
            "simplebackups-server.toml": validate_server_toml,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Simple Backups static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


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
