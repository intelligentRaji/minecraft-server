#!/usr/bin/env python3
"""One-way deterministic configuration placement & key-level merge for Paradigm Essentials.

Places static configurations from `mods/paradigm/configs/` into `data/config/paradigm/`:
- Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
- Atomically replaces pure static JSON files when SHA-256 differs.
- Atomically key-merges `cooldowns.json` and `holograms.json` so live player cooldowns
  (`"cooldowns"`) and in-world holograms (`"holograms"`) in `data/` are never overwritten.
- Never reads or modifies forbidden secret/database files (`discord.json`, `storage.json`,
  `discovered_permissions.json`, `data/`, `libs/`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# Deterministic zero-walk path resolution (mods/paradigm/sync.py -> repo root)
MOD_DIR = Path(__file__).resolve().parent
REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"
TARGET_DIR = DATA_DIR / "config" / "paradigm"

STATIC_FILES: tuple[str, ...] = (
    "afk.json",
    "announcements.json",
    "chat.json",
    "commands.json",
    "commands/examples.json",
    "dashboard.json",
    "emojis.json",
    "lang/cs.json",
    "lang/en.json",
    "lang/ru.json",
    "main.json",
    "mentions.json",
    "moderation-settings.json",
    "motd.json",
    "restarts.json",
    "tablist.json",
    "tickets.json",
)

COOLDOWNS_STATIC_KEYS: tuple[str, ...] = (
    "commandCooldownSeconds",
    "commandWarmupSeconds",
)

HOLOGRAMS_STATIC_KEYS: tuple[str, ...] = (
    "enabled",
    "defaultViewDistance",
    "defaultRefreshIntervalSeconds",
    "renderMode",
)

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "discord.json",
    "storage.json",
    "discovered_permissions.json",
    "data",
    "libs",
    "icons",
    "menus",
})

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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_json_for_secrets(obj: Any, rel_path: str, key_path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{key_path}.{k}" if key_path else k
            if k.lower() in SECRET_KEY_NAMES and isinstance(v, str) and v.strip():
                errors.append(f"{rel_path}: non-empty secret key '{current_path}'")
            errors.extend(scan_json_for_secrets(v, rel_path, current_path))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            errors.extend(scan_json_for_secrets(item, rel_path, f"{key_path}[{idx}]"))
    elif isinstance(obj, str):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(obj):
                errors.append(f"{rel_path}: detected {label} at '{key_path}'")
    return errors


def validate_configs() -> dict[str, Any]:
    """Validate all static and mixed config files in mods/paradigm/configs/ before placement."""
    errors: list[str] = []

    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    for forbidden in sorted(FORBIDDEN_NAMES):
        candidate = CONFIGS_DIR / forbidden
        if candidate.exists():
            errors.append(f"Forbidden file/directory present in configs/: {forbidden}")

    expected_files = set(STATIC_FILES) | {"cooldowns.json", "holograms.json"}
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

    parsed: dict[str, Any] = {}
    for rel in sorted(actual_files & expected_files):
        fpath = CONFIGS_DIR / rel
        try:
            raw_text = fpath.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            parsed[rel] = data
        except Exception as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
            continue

        errors.extend(scan_json_for_secrets(data, rel))

    main_data = parsed.get("main.json")
    if isinstance(main_data, dict):
        internal_perms = main_data.get("internalPermissionsEnable", {})
        val = internal_perms.get("value") if isinstance(internal_perms, dict) else None
        if val is not False:
            errors.append(
                f"main.json invariant violation: internalPermissionsEnable.value must be false (got {val!r}) "
                "because LuckPerms is the single source of truth for permissions and {prefix}/{suffix} metadata "
                "rather than Paradigm's internal SQLite database (paradigm.db)."
            )

    chat_data = parsed.get("chat.json")
    if isinstance(chat_data, dict):
        chat_fmt_obj = chat_data.get("customChatFormat", {})
        chat_fmt = chat_fmt_obj.get("value") if isinstance(chat_fmt_obj, dict) else None
        if not isinstance(chat_fmt, str) or "{prefix}{player_name}{suffix}" not in chat_fmt:
            errors.append(
                "chat.json invariant violation: customChatFormat.value must contain '{prefix}{player_name}{suffix}' "
                "so LuckPerms staff prefixes (&c&l[OWN] , &c[ADM] , &d[MOD] ) and FCM Clan suffixes color the "
                "prefix, player nickname, and clan tag uniformly."
            )

    tablist_data = parsed.get("tablist.json")
    if isinstance(tablist_data, dict):
        tab_fmt_obj = tablist_data.get("playerFormat", {})
        tab_fmt = tab_fmt_obj.get("value") if isinstance(tab_fmt_obj, dict) else None
        if not isinstance(tab_fmt, str) or "{prefix}{player_name}{suffix}" not in tab_fmt:
            errors.append(
                "tablist.json invariant violation: playerFormat.value must contain '{prefix}{player_name}{suffix}' "
                "so LuckPerms staff prefixes and FCM Clan suffixes render uniformly in the player tablist."
            )

    cooldowns_data = parsed.get("cooldowns.json")
    if isinstance(cooldowns_data, dict):
        if "cooldowns" in cooldowns_data:
            errors.append(
                "cooldowns.json state isolation violation: runtime key 'cooldowns' must not exist in repo configs/ "
                "because per-player cooldown UUID timestamps are live server runtime state in data/ that sync.py "
                "preserves via key-level merge."
            )
        actual_keys = set(cooldowns_data.keys())
        expected_keys = set(COOLDOWNS_STATIC_KEYS)
        if actual_keys != expected_keys:
            errors.append(
                f"cooldowns.json key mismatch: expected only static keys {sorted(expected_keys)}, got {sorted(actual_keys)} "
                "(live per-player cooldown state must remain exclusively in data/config/paradigm/cooldowns.json)."
            )
    elif "cooldowns.json" in parsed:
        errors.append("cooldowns.json must be a JSON object")

    holograms_data = parsed.get("holograms.json")
    if isinstance(holograms_data, dict):
        if "holograms" in holograms_data:
            errors.append(
                "holograms.json state isolation violation: runtime key 'holograms' must not exist in repo configs/ "
                "because placed in-world holograms are mutated live in-game via /hologram and preserved in data/ "
                "via key-level merge."
            )
        actual_keys = set(holograms_data.keys())
        expected_keys = set(HOLOGRAMS_STATIC_KEYS)
        if actual_keys != expected_keys:
            errors.append(
                f"holograms.json key mismatch: expected only static keys {sorted(expected_keys)}, got {sorted(actual_keys)} "
                "(live in-world hologram definitions must remain exclusively in data/config/paradigm/holograms.json)."
            )
    elif "holograms.json" in parsed:
        errors.append("holograms.json must be a JSON object")

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return parsed


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


def sync_static_file(rel: str, dry_run: bool) -> bool:
    """Atomically copy `configs/<rel>` to `data/config/paradigm/<rel>` when SHA-256 differs."""
    src_path = CONFIGS_DIR / rel
    dst_path = TARGET_DIR / rel
    src_bytes = src_path.read_bytes()

    if dst_path.exists() and sha256_bytes(dst_path.read_bytes()) == sha256_bytes(src_bytes):
        return False

    action = "Would update (static)" if dry_run else "Updated (static)"
    print(f"  [{action}] {rel}")
    if not dry_run:
        atomic_write_bytes(dst_path, src_bytes)
    return True


def sync_mixed_file(
    rel: str,
    static_data: dict[str, Any],
    static_keys: tuple[str, ...],
    runtime_key: str,
    runtime_first: bool,
    dry_run: bool,
) -> bool:
    """Atomically merge `static_keys` into `data/config/paradigm/<rel>` while preserving live `runtime_key`."""
    dst_path = TARGET_DIR / rel
    existing_bytes: bytes | None = None
    existing_obj: dict[str, Any] = {}
    trailing_newline = False

    if dst_path.exists():
        existing_bytes = dst_path.read_bytes()
        trailing_newline = existing_bytes.endswith(b"\n")
        loaded = json.loads(existing_bytes.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Target file {dst_path} is not a JSON object")
        existing_obj = loaded

    merged: dict[str, Any] = {}
    if runtime_first:
        merged[runtime_key] = existing_obj.get(runtime_key, {})
        for k in static_keys:
            merged[k] = static_data[k]
        for k, v in existing_obj.items():
            if k not in merged:
                merged[k] = v
    else:
        for k in static_keys:
            merged[k] = static_data[k]
        merged[runtime_key] = existing_obj.get(runtime_key, {})
        for k, v in existing_obj.items():
            if k not in merged:
                merged[k] = v

    serialized_str = json.dumps(merged, indent=2, ensure_ascii=False)
    if trailing_newline:
        serialized_str += "\n"
    new_bytes = serialized_str.encode("utf-8")

    if existing_bytes is not None and sha256_bytes(existing_bytes) == sha256_bytes(new_bytes):
        return False

    action = "Would key-merge (mixed)" if dry_run else "Key-merged (mixed)"
    print(f"  [{action}] {rel} (preserved runtime '{runtime_key}')")
    if not dry_run:
        atomic_write_bytes(dst_path, new_bytes)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and atomically place Paradigm static configs into data/config/paradigm/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview changes without modifying data/config/paradigm/.",
    )
    args = parser.parse_args(argv)

    try:
        parsed = validate_configs()
    except Exception as exc:
        print(f"[paradigm/sync.py] ERROR: {exc}", file=sys.stderr)
        return 1

    changed_count = 0
    unchanged_count = 0

    for rel in STATIC_FILES:
        if sync_static_file(rel, dry_run=args.dry_run):
            changed_count += 1
        else:
            unchanged_count += 1

    if sync_mixed_file(
        rel="cooldowns.json",
        static_data=parsed["cooldowns.json"],
        static_keys=COOLDOWNS_STATIC_KEYS,
        runtime_key="cooldowns",
        runtime_first=True,
        dry_run=args.dry_run,
    ):
        changed_count += 1
    else:
        unchanged_count += 1

    if sync_mixed_file(
        rel="holograms.json",
        static_data=parsed["holograms.json"],
        static_keys=HOLOGRAMS_STATIC_KEYS,
        runtime_key="holograms",
        runtime_first=False,
        dry_run=args.dry_run,
    ):
        changed_count += 1
    else:
        unchanged_count += 1

    mode_label = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[paradigm/sync.py] {mode_label}: {changed_count} changed, {unchanged_count} unchanged "
        f"(total {changed_count + unchanged_count} files verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
