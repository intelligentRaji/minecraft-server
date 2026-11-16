#!/usr/bin/env python3
"""Remove one or more mods/<slug>/ directories and unregister their skills from .agents/skills.json."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
if not (REPO_ROOT / "docker-compose.yml").is_file():
    raise RuntimeError(f"Expected docker-compose.yml at resolved REPO_ROOT={REPO_ROOT}")

MODS_DIR = REPO_ROOT / "mods"
SKILLS_JSON = REPO_ROOT / ".agents" / "skills.json"
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def unregister_skill(slug: str, *, dry_run: bool) -> bool:
    """Remove mods/<slug>/.agents/skills from root .agents/skills.json."""
    if not SKILLS_JSON.is_file():
        return False

    entry_path = f"mods/{slug}/.agents/skills"
    data = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    filtered = [
        item
        for item in entries
        if not (isinstance(item, dict) and item.get("path") == entry_path)
    ]
    if len(filtered) == len(entries):
        return False

    if dry_run:
        print(f"[DRY-RUN] Would unregister '{entry_path}' from {SKILLS_JSON.relative_to(REPO_ROOT)}")
        return True

    data["entries"] = filtered
    SKILLS_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Unregistered '{entry_path}' from {SKILLS_JSON.relative_to(REPO_ROOT)}")
    return True


def remove_single_mod(slug: str, *, dry_run: bool) -> int:
    """Remove a single mod folder and unregister its skill."""
    if not SLUG_RE.fullmatch(slug):
        print(f"ERROR: Invalid slug '{slug}'.", file=sys.stderr)
        return 1

    mod_dir = MODS_DIR / slug
    removed_skill = unregister_skill(slug, dry_run=dry_run)

    if not mod_dir.exists() and not removed_skill:
        print(f"ERROR: No mod harness or skills.json entry found for '{slug}'.", file=sys.stderr)
        return 1

    if mod_dir.exists():
        if dry_run:
            print(f"[DRY-RUN] Would remove {mod_dir.relative_to(REPO_ROOT)}/")
        else:
            shutil.rmtree(mod_dir)
            print(f"Removed {mod_dir.relative_to(REPO_ROOT)}/")

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Remove mods/<slug>/ and unregister its skill from .agents/skills.json."
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
