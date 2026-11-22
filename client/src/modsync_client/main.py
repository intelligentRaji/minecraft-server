"""CLI and desktop entry point for ModSync client."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from modsync_client import __version__
from modsync_client.config import Config, default_config_path, default_staging_dir
from modsync_client.onboarding import resolve_or_setup_config
from modsync_client.syncer import ModSyncer, SyncStatus
from modsync_client.updater import (
    check_for_update,
    cleanup_old_binary,
    download_and_apply_update,
    relaunch_executable,
)
from modsync_client.ws_client import ModSyncService

logger = logging.getLogger("modsync_client")


def build_parser() -> argparse.ArgumentParser:
    """Create the ModSync CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="ModSync background Minecraft mod synchronizer."
    )
    parser.add_argument(
        "invite_uri",
        nargs="?",
        default=None,
        help="Optional modsync://connect?... invite link or server URL",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
        help="Reconfigure server invite link and Minecraft folder",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Check for a newer ModSync release, install it, and exit",
    )
    parser.add_argument(
        "--relaunch",
        action="store_true",
        help="Relaunch ModSync in the background after applying an update with --update",
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
    except Exception as exc:
        logger.error("Sync failed: %s", exc)
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    finally:
        syncer.close()


def _run_update(*, relaunch: bool = False) -> int:
    """Check GitHub Releases for a newer standalone ModSync binary and apply it in place."""
    try:
        update = check_for_update(__version__)
    except Exception as exc:
        print(f"Update check failed: {exc}", file=sys.stderr)
        return 1

    if update is None:
        print(f"ModSync is already up to date (v{__version__}).")
        return 0

    if not getattr(sys, "frozen", False):
        print(
            f"ModSync v{update.version} is available (you have v{__version__}): {update.html_url}\n"
            "In-place updates only apply to standalone frozen binaries.",
            file=sys.stderr,
        )
        return 1

    try:
        download_and_apply_update(update)
    except Exception as exc:
        print(f"Failed to apply update v{update.version}: {exc}", file=sys.stderr)
        return 1

    print(f"Updated ModSync from v{__version__} to v{update.version}.")
    if relaunch:
        relaunch_executable()
    return 0


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
    cleanup_old_binary()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.update:
        return _run_update(relaunch=args.relaunch)

    config = resolve_or_setup_config(args)

    if args.sync_once or args.install_recommended:
        return _run_one_shot(config, install_recommended=args.install_recommended)

    if args.headless:
        return _run_headless(config)

    from modsync_client.tray import ModSyncTrayApp

    ModSyncTrayApp(config, args.config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
