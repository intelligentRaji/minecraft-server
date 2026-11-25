#!/usr/bin/env python3
"""Resolve a player's exact nickname case and UUID from server/data/usercache.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NICKNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def find_server_root(start: Path) -> Path:
    """Walk upward from start to locate the server directory."""
    for candidate in (start, *start.parents):
        if (candidate / "docker-compose.yml").is_file() and (candidate / "server" / "mods").is_dir():
            return candidate / "server"
        if (candidate / "sync_mod_configurations.py").is_file() and (candidate / "mods").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate server directory above {start}")


USERCACHE_FILE = find_server_root(Path(__file__).resolve().parent) / "data" / "usercache.json"


def resolve_player(nickname: str) -> dict[str, str | None]:
    """Match nickname case-insensitively against data/usercache.json."""
    if USERCACHE_FILE.is_file():
        try:
            cache = json.loads(USERCACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = []
        if isinstance(cache, list):
            for entry in cache:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if isinstance(name, str) and name.lower() == nickname.lower():
                    uuid = entry.get("uuid")
                    return {
                        "name": name,
                        "uuid": uuid if isinstance(uuid, str) else None,
                    }
    return {"name": nickname, "uuid": None}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a player's exact nickname and UUID from data/usercache.json."
    )
    parser.add_argument("nickname", help="Player's Minecraft nickname (1-16 chars: A-Z, a-z, 0-9, _)")
    args = parser.parse_args()

    if not NICKNAME_PATTERN.fullmatch(args.nickname):
        parser.error(
            f"Invalid nickname '{args.nickname}'. Must be 1-16 characters (letters, digits, underscore)."
        )

    print(json.dumps(resolve_player(args.nickname)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
