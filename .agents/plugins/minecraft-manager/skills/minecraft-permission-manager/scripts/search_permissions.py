#!/usr/bin/env python3
"""Search discovered Paradigm/LuckPerms permission nodes in data/config/paradigm/discovered_permissions.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def find_repo_root(start: Path) -> Path:
    """Walk upward from start to locate the repository root (containing docker-compose.yml)."""
    for candidate in (start, *start.parents):
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root (docker-compose.yml) above {start}")


PERMS_FILE = (
    find_repo_root(Path(__file__).resolve().parent)
    / "data"
    / "config"
    / "paradigm"
    / "discovered_permissions.json"
)


def search_nodes(query: str, limit: int) -> list[tuple[str, str]]:
    """Return matching (node, description) pairs sorted by node name."""
    if not PERMS_FILE.is_file():
        raise RuntimeError(f"Missing {PERMS_FILE} (has Paradigm started at least once?)")

    data = json.loads(PERMS_FILE.read_text(encoding="utf-8"))
    nodes = data.get("nodes", {})
    if not isinstance(nodes, dict):
        raise RuntimeError(f"Unexpected structure in {PERMS_FILE}: 'nodes' must be an object")

    needle = query.lower()
    matches: list[tuple[str, str]] = []
    for node_name in sorted(nodes):
        if needle in node_name.lower():
            meta = nodes[node_name]
            desc = meta.get("description", "") if isinstance(meta, dict) else ""
            matches.append((node_name, desc))
            if len(matches) >= limit:
                break
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search Paradigm discovered_permissions.json for LuckPerms nodes."
    )
    parser.add_argument("query", help="Substring to match against permission node names (e.g. 'kick', 'command.tp')")
    parser.add_argument("--limit", type=int, default=50, help="Max results to print (default: 50)")
    args = parser.parse_args()

    try:
        matches = search_nodes(args.query, args.limit)
    except (RuntimeError, json.JSONDecodeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not matches:
        print(f"No permission nodes matching '{args.query}'.")
        return 0

    for node_name, desc in matches:
        print(f"{node_name}: {desc}" if desc else node_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
