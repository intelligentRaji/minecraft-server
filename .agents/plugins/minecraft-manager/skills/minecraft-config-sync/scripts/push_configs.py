#!/usr/bin/env python3
"""Push versioned server configs from server-config/ into runtime data/."""

from __future__ import annotations

import argparse
import shutil
import sys

from config_utils import DATA_DIR, SERVER_CONFIG_DIR, collect_files, sha256_file


def push_configs(*, dry_run: bool) -> int:
    """Apply allowlisted configs from server-config/ into data/."""
    if not SERVER_CONFIG_DIR.exists():
        print(f"ERROR: Source directory does not exist: {SERVER_CONFIG_DIR}", file=sys.stderr)
        return 1

    src_files = collect_files(SERVER_CONFIG_DIR, allowlist_only=True, exclude_lp_snapshot=True)
    copied = 0
    unchanged = 0

    for rel_posix, src_path in src_files.items():
        dst_path = DATA_DIR / rel_posix
        is_existing_file = dst_path.is_file()
        if is_existing_file:
            try:
                if sha256_file(src_path) == sha256_file(dst_path):
                    unchanged += 1
                    continue
            except OSError as exc:
                print(f"ERROR: Could not hash {rel_posix}: {exc}", file=sys.stderr)
                return 1

        action = "UPDATE" if is_existing_file else "ADD"
        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"{prefix}{action}: {rel_posix}")
        if not dry_run:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            # copyfile preserves existing target ownership and permissions
            shutil.copyfile(src_path, dst_path)
        copied += 1

    mode = "Dry-run complete" if dry_run else "Push complete"
    print(f"{mode}: {copied} applied, {unchanged} unchanged.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Push allowlisted server configs from server-config/ into data/."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files.")
    args = parser.parse_args(argv)
    return push_configs(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
