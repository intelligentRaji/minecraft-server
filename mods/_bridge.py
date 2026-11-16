"""Shared non-AI Mod Bridge services for `mods/<slug>/sync.py` scripts.

Provides common security guards (secret scanning, forbidden entry checks, symlink
rejection), deterministic atomic file placement, hashing, type checks, and CLI
execution so individual mod sync scripts stay small and focused on mod-specific
schemas and invariants.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Discord Webhook URL",
        re.compile(
            r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+",
            re.IGNORECASE,
        ),
    ),
    (
        "Discord Bot Token",
        re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}"),
    ),
    (
        "Private Key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
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
    """Return the lowercase SHA-256 hex digest of `data`."""
    return hashlib.sha256(data).hexdigest()


def is_strict_int(value: Any) -> bool:
    """Return True if `value` is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def scan_mapping_for_secrets(
    obj: Any,
    rel_path: str,
    key_path: str = "",
    *,
    extra_key_names: frozenset[str] = frozenset(),
) -> list[str]:
    """Recursively scan parsed JSON/TOML/YAML structures for secret keys or patterns."""
    errors: list[str] = []
    secret_keys = SECRET_KEY_NAMES | extra_key_names

    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{key_path}.{k}" if key_path else str(k)
            if str(k).lower() in secret_keys and isinstance(v, str) and v.strip():
                errors.append(
                    f"{rel_path}: non-empty secret key '{current_path}' "
                    "(credentials and tokens must never be committed to static mod configs)"
                )
            errors.extend(
                scan_mapping_for_secrets(
                    v, rel_path, current_path, extra_key_names=extra_key_names
                )
            )
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            errors.extend(
                scan_mapping_for_secrets(
                    item, rel_path, f"{key_path}[{idx}]", extra_key_names=extra_key_names
                )
            )
    elif isinstance(obj, str):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(obj):
                errors.append(
                    f"{rel_path}: detected {label} at '{key_path}' "
                    "(secrets must never be committed to static mod configs)"
                )
    return errors


def scan_text_for_secrets(text: str, rel_path: str) -> list[str]:
    """Scan raw text (e.g., HOCON or properties) for known secret patterns."""
    errors: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(
                f"{rel_path}: detected {label} "
                "(secrets must never be committed to static mod configs)"
            )
    return errors


def check_forbidden_entries(
    configs_dir: Path,
    forbidden_names: Iterable[str] = (),
    forbidden_suffixes: Iterable[str] = (),
    *,
    suffix_label: str = "archive/runtime",
) -> list[str]:
    """Verify `configs_dir` contains no symlinks, forbidden names, or forbidden suffixes."""
    errors: list[str] = []
    forbidden_name_set = set(forbidden_names)
    suffix_tuple = tuple(s.lower() for s in forbidden_suffixes)

    for name in sorted(forbidden_name_set):
        if (configs_dir / name).exists() or (configs_dir / name).is_symlink():
            errors.append(
                f"Forbidden file/directory present in configs/: {name}"
            )

    for entry in sorted(configs_dir.rglob("*")):
        rel = entry.relative_to(configs_dir).as_posix()
        if entry.is_symlink():
            errors.append(f"Symlinks are forbidden in configs/: {rel}")
            continue
        if entry.name in forbidden_name_set and rel != entry.name:
            errors.append(f"Forbidden file/directory present in configs/: {rel}")
        if entry.is_file() and suffix_tuple and entry.name.lower().endswith(suffix_tuple):
            errors.append(f"Forbidden {suffix_label} file present in configs/: {rel}")

    return errors


def collect_config_files(configs_dir: Path) -> tuple[dict[str, Path], list[str]]:
    """Return `({rel_posix: path}, errors)` for all non-symlink files in `configs_dir`."""
    files: dict[str, Path] = {}
    errors: list[str] = []
    for entry in sorted(configs_dir.rglob("*")):
        rel = entry.relative_to(configs_dir).as_posix()
        if entry.is_symlink():
            errors.append(f"Symlinks are forbidden in configs/: {rel}")
            continue
        if entry.is_file():
            files[rel] = entry
    return files, errors


def atomic_write_bytes(
    target_path: Path, data: bytes, default_mode: int = 0o664
) -> None:
    """Atomically write `data` to `target_path`, preserving existing mode and UID/GID."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_stat = target_path.stat() if target_path.exists() else None
    mode = stat.S_IMODE(target_stat.st_mode) if target_stat else default_mode

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=str(target_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        if target_stat is not None and hasattr(os, "chown"):
            try:
                os.chown(tmp_path, target_stat.st_uid, target_stat.st_gid)
            except PermissionError:
                pass
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def sync_static_file(
    target_path: Path,
    src_bytes: bytes,
    dry_run: bool,
    default_mode: int = 0o664,
) -> bool:
    """Place `src_bytes` at `target_path` if missing or changed. Return True if changed."""
    if target_path.exists():
        dst_bytes = target_path.read_bytes()
        if sha256_bytes(src_bytes) == sha256_bytes(dst_bytes):
            return False

    if not dry_run:
        atomic_write_bytes(target_path, src_bytes, default_mode=default_mode)
    return True


def run_sync_cli(
    slug: str,
    validate_fn: Callable[[], T],
    apply_fn: Callable[[T, bool], tuple[int, int]],
    argv: list[str] | None = None,
    description: str | None = None,
) -> int:
    """Standard CLI runner for `mods/<slug>/sync.py` scripts."""
    parser = argparse.ArgumentParser(
        description=description or f"Synchronize {slug} static configurations into data/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview changes without modifying files in data/.",
    )
    args = parser.parse_args(argv)

    try:
        validated = validate_fn()
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"[{slug}/sync.py] ERROR: {exc}", file=sys.stderr)
        return 1

    changed, unchanged = apply_fn(validated, args.dry_run)
    total = changed + unchanged
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[{slug}/sync.py] {mode}: {changed} changed, {unchanged} unchanged "
        f"(total {total} files verified)."
    )
    return 0
