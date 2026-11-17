#!/usr/bin/env python3
"""
sync_mods.py - Synchronize server mods from server/modpack/ to server/data/mods/ and notify modsync-api.

Categories:
  server/modpack/server-client/ -> Copied to Server (server/data/mods) and served to clients via modsync-api
  server/modpack/server-only/   -> Copied only to Server (server/data/mods)
  server/modpack/client-only/   -> Served only to clients via modsync-api
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def find_server_root() -> Path:
    """Walk upward from this script to locate the server root containing docker-compose.yml."""
    p = Path(__file__).resolve().parent
    for parent in [p] + list(p.parents):
        if (parent / "server" / "docker-compose.yml").is_file():
            return parent / "server"
        if (parent / "docker-compose.yml").is_file():
            return parent
    raise RuntimeError("Could not locate server root containing docker-compose.yml")


SERVER_ROOT = find_server_root()
MODPACK_DIR = SERVER_ROOT / "modpack"
SERVER_CLIENT_DIR = MODPACK_DIR / "server-client"
SERVER_ONLY_DIR = MODPACK_DIR / "server-only"
CLIENT_ONLY_DIR = MODPACK_DIR / "client-only"
SERVER_MODS_DIR = SERVER_ROOT / "data" / "mods"


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

    for name, path in existing_jars.items():
        if name not in desired_jars:
            print(f"  [-] Removing stale mod: {name}")
            changed = True
            if not dry_run:
                path.unlink()

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


def notify_modsync_api(base_url: str, admin_token: str | None) -> None:
    """Trigger modsync-api manifest reload so connected WebSocket clients update immediately."""
    reload_url = f"{base_url.rstrip('/')}/api/reload"
    headers = {"User-Agent": "sync_mods/1.0"}
    if admin_token:
        headers["X-Admin-Token"] = admin_token
    req = urllib.request.Request(reload_url, data=b"", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            print(
                f"\n[MODSYNC] Notified {reload_url}: version={payload.get('version')} "
                f"(broadcast={payload.get('notified_clients', 0)} client(s))"
            )
    except urllib.error.URLError as exc:
        print(f"\n[MODSYNC] Skipped reload notification ({reload_url} unreachable: {exc.reason})")
    except Exception as exc:
        print(f"\n[MODSYNC] Reload notification failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Minecraft server mods from server/modpack/ and notify modsync-api."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    parser.add_argument("--restart", action="store_true", help="Restart Docker Minecraft server if server mods changed")
    parser.add_argument(
        "--client-path",
        type=Path,
        default=Path(os.environ["MODRINTH_CLIENT_MODS"]) if "MODRINTH_CLIENT_MODS" in os.environ else None,
        help="Optional local client mods folder path (for direct host testing only)",
    )
    parser.add_argument(
        "--modsync-url",
        default=os.environ.get("MODSYNC_API_URL", "http://127.0.0.1:8080"),
        help="modsync-api base URL to notify on changes (default: http://127.0.0.1:8080)",
    )
    parser.add_argument("--no-notify", action="store_true", help="Do not call modsync-api /api/reload")
    args = parser.parse_args()

    # 1. Sync Server (server-client + server-only)
    server_changed = sync_target(
        "Server",
        SERVER_MODS_DIR,
        [SERVER_CLIENT_DIR, SERVER_ONLY_DIR],
        dry_run=args.dry_run,
    )

    # 2. Optional local client path (only when explicitly configured)
    if args.client_path is not None:
        sync_target(
            "Local Client",
            args.client_path,
            [SERVER_CLIENT_DIR, CLIENT_ONLY_DIR],
            dry_run=args.dry_run,
        )

    # 3. Optional server restart
    if args.restart and server_changed and not args.dry_run:
        print("\nRestarting Docker Minecraft server container...")
        subprocess.run(["docker", "compose", "restart", "mc"], cwd=SERVER_ROOT, check=True)
        print("Server restarted successfully.")

    # 4. Notify modsync-api to recompute manifest & push WebSocket updates to connected players
    if not args.dry_run and not args.no_notify:
        notify_modsync_api(args.modsync_url, os.environ.get("MODSYNC_ADMIN_TOKEN"))


if __name__ == "__main__":
    main()
