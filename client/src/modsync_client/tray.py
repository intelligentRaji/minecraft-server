"""System tray UI controller for ModSync."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

import pystray

from . import __version__
from .config import Config, save_config
from .desktop import (
    DEFAULT_STATUS_COLOR,
    STATUS_COLORS,
    is_windows_autostart_enabled,
    make_badge_icon,
    open_folder,
    set_windows_autostart,
)
from .onboarding import prompt_config_gui
from .syncer import SyncResult, SyncStatus
from .updater import (
    UpdateInfo,
    check_for_update,
    download_and_apply_update,
    relaunch_executable,
)
from .ws_client import ModSyncService

logger = logging.getLogger("modsync_client.tray")

MAX_TRAY_TITLE_LENGTH = 120
BG_THREAD_JOIN_TIMEOUT_SECONDS = 5

__all__ = [
    "ModSyncTrayApp",
    "STATUS_COLORS",
    "is_windows_autostart_enabled",
    "make_badge_icon",
    "prompt_config_gui",
    "set_windows_autostart",
]


class ModSyncTrayApp:
    """Connects pystray UI with ModSyncService background asyncio loop."""

    def __init__(self, config: Config, config_path: Path) -> None:
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
            pystray.MenuItem("Install Recommended Client Mods", self._on_install_recommended),
            pystray.MenuItem("Open Mods Folder", self._on_open_folder),
            pystray.MenuItem("Configure...", self._on_configure),
            pystray.MenuItem("Check for Updates...", self._on_check_updates),
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

    def _notify_if_changed(self, message: str, result: SyncResult | None) -> None:
        if result is None or not (result.added or result.updated or result.removed):
            return
        notify_key = f"{result.status.value}:{result.version}"
        if self._last_notified_version == notify_key:
            return
        self._last_notified_version = notify_key
        try:
            self.icon.notify(message, "ModSync")
        except Exception:
            pass

    def _on_status_update(
        self,
        status: SyncStatus,
        message: str,
        result: SyncResult | None,
    ) -> None:
        self.status = status
        self.status_text = message
        self.icon.icon = make_badge_icon(STATUS_COLORS.get(status, DEFAULT_STATUS_COLOR))
        self.icon.title = f"ModSync — {message}"[:MAX_TRAY_TITLE_LENGTH]
        self.icon.update_menu()
        self._notify_if_changed(message, result)

    def _on_sync_now(self, _icon: Any, _item: Any) -> None:
        self.service.request_sync()

    def _on_install_recommended(self, _icon: Any, _item: Any) -> None:
        self.service.request_install_recommended()

    def _on_open_folder(self, _icon: Any, _item: Any) -> None:
        open_folder(self.config.mods_path)

    def _on_configure(self, _icon: Any, _item: Any) -> None:
        updated = prompt_config_gui(self.config)
        if updated is not None:
            self.config = updated
            save_config(updated, self.config_path)
            self.service.reconfigure(updated)

    def _on_toggle_autostart(self, _icon: Any, _item: Any) -> None:
        set_windows_autostart(not is_windows_autostart_enabled())
        self.icon.update_menu()

    @staticmethod
    def _prompt_update_dialog(update: UpdateInfo) -> bool:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            action = (
                "Download and install now?"
                if getattr(sys, "frozen", False)
                else "Open the release page?"
            )
            return messagebox.askyesno(
                "ModSync Update Available",
                f"ModSync v{update.version} is available (you have v{__version__}).\n\n{action}",
                parent=root,
            )
        finally:
            root.destroy()

    @staticmethod
    def _show_info_dialog(title: str, message: str, *, error: bool = False) -> None:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if error:
                messagebox.showerror(title, message, parent=root)
            else:
                messagebox.showinfo(title, message, parent=root)
        finally:
            root.destroy()

    def _run_update_check(self, *, interactive: bool) -> None:
        try:
            update = check_for_update(__version__)
        except Exception as exc:
            logger.warning("Update check failed: %s", exc)
            if interactive:
                self._show_info_dialog(
                    "ModSync Update Check",
                    f"Could not check for updates:\n{exc}",
                    error=True,
                )
            return

        if update is None:
            if interactive:
                self._show_info_dialog(
                    "ModSync Update Check",
                    f"You are running the latest version (v{__version__}).",
                )
            return

        if not interactive:
            try:
                self.icon.notify(
                    f"ModSync v{update.version} is available. Click 'Check for Updates...' to install.",
                    "ModSync Update",
                )
            except Exception:
                pass
            return

        if not self._prompt_update_dialog(update):
            return

        if not getattr(sys, "frozen", False):
            if update.html_url:
                webbrowser.open(update.html_url)
            return

        try:
            download_and_apply_update(update)
        except Exception as exc:
            logger.error("Failed to apply update: %s", exc)
            self._show_info_dialog(
                "ModSync Update Failed",
                f"Could not install update v{update.version}:\n{exc}",
                error=True,
            )
            return

        relaunch_executable()
        self.service.stop()
        self.icon.stop()

    def _on_check_updates(self, _icon: Any, _item: Any) -> None:
        threading.Thread(
            target=self._run_update_check,
            kwargs={"interactive": True},
            daemon=True,
            name="modsync-update-check",
        ).start()

    def _on_quit(self, _icon: Any, _item: Any) -> None:
        self.service.stop()
        self.icon.stop()

    def run(self) -> None:
        worker = threading.Thread(
            target=lambda: asyncio.run(self.service.run()),
            daemon=True,
            name="modsync-bg",
        )
        worker.start()
        threading.Thread(
            target=self._run_update_check,
            kwargs={"interactive": False},
            daemon=True,
            name="modsync-startup-update-check",
        ).start()
        try:
            self.icon.run()
        finally:
            self.service.stop()
            worker.join(timeout=BG_THREAD_JOIN_TIMEOUT_SECONDS)
