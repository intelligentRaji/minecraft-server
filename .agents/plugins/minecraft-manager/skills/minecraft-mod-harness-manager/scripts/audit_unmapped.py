#!/usr/bin/env python3
"""Audit data/ for unmapped server config files and cross-mod target path collisions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
if not (REPO_ROOT / "docker-compose.yml").is_file():
    raise RuntimeError(f"Expected docker-compose.yml at resolved REPO_ROOT={REPO_ROOT}")

MODS_DIR = REPO_ROOT / "mods"
DATA_DIR = REPO_ROOT / "data"

EXCLUDED_DIR_PARTS = frozenset({"libs", "data", "cache", "translations", "tmp"})
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


def is_candidate_runtime_config(rel_path: Path) -> bool:
    """Return True if a relative path under data/ is an auditable config file."""
    if any(part in EXCLUDED_DIR_PARTS for part in rel_path.parts[:-1]):
        return False
    if rel_path.name.lower().endswith(EXCLUDED_SUFFIXES):
        return False

    rel_posix = rel_path.as_posix()
    if rel_posix == "user_jvm_args.txt":
        return True

    parts = rel_path.parts
    if len(parts) >= 2 and parts[0] in {"config", "defaultconfigs"}:
        return True

    if len(parts) >= 3 and parts[0] == "world" and parts[1] == "serverconfig":
        return rel_path.suffix.lower() in {".toml", ".ini"}

    return False


def collect_runtime_configs() -> list[str]:
    """Collect all non-symlink auditable config files under data/."""
    candidates: list[str] = []
    roots = [
        DATA_DIR / "user_jvm_args.txt",
        DATA_DIR / "config",
        DATA_DIR / "defaultconfigs",
        DATA_DIR / "world" / "serverconfig",
    ]
    for root in roots:
        if not root.exists() or root.is_symlink():
            continue
        if root.is_file():
            rel = root.relative_to(DATA_DIR)
            if is_candidate_runtime_config(rel):
                candidates.append(rel.as_posix())
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(DATA_DIR)
            if is_candidate_runtime_config(rel):
                candidates.append(rel.as_posix())
    return sorted(set(candidates))


def collect_mod_mappings() -> tuple[dict[str, str], set[str], list[str]]:
    """Collect mapped and forbidden data/ paths across all mods/*/sync_config.py scripts."""
    claimed_by: dict[str, str] = {}
    forbidden: set[str] = set()
    conflicts: list[str] = []

    for script in sorted(MODS_DIR.glob("*/.agents/skills/*/scripts/sync_config.py")):
        res = subprocess.run([sys.executable, str(script), "mappings"], capture_output=True, text=True)
        if res.returncode != 0:
            conflicts.append(f"{script.relative_to(REPO_ROOT)} failed: {res.stderr.strip()}")
            continue
        meta = json.loads(res.stdout)
        slug = meta["slug"]
        for data_rel in meta.get("file_map", {}).values():
            if data_rel in claimed_by:
                conflicts.append(
                    f"Collision on data/{data_rel}: claimed by both '{claimed_by[data_rel]}' and '{slug}'"
                )
            claimed_by[data_rel] = slug
        for data_rel in meta.get("forbidden_data_paths", []):
            forbidden.add(data_rel)

    return claimed_by, forbidden, conflicts


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Audit data/ for unmapped server configs and mod slice path conflicts."
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with code 1 if any unmapped files or path conflicts are found.",
    )
    args = parser.parse_args(argv)

    if not DATA_DIR.is_dir():
        print(f"ERROR: Runtime data directory not found: {DATA_DIR}", file=sys.stderr)
        return 1

    claimed_by, forbidden, conflicts = collect_mod_mappings()
    runtime_configs = collect_runtime_configs()
    known = set(claimed_by) | forbidden
    unmapped = [rel for rel in runtime_configs if rel not in known]

    print(f"Audited {len(runtime_configs)} runtime config file(s) across {len(set(claimed_by.values()))} mod slice(s).")
    if conflicts:
        print("Path conflicts detected:", file=sys.stderr)
        for msg in conflicts:
            print(f"  - {msg}", file=sys.stderr)

    if unmapped:
        print("Unmapped runtime config file(s) in data/:")
        for rel in unmapped:
            print(f"  - data/{rel}")
    else:
        print("All runtime config files in data/ are mapped or explicitly forbidden (0 unmapped).")

    if conflicts:
        return 1
    if unmapped and args.exit_code:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
