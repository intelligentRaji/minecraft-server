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

import argparse
import hashlib
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
REPO_ROOT = MOD_DIR.parent.parent
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

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Discord Webhook URL", re.compile(r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+", re.IGNORECASE)),
    ("Discord Bot Token", re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}")),
    ("Private Key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

SECRET_KEY_NAMES: frozenset[str] = frozenset({
    "bottoken",
    "webhookurl",
    "password",
    "secret",
    "apikey",
    "accesstoken",
    "clientsecret",
})

VALID_BACKUP_TYPES: frozenset[str] = frozenset({
    "FULL_BACKUPS",
    "MODIFIED_SINCE_LAST",
    "MODIFIED_SINCE_FULL",
})

MAX_DISK_SIZE_RE = re.compile(r"^\d+\s+(B|KB|MB|GB|TB)$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def scan_toml_for_secrets(obj: Any, rel_path: str, key_path: str = "") -> list[str]:
    """Recursively scan parsed TOML keys and string values for secrets or credentials."""
    errors: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{key_path}.{k}" if key_path else k
            if k.lower() in SECRET_KEY_NAMES and isinstance(v, str) and v.strip():
                errors.append(
                    f"{rel_path}: non-empty secret key '{current_path}' "
                    "(credentials and tokens must never be committed to static mod configs)"
                )
            errors.extend(scan_toml_for_secrets(v, rel_path, current_path))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            errors.extend(scan_toml_for_secrets(item, rel_path, f"{key_path}[{idx}]"))
    elif isinstance(obj, str):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(obj):
                errors.append(
                    f"{rel_path}: detected {label} at '{key_path}' "
                    "(secrets must never be committed to static mod configs)"
                )
    return errors


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
    errors: list[str] = []

    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    for forbidden in sorted(FORBIDDEN_NAMES):
        candidate = CONFIGS_DIR / forbidden
        if candidate.exists():
            errors.append(
                f"Forbidden file/directory present in configs/: {forbidden} "
                "(live backup archives, logs, and world state must remain exclusively in data/ and never be committed)"
            )

    for p in sorted(CONFIGS_DIR.rglob("*")):
        rel = p.relative_to(CONFIGS_DIR).as_posix()
        if p.is_file() and p.name.endswith(FORBIDDEN_SUFFIXES) and rel not in FORBIDDEN_NAMES:
            errors.append(
                f"Forbidden archive/runtime file present in configs/: {rel} "
                "(backup archives, locks, databases, and JAR artifacts must remain exclusively in data/)"
            )

    expected_files = set(STATIC_FILES.keys())
    actual_files = {
        p.relative_to(CONFIGS_DIR).as_posix()
        for p in CONFIGS_DIR.rglob("*")
        if p.is_file()
    }

    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing:
        errors.append(f"Missing expected config files in configs/: {', '.join(missing)}")
    if unexpected:
        errors.append(f"Unexpected files in configs/: {', '.join(unexpected)}")

    loaded_bytes: dict[str, bytes] = {}
    for rel in sorted(actual_files & expected_files):
        fpath = CONFIGS_DIR / rel
        raw_bytes = fpath.read_bytes()
        loaded_bytes[rel] = raw_bytes
        raw_text = raw_bytes.decode("utf-8")

        for label, pattern in SECRET_PATTERNS:
            if pattern.search(raw_text):
                errors.append(
                    f"{rel}: detected {label} "
                    "(secrets must never be committed to static mod configs)"
                )

        try:
            parsed = tomllib.loads(raw_text)
        except Exception as exc:
            errors.append(f"{rel}: invalid TOML ({exc})")
            continue

        errors.extend(scan_toml_for_secrets(parsed, rel))

        if rel == "simplebackups-common.toml":
            errors.extend(validate_common_toml(parsed))
        elif rel == "simplebackups-server.toml":
            errors.extend(validate_server_toml(parsed))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def atomic_write_bytes(target_path: Path, data: bytes, default_mode: int = 0o664) -> None:
    """Write `data` to a temporary file in `target_path.parent`, preserve permissions/ownership, and atomically replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        st = target_path.stat()
        mode = st.st_mode & 0o777
        uid, gid = st.st_uid, st.st_gid
    else:
        parent_st = target_path.parent.stat()
        mode = default_mode
        uid, gid = parent_st.st_uid, parent_st.st_gid

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=str(target_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.chown(tmp_path, uid, gid)
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def sync_static_file(rel: str, src_bytes: bytes, dry_run: bool) -> bool:
    """Atomically copy `configs/<rel>` to its target path under `DATA_DIR` when SHA-256 differs."""
    dst_path = DATA_DIR.joinpath(*STATIC_FILES[rel])

    if dst_path.exists() and sha256_bytes(dst_path.read_bytes()) == sha256_bytes(src_bytes):
        return False

    action = "Would update (static)" if dry_run else "Updated (static)"
    print(f"  [{action}] {rel} -> {dst_path.relative_to(DATA_DIR).as_posix()}")
    if not dry_run:
        atomic_write_bytes(dst_path, src_bytes)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and atomically place Simple Backups static configs into data/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview changes without modifying data/.",
    )
    args = parser.parse_args(argv)

    try:
        loaded_bytes = validate_configs()
    except Exception as exc:
        print(f"[simplebackups/sync.py] ERROR: {exc}", file=sys.stderr)
        return 1

    changed_count = 0
    unchanged_count = 0

    for rel in STATIC_FILES:
        if sync_static_file(rel, loaded_bytes[rel], dry_run=args.dry_run):
            changed_count += 1
        else:
            unchanged_count += 1

    mode_label = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[simplebackups/sync.py] {mode_label}: {changed_count} changed, {unchanged_count} unchanged "
        f"(total {changed_count + unchanged_count} files verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
