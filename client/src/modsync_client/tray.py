"""System tray UI and first-run GUI onboarding for ModSync."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

from .config import AppConfig, DEFAULT_SERVER_URL, detect_mods_dirs, save_config
from .syncer import SyncResult, SyncStatus
from .ws_client import ModSyncService

logger = logging.getLogger("modsync_client.tray")

STATUS_COLORS: dict[SyncStatus, str] = {
    SyncStatus.IDLE: "#6b7280",
    SyncStatus.SYNCING: "#3b82f6",
    SyncStatus.SYNCED: "#22c55e",
    SyncStatus.STAGED_WAITING_MC: "#f59e0b",
    SyncStatus.ERROR: "#ef4444",
}


def make_badge_icon(color: str) -> Image.Image:
    """Generate a crisp 64x64 rounded square icon with a status indicator."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#1f2937", outline=color, width=4)
    draw.ellipse((18, 18, 46, 46), fill=color)
    return img


def _startup_script_path() -> Path | None:
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "ModSync.bat"


def is_windows_autostart_enabled() -> bool:
    script = _startup_script_path()
    return script is not None and script.is_file()


def set_windows_autostart(enabled: bool) -> bool:
    script = _startup_script_path()
    if script is None:
        return False
    if enabled:
        script.parent.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            cmd = f'start "" "{sys.executable}"'
        else:
            cmd = f'start "" "{sys.executable}" -m modsync_client.main'
        script.write_text(f"@echo off\n{cmd}\n", encoding="utf-8")
        return True
    script.unlink(missing_ok=True)
    return False


def prompt_config_gui(existing: AppConfig | None = None) -> AppConfig | None:
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

        return AppConfig(
            server_url=server_url.strip().rstrip("/"),
            mods_dir=selected_dir,
            client_token=existing.client_token if existing else "",
            poll_fallback_seconds=existing.poll_fallback_seconds if existing else 300,
        )
    finally:
        root.destroy()


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ModSyncTrayApp:
    """Connects pystray UI with ModSyncService background asyncio loop."""

    def __init__(self, config: AppConfig, config_path: Path) -> None:
        self.config = config
        self.config_path = config_path
        self.status = SyncStatus.IDLE
        self.status_text = "Starting..."
        self._last_notified_version: str | None = None

        self.service = ModSyncService(config, on_status=self._on_status_update)
        self.icon = pystray.Icon(
            "ModSync",
            make_badge_icon(STATUS_COLORS[SyncStatus.IDLE]),
            "ModSync",
            menu=self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem(lambda _item: f"Status: {self.status_text}", None, enabled=False),
            pystray.MenuItem("Sync Now", self._on_sync_now),
            pystray.MenuItem("Open Mods Folder", self._on_open_folder),
            pystray.MenuItem("Configure...", self._on_configure),
        ]
        if sys.platform == "win32":
            items.append(
                pystray.MenuItem(
                    "Start with Windows",
                    self._on_toggle_autostart,
                    checked=lambda _item: is_windows_autostart_enabled(),
                )
            )
        items.append(pystray.MenuItem("Quit", self._on_quit))
        return pystray.Menu(*items)

    def _on_status_update(self, status: SyncStatus, message: str, result: SyncResult | None) -> None:
        self.status = status
        self.status_text = message
        self.icon.icon = make_badge_icon(STATUS_COLORS.get(status, "#6b7280"))
        self.icon.title = f"ModSync — {message}"[:120]
        self.icon.update_menu()

        if result is not None and (result.added or result.updated or result.removed):
            notify_key = f"{result.status.value}:{result.version}"
            if self._last_notified_version != notify_key:
                self._last_notified_version = notify_key
                try:
                    self.icon.notify(message, "ModSync")
                except Exception:
                    pass

    def _on_sync_now(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.service.request_sync()

    def _on_open_folder(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        _open_folder(self.config.mods_path)

    def _on_configure(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        updated = prompt_config_gui(self.config)
        if updated is not None:
            self.config = updated
            save_config(updated, self.config_path)
            self.service.reconfigure(updated)

    def _on_toggle_autostart(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        set_windows_autostart(not is_windows_autostart_enabled())
        self.icon.update_menu()

    def _on_quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.service.stop()
        self.icon.stop()

    def run(self) -> None:
        def _bg_runner() -> None:
            asyncio.run(self.service.run())

        worker = threading.Thread(target=_bg_runner, daemon=True, name="modsync-bg")
        worker.start()
        try:
            self.icon.run()
        finally:
            self.service.stop()
            worker.join(timeout=5)
