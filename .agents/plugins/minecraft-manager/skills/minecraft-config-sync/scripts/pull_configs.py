#!/usr/bin/env python3
"""Pull allowlisted server configs from data/ into Git-tracked server-config/."""

from __future__ import annotations

import argparse
import shutil
import sys

from config_utils import (
    DATA_DIR,
    SERVER_CONFIG_DIR,
    collect_files,
    prune_empty_dirs,
    scan_for_secrets,
    sha256_file,
)


def pull_configs(*, dry_run: bool, prune: bool) -> int:
    """Pull allowlisted configs from data/ into server-config/ after scanning for secrets."""
    if not DATA_DIR.exists():
        print(f"ERROR: Source directory does not exist: {DATA_DIR}", file=sys.stderr)
        return 1

    src_files = collect_files(DATA_DIR, allowlist_only=True)
    findings = scan_for_secrets(src_files)
    if findings:
        print("ABORTED: Potential non-empty secret(s) detected in candidate files:", file=sys.stderr)
        for rel_posix, lineno, key_name in findings:
            print(f"  - {rel_posix}:{lineno} ({key_name})", file=sys.stderr)
        return 1

    copied = 0
    unchanged = 0
    for rel_posix, src_path in src_files.items():
        dst_path = SERVER_CONFIG_DIR / rel_posix
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
            shutil.copy2(src_path, dst_path)
        copied += 1

    pruned = 0
    if prune:
        dst_files = collect_files(SERVER_CONFIG_DIR, allowlist_only=False, exclude_lp_snapshot=True)
        for rel_posix, dst_path in dst_files.items():
            if rel_posix not in src_files:
                prefix = "[DRY-RUN] " if dry_run else ""
                print(f"{prefix}PRUNE: {rel_posix}")
                if not dry_run:
                    dst_path.unlink()
                pruned += 1
        if not dry_run and pruned:
            prune_empty_dirs(SERVER_CONFIG_DIR)

    mode = "Dry-run complete" if dry_run else "Pull complete"
    print(f"{mode}: {copied} copied, {unchanged} unchanged, {pruned} pruned.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Pull allowlisted server configs from data/ into server-config/."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files.")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove files from server-config/ that are not allowlisted in data/.",
    )
    args = parser.parse_args(argv)
    return pull_configs(dry_run=args.dry_run, prune=args.prune)


if __name__ == "__main__":
    raise SystemExit(main())
