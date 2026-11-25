#!/usr/bin/env python3
"""One-way deterministic configuration placement for LuckPerms.

Places static configurations from `mods/luckperms/configs/` into `data/config/luckperms/`:
- Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
- Atomically replaces pure static files (`contexts.json`, `luckperms.conf`) when SHA-256 differs.
- Never reads, copies, or modifies excluded runtime databases/directories (`luckperms-h2-v2.mv.db`,
  `libs/`, `translations/`, `*-storage/`, `logs/`).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Deterministic zero-walk path resolution (mods/luckperms/sync.py -> repo root)
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
)
from _bridge import (  # noqa: E402
    sync_static_file as bridge_sync_static_file,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"
TARGET_DIR = DATA_DIR / "config" / "luckperms"

STATIC_FILES: tuple[str, ...] = (
    "contexts.json",
    "luckperms.conf",
)

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "luckperms-h2-v2.mv.db",
    "libs",
    "translations",
    "yaml-storage",
    "json-storage",
    "hocon-storage",
    "toml-storage",
    "logs",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".mv.db",
    ".trace.db",
    ".lock.db",
    ".db",
    ".jar",
)


def strip_hocon_comments(text: str) -> str:
    """Strip `#` and `//` HOCON comments while preserving quoted string contents."""
    out_lines: list[str] = []
    for line in text.splitlines():
        in_quotes = False
        escaped = False
        cut_idx = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if escaped:
                escaped = False
            elif ch == "\\" and in_quotes:
                escaped = True
            elif ch == '"':
                in_quotes = not in_quotes
            elif not in_quotes and (ch == "#" or (ch == "/" and i + 1 < len(line) and line[i + 1] == "/")):
                cut_idx = i
                break
            i += 1
        out_lines.append(line[:cut_idx])
    return "\n".join(out_lines)


def extract_hocon_block(clean_text: str, block_name: str) -> str | None:
    """Return the inner body of a named HOCON `{ ... }` block, or None if not found."""
    match = re.search(rf"(?:^|\s){re.escape(block_name)}\s*\{{", clean_text)
    if not match:
        return None
    start = match.end()
    depth = 1
    in_quotes = False
    escaped = False
    i = start
    while i < len(clean_text):
        ch = clean_text[i]
        if escaped:
            escaped = False
        elif ch == "\\" and in_quotes:
            escaped = True
        elif ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return clean_text[start:i]
        i += 1
    return None


def extract_hocon_scalar(clean_text: str, key: str) -> str | None:
    """Extract a scalar string or unquoted token value for `key = value` in HOCON text."""
    pattern = re.compile(rf'(?:^|\n)\s*{re.escape(key)}\s*=\s*(?:"([^"]*)"|([^\s\n{{}}\[\]]+))')
    match = pattern.search(clean_text)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def extract_hocon_list(clean_text: str, key: str) -> list[str] | None:
    """Extract a list of strings for `key = [ ... ]` in HOCON text."""
    match = re.search(rf"(?:^|\n)\s*{re.escape(key)}\s*=\s*\[(.*?)\]", clean_text, re.DOTALL)
    if not match:
        return None
    body = match.group(1)
    return re.findall(r'"([^"]*)"', body)


def validate_luckperms_conf(raw_text: str) -> list[str]:
    """Validate architectural invariants for `luckperms.conf`."""
    errors: list[str] = []

    clean = strip_hocon_comments(raw_text)

    storage_method = extract_hocon_scalar(clean, "storage-method")
    if storage_method is None or storage_method.lower() != "h2":
        errors.append(
            f"luckperms.conf invariant violation: storage-method must be \"h2\" (got {storage_method!r}) "
            "because live permissions, groups, and user metadata reside in luckperms-h2-v2.mv.db and are "
            "managed live via /lp commands."
        )

    data_block = extract_hocon_block(clean, "data")
    if data_block is not None:
        data_password = extract_hocon_scalar(data_block, "password")
        if data_password is not None and data_password.strip():
            errors.append("luckperms.conf: non-empty secret key 'data.password'")

        mongo_uri = extract_hocon_scalar(data_block, "mongodb-connection-uri")
        if mongo_uri is not None and mongo_uri.strip():
            errors.append("luckperms.conf: non-empty secret key 'data.mongodb-connection-uri'")

    redis_block = extract_hocon_block(clean, "redis")
    if redis_block is not None:
        redis_password = extract_hocon_scalar(redis_block, "password")
        if redis_password is not None and redis_password.strip():
            errors.append("luckperms.conf: non-empty secret key 'redis.password'")

    rabbitmq_block = extract_hocon_block(clean, "rabbitmq")
    if rabbitmq_block is not None:
        rabbit_enabled = (extract_hocon_scalar(rabbitmq_block, "enabled") or "false").lower() == "true"
        rabbit_password = extract_hocon_scalar(rabbitmq_block, "password")
        if rabbit_password is not None and (rabbit_enabled or rabbit_password != "guest"):
            errors.append(
                "luckperms.conf: non-default secret key 'rabbitmq.password' "
                "(must remain \"guest\" with rabbitmq.enabled = false in committed configs)"
            )

    meta_block = extract_hocon_block(clean, "meta-formatting")
    for section in ("prefix", "suffix"):
        section_block = extract_hocon_block(meta_block, section) if meta_block is not None else None
        fmt_list = extract_hocon_list(section_block, "format") if section_block is not None else None
        if fmt_list != ["highest"]:
            errors.append(
                f"luckperms.conf invariant violation: meta-formatting.{section}.format must be [\"highest\"] "
                f"(got {fmt_list!r}) so staff prefixes (&c&l[OWN] , &c[ADM] , &d[MOD] ) and FCM Clans "
                "priority-100 suffixes resolve deterministically."
            )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in mods/luckperms/configs/ before placement."""
    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    errors = check_forbidden_entries(
        CONFIGS_DIR,
        FORBIDDEN_NAMES,
        FORBIDDEN_SUFFIXES,
        suffix_label="binary/database",
    )
    config_files, collect_errors = collect_config_files(CONFIGS_DIR)
    errors.extend(collect_errors)

    expected_files = set(STATIC_FILES)
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

        if rel == "contexts.json":
            try:
                ctx_data = json.loads(raw_text)
            except Exception as exc:
                errors.append(f"contexts.json: invalid JSON ({exc})")
                continue

            errors.extend(scan_mapping_for_secrets(ctx_data, rel))
            if not isinstance(ctx_data, dict):
                errors.append("contexts.json must be a JSON object")
            else:
                for required_key in ("static-contexts", "default-contexts"):
                    if not isinstance(ctx_data.get(required_key), dict):
                        errors.append(
                            f"contexts.json invariant violation: '{required_key}' must be a JSON object "
                            "so LuckPerms context serialization remains valid on server startup."
                        )
        elif rel == "luckperms.conf":
            errors.extend(scan_text_for_secrets(raw_text, rel))
            errors.extend(validate_luckperms_conf(raw_text))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated LuckPerms static files into `TARGET_DIR`."""
    changed = 0
    unchanged = 0
    for rel in STATIC_FILES:
        dst_path = TARGET_DIR / rel
        if bridge_sync_static_file(dst_path, loaded_bytes[rel], dry_run=dry_run):
            action = "Would update (static)" if dry_run else "Updated (static)"
            print(f"  [{action}] {rel}")
            changed += 1
        else:
            unchanged += 1
    return changed, unchanged


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "luckperms",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place LuckPerms static configs into data/config/luckperms/.",
    )


if __name__ == "__main__":
    sys.exit(main())
