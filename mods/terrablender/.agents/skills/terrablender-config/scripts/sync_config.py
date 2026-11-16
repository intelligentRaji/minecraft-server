#!/usr/bin/env python3
"""Synchronize and validate configuration files for the 'terrablender' mod slice."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

SLUG = 'terrablender'
INVARIANT = None

MOD_DIR = Path(__file__).resolve().parents[4]
REPO_ROOT = MOD_DIR.parent.parent
MOD_CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

FILE_MAP: dict[str, str] = {
    "terrablender.toml": "config/terrablender.toml"
}
FORBIDDEN_DATA_PATHS: tuple[str, ...] = ()

KEY_VALUE_RE = re.compile(
    r"""(?:^|[\s,{])(?:["']([^"']+)["']|([A-Za-z0-9_.-]+))\s*[:=]\s*(.+?)\s*$"""
)
SECRET_KEY_RE = re.compile(
    r"""(?:^|[._\-\s]|(?<=[a-z]))(?i:bot_token|botToken|token|secret|apiKey|api_key|password|passwd|webhook|connection-uri|connection_uri|connectionUri|dsn|jdbcUrl|privateKey|private_key|rcon\.password)(?=$)"""
)
IGNORED_SECRET_VALUES = frozenset({"", "null", "none", "true", "false", "{", "["})
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
FORGE_PERM_RE = re.compile(
    r'^\s*permissionHandler\s*=\s*"luckperms:permission_handler"\s*(?:#.*)?$',
    re.MULTILINE,
)

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
    """Scan candidate files for non-empty secret values."""
    findings: list[tuple[str, int, str]] = []
    for rel_label, path in files.items():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"ERROR: Could not read {path} during secret scan: {exc}", file=sys.stderr)
            findings.append((rel_label, 0, "<unreadable>"))
            continue

        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(("#", "//", ";")):
                continue

            matched_value = False
            for label, pattern in VALUE_SECRET_PATTERNS:
                if pattern.search(raw_line):
                    findings.append((rel_label, lineno, label))
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

            if unquoted.lower() in IGNORED_SECRET_VALUES:
                continue
            is_password_key = "password" in key_name.lower() or "passwd" in key_name.lower()
            if not is_password_key and NUMERIC_RE.fullmatch(unquoted):
                continue

            findings.append((rel_label, lineno, key_name))

    return findings


def validate_invariants(files: dict[str, Path]) -> list[str]:
    """Validate mod-specific operational invariants before syncing."""
    errors: list[str] = []
    if INVARIANT == "server-core":
        for local_rel, data_rel in FILE_MAP.items():
            if data_rel == "world/serverconfig/forge-server.toml" and local_rel in files:
                text = files[local_rel].read_text(encoding="utf-8", errors="replace")
                if not FORGE_PERM_RE.search(text):
                    errors.append(
                        f"{local_rel}: permissionHandler must be set to \"luckperms:permission_handler\""
                    )
    elif INVARIANT == "paradigm":
        for local_rel, data_rel in FILE_MAP.items():
            if data_rel == "config/paradigm/main.json" and local_rel in files:
                try:
                    payload = json.loads(files[local_rel].read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(f"{local_rel}: invalid JSON ({exc})")
                    continue
                val = payload.get("internalPermissionsEnable", {}).get("value")
                if val is not False:
                    errors.append(
                        f"{local_rel}: internalPermissionsEnable.value must be false (got {val!r})"
                    )
    return errors


def validate_mappings() -> str | None:
    """Validate that no FILE_MAP destination overlaps FORBIDDEN_DATA_PATHS."""
    forbidden = set(FORBIDDEN_DATA_PATHS)
    for local_rel, data_rel in FILE_MAP.items():
        if data_rel in forbidden:
            return f"Mapping {local_rel} -> {data_rel} is in FORBIDDEN_DATA_PATHS"
    return None


def cmd_pull(*, dry_run: bool) -> int:
    """Pull this mod's allowlisted configs from data/ into mods/<slug>/configs/."""
    err = validate_mappings()
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    if not DATA_DIR.is_dir():
        print(f"ERROR: Runtime data directory does not exist: {DATA_DIR}", file=sys.stderr)
        return 1

    src_files: dict[str, Path] = {}
    for local_rel, data_rel in sorted(FILE_MAP.items()):
        src_path = DATA_DIR / data_rel
        if src_path.is_symlink() or not src_path.is_file():
            print(f"ERROR: Expected source config file not found: {src_path}", file=sys.stderr)
            return 1
        src_files[local_rel] = src_path

    findings = scan_for_secrets(src_files)
    if findings:
        print(f"ABORTED [{SLUG}]: Potential secret(s) detected in data/:", file=sys.stderr)
        for rel_label, lineno, key_name in findings:
            print(f"  - {FILE_MAP[rel_label]}:{lineno} ({key_name})", file=sys.stderr)
        return 1

    inv_errors = validate_invariants(src_files)
    if inv_errors:
        print(f"ABORTED [{SLUG}]: Invariant check failed:", file=sys.stderr)
        for msg in inv_errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1

    copied = 0
    unchanged = 0
    for local_rel, src_path in src_files.items():
        dst_path = MOD_CONFIGS_DIR / local_rel
        is_existing = dst_path.is_file()
        if is_existing and sha256_file(src_path) == sha256_file(dst_path):
            unchanged += 1
            continue

        action = "UPDATE" if is_existing else "ADD"
        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"{prefix}[{SLUG}] {action}: {local_rel} <- data/{FILE_MAP[local_rel]}")
        if not dry_run:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
        copied += 1

    mode = "Dry-run" if dry_run else "Pull"
    print(f"[{SLUG}] {mode} complete: {copied} copied, {unchanged} unchanged.")
    return 0


