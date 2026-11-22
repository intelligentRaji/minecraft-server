"""Screen-object over ModSync GUI onboarding wizard dialogs."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest

from .client_cli import EXIT_CODE_SUCCESS, TRACEBACK_MARKER, ModSyncCli
from .dialog_driver import BaseDialogDriver, DialogWindow, is_ci_environment
from .fixtures import PersistedConfigSnapshot
from .polling import terminate_process_tree

T = TypeVar("T")

DIALOG_TITLE_SETUP = "ModSync Setup"
DIALOG_TITLE_INVALID_INVITE = "Invalid Invite Link"
DIALOG_TITLE_SELECT_FOLDER = "Select Minecraft folder"

TIMEOUT_DIALOG = 30.0
TIMEOUT_COMPLETION = 45.0


@dataclass
class OnboardingWizard:
    """Screen-object automating ModSync's 3-step GUI onboarding wizard."""

    cli: ModSyncCli
    driver: BaseDialogDriver
    proc: subprocess.Popen[str]
    _seen_handles: set[int] = field(default_factory=set)

    @classmethod
    def launch(cls, cli: ModSyncCli, driver: BaseDialogDriver) -> OnboardingWizard:
        """Verify tkinter support and launch the GUI onboarding wizard process."""
        env = driver.prepare_env(cli.isolated_env.env)
        if not cli.supports_tkinter(env=env):
            msg = (
                f"Binary {cli.binary} was built without tkinter support "
                "(install python3-tk before PyInstaller build)"
            )
            if is_ci_environment():
                pytest.fail(msg)
            pytest.skip(msg)

        proc = cli.launch_gui_setup(dialog_driver=driver)
        return cls(cli=cli, driver=driver, proc=proc)

    def _diagnostic_context(self) -> str:
        rc = self.proc.poll()
        stderr_detail = ""
        if rc is not None and self.proc.stderr is not None:
            try:
                stderr_detail = self.proc.stderr.read().strip()
            except (OSError, ValueError):
                stderr_detail = "<unavailable>"
        try:
            visible = [(w.handle, w.title) for w in self.driver.list_visible_windows(self.proc.pid)]
        except Exception as exc:
            visible = [f"<error: {exc}>"]
        return f"proc_rc={rc!r}, visible_windows={visible!r}, stderr={stderr_detail!r}"

    def _run_step(self, action_name: str, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except Exception as exc:
            raise RuntimeError(f"{action_name} failed ({exc}); {self._diagnostic_context()}") from exc

    def _wait_next_dialog(self, title: str) -> DialogWindow:
        win = self._run_step(
            f"wait_for_dialog({title!r})",
            lambda: self.driver.wait_for_dialog(
                self.proc.pid,
                title,
                exclude_handles=self._seen_handles,
                timeout=TIMEOUT_DIALOG,
            ),
        )
        self._seen_handles.add(win.handle)
        return win

    def submit_invite(self, invite_url: str) -> None:
        """Enter invite_url into the Step 1 setup dialog and accept."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_SETUP)
        self._run_step(
            "enter_text_and_accept(invite)",
            lambda: self.driver.enter_text_and_accept(dialog, invite_url),
        )

    def cancel_invite_step(self) -> None:
        """Cancel or close the Step 1 invite dialog."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_SETUP)
        self._run_step(
            "cancel_or_close_dialog(invite)",
            lambda: self.driver.cancel_or_close_dialog(dialog),
        )

    def acknowledge_invalid_invite_error(self) -> None:
        """Dismiss the 'Invalid Invite Link' error dialog."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_INVALID_INVITE)
        self._run_step(
            "accept_dialog(invalid_invite)",
            lambda: self.driver.accept_dialog(dialog),
        )

    def confirm_folder_notice(self) -> None:
        """Accept the Step 2 pre-folder confirmation dialog."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_SETUP)
        self._run_step(
            "accept_dialog(folder_notice)",
            lambda: self.driver.accept_dialog(dialog),
        )

    def cancel_folder_notice(self) -> None:
        """Cancel or close the Step 2 pre-folder confirmation dialog."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_SETUP)
        self._run_step(
            "cancel_or_close_dialog(folder_notice)",
            lambda: self.driver.cancel_or_close_dialog(dialog),
        )

    def accept_folder_picker(self) -> None:
        """Accept the Step 3 'Select Minecraft folder' directory picker."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_SELECT_FOLDER)
        self._run_step(
            "accept_dialog(folder_picker)",
            lambda: self.driver.accept_dialog(dialog),
        )

    def cancel_folder_picker(self) -> None:
        """Cancel or close the Step 3 'Select Minecraft folder' directory picker."""
        dialog = self._wait_next_dialog(DIALOG_TITLE_SELECT_FOLDER)
        self._run_step(
            "cancel_or_close_dialog(folder_picker)",
            lambda: self.driver.cancel_or_close_dialog(dialog),
        )

    def assert_cancelled_cleanly(self) -> None:
        """Assert the wizard exited 0 without traceback or persisting config.json."""
        _, stderr = self.proc.communicate(timeout=TIMEOUT_DIALOG)
        rc = self.proc.returncode
        assert rc == EXIT_CODE_SUCCESS, (
            f"Expected exit code {EXIT_CODE_SUCCESS} on cancellation, got {rc}: {stderr}"
        )
        assert TRACEBACK_MARKER not in stderr
        assert not self.cli.isolated_env.config_path.exists()

    def assert_completed_successfully(self) -> PersistedConfigSnapshot:
        """Assert the wizard exited 0, wrote config.json, and return its snapshot."""
        _, stderr = self.proc.communicate(timeout=TIMEOUT_COMPLETION)
        rc = self.proc.returncode
        assert rc == EXIT_CODE_SUCCESS, (
            f"Expected exit code {EXIT_CODE_SUCCESS} on completion, got {rc}: {stderr}"
        )
        assert TRACEBACK_MARKER not in stderr
        cfg_path = self.cli.isolated_env.config_path
        assert cfg_path.is_file()
        return PersistedConfigSnapshot.from_file(cfg_path)

    def close(self) -> None:
        """Terminate the wizard process tree if it is still running."""
        if self.proc.poll() is None:
            terminate_process_tree(self.proc)
        elif self.proc.stderr is not None:
            try:
                self.proc.stderr.close()
            except (OSError, ValueError):
                pass

    def __enter__(self) -> OnboardingWizard:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
