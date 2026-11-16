#!/usr/bin/env python3
"""Extract and sanitize a LuckPerms export archive into mods/luckperms/configs/."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from pathlib import Path

LP_EXPORT_TIMEOUT_SECONDS = 5.0
LP_EXPORT_POLL_INTERVAL = 0.25
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from start to locate the repository root (containing docker-compose.yml)."""
    origin = start if start is not None else Path(__file__).resolve().parent
    for candidate in (origin, *origin.parents):
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root (docker-compose.yml) above {origin}")


REPO_ROOT = find_repo_root()
LP_DATA_DIR = REPO_ROOT / "data" / "config" / "luckperms"
LP_SNAPSHOT_OUT = (
    REPO_ROOT / "mods" / "luckperms" / "configs" / "luckperms-snapshot.json"
)


def archive_path_for(name: str) -> Path:
    """Return the validated LuckPerms export archive path under data/config/luckperms/."""
    if not SAFE_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise ValueError(f"Invalid export name '{name}'; use letters, digits, '.', '_', or '-'.")
    return LP_DATA_DIR / f"{name}.json.gz"


def clean_archive(archive_path: Path, *, dry_run: bool) -> int:
    """Remove any pre-existing LuckPerms export archive before running lp export."""
    if not archive_path.is_file():
        return 0
    if dry_run:
        print(f"[DRY-RUN] Would remove existing archive: {archive_path.relative_to(REPO_ROOT)}")
        return 0
    archive_path.unlink(missing_ok=True)
    print(f"Removed pre-existing archive: {archive_path.relative_to(REPO_ROOT)}")
    return 0


def wait_and_load_archive(archive_path: Path) -> object:
    """Poll briefly for LuckPerms async export completion and parse gzipped JSON."""
    deadline = time.monotonic() + LP_EXPORT_TIMEOUT_SECONDS
    last_exc: Exception | None = None
    while True:
        if archive_path.is_file():
            try:
                with gzip.open(archive_path, "rt", encoding="utf-8") as gz_fh:
                    return json.load(gz_fh)
            except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
                last_exc = exc
        if time.monotonic() >= deadline:
            if not archive_path.is_file():
                raise FileNotFoundError(f"Expected snapshot archive not found at {archive_path}")
            raise RuntimeError(f"Snapshot archive at {archive_path} was unreadable/invalid: {last_exc}")
        time.sleep(LP_EXPORT_POLL_INTERVAL)


def extract_snapshot(archive_path: Path, *, keep_users: bool, dry_run: bool) -> int:
    """Load, sanitize, write, and clean up the LuckPerms export archive."""
    try:
        try:
            payload = wait_and_load_archive(archive_path)
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        if not keep_users and isinstance(payload, dict) and "users" in payload:
            del payload["users"]

        user_note = "kept users" if keep_users else "stripped users"
        rel_out = LP_SNAPSHOT_OUT.relative_to(REPO_ROOT)
        if dry_run:
            print(f"[DRY-RUN] Validated {archive_path.relative_to(REPO_ROOT)}; would write ({user_note}) to {rel_out}")
            return 0

        LP_SNAPSHOT_OUT.parent.mkdir(parents=True, exist_ok=True)
        LP_SNAPSHOT_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Saved LuckPerms snapshot ({user_note}) to {rel_out}")
        return 0
    finally:
        if not dry_run:
            archive_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Clean or extract a LuckPerms export archive into mods/luckperms/configs/luckperms-snapshot.json."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove any pre-existing export archive before running 'lp export <name>' via minecraft-rcon.",
    )
    parser.add_argument(
        "--name",
        default="snapshot",
        help="Export archive base name under data/config/luckperms/ (default: snapshot).",
    )
    parser.add_argument(
        "--keep-users",
        action="store_true",
        help="Retain the 'users' section in the exported LuckPerms snapshot.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview without writing or deleting files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        archive_path = archive_path_for(args.name)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.clean:
        return clean_archive(archive_path, dry_run=args.dry_run)
    return extract_snapshot(archive_path, keep_users=args.keep_users, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
