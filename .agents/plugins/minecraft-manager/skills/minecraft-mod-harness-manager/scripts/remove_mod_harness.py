#!/usr/bin/env python3
"""Remove a mod's mods/<slug>/ directory, unregister its skill harness, and optionally prune data/."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
if not (REPO_ROOT / "docker-compose.yml").is_file():
    raise RuntimeError(f"Expected docker-compose.yml at resolved REPO_ROOT={REPO_ROOT}")

MODS_DIR = REPO_ROOT / "mods"
DATA_DIR = REPO_ROOT / "data"
SKILLS_JSON = REPO_ROOT / ".agents" / "skills.json"
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def unregister_skill(slug: str, *, dry_run: bool) -> bool:
    """Remove mods/<slug>/.agents/skills from root .agents/skills.json."""
    if not SKILLS_JSON.is_file():
        return False

    entry_path = f"mods/{slug}/.agents/skills"
    data = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    filtered = [item for item in entries if not (isinstance(item, dict) and item.get("path") == entry_path)]
    if len(filtered) == len(entries):
        return False

    if dry_run:
        print(f"[DRY-RUN] Would unregister '{entry_path}' from {SKILLS_JSON.relative_to(REPO_ROOT)}")
        return True

    data["entries"] = filtered
    SKILLS_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Unregistered '{entry_path}' from {SKILLS_JSON.relative_to(REPO_ROOT)}")
    return True


def prune_mapped_data_files(slug: str, mod_dir: Path, *, dry_run: bool) -> None:
    """Delete this mod's mapped configuration files from data/."""
    scripts = sorted(mod_dir.glob(".agents/skills/*/scripts/sync_config.py"))
    for script in scripts:
        res = subprocess.run([sys.executable, str(script), "mappings"], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"WARNING: Could not read mappings from {script}: {res.stderr.strip()}", file=sys.stderr)
            continue
        meta = json.loads(res.stdout)
        for data_rel in sorted(meta.get("file_map", {}).values()):
            target = DATA_DIR / data_rel
            if target.is_file() or target.is_symlink():
                if dry_run:
                    print(f"[DRY-RUN] Would prune data/{data_rel}")
                else:
                    target.unlink()
                    print(f"Pruned data/{data_rel}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Remove mods/<slug>/ and unregister its skill from .agents/skills.json."
    )
    parser.add_argument("slug", help="Mod slug under mods/<slug>/ to remove.")
    parser.add_argument(
        "--prune-data",
        action="store_true",
        help="Also delete this mod's mapped config files from data/.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview removal without modifying files.")
    args = parser.parse_args(argv)

    if not SLUG_RE.fullmatch(args.slug):
        print(f"ERROR: Invalid slug '{args.slug}'.", file=sys.stderr)
        return 1

    mod_dir = MODS_DIR / args.slug
    removed_skill = unregister_skill(args.slug, dry_run=args.dry_run)

    if not mod_dir.exists() and not removed_skill:
        print(f"ERROR: No mod harness or skills.json entry found for '{args.slug}'.", file=sys.stderr)
        return 1

    if args.prune_data and mod_dir.exists():
        prune_mapped_data_files(args.slug, mod_dir, dry_run=args.dry_run)

    if mod_dir.exists():
        if args.dry_run:
            print(f"[DRY-RUN] Would remove {mod_dir.relative_to(REPO_ROOT)}/")
        else:
            shutil.rmtree(mod_dir)
            print(f"Removed {mod_dir.relative_to(REPO_ROOT)}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
