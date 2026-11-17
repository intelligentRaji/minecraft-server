#!/usr/bin/env python3
"""Project-root runner that executes per-mod mods/<slug>/sync.py placement scripts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MODS_DIR = REPO_ROOT / "mods"


def discover_sync_scripts(mod_slug: str | None) -> list[Path]:
    """Return sorted list of mods/<slug>/sync.py scripts to execute."""
    if not MODS_DIR.is_dir():
        return []

    if mod_slug is not None:
        script = MODS_DIR / mod_slug / "sync.py"
        if not script.is_file():
            raise FileNotFoundError(
                f"Mod sync script not found for '{mod_slug}': {script.relative_to(REPO_ROOT)}"
            )
        return [script]

    return sorted(
        path
        for path in MODS_DIR.glob("*/sync.py")
        if path.is_file() and not path.is_symlink()
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Synchronize tracked mod configurations from mods/<slug>/configs/ into data/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview configuration placement without modifying files in data/.",
    )
    parser.add_argument(
        "--mod",
        dest="mod_slug",
        metavar="SLUG",
        help="Only run mods/<SLUG>/sync.py for the specified mod.",
    )
    args = parser.parse_args(argv)

    try:
        scripts = discover_sync_scripts(args.mod_slug)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not scripts:
        print("No mods/*/sync.py scripts found.")
        return 0

    mode_label = "DRY-RUN" if args.dry_run else "SYNC"
    print(f"=== [{mode_label}] Running {len(scripts)} mod configuration sync script(s) ===")

    for script in scripts:
        slug = script.parent.name
        cmd = [sys.executable, str(script)]
        if args.dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(cmd, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(
                f"ERROR: Configuration sync failed for mod '{slug}' "
                f"({script.relative_to(REPO_ROOT)}, exit code {result.returncode}).",
                file=sys.stderr,
            )
            return result.returncode

    print(f"=== [{mode_label}] All {len(scripts)} mod configuration(s) synchronized cleanly ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
