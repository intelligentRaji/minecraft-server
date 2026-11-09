#!/usr/bin/env python3
"""
upload_to_gdrive.py - Upload modpack .jar files to Google Drive under minecraft-server/mods/.
"""

import sys
import json
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
CATEGORIES = ["server-client", "server-only", "client-only"]


def run_gdrive_json(cmd: list[str]) -> list | dict:
    full_cmd = ["gdrive"] + cmd + ["--json"]
    res = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(full_cmd)}): {res.stderr}")
    try:
        return json.loads(res.stdout.strip()) if res.stdout.strip() else []
    except json.JSONDecodeError:
        raise RuntimeError(f"Failed to parse JSON output: {res.stdout}")


def get_or_create_folder(name: str, parent_id: str | None = None) -> str:
    search_args = ["readonly", "search", "--name-exact", name, "--type", "folder"]
    if parent_id:
        search_args.extend(["--parent-id", parent_id])
    
    results = run_gdrive_json(search_args)
    if results and isinstance(results, list):
        for item in results:
            if item.get("name") == name:
                return item["id"]

    # Not found, create it using gdrive mutate mkdir
    mkdir_cmd = ["gdrive", "mutate", "mkdir", name]
    if parent_id:
        mkdir_cmd.extend(["--parent", parent_id])
    
    res = subprocess.run(mkdir_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"mkdir failed for '{name}': {res.stderr}")
    
    out = res.stdout.strip()
    if "ID: " in out:
        return out.split("ID: ")[1].rstrip(")")
    raise RuntimeError(f"Unexpected response when creating folder '{name}': {out}")


def get_existing_filenames(parent_id: str) -> set[str]:
    items = run_gdrive_json(["readonly", "ls", parent_id])
    if isinstance(items, list):
        return {item["name"] for item in items if "name" in item}
    return set()


def main():
    print("[+] Connecting to Google Drive...")
    root_id = get_or_create_folder("minecraft-server")
    mods_id = get_or_create_folder("mods", parent_id=root_id)

    total_uploaded = 0
    for cat in CATEGORIES:
        cat_dir = MODPACK_DIR / cat
        if not cat_dir.exists():
            continue
        jars = sorted([f for f in cat_dir.iterdir() if f.is_file() and f.suffix == ".jar"])
        if not jars:
            continue

        cat_folder_id = get_or_create_folder(cat, parent_id=mods_id)
        existing = get_existing_filenames(cat_folder_id)

        print(f"\n[{cat.upper()}] Checking {len(jars)} jars...")
        for jar in jars:
            if jar.name in existing:
                print(f"  [=] Already on Drive: {jar.name}")
            else:
                print(f"  [+] Uploading {jar.name}...")
                upload_res = subprocess.run(
                    ["gdrive", "mutate", "upload", str(jar), "--parent", cat_folder_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if upload_res.returncode != 0:
                    print(f"  [!] Failed to upload {jar.name}: {upload_res.stderr}", file=sys.stderr)
                else:
                    print(f"  [+] Uploaded successfully: {jar.name}")
                    total_uploaded += 1

    print(f"\n[✓] Done! {total_uploaded} new file(s) uploaded.")
    url_res = subprocess.run(["gdrive", "readonly", "url", root_id], stdout=subprocess.PIPE, text=True)
    if url_res.returncode == 0:
        print(f"Google Drive URL: {url_res.stdout.strip()}")


if __name__ == "__main__":
    main()
