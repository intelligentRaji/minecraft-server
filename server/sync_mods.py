#!/usr/bin/env python3
"""Synchronize server mods from modpack/ to data/mods/ and notify modsync-api."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent
MODPACK_DIR = (
    Path(os.environ["MODPACK_DIR"])
    if "MODPACK_DIR" in os.environ
    else (SERVER_ROOT / "modpack" if (SERVER_ROOT / "modpack").is_dir() else SERVER_ROOT.parent / "modpack")
)
DATA_MODS_DIR = SERVER_ROOT / "data" / "mods"
SERVER_CATEGORIES = ("server-client", "server-only")
HASH_CHUNK_SIZE = 1024 * 1024
HTTP_TIMEOUT_SECONDS = 5.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_jars(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        return {}
    return {
        entry.name: entry
        for entry in sorted(directory.iterdir(), key=lambda p: p.name)
        if not entry.is_symlink() and entry.is_file() and entry.suffix == ".jar"
    }


def _check_modsync_health(base_url: str) -> None:
    health_url = f"{base_url.rstrip('/')}/health"
    req = urllib.request.Request(health_url, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise RuntimeError(f"modsync-api healthcheck returned HTTP {resp.status}")


def _trigger_modsync_reload(base_url: str, admin_token: str) -> dict[str, object]:
    if not admin_token:
        raise RuntimeError("MODSYNC_ADMIN_TOKEN is required to notify modsync-api /api/reload")
    reload_url = f"{base_url.rstrip('/')}/api/reload"
    req = urllib.request.Request(
        reload_url,
        data=b"",
        method="POST",
        headers={
            "User-Agent": "mc-sync-mods/1.0",
            "X-Admin-Token": admin_token,
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _atomic_copy(src: Path, dst: Path, uid: int | None, gid: int | None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle, src.open("rb") as src_handle:
            shutil.copyfileobj(src_handle, handle)
        os.chmod(tmp_path, 0o644)
        if os.geteuid() == 0 and uid is not None and gid is not None:
            os.chown(tmp_path, uid, gid)
        os.replace(tmp_path, dst)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def sync_server_mods(
    modpack_dir: Path | None = None,
    data_mods_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Mirror server-client and server-only jars into data/mods/. Returns (added_or_updated, removed, unchanged)."""
    resolved_modpack = MODPACK_DIR if modpack_dir is None else modpack_dir
    resolved_data_mods = DATA_MODS_DIR if data_mods_dir is None else data_mods_dir

    desired: dict[str, Path] = {}
    for category in SERVER_CATEGORIES:
        for name, path in _collect_jars(resolved_modpack / category).items():
            desired[name] = path

    existing = _collect_jars(resolved_data_mods)
    target_uid = resolved_data_mods.stat().st_uid if resolved_data_mods.exists() else None
    target_gid = resolved_data_mods.stat().st_gid if resolved_data_mods.exists() else None

    if not dry_run:
        resolved_data_mods.mkdir(parents=True, exist_ok=True)

    removed = 0
    for name, path in existing.items():
        if name not in desired:
            print(f"  [-] Removing stale mod: {name}")
            removed += 1
            if not dry_run:
                path.unlink()

    updated = 0
    unchanged = 0
    for name, src_path in desired.items():
        dst_path = resolved_data_mods / name
        needs_copy = (
            not dst_path.exists()
            or src_path.stat().st_size != dst_path.stat().st_size
            or _sha256(src_path) != _sha256(dst_path)
        )
        if needs_copy:
            action = "Adding" if not dst_path.exists() else "Updating"
            print(f"  [+] {action} mod: {name}")
            updated += 1
            if not dry_run:
                _atomic_copy(src_path, dst_path, target_uid, target_gid)
        else:
            unchanged += 1

    return updated, removed, unchanged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize server mods from modpack/ into data/mods/ and notify modsync-api."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files or calling API.")
    parser.add_argument("--skip-api", action="store_true", help="Skip modsync-api healthcheck and reload notification.")
    parser.add_argument(
        "--modsync-url",
        default=os.environ.get("MODSYNC_API_URL", "http://modsync-api:8080"),
        help="modsync-api base URL (default: MODSYNC_API_URL or http://modsync-api:8080).",
    )
    args = parser.parse_args(argv)

    mode_label = "DRY-RUN" if args.dry_run else "SYNC"
    print(f"=== [{mode_label}] Synchronizing server mods ({MODPACK_DIR} -> {DATA_MODS_DIR}) ===")

    if not args.dry_run and not args.skip_api:
        try:
            _check_modsync_health(args.modsync_url)
        except Exception as exc:
            print(
                f"ERROR: modsync-api is unavailable at {args.modsync_url} ({exc}); "
                "aborting mod sync so server mods never diverge from client manifest.",
                file=sys.stderr,
            )
            return 1

    updated, removed, unchanged = sync_server_mods(dry_run=args.dry_run)
    print(f"=== [{mode_label}] Server mods: {updated} updated, {removed} removed, {unchanged} unchanged ===")

    if not args.dry_run and not args.skip_api:
        admin_token = os.environ.get("MODSYNC_ADMIN_TOKEN", "").strip()
        try:
            payload = _trigger_modsync_reload(args.modsync_url, admin_token)
            print(
                f"[MODSYNC] Reloaded manifest: version={payload.get('version')} "
                f"(notified={payload.get('notified_clients', 0)} client(s))"
            )
        except urllib.error.HTTPError as exc:
            print(f"ERROR: modsync-api /api/reload failed with HTTP {exc.code}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERROR: modsync-api /api/reload failed ({exc})", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
