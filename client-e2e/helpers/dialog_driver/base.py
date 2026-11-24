"""Abstract dialog driver contract and shared window discovery logic."""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from pathlib import Path

from ..polling import wait_until

ENV_CI = "CI"
CI_TRUTHY_VALUES = frozenset({"1", "true", "yes"})

WIN32_DIALOG_CLASS = "#32770"

POLL_INTERVAL_FAST = 0.05
POLL_INTERVAL_DEFAULT = 0.1
KEY_EVENT_DELAY = 0.01
DIALOG_CLOSE_DELAY = 0.15
TIMEOUT_PROC_WAIT = 20.0
TIMEOUT_DIALOG = 30.0


def is_ci_environment() -> bool:
    """Return True when executing inside a CI environment."""
    return os.environ.get(ENV_CI, "").strip().lower() in CI_TRUTHY_VALUES


@dataclass(frozen=True)
class DialogWindow:
    """Represents a discovered OS dialog window handle/ID and metadata."""

    handle: int
    title: str
    class_name: str = ""


class BaseDialogDriver(abc.ABC):
    """Platform-agnostic dialog driver interface for ModSync onboarding and tray E2E tests."""

    has_system_tray: bool = True

    def prepare_env(self, env: dict[str, str]) -> dict[str, str]:
        """Return an environment mapping configured for this GUI driver."""
        return dict(env)

    def wait_for_dialog(
        self,
        root_pid: int,
        title_substring: str,
        *,
        exclude_handles: set[int] | None = None,
        class_name: str | None = None,
        timeout: float = TIMEOUT_DIALOG,
    ) -> DialogWindow:
        """Poll visible windows belonging to root_pid until one matches title/class."""
        excluded = exclude_handles or set()
        needle = title_substring.lower()

        def _find() -> DialogWindow | None:
            for win in self.list_visible_windows(root_pid):
                if win.handle in excluded:
                    continue
                if class_name and win.class_name != class_name:
                    continue
                if needle in win.title.lower():
                    return win
            return None

        return wait_until(
            _find,
            timeout=timeout,
            interval=POLL_INTERVAL_DEFAULT,
            description=f"dialog matching {title_substring!r} (class={class_name})",
        )

    @abc.abstractmethod
    def list_visible_windows(self, root_pid: int) -> list[DialogWindow]:
        """List currently visible top-level windows owned by root_pid's process tree."""

    @abc.abstractmethod
    def enter_text_and_accept(self, window: DialogWindow, text: str) -> None:
        """Focus a prompt dialog, replace any pre-filled text, type text, and accept."""

    @abc.abstractmethod
    def accept_dialog(self, window: DialogWindow) -> None:
        """Accept or confirm a visible dialog."""

    @abc.abstractmethod
    def cancel_or_close_dialog(self, window: DialogWindow) -> None:
        """Cancel or close a visible dialog."""

    @abc.abstractmethod
    def select_folder(self, window: DialogWindow, folder_path: Path) -> None:
        """Navigate/type folder_path into a directory-picker dialog and confirm selection."""

    @abc.abstractmethod
    def capture_screenshot(self, output_path: Path) -> Path | None:
        """Capture the current GUI display to output_path as PNG, or return None if unavailable."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release any managed display/WM/tray resources."""
