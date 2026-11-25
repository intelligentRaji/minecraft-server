"""Cross-platform GUI dialog and system-tray automation drivers for ModSync E2E."""

from __future__ import annotations

import sys
from pathlib import Path

from .base import TIMEOUT_DIALOG, BaseDialogDriver, DialogWindow, is_ci_environment
from .win32 import Win32DialogDriver
from .x11 import X11DialogDriver

__all__ = [
    "TIMEOUT_DIALOG",
    "BaseDialogDriver",
    "DialogWindow",
    "Win32DialogDriver",
    "X11DialogDriver",
    "create_dialog_driver",
    "is_ci_environment",
]


def create_dialog_driver(
    *,
    use_live_display: bool = False,
    log_dir: Path | None = None,
) -> BaseDialogDriver:
    """Create and initialize the platform-appropriate GUI dialog driver."""
    if sys.platform == "win32":
        return Win32DialogDriver()
    return X11DialogDriver.start(use_live_display=use_live_display, log_dir=log_dir)
