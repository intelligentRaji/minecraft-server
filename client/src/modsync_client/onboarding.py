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
    load_config,
    parse_server_input,
    resolve_mods_dir,
    save_config,
)

logger = logging.getLogger("modsync_client.onboarding")

_last_gui_unavailable = False


def _is_interactive_tty() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _existing_minecraft_dir(existing: Config) -> str:
    mods_path = existing.mods_path
    return str(mods_path.parent if mods_path.name.lower() == "mods" else mods_path)


def _prompt_with_default(label: str, default: str = "") -> str:
    prompt = f"{label} [{default}]: " if default else f"{label}: "
    try:
        return input(prompt).strip() or default
    except (EOFError, KeyboardInterrupt):
        logger.info("Setup cancelled.")
        raise SystemExit(0) from None


def _build_prompted_config(
    *,
    server_url: str,
    selected_folder: str,
    parsed_token: str | None,
    existing: Config | None,
    preset_token: str | None,
) -> Config:
    if parsed_token is not None:
        token = parsed_token
    elif preset_token is not None:
        token = preset_token
    elif existing is not None:
        token = existing.client_token
    else:
        token = ""

    return Config(
        server_url=server_url,
        mods_dir=str(resolve_mods_dir(selected_folder)),
        client_token=token,
        poll_fallback_seconds=(
            existing.poll_fallback_seconds if existing else DEFAULT_POLL_FALLBACK_SECONDS
        ),
    )


def prompt_config_cli(
    existing: Config | None = None,
    *,
    preset_url: str = "",
    preset_token: str | None = None,
) -> Config:
    """Prompt the user for Minecraft folder (and invite link/URL when not preconfigured)."""
    normalized_preset = preset_url.strip().rstrip("/")
    parsed_token: str | None = None
    if existing is None and normalized_preset:
        server_url = normalized_preset
        print(f"Using ModSync server URL: {server_url}")
    else:
        default_url = existing.server_url if existing else ""
        raw_input = _prompt_with_default("Server invite link (modsync://...) or URL", default_url)
        try:
            server_url, parsed_token = parse_server_input(raw_input)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    if existing is not None:
        default_folder = _existing_minecraft_dir(existing)
    else:
        detected = detect_minecraft_dirs()
        default_folder = str(detected[0]) if detected else ""
        if detected:
            print("Detected Minecraft folders:")
            for idx, path in enumerate(detected, start=1):
                print(f"  {idx}. {path}")

    selected_folder = _prompt_with_default("Minecraft folder", default_folder)
    if not selected_folder:
        raise SystemExit("Minecraft folder path is required.")

    return _build_prompted_config(
        server_url=server_url,
        selected_folder=selected_folder,
        parsed_token=parsed_token,
        existing=existing,
        preset_token=preset_token,
    )


def prompt_config_gui(
    existing: Config | None = None,
    *,
    preset_url: str = "",
    preset_token: str | None = None,
) -> Config | None:
    """Prompt the user for Minecraft folder (and invite link/URL when not preconfigured) via tkinter."""
    global _last_gui_unavailable
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog

        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - headless environments without tk
        _last_gui_unavailable = True
        logger.error("tkinter unavailable for GUI setup: %s", exc)
        return None

    _last_gui_unavailable = False
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        normalized_preset = preset_url.strip().rstrip("/")
        parsed_token: str | None = None
        if existing is None and normalized_preset:
            server_url = normalized_preset
        else:
            default_url = existing.server_url if existing else "modsync://"
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

        if existing is not None:
            initial_dir = _existing_minecraft_dir(existing)
        else:
            detected = detect_minecraft_dirs()
            initial_dir = str(detected[0]) if detected else str(Path.home())

        if not messagebox.askokcancel(
            "ModSync Setup",
            "Select your Minecraft folder on the next dialog (the 'mods' folder inside it will be synced).",
            parent=root,
        ):
            return None
        selected_dir = filedialog.askdirectory(
            title="Select Minecraft folder",
            initialdir=initial_dir,
            parent=root,
        )
        if not selected_dir:
            return None

        return _build_prompted_config(
            server_url=server_url,
            selected_folder=selected_dir,
            parsed_token=parsed_token,
            existing=existing,
            preset_token=preset_token,
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
    global _last_gui_unavailable
    _last_gui_unavailable = False
    cfg = prompt_config_gui(existing, preset_url=preset_url, preset_token=preset_token)
    if cfg is not None:
        return cfg
    if _last_gui_unavailable:
        if _is_interactive_tty():
            return prompt_config_cli(existing, preset_url=preset_url, preset_token=preset_token)
        raise SystemExit("Setup cancelled: GUI unavailable and stdin is not a TTY.")
    logger.info("Setup cancelled.")
    raise SystemExit(0)


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
    try:
        invite_url, invite_token = parse_server_input(invite_uri)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
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

    if preset_url and args.mods_dir:
        cfg = Config(
            server_url=preset_url.rstrip("/"),
            mods_dir=str(args.mods_dir),
            client_token=(
                args.token
                if args.token is not None
                else (existing.client_token if existing else "")
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

    if args.headless or args.sync_once or getattr(args, "install_recommended", False):
        if not _is_interactive_tty():
            raise SystemExit(
                "No config found. Pass an invite URI or --server-url and --mods-dir (or run with --setup)."
            )
        cfg = prompt_config_cli(None, preset_url=preset_url, preset_token=preset_token)
        save_config(cfg, cfg_path)
        return cfg

    cfg = setup_gui_or_cli(None, preset_url=preset_url, preset_token=preset_token)
    save_config(cfg, cfg_path)
    return cfg
