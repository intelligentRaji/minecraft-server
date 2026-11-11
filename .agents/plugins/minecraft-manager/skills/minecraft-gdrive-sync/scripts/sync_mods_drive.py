#!/usr/bin/env python3
"""
sync_mods_drive.py - Synchronize local modpack/ directory with Google Drive under minecraft-server/mods/.
Uploads missing files and prunes stale files from Drive.
"""

import argparse
from pathlib import Path
from gdrive_utils import GDriveClient, find_repo_root

REPO_ROOT = find_repo_root()
MODPACK_DIR = REPO_ROOT / "modpack"
CATEGORIES = ["server-client", "server-only", "client-only"]


def main():
    parser = argparse.ArgumentParser(description="Synchronize local Minecraft modpack with Google Drive.")
    parser.add_argument("--no-prune", action="store_true", help="Do not prune stale files from Drive")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying Google Drive")
    args = parser.parse_args()

    client = GDriveClient()

    print("[+] Connecting to Google Drive...")
    root_id = client.get_or_create_folder("minecraft-server")
    mods_id = client.get_or_create_folder("mods", parent_id=root_id)

    total_uploaded = 0
    total_trashed = 0

    for cat in CATEGORIES:
        local_dir = MODPACK_DIR / cat
        cat_folder_id = client.get_or_create_folder(cat, parent_id=mods_id)

        print(f"\n[{cat.upper()}] Synchronizing local modpack/{cat} with Drive...")
        uploaded, trashed = client.sync_directory(
            local_dir=local_dir,
            remote_folder_id=cat_folder_id,
            extension=".jar",
            prune=not args.no_prune,
            dry_run=args.dry_run
        )
        total_uploaded += uploaded
        total_trashed += trashed

    summary = []
    if total_uploaded > 0:
        summary.append(f"{total_uploaded} file(s) {'would be uploaded' if args.dry_run else 'uploaded'}")
    if total_trashed > 0:
        summary.append(f"{total_trashed} stale file(s) {'would be trashed' if args.dry_run else 'trashed'}")
    if not summary:
        summary.append("Already fully synchronized")

    print(f"\n[✓] Done! {', '.join(summary)}.")
    web_url = client.get_web_url(root_id)
    if web_url:
        print(f"Google Drive URL: {web_url}")


if __name__ == "__main__":
    main()
