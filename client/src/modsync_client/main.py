"""CLI and desktop entry point for ModSync client."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from .config import (
    AppConfig,
    DEFAULT_SERVER_URL,
    default_config_path,
    default_staging_dir,
    detect_mods_dirs,
    load_config,
    save_config,
)
from .syncer import ModSyncer, SyncStatus
from .ws_client import ModSyncService

logger = logging.getLogger("modsync_client")


def _prompt_config_cli(existing: AppConfig | None = None) -> AppConfig:
    default_url = existing.server_url if existing else (DEFAULT_SERVER_URL or "https://mods.example.com")
    server_url = input(f"ModSync server URL [{default_url}]: ").strip() or default_url

    detected = detect_mods_dirs()
    default_mods = existing.mods_dir if existing else (str(detected[0]) if detected else "")
    if detected:
        print("Detected Minecraft mods folders:")
        for idx, path in enumerate(detected, start=1):
            print(f"  {idx}. {path}")
    prompt_label = f"Minecraft mods folder [{default_mods}]: " if default_mods else "Minecraft mods folder: "
    mods_dir = input(prompt_label).strip() or default_mods
    if not mods_dir:
        raise SystemExit("Mods folder path is required.")

    return AppConfig(
        server_url=server_url.rstrip("/"),
        mods_dir=mods_dir,
        client_token=existing.client_token if existing else os.environ.get("MODSYNC_CLIENT_TOKEN", ""),
    )


def resolve_or_setup_config(args: argparse.Namespace) -> AppConfig:
    cfg_path: Path = args.config
    existing = load_config(cfg_path)

    if args.setup:
        cfg = _prompt_config_cli(existing) if args.headless else _setup_gui_or_cli(existing)
        save_config(cfg, cfg_path)
        return cfg

    if args.server_url and args.mods_dir:
        cfg = AppConfig(
            server_url=args.server_url.rstrip("/"),
            mods_dir=str(args.mods_dir),
            client_token=args.token or (existing.client_token if existing else ""),
        )
        save_config(cfg, cfg_path)
        return cfg

    if existing is not None:
        updated = AppConfig(
            server_url=(args.server_url or existing.server_url).rstrip("/"),
            mods_dir=str(args.mods_dir or existing.mods_dir),
            client_token=args.token if args.token is not None else existing.client_token,
            poll_fallback_seconds=existing.poll_fallback_seconds,
        )
        if args.server_url or args.mods_dir or args.token is not None:
            save_config(updated, cfg_path)
        return updated

    env_url = os.environ.get("MODSYNC_SERVER_URL", "").strip()
    env_mods = os.environ.get("MODSYNC_MODS_DIR", "").strip()
    if env_url and env_mods:
        cfg = AppConfig(
            server_url=env_url.rstrip("/"),
            mods_dir=env_mods,
            client_token=os.environ.get("MODSYNC_CLIENT_TOKEN", ""),
        )
        save_config(cfg, cfg_path)
        return cfg

    if args.headless or args.sync_once:
        if not sys.stdin.isatty():
            raise SystemExit(
                "No config found. Pass --server-url and --mods-dir (or run with --setup)."
            )
        cfg = _prompt_config_cli(None)
        save_config(cfg, cfg_path)
        return cfg

    cfg = _setup_gui_or_cli(None)
    save_config(cfg, cfg_path)
    return cfg


def _setup_gui_or_cli(existing: AppConfig | None) -> AppConfig:
    from .tray import prompt_config_gui

    cfg = prompt_config_gui(existing)
    if cfg is not None:
        return cfg
    if sys.stdin.isatty():
        return _prompt_config_cli(existing)
    raise SystemExit("Setup cancelled.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ModSync background Minecraft mod synchronizer.")
    parser.add_argument("--headless", action="store_true", help="Run without system tray icon")
    parser.add_argument("--sync-once", action="store_true", help="Perform a single sync and exit")
    parser.add_argument("--setup", action="store_true", help="Reconfigure server URL and mods folder")
    parser.add_argument("--server-url", help="Override ModSync server URL")
    parser.add_argument("--mods-dir", type=Path, help="Override Minecraft mods directory")
    parser.add_argument("--token", default=None, help="Optional client auth token")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="Config JSON path")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = resolve_or_setup_config(args)

    if args.sync_once:
        syncer = ModSyncer(
            server_url=config.normalized_server_url,
            mods_dir=config.mods_path,
            staging_dir=default_staging_dir(),
        )
        try:
            result = syncer.sync_once()
            print(result.message)
            return 0 if result.status != SyncStatus.ERROR else 1
        finally:
            syncer.close()

    if args.headless:
        service = ModSyncService(
            config,
            on_status=lambda status, msg, _res: logger.info("[%s] %s", status.value, msg),
        )
        try:
            asyncio.run(service.run())
        except KeyboardInterrupt:
            service.stop()
        return 0

    from .tray import ModSyncTrayApp

    app = ModSyncTrayApp(config, args.config)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
