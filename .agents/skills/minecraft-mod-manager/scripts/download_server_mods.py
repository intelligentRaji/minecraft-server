#!/usr/bin/env python3
"""
download_server_mods.py - Download recommended server-side performance & utility mods.
"""

import json
import urllib.request
from pathlib import Path

def find_repo_root() -> Path:
    p = Path(__file__).resolve().parent
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists() or (parent / "docker-compose.yml").exists():
            return parent
    return p.parents[3]

REPO_ROOT = find_repo_root()
DEST_DIR = REPO_ROOT / "modpack" / "server-only"
DEST_DIR.mkdir(parents=True, exist_ok=True)

MOD_SLUGS = [
    "chunky",
    "ferrite-core",
    "modernfix",
    "simple-backups",
]

headers = {"User-Agent": "Antigravity-Minecraft-Setup/1.0"}

for slug in MOD_SLUGS:
    url = f"https://api.modrinth.com/v2/project/{slug}/version?game_versions=%5B%221.20.1%22%5D&loaders=%5B%22forge%22%5D"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            if not data:
                print(f"[-] No 1.20.1 Forge version found for: {slug}")
                continue
            v = data[0]
            f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
            dest_file = DEST_DIR / f["filename"]
            if not dest_file.exists():
                print(f"[+] Downloading {f['filename']}...")
                urllib.request.urlretrieve(f["url"], dest_file)
                print(f"[+] Saved {f['filename']}")
            else:
                print(f"[=] Already exists: {f['filename']}")
    except Exception as e:
        print(f"[!] Error fetching {slug}: {e}")

print("\nDone downloading server mods!")
