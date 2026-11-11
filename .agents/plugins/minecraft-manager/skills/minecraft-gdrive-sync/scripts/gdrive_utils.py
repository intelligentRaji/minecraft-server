#!/usr/bin/env python3
"""
gdrive_utils.py - Common Google Drive utilities for minecraft-gdrive-sync skill scripts.
Provides reusable operations wrapping the gdrive CLI tool.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_repo_root() -> Path:
    """Dynamically finds the repository root by locating .git or docker-compose.yml."""
    p = Path(__file__).resolve().parent
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists() or (parent / "docker-compose.yml").exists():
            return parent
    raise RuntimeError("Could not determine repository root (missing .git or docker-compose.yml)")


class GDriveClient:
    """Reusable Google Drive client wrapping the gdrive CLI tool."""

    def __init__(self, binary_path: str = "gdrive"):
        self.binary_path = binary_path

    def run_json(self, cmd: List[str]) -> Any:
        full_cmd = [self.binary_path] + cmd + ["--json"]
        res = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Command failed ({' '.join(full_cmd)}): {res.stderr.strip()}")
        try:
            return json.loads(res.stdout.strip()) if res.stdout.strip() else []
        except json.JSONDecodeError:
            raise RuntimeError(f"Failed to parse JSON output: {res.stdout.strip()}")

    def get_folder_id(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        args = ["readonly", "search", "--name-exact", name, "--type", "folder"]
        if parent_id:
            args.extend(["--parent-id", parent_id])
        
        results = self.run_json(args)
        if results and isinstance(results, list):
            for item in results:
                if item.get("name") == name:
                    return item["id"]
        return None

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        folder_id = self.get_folder_id(name, parent_id=parent_id)
        if folder_id:
            return folder_id

        mkdir_cmd = [self.binary_path, "mutate", "mkdir", name]
        if parent_id:
            mkdir_cmd.extend(["--parent", parent_id])

        res = subprocess.run(mkdir_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"mkdir failed for '{name}': {res.stderr.strip()}")

        out = res.stdout.strip()
        if "ID: " in out:
            return out.split("ID: ")[1].rstrip(")")
        raise RuntimeError(f"Unexpected response when creating folder '{name}': {out}")

    def list_files(self, parent_id: str) -> List[Dict[str, Any]]:
        items = self.run_json(["readonly", "ls", parent_id])
        return items if isinstance(items, list) else []

    def get_file_map(self, parent_id: str, extension: Optional[str] = None) -> Dict[str, str]:
        """Returns filename -> file_id dictionary."""
        items = self.list_files(parent_id)
        file_map: Dict[str, str] = {}
        for it in items:
            name = it.get("name", "")
            if extension is None or name.endswith(extension):
                file_map[name] = it["id"]
        return file_map

    def trash_file(self, file_id: str, name: str = "", dry_run: bool = False) -> bool:
        label = name or file_id
        if dry_run:
            print(f"  [DRY-RUN] Would trash: {label} (ID: {file_id})")
            return True

        res = subprocess.run([self.binary_path, "mutate", "trash", file_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"  [!] Failed to trash {label}: {res.stderr.strip()}", file=sys.stderr)
            return False
        print(f"  [-] Trashed on Drive: {label}")
        return True

    def upload_file(self, local_path: Path, parent_id: str, dry_run: bool = False) -> bool:
        if dry_run:
            print(f"  [DRY-RUN] Would upload: {local_path.name}")
            return True

        print(f"  [+] Uploading {local_path.name}...")
        res = subprocess.run(
            [self.binary_path, "mutate", "upload", str(local_path), "--parent", parent_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode != 0:
            print(f"  [!] Failed to upload {local_path.name}: {res.stderr.strip()}", file=sys.stderr)
            return False
        print(f"  [+] Uploaded successfully: {local_path.name}")
        return True

    def sync_directory(
        self,
        local_dir: Path,
        remote_folder_id: str,
        extension: str = ".jar",
        prune: bool = True,
        dry_run: bool = False
    ) -> Tuple[int, int]:
        """
        Synchronizes local directory with remote Google Drive folder.
        Returns (uploaded_count, trashed_count).
        """
        trashed_count = 0
        uploaded_count = 0

        local_files: Dict[str, Path] = {}
        if local_dir.exists():
            local_files = {f.name: f for f in local_dir.iterdir() if f.is_file() and f.suffix == extension}

        remote_map = self.get_file_map(remote_folder_id, extension=extension)

        if prune:
            for r_name, r_id in remote_map.items():
                if r_name not in local_files:
                    if self.trash_file(r_id, name=r_name, dry_run=dry_run):
                        trashed_count += 1

        for l_name, l_path in sorted(local_files.items()):
            if l_name in remote_map:
                print(f"  [=] Already on Drive: {l_name}")
            else:
                if self.upload_file(l_path, remote_folder_id, dry_run=dry_run):
                    uploaded_count += 1

        return uploaded_count, trashed_count

    def get_web_url(self, folder_id: str) -> Optional[str]:
        res = subprocess.run([self.binary_path, "readonly", "url", folder_id], stdout=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        return None
