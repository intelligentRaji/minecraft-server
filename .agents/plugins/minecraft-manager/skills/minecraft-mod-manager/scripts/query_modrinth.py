#!/usr/bin/env python3
"""
query_modrinth.py - CLI tool to inspect and optionally download Forge 1.20.1 mods from Modrinth.
"""

import sys
import json
import argparse
import urllib.request
from pathlib import Path


def inspect_mod(slug: str, game_version: str = "1.20.1", loader: str = "forge") -> dict | None:
    url = f"https://api.modrinth.com/v2/project/{slug}/version?game_versions=%5B%22{game_version}%22%5D&loaders=%5B%22{loader}%22%5D"
    req = urllib.request.Request(url, headers={"User-Agent": "Antigravity/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            versions = json.load(resp)
            if not versions:
                return None
            latest = versions[0]
            file_info = next((f for f in latest["files"] if f.get("primary")), latest["files"][0])
            deps = [
                d.get("project_id")
                for d in latest.get("dependencies", [])
                if d.get("dependency_type") == "required"
            ]
            return {
                "project_slug": slug,
                "version_number": latest["version_number"],
                "filename": file_info["filename"],
                "url": file_info["url"],
                "dependencies": deps,
            }
    except Exception as e:
        print(f"Error querying Modrinth for '{slug}': {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Query and inspect mods from Modrinth API.")
    parser.add_argument("slug", help="Modrinth project slug (e.g. chunky, embeddium, ferrite-core)")
    parser.add_argument("--version", default="1.20.1", help="Minecraft game version (default: 1.20.1)")
    parser.add_argument("--loader", default="forge", help="Modloader (default: forge)")
    parser.add_argument("--download-to", type=Path, default=None, help="Optional directory to download the .jar to")
    args = parser.parse_args()

    result = inspect_mod(args.slug, game_version=args.version, loader=args.loader)
    if not result:
        print(f"[-] No compatible file found on Modrinth for '{args.slug}' ({args.version} / {args.loader})")
        sys.exit(1)

    print(f"[+] Found mod: {result['project_slug']}")
    print(f"    Version:      {result['version_number']}")
    print(f"    Filename:     {result['filename']}")
    print(f"    Download URL: {result['url']}")
    if result["dependencies"]:
        print(f"    Dependencies: {', '.join(result['dependencies'])}")
    else:
        print("    Dependencies: None (Self-contained)")

    if args.download_to:
        args.download_to.mkdir(parents=True, exist_ok=True)
        dest = args.download_to / result["filename"]
        if dest.exists():
            print(f"    [=] Already downloaded at: {dest}")
        else:
            print(f"    [+] Downloading to: {dest}...")
            urllib.request.urlretrieve(result["url"], dest)
            print(f"    [+] Download complete!")


if __name__ == "__main__":
    main()
