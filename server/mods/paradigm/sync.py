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

import json
import sys
from pathlib import Path
from typing import Any

# Deterministic zero-walk path resolution (mods/paradigm/sync.py -> repo root)
MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    atomic_write_bytes,
    check_forbidden_entries,
    collect_config_files,
    run_sync_cli,
    scan_mapping_for_secrets,
    sha256_bytes,
)
from _bridge import (  # noqa: E402
    sync_static_file as bridge_sync_static_file,
)

REPO_ROOT = MODS_DIR.parent
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


def validate_configs() -> dict[str, Any]:
    """Validate all static and mixed config files in mods/paradigm/configs/ before placement."""
    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    errors = check_forbidden_entries(CONFIGS_DIR, FORBIDDEN_NAMES)
    config_files, collect_errors = collect_config_files(CONFIGS_DIR)
    errors.extend(collect_errors)

    expected_files = set(STATIC_FILES) | {"cooldowns.json", "holograms.json"}
    actual_files = set(config_files.keys())

    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing:
        errors.append(f"Missing expected config files in configs/: {', '.join(missing)}")
    if unexpected:
        errors.append(f"Unexpected files in configs/: {', '.join(unexpected)}")

    parsed: dict[str, Any] = {}
    for rel in sorted(actual_files & expected_files):
        fpath = config_files[rel]
        try:
            raw_text = fpath.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            parsed[rel] = data
        except Exception as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
            continue

        errors.extend(scan_mapping_for_secrets(data, rel))

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
                f"cooldowns.json key mismatch: expected only static keys {sorted(expected_keys)}, "
                f"got {sorted(actual_keys)} "
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
                f"holograms.json key mismatch: expected only static keys {sorted(expected_keys)}, "
                f"got {sorted(actual_keys)} "
                "(live in-world hologram definitions must remain exclusively in data/config/paradigm/holograms.json)."
            )
    elif "holograms.json" in parsed:
        errors.append("holograms.json must be a JSON object")

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return parsed


def sync_static_file(rel: str, dry_run: bool) -> bool:
    """Atomically copy `configs/<rel>` to `data/config/paradigm/<rel>` when SHA-256 differs."""
    src_bytes = (CONFIGS_DIR / rel).read_bytes()
    dst_path = TARGET_DIR / rel
    if bridge_sync_static_file(dst_path, src_bytes, dry_run=dry_run):
        action = "Would update (static)" if dry_run else "Updated (static)"
        print(f"  [{action}] {rel}")
        return True
    return False


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


def apply_configs(parsed: dict[str, Any], dry_run: bool) -> tuple[int, int]:
    """Place validated Paradigm static and mixed configs into `TARGET_DIR`."""
    changed_count = 0
    unchanged_count = 0

    for rel in STATIC_FILES:
        if sync_static_file(rel, dry_run=dry_run):
            changed_count += 1
        else:
            unchanged_count += 1

    if sync_mixed_file(
        rel="cooldowns.json",
        static_data=parsed["cooldowns.json"],
        static_keys=COOLDOWNS_STATIC_KEYS,
        runtime_key="cooldowns",
        runtime_first=True,
        dry_run=dry_run,
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
        dry_run=dry_run,
    ):
        changed_count += 1
    else:
        unchanged_count += 1

    return changed_count, unchanged_count


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "paradigm",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Paradigm static configs into data/config/paradigm/.",
    )


if __name__ == "__main__":
    sys.exit(main())
