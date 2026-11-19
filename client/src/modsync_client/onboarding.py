"""Interactive CLI/GUI onboarding and configuration resolution."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import (
    DEFAULT_POLL_FALLBACK_SECONDS,
    DEFAULT_SERVER_URL,
    Config,
    detect_mods_dirs,
    load_config,
    save_config,
)

logger = logging.getLogger("modsync_client.onboarding")

FALLBACK_PROMPT_URL = "https://mods.example.com"


def prompt_config_cli(existing: Config | None = None) -> Config:
    """Prompt the user for server URL and Minecraft mods folder in the terminal."""
    default_url = existing.server_url if existing else (DEFAULT_SERVER_URL or FALLBACK_PROMPT_URL)
    server_url = input(f"ModSync server URL [{default_url}]: ").strip() or default_url

    detected = detect_mods_dirs()
    default_mods = existing.mods_dir if existing else (str(detected[0]) if detected else "")
    if detected:
        print("Detected Minecraft mods folders:")
        for idx, path in enumerate(detected, start=1):
            print(f"  {idx}. {path}")
    prompt_label = (
        f"Minecraft mods folder [{default_mods}]: "
        if default_mods
        else "Minecraft mods folder: "
    )
    mods_dir = input(prompt_label).strip() or default_mods
    if not mods_dir:
        raise SystemExit("Mods folder path is required.")

    return Config(
        server_url=server_url.rstrip("/"),
        mods_dir=mods_dir,
        client_token=(
            existing.client_token
            if existing
            else os.environ.get("MODSYNC_CLIENT_TOKEN", "")
        ),
        poll_fallback_seconds=(
            existing.poll_fallback_seconds if existing else DEFAULT_POLL_FALLBACK_SECONDS
        ),
    )


def prompt_config_gui(existing: Config | None = None) -> Config | None:
    """Prompt the user for server URL and Minecraft mods folder using tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog
    except Exception as exc:  # pragma: no cover - headless environments without tk
        logger.error("tkinter unavailable for GUI setup: %s", exc)
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        default_url = existing.server_url if existing else (DEFAULT_SERVER_URL or "https://")
        server_url = simpledialog.askstring(
            "ModSync Setup",
            "Enter the ModSync server URL (e.g. https://mods.example.com):",
            initialvalue=default_url,
            parent=root,
        )
        if not server_url or not server_url.strip():
            return None

        detected = detect_mods_dirs()
        initial_dir = (
            existing.mods_dir
            if existing
            else (str(detected[0]) if detected else str(Path.home()))
        )
        messagebox.showinfo(
            "ModSync Setup",
            "Select your Minecraft launcher's 'mods' folder on the next dialog.",
            parent=root,
        )
        selected_dir = filedialog.askdirectory(
            title="Select Minecraft mods folder",
            initialdir=initial_dir,
            parent=root,
        )
        if not selected_dir:
            return None

        return Config(
            server_url=server_url.strip().rstrip("/"),
            mods_dir=selected_dir,
            client_token=existing.client_token if existing else "",
            poll_fallback_seconds=(
                existing.poll_fallback_seconds if existing else DEFAULT_POLL_FALLBACK_SECONDS
            ),
        )
    finally:
        root.destroy()


def setup_gui_or_cli(existing: Config | None = None) -> Config:
    """Prompt via tkinter GUI with terminal fallback when running in an interactive TTY."""
    cfg = prompt_config_gui(existing)
    if cfg is not None:
        return cfg
    if sys.stdin.isatty():
        return prompt_config_cli(existing)
    raise SystemExit("Setup cancelled.")


def _merge_cli_overrides(existing: Config, args: argparse.Namespace) -> tuple[Config, bool]:
    has_override = bool(args.server_url or args.mods_dir or args.token is not None)
    updated = Config(
        server_url=(args.server_url or existing.server_url).rstrip("/"),
        mods_dir=str(args.mods_dir or existing.mods_dir),
        client_token=args.token if args.token is not None else existing.client_token,
        poll_fallback_seconds=existing.poll_fallback_seconds,
    )
    return updated, has_override


def resolve_or_setup_config(args: argparse.Namespace) -> Config:
    """Resolve configuration from CLI flags, persisted JSON, environment, or interactive setup."""
    cfg_path: Path = args.config
    existing = load_config(cfg_path)

    if args.setup:
        cfg = prompt_config_cli(existing) if args.headless else setup_gui_or_cli(existing)
        save_config(cfg, cfg_path)
        return cfg

    if args.server_url and args.mods_dir:
        cfg = Config(
            server_url=args.server_url.rstrip("/"),
            mods_dir=str(args.mods_dir),
            client_token=args.token or (existing.client_token if existing else ""),
        )
        save_config(cfg, cfg_path)
        return cfg

    if existing is not None:
        updated, changed = _merge_cli_overrides(existing, args)
        if changed:
            save_config(updated, cfg_path)
        return updated

    env_cfg = Config.from_env()
    if env_cfg is not None:
        save_config(env_cfg, cfg_path)
        return env_cfg

    if args.headless or args.sync_once:
        if not sys.stdin.isatty():
            raise SystemExit(
                "No config found. Pass --server-url and --mods-dir (or run with --setup)."
            )
        cfg = prompt_config_cli(None)
        save_config(cfg, cfg_path)
        return cfg

    cfg = setup_gui_or_cli(None)
    save_config(cfg, cfg_path)
    return cfg
