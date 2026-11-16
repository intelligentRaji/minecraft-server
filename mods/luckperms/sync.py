#!/usr/bin/env python3
"""One-way deterministic configuration placement for LuckPerms.

Places static configurations from `mods/luckperms/configs/` into `data/config/luckperms/`:
- Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
- Atomically replaces pure static files (`contexts.json`, `luckperms.conf`) when SHA-256 differs.
- Never reads, copies, or modifies excluded runtime databases/directories (`luckperms-h2-v2.mv.db`,
  `libs/`, `translations/`, `*-storage/`, `logs/`).
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

# Deterministic zero-walk path resolution (mods/luckperms/sync.py -> repo root)
MOD_DIR = Path(__file__).resolve().parent
REPO_ROOT = MOD_DIR.parent.parent
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
            elif not in_quotes:
                if ch == "#" or (ch == "/" and i + 1 < len(line) and line[i + 1] == "/"):
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
    """Validate secret guards and architectural invariants for `luckperms.conf`."""
    errors: list[str] = []

    for label, pattern in SECRET_PATTERNS:
        if pattern.search(raw_text):
            errors.append(f"luckperms.conf: detected {label}")

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
    errors: list[str] = []

    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    for forbidden in sorted(FORBIDDEN_NAMES):
        candidate = CONFIGS_DIR / forbidden
        if candidate.exists():
            errors.append(
                f"Forbidden file/directory present in configs/: {forbidden} "
                "(live LuckPerms databases, runtime libs/translations, and storage directories must never be committed)"
            )

    for p in sorted(CONFIGS_DIR.rglob("*")):
        rel = p.relative_to(CONFIGS_DIR).as_posix()
        if p.is_file() and p.name.endswith(FORBIDDEN_SUFFIXES) and rel not in FORBIDDEN_NAMES:
            errors.append(
                f"Forbidden binary/database file present in configs/: {rel} "
                "(database and JAR artifacts must remain exclusively in data/config/luckperms/)"
            )

    expected_files = set(STATIC_FILES)
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

        if rel == "contexts.json":
            try:
                ctx_data = json.loads(raw_text)
            except Exception as exc:
                errors.append(f"contexts.json: invalid JSON ({exc})")
                continue

            errors.extend(scan_json_for_secrets(ctx_data, rel))
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
            errors.extend(validate_luckperms_conf(raw_text))

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
    """Atomically copy `configs/<rel>` to `data/config/luckperms/<rel>` when SHA-256 differs."""
    dst_path = TARGET_DIR / rel

    if dst_path.exists() and sha256_bytes(dst_path.read_bytes()) == sha256_bytes(src_bytes):
        return False

    action = "Would update (static)" if dry_run else "Updated (static)"
    print(f"  [{action}] {rel}")
    if not dry_run:
        atomic_write_bytes(dst_path, src_bytes)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and atomically place LuckPerms static configs into data/config/luckperms/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview changes without modifying data/config/luckperms/.",
    )
    args = parser.parse_args(argv)

    try:
        loaded_bytes = validate_configs()
    except Exception as exc:
        print(f"[luckperms/sync.py] ERROR: {exc}", file=sys.stderr)
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
        f"[luckperms/sync.py] {mode_label}: {changed_count} changed, {unchanged_count} unchanged "
        f"(total {changed_count + unchanged_count} files verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