def cmd_push(*, dry_run: bool) -> int:
    """Push this mod's configs from mods/<slug>/configs/ into data/."""
    err = validate_mappings()
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    if not MOD_CONFIGS_DIR.is_dir():
        print(f"ERROR: Mod configs directory does not exist: {MOD_CONFIGS_DIR}", file=sys.stderr)
        return 1

    src_files: dict[str, Path] = {}
    for local_rel in sorted(FILE_MAP):
        src_path = MOD_CONFIGS_DIR / local_rel
        if src_path.is_symlink() or not src_path.is_file():
            print(f"ERROR: Tracked config file missing: {src_path}", file=sys.stderr)
            return 1
        src_files[local_rel] = src_path

    findings = scan_for_secrets(src_files)
    if findings:
        print(f"ABORTED [{SLUG}]: Potential secret(s) detected in configs/:", file=sys.stderr)
        for rel_label, lineno, key_name in findings:
            print(f"  - {rel_label}:{lineno} ({key_name})", file=sys.stderr)
        return 1

    inv_errors = validate_invariants(src_files)
    if inv_errors:
        print(f"ABORTED [{SLUG}]: Invariant check failed:", file=sys.stderr)
        for msg in inv_errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1

    applied = 0
    unchanged = 0
    for local_rel, src_path in src_files.items():
        data_rel = FILE_MAP[local_rel]
        dst_path = DATA_DIR / data_rel
        is_existing = dst_path.is_file()
        if is_existing and sha256_file(src_path) == sha256_file(dst_path):
            unchanged += 1
            continue

        action = "UPDATE" if is_existing else "ADD"
        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"{prefix}[{SLUG}] {action}: {local_rel} -> data/{data_rel}")
        if not dry_run:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_path, dst_path)
        applied += 1

    mode = "Dry-run" if dry_run else "Push"
    print(f"[{SLUG}] {mode} complete: {applied} applied, {unchanged} unchanged.")
    return 0


def cmd_diff(*, exit_code: bool) -> int:
    """Print unified diff between mods/<slug>/configs/ and data/."""
    has_diff = False
    had_error = False
    for local_rel, data_rel in sorted(FILE_MAP.items()):
        repo_path = MOD_CONFIGS_DIR / local_rel
        data_path = DATA_DIR / data_rel
        repo_exists = repo_path.is_file() and not repo_path.is_symlink()
        data_exists = data_path.is_file() and not data_path.is_symlink()

        if repo_exists and data_exists:
            try:
                if sha256_file(repo_path) == sha256_file(data_path):
                    continue
            except OSError as exc:
                print(f"ERROR [{SLUG}]: Could not read {local_rel}: {exc}", file=sys.stderr)
                had_error = True
                continue

        if not repo_exists and not data_exists:
            continue

        try:
            repo_lines = repo_path.read_text(encoding="utf-8").splitlines(keepends=True) if repo_exists else []
            data_lines = data_path.read_text(encoding="utf-8").splitlines(keepends=True) if data_exists else []
        except (OSError, UnicodeDecodeError) as exc:
            print(f"WARNING [{SLUG}]: Diff failed for {local_rel}: {exc}", file=sys.stderr)
            has_diff = True
            continue

        diff = list(
            difflib.unified_diff(
                repo_lines,
                data_lines,
                fromfile=f"mods/{SLUG}/configs/{local_rel}",
                tofile=f"data/{data_rel}",
            )
        )
        if diff:
            has_diff = True
            sys.stdout.writelines(diff)
            if not diff[-1].endswith("\n"):
                print()

    if had_error:
        return 1
    if not has_diff:
        print(f"[{SLUG}] No differences found.")
        return 0
    return 1 if exit_code else 0


def cmd_mappings() -> int:
    """Print JSON mapping metadata for conflict detection and unmapped auditing."""
    print(
        json.dumps(
            {
                "slug": SLUG,
                "file_map": FILE_MAP,
                "forbidden_data_paths": list(FORBIDDEN_DATA_PATHS),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=f"Manage and synchronize configs for '{SLUG}'.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_p = subparsers.add_parser("push", help="Push mods/<slug>/configs/ to data/.")
    push_p.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files.")

    pull_p = subparsers.add_parser("pull", help="Pull allowlisted configs from data/ into mods/<slug>/configs/.")
    pull_p.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files.")

    diff_p = subparsers.add_parser("diff", help="Show unified diff between mods/<slug>/configs/ and data/.")
    diff_p.add_argument("--exit-code", action="store_true", help="Exit with code 1 if differences exist.")

    subparsers.add_parser("mappings", help="Print JSON mapping metadata.")

    args = parser.parse_args(argv)
    if args.command == "push":
        return cmd_push(dry_run=args.dry_run)
    if args.command == "pull":
        return cmd_pull(dry_run=args.dry_run)
    if args.command == "diff":
        return cmd_diff(exit_code=args.exit_code)
    if args.command == "mappings":
        return cmd_mappings()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
