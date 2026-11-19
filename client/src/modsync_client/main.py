"""CLI and desktop entry point for ModSync client."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .config import Config, default_config_path, default_staging_dir
from .onboarding import resolve_or_setup_config
from .syncer import ModSyncer, SyncStatus
from .ws_client import ModSyncService

logger = logging.getLogger("modsync_client")


def build_parser() -> argparse.ArgumentParser:
    """Create the ModSync CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="ModSync background Minecraft mod synchronizer."
    )
    parser.add_argument("--headless", action="store_true", help="Run without system tray icon")
    parser.add_argument(
        "--sync-once",
        action="store_true",
        help="Perform a single mandatory mod sync and exit",
    )
    parser.add_argument(
        "--install-recommended",
        action="store_true",
        help="Install optional client-only mods and exit",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Reconfigure server URL and mods folder",
    )
    parser.add_argument("--server-url", help="Override ModSync server URL")
    parser.add_argument("--mods-dir", type=Path, help="Override Minecraft mods directory")
    parser.add_argument("--token", default=None, help="Optional client auth token")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Config JSON path",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def _run_one_shot(config: Config, *, install_recommended: bool) -> int:
    syncer = ModSyncer(
        server_url=config.normalized_server_url,
        mods_dir=config.mods_path,
        staging_dir=default_staging_dir(),
        client_token=config.client_token,
    )
    try:
        result = syncer.install_recommended() if install_recommended else syncer.sync_once()
        print(result.message)
        return 0 if result.status != SyncStatus.ERROR else 1
    finally:
        syncer.close()


def _run_headless(config: Config) -> int:
    service = ModSyncService(
        config,
        on_status=lambda status, msg, _res: logger.info("[%s] %s", status.value, msg),
    )
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        service.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = resolve_or_setup_config(args)

    if args.sync_once or args.install_recommended:
        return _run_one_shot(config, install_recommended=args.install_recommended)

    if args.headless:
        return _run_headless(config)

    from .tray import ModSyncTrayApp

    ModSyncTrayApp(config, args.config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
