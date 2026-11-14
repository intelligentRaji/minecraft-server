#!/usr/bin/env python3
"""
sync_mods.py - Synchronize Minecraft mods between modpack categories, Docker server, and Modrinth client.

Categories:
  modpack/server-client/ -> Copied to both Server (./data/mods) and Client (Modrinth profile)
  modpack/server-only/   -> Copied only to Server (./data/mods)
  modpack/client-only/   -> Copied only to Client (Modrinth profile)
"""

import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

def find_repo_root() -> Path:
    p = Path(__file__).resolve().parent
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists() or (parent / "docker-compose.yml").exists():
            return parent
    return p.parents[3]

REPO_ROOT = find_repo_root()
MODPACK_DIR = REPO_ROOT / "modpack"
SERVER_CLIENT_DIR = MODPACK_DIR / "server-client"
SERVER_ONLY_DIR = MODPACK_DIR / "server-only"
CLIENT_ONLY_DIR = MODPACK_DIR / "client-only"
SERVER_MODS_DIR = REPO_ROOT / "data" / "mods"

def detect_client_mods_dir() -> Path:
    # 1. Environment variable override
    if "MODRINTH_CLIENT_MODS" in os.environ:
        return Path(os.environ["MODRINTH_CLIENT_MODS"])
    # 2. Dynamic discovery in WSL Windows users
    users_dir = Path("/mnt/c/Users")
    if users_dir.exists():
        for candidate in users_dir.glob("*/AppData/Roaming/ModrinthApp/profiles/Forge 1.20.1/mods"):
            if candidate.is_dir():
                return candidate
    # 3. Fallback to default relative path
    return Path.home() / ".minecraft" / "mods"


DEFAULT_CLIENT_MODS_DIR = detect_client_mods_dir()


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

    # 1. Sync Server (server-client + server-only)
    server_changed = sync_target(
        "Server",
        SERVER_MODS_DIR,
        [SERVER_CLIENT_DIR, SERVER_ONLY_DIR],
        dry_run=args.dry_run
    )

    # 2. Sync Client (server-client + client-only)
    client_missing = False
    if not args.skip_client:
        if args.client_path.exists():
            sync_target(
                "Client (Modrinth)",
                args.client_path,
                [SERVER_CLIENT_DIR, CLIENT_ONLY_DIR],
                dry_run=args.dry_run
            )
        else:
            client_missing = True
            if not Path("/mnt/c/Users").exists() and args.client_path == DEFAULT_CLIENT_MODS_DIR:
                print(f"\n[CLIENT] Error: /mnt/c/Users is not accessible (likely sandboxed) and fallback {args.client_path} does not exist.")
                print("  -> Re-run outside the sandbox (BypassSandbox: true), or pass --skip-client / --client-path.")
            else:
                print(f"\n[CLIENT] Error: Directory not found: {args.client_path}")
                print("  -> Pass --client-path <dir> or --skip-client if client sync is not needed.")

    # 3. Optional server restart
    if args.restart and server_changed and not args.dry_run:
        print("\nRestarting Docker Minecraft server container...")
        subprocess.run(["docker", "compose", "restart", "mc"], cwd=REPO_ROOT, check=True)
        print("Server restarted successfully.")

    if client_missing and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
