#!/usr/bin/env python3
"""
trash_drive.py - Trash specific files or prune stale mods from Google Drive (minecraft-server/mods/).
"""

import sys
import argparse
from pathlib import Path
from gdrive_utils import GDriveClient, find_repo_root

REPO_ROOT = find_repo_root()
MODPACK_DIR = REPO_ROOT / "modpack"
CATEGORIES = ["server-client", "server-only", "client-only"]


def delete_targeted_jars(client: GDriveClient, targets: set[str], mods_folder_id: str, dry_run: bool = False) -> int:
    trashed_count = 0
    for cat in CATEGORIES:
        cat_id = client.get_folder_id(cat, parent_id=mods_folder_id)
        if not cat_id:
            continue
        grouped = client.get_grouped_files(cat_id)
        for name, file_ids in grouped.items():
            if name in targets:
                print(f"[{cat.upper()}] Found targeted file: {name} ({len(file_ids)} copy/copies)")
                for file_id in file_ids:
                    if client.trash_file(file_id, name=name, dry_run=dry_run):
                        trashed_count += 1
    return trashed_count


def prune_all_categories(client: GDriveClient, mods_folder_id: str, dry_run: bool = False) -> int:
    trashed_count = 0
    for cat in CATEGORIES:
        cat_id = client.get_folder_id(cat, parent_id=mods_folder_id)
        if not cat_id:
            continue
        local_dir = MODPACK_DIR / cat
        local_jars = set()
        if local_dir.exists():
            local_jars = {f.name for f in local_dir.iterdir() if f.is_file() and f.suffix == ".jar"}

        remote_grouped = client.get_grouped_files(cat_id, extension=".jar")
        print(f"\n[{cat.upper()}] Checking Drive contents vs local modpack/{cat}...")
        found_issue = False
        for name, file_ids in remote_grouped.items():
            if name not in local_jars:
                found_issue = True
                for file_id in file_ids:
                    if client.trash_file(file_id, name=name, dry_run=dry_run):
                        trashed_count += 1
            elif len(file_ids) > 1:
                found_issue = True
                for dup_id in file_ids[1:]:
                    if client.trash_file(dup_id, name=f"{name} (duplicate)", dry_run=dry_run):
                        trashed_count += 1

        if not found_issue:
            print("  -> Drive is in sync with local.")

    return trashed_count


def main():
    parser = argparse.ArgumentParser(description="Trash specific files or prune stale mods from Google Drive.")
    parser.add_argument("jars", nargs="*", help="Specific jar file names to trash on Google Drive")
    parser.add_argument("--prune", action="store_true", help="Prune all files on Drive missing from local modpack/")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without deleting anything")
    args = parser.parse_args()

    client = GDriveClient()

    print("[+] Connecting to Google Drive...")
    root_id = client.get_folder_id("minecraft-server")
    if not root_id:
        print("[!] Folder 'minecraft-server' not found on Google Drive.", file=sys.stderr)
        sys.exit(1)

    mods_id = client.get_folder_id("mods", parent_id=root_id)
    if not mods_id:
        print("[!] Folder 'minecraft-server/mods' not found on Google Drive.", file=sys.stderr)
        sys.exit(1)

    if args.jars:
        targets = set(args.jars)
        print(f"[+] Trashing {len(targets)} specified jar(s) on Drive...")
        total_trashed = delete_targeted_jars(client, targets, mods_id, dry_run=args.dry_run)
    else:
        total_trashed = prune_all_categories(client, mods_id, dry_run=args.dry_run)

    action_label = "Would trash" if args.dry_run else "Successfully trashed"
    print(f"\n[✓] Done! {action_label} {total_trashed} file(s).")


if __name__ == "__main__":
    main()
