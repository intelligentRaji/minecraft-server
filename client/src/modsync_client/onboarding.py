"""Interactive CLI/GUI onboarding and configuration resolution."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import (
    DEFAULT_POLL_FALLBACK_SECONDS,
    Config,
    detect_minecraft_dirs,
    get_default_client_token,
    get_default_server_url,
    load_config,
    parse_server_input,
    resolve_mods_dir,
    save_config,
)

logger = logging.getLogger("modsync_client.onboarding")

FALLBACK_PROMPT_URL = "https://mods.example.com"


def _initial_minecraft_dir(existing: Config | None, detected: list[Path]) -> str:
    if existing is not None:
        mods_path = existing.mods_path
        return str(mods_path.parent if mods_path.name.lower() == "mods" else mods_path)
    return str(detected[0]) if detected else ""


def _resolve_token(
    parsed_token: str | None,
    existing: Config | None,
    preset_token: str | None = None,
) -> str:
    if parsed_token is not None:
        return parsed_token
    if preset_token is not None:
        return preset_token
    if existing is not None and existing.client_token:
        return existing.client_token
    return get_default_client_token()


def prompt_config_cli(
    existing: Config | None = None,
    *,
    preset_url: str = "",
    preset_token: str | None = None,
) -> Config:
    """Prompt the user for Minecraft folder (and invite link/URL when not preconfigured)."""
    default_env_url = preset_url.strip().rstrip("/") or get_default_server_url()
    parsed_token: str | None = None
    if existing is None and default_env_url:
        server_url = default_env_url
        print(f"Using ModSync server URL: {server_url}")
    else:
        default_url = (
            existing.server_url
            if existing
            else (default_env_url or FALLBACK_PROMPT_URL)
        )
        raw_input = (
            input(f"Server invite link (modsync://...) or URL [{default_url}]: ").strip()
            or default_url
        )
        try:
            server_url, parsed_token = parse_server_input(raw_input)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    detected = detect_minecraft_dirs()
    default_folder = _initial_minecraft_dir(existing, detected)
    if detected:
        print("Detected Minecraft folders:")
        for idx, path in enumerate(detected, start=1):
            print(f"  {idx}. {path}")
    prompt_label = (
        f"Minecraft folder [{default_folder}]: "
        if default_folder
        else "Minecraft folder: "
    )
    selected_folder = input(prompt_label).strip() or default_folder
    if not selected_folder:
        raise SystemExit("Minecraft folder path is required.")

    return Config(
        server_url=server_url.rstrip("/"),
        mods_dir=str(resolve_mods_dir(selected_folder)),
        client_token=_resolve_token(parsed_token, existing, preset_token),
        poll_fallback_seconds=(
            existing.poll_fallback_seconds if existing else DEFAULT_POLL_FALLBACK_SECONDS
        ),
    )


def prompt_config_gui(
    existing: Config | None = None,
    *,
    preset_url: str = "",
    preset_token: str | None = None,
) -> Config | None:
    """Prompt the user for Minecraft folder (and invite link/URL when not preconfigured) via tkinter."""
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
        default_env_url = preset_url.strip().rstrip("/") or get_default_server_url()
        parsed_token: str | None = None
        if existing is None and default_env_url:
            server_url = default_env_url
        else:
            default_url = existing.server_url if existing else (default_env_url or "modsync://")
            while True:
                raw_input = simpledialog.askstring(
                    "ModSync Setup",
                    "Paste your server invite link (modsync://...) or enter the server URL:",
                    initialvalue=default_url,
                    parent=root,
                )
                if not raw_input or not raw_input.strip():
                    return None
                try:
                    server_url, parsed_token = parse_server_input(raw_input)
                    break
                except ValueError as exc:
                    messagebox.showerror("Invalid Invite Link", str(exc), parent=root)
                    default_url = raw_input.strip()

        detected = detect_minecraft_dirs()
        initial_dir = _initial_minecraft_dir(existing, detected) or str(Path.home())
        messagebox.showinfo(
            "ModSync Setup",
            "Select your Minecraft folder on the next dialog (the 'mods' folder inside it will be synced).",
            parent=root,
        )
        selected_dir = filedialog.askdirectory(
            title="Select Minecraft folder",
            initialdir=initial_dir,
            parent=root,
        )
        if not selected_dir:
            return None

        return Config(
            server_url=server_url.strip().rstrip("/"),
            mods_dir=str(resolve_mods_dir(selected_dir)),
            client_token=_resolve_token(parsed_token, existing, preset_token),
            poll_fallback_seconds=(
                existing.poll_fallback_seconds if existing else DEFAULT_POLL_FALLBACK_SECONDS
            ),
        )
    finally:
        root.destroy()


def setup_gui_or_cli(
    existing: Config | None = None,
    *,
    preset_url: str = "",
    preset_token: str | None = None,
) -> Config:
    """Prompt via tkinter GUI with terminal fallback when running in an interactive TTY."""
    cfg = prompt_config_gui(existing, preset_url=preset_url, preset_token=preset_token)
    if cfg is not None:
        return cfg
    if sys.stdin.isatty():
        return prompt_config_cli(existing, preset_url=preset_url, preset_token=preset_token)
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


def _apply_invite_uri(args: argparse.Namespace) -> None:
    invite_uri = getattr(args, "invite_uri", None)
    if not invite_uri:
        return
    invite_url, invite_token = parse_server_input(invite_uri)
    if not args.server_url:
        args.server_url = invite_url
    if args.token is None and invite_token is not None:
        args.token = invite_token


def resolve_or_setup_config(args: argparse.Namespace) -> Config:
    """Resolve configuration from CLI flags, persisted JSON, environment, or interactive setup."""
    _apply_invite_uri(args)
    cfg_path: Path = args.config
    existing = load_config(cfg_path)
    preset_url = (args.server_url or "").strip()
    preset_token = args.token

    if args.setup:
        cfg = (
            prompt_config_cli(existing, preset_url=preset_url, preset_token=preset_token)
            if args.headless
            else setup_gui_or_cli(existing, preset_url=preset_url, preset_token=preset_token)
        )
        save_config(cfg, cfg_path)
        return cfg

    effective_url = preset_url or (get_default_server_url() if existing is None else "")
    if effective_url and args.mods_dir:
        cfg = Config(
            server_url=effective_url.rstrip("/"),
            mods_dir=str(args.mods_dir),
            client_token=(
                args.token
                if args.token is not None
                else (
                    (existing.client_token or get_default_client_token())
                    if existing
                    else get_default_client_token()
                )
            ),
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
                "No config found. Pass an invite URI or --server-url and --mods-dir (or run with --setup)."
            )
        cfg = prompt_config_cli(None, preset_url=preset_url, preset_token=preset_token)
        save_config(cfg, cfg_path)
        return cfg

    cfg = setup_gui_or_cli(None, preset_url=preset_url, preset_token=preset_token)
    save_config(cfg, cfg_path)
    return cfg
