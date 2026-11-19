"""Desktop integration utilities: tray badge icons, Windows autostart, and folder opener."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from .syncer import SyncStatus

ICON_SIZE = 64
ICON_BG_COLOR = "#1f2937"
DEFAULT_STATUS_COLOR = "#6b7280"

STATUS_COLORS: dict[SyncStatus, str] = {
    SyncStatus.IDLE: DEFAULT_STATUS_COLOR,
    SyncStatus.SYNCING: "#3b82f6",
    SyncStatus.SYNCED: "#22c55e",
    SyncStatus.STAGED_WAITING_MC: "#f59e0b",
    SyncStatus.ERROR: "#ef4444",
}


def make_badge_icon(color: str) -> Image.Image:
    """Generate a crisp 64x64 rounded square icon with a status indicator."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=ICON_BG_COLOR, outline=color, width=4)
    draw.ellipse((18, 18, 46, 46), fill=color)
    return img


def _startup_script_path() -> Path | None:
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "ModSync.bat"
    )


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


def open_folder(path: Path) -> None:
    """Open a local directory in the system file manager."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
