#!/usr/bin/env python3
"""Remove one or more mods/<slug>/ directories."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
if not (REPO_ROOT / "docker-compose.yml").is_file():
    raise RuntimeError(f"Expected docker-compose.yml at resolved REPO_ROOT={REPO_ROOT}")

MODS_DIR = REPO_ROOT / "mods"
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def remove_single_mod(slug: str, *, dry_run: bool) -> int:
    """Validate slug and remove its mods/<slug>/ directory."""
    if not SLUG_RE.fullmatch(slug):
        print(f"ERROR: Invalid slug '{slug}'.", file=sys.stderr)
        return 1

    mod_dir = MODS_DIR / slug
    if not mod_dir.exists():
        print(f"ERROR: No mod harness found for '{slug}'.", file=sys.stderr)
        return 1

    if dry_run:
        print(f"[DRY-RUN] Would remove {mod_dir.relative_to(REPO_ROOT)}/")
    else:
        shutil.rmtree(mod_dir)
        print(f"Removed {mod_dir.relative_to(REPO_ROOT)}/")

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Remove mods/<slug>/ directories."
    )
    parser.add_argument(
        "slugs",
        nargs="+",
        help="One or more mod slugs under mods/<slug>/ to remove.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview removal without modifying files.",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    for slug in args.slugs:
        rc = remove_single_mod(slug, dry_run=args.dry_run)
        if rc != 0:
            exit_code = rc
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
