#!/usr/bin/env python3
"""Shared utilities for synchronizing versioned Minecraft configs between data/ and server-config/."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from start to locate the repository root (containing docker-compose.yml)."""
    origin = start if start is not None else Path(__file__).resolve().parent
    for candidate in (origin, *origin.parents):
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root (docker-compose.yml) above {origin}")


REPO_ROOT = find_repo_root()
DATA_DIR = REPO_ROOT / "data"
SERVER_CONFIG_DIR = REPO_ROOT / "server-config"

LP_SNAPSHOT_REL = "config/luckperms/luckperms-snapshot.json"

STANDARD_EXTENSIONS = frozenset({
    ".json",
    ".toml",
    ".cfg",
    ".conf",
    ".properties",
    ".yml",
    ".yaml",
    ".txt",
})

EXCLUDED_EXACT_PATHS = frozenset({
    "config/paradigm/discord.json",
    "config/paradigm/storage.json",
    "config/luckperms/luckperms.conf",
    "config/corecommands/afkstatus.json",
    "config/corecommands/deathlocation.json",
    "config/corecommands/homes.json",
    "config/corecommands/lastlocation.json",
    "config/corecommands/lastmessagerecipient.json",
    "config/corecommands/logoutposition.json",
    "config/corecommands/playerjoinstatus.json",
    "config/corecommands/tparequests.json",
})

EXCLUDED_DIR_PARTS = frozenset({
    "libs",
    "data",
    "cache",
    "translations",
    "tmp",
})

EXCLUDED_SUFFIXES = (
    ".mv.db",
    ".trace.db",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".jar",
    ".gz",
    ".zip",
    ".log",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tar.xz",
)

KEY_VALUE_RE = re.compile(
    r"""(?:^|[\s,{])(?:["']([^"']+)["']|([A-Za-z0-9_.-]+))\s*[:=]\s*(.+?)\s*$"""
)
SECRET_KEY_RE = re.compile(
    r"""(?:^|[._\-\s]|(?<=[a-z]))(?i:bot_token|botToken|token|secret|apiKey|api_key|password|passwd|webhook|connection-uri|connection_uri|connectionUri|dsn|jdbcUrl|privateKey|private_key|rcon\.password)(?=$)"""
)
IGNORED_SECRET_VALUES = frozenset({"", "null", "none", "true", "false", "{", "["})
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

VALUE_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "webhook-url",
        re.compile(r"""https://(?:discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services)/[^\s"'`]+"""),
    ),
    (
        "uri-credentials",
        re.compile(r"""[a-zA-Z][a-zA-Z0-9+.-]*://[^:\s/"']+:[^@\s"']+@[^\s"']+"""),
    ),
    (
        "private-key",
        re.compile(r"""-----BEGIN .* PRIVATE KEY-----"""),
    ),
    (
        "jwt",
        re.compile(r"""eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"""),
    ),
)


def is_excluded(rel_path: Path) -> bool:
    """Return True if a relative path matches any hard exclusion rule."""
    rel_posix = rel_path.as_posix()
    if rel_posix in EXCLUDED_EXACT_PATHS:
        return True

    if any(part in EXCLUDED_DIR_PARTS for part in rel_path.parts[:-1]):
        return True

    name_lower = rel_path.name.lower()
    if name_lower.endswith(EXCLUDED_SUFFIXES):
        return True

    return False


def is_allowlisted(rel_path: Path) -> bool:
    """Return True if a relative path is within the allowed roots and extensions."""
    if is_excluded(rel_path):
        return False

    rel_posix = rel_path.as_posix()
    if rel_posix == "user_jvm_args.txt":
        return True

    parts = rel_path.parts
    suffix = rel_path.suffix.lower()
    if len(parts) >= 2 and parts[0] in {"config", "defaultconfigs"}:
        return suffix in STANDARD_EXTENSIONS

    if len(parts) >= 3 and parts[0] == "world" and parts[1] == "serverconfig":
        return suffix == ".toml"

    return False


def collect_files(
    root: Path,
    *,
    allowlist_only: bool = True,
    exclude_lp_snapshot: bool = False,
) -> dict[str, Path]:
    """Collect non-symlink files under root, keyed by relative POSIX path."""
    files: dict[str, Path] = {}
    if not root.exists():
        return files

    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_posix = rel.as_posix()
        if exclude_lp_snapshot and rel_posix == LP_SNAPSHOT_REL:
            continue
        if not allowlist_only or is_allowlisted(rel):
            files[rel_posix] = path

    return files


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_inline_comment(value: str) -> str:
    """Strip inline comments (#, //, ;) outside quotes and trailing commas."""
    in_quote: str | None = None
    escaped = False
    for idx, ch in enumerate(value):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_quote is not None:
            escaped = True
            continue
        if ch in {'"', "'"}:
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
            continue
        if in_quote is None:
            if ch in {"#", ";"} or (ch == "/" and idx + 1 < len(value) and value[idx + 1] == "/"):
                value = value[:idx]
                break
    return value.strip().rstrip(",").strip()


def scan_for_secrets(files: dict[str, Path]) -> list[tuple[str, int, str]]:
    """Scan candidate files for non-empty secret values.

    Returns a list of (rel_path, line_number, key_or_pattern) tuples.
    """
    findings: list[tuple[str, int, str]] = []
    for rel_posix, path in files.items():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"ERROR: Could not read {path} during secret scan: {exc}", file=sys.stderr)
            findings.append((rel_posix, 0, "<unreadable>"))
            continue

        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(("#", "//", ";")):
                continue

            matched_value = False
            for label, pattern in VALUE_SECRET_PATTERNS:
                if pattern.search(raw_line):
                    findings.append((rel_posix, lineno, label))
                    matched_value = True
            if matched_value:
                continue

            match = KEY_VALUE_RE.search(raw_line)
            if not match:
                continue
            key_name = (match.group(1) or match.group(2)).strip()
            if not SECRET_KEY_RE.search(key_name):
                continue

            raw_val = strip_inline_comment(match.group(3))
            if len(raw_val) >= 2 and raw_val[0] == raw_val[-1] and raw_val[0] in {'"', "'"}:
                unquoted = raw_val[1:-1].strip()
            else:
                unquoted = raw_val

            lowered = unquoted.lower()
            if lowered in IGNORED_SECRET_VALUES:
                continue
            is_password_key = "password" in key_name.lower() or "passwd" in key_name.lower()
            if not is_password_key and NUMERIC_RE.fullmatch(unquoted):
                continue

            findings.append((rel_posix, lineno, key_name))

    return findings


def prune_empty_dirs(root: Path) -> None:
    """Remove empty subdirectories beneath root."""
    if not root.exists():
        return
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
