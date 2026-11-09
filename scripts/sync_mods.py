#!/usr/bin/env python3
"""
sync_mods.py - Synchronize Minecraft mods between modpack categories, Docker server, and Modrinth client.

Categories:
  modpack/both/        -> Copied to both Server (./data/mods) and Client (Modrinth profile)
  modpack/server-only/ -> Copied only to Server (./data/mods)
  modpack/client-only/ -> Copied only to Client (Modrinth profile)
"""

import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODPACK_DIR = REPO_ROOT / "modpack"
BOTH_DIR = MODPACK_DIR / "both"
SERVER_ONLY_DIR = MODPACK_DIR / "server-only"
CLIENT_ONLY_DIR = MODPACK_DIR / "client-only"
SERVER_MODS_DIR = REPO_ROOT / "data" / "mods"

# Default Modrinth Windows profile path
DEFAULT_CLIENT_MODS_DIR = Path("/mnt/c/Users/sergd/AppData/Roaming/ModrinthApp/profiles/Forge 1.20.1/mods")


def get_jars_in_dir(directory: Path) -> dict[str, Path]:
    if not directory.exists():
        return {}
    return {f.name: f for f in directory.iterdir() if f.is_file() and f.suffix == ".jar"}


def sync_target(target_name: str, target_dir: Path, source_dirs: list[Path], dry_run: bool = False) -> bool:
    target_dir.mkdir(parents=True, exist_ok=True)
    desired_jars: dict[str, Path] = {}
    for sdir in source_dirs:
        for name, path in get_jars_in_dir(sdir).items():
            desired_jars[name] = path

    existing_jars = get_jars_in_dir(target_dir)
    changed = False

    print(f"\n[{target_name.upper()}] Target: {target_dir}")
    print(f"  Desired mods ({len(desired_jars)}): {', '.join(sorted(desired_jars.keys())) if desired_jars else 'None'}")

    # Remove stale jars
    for name, path in existing_jars.items():
        if name not in desired_jars:
            print(f"  [-] Removing stale mod: {name}")
            changed = True
            if not dry_run:
                path.unlink()

    # Copy new or updated jars
    for name, src_path in desired_jars.items():
        dst_path = target_dir / name
        if not dst_path.exists() or src_path.stat().st_size != dst_path.stat().st_size:
            action = "Adding" if not dst_path.exists() else "Updating"
            print(f"  [+] {action} mod: {name}")
            changed = True
            if not dry_run:
                shutil.copy2(src_path, dst_path)

    if not changed:
        print("  -> Already up to date.")
    return changed


def main():
    parser = argparse.ArgumentParser(description="Sync Minecraft mods between modpack folders, server, and client.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    parser.add_argument("--restart", action="store_true", help="Restart Docker server if server mods changed")
    parser.add_argument("--client-path", type=Path, default=DEFAULT_CLIENT_MODS_DIR, help="Custom client mods folder path")
    parser.add_argument("--skip-client", action="store_true", help="Do not sync client mods")
    args = parser.parse_args()

    # 1. Sync Server (both + server-only)
    server_changed = sync_target(
        "Server",
        SERVER_MODS_DIR,
        [BOTH_DIR, SERVER_ONLY_DIR],
        dry_run=args.dry_run
    )

    # 2. Sync Client (both + client-only)
    if not args.skip_client:
        if args.client_path.exists():
            sync_target(
                "Client (Modrinth)",
                args.client_path,
                [BOTH_DIR, CLIENT_ONLY_DIR],
                dry_run=args.dry_run
            )
        else:
            print(f"\n[CLIENT] Directory not found: {args.client_path} (Skipping client sync)")

    # 3. Optional server restart
    if args.restart and server_changed and not args.dry_run:
        print("\nRestarting Docker Minecraft server container...")
        subprocess.run(["docker", "compose", "restart", "mc"], cwd=REPO_ROOT, check=True)
        print("Server restarted successfully.")


if __name__ == "__main__":
    main()
