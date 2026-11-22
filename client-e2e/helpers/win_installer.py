"""Windows Inno Setup installer/uninstaller and HKCU registry verification harness."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from .polling import (
    get_process_tree_pids,
    run_with_tree_timeout,
    terminate_process_tree,
    wait_until,
)

APP_DISPLAY_NAME = "ModSync"
WIN_APP_EXE_NAME = "ModSync.exe"
WIN_INSTALLER_EXE_NAME = "ModSync-Setup.exe"
WIN_UNINSTALLER_EXE_NAME = "unins000.exe"
WIN_STARTUP_SCRIPT_NAME = "ModSync.bat"
OLD_BINARY_SUFFIX = ".old"
NEW_BINARY_PREFIX = "."
NEW_BINARY_SUFFIX = ".new"

ENV_APPDATA = "APPDATA"
ENV_LOCALAPPDATA = "LOCALAPPDATA"

INNO_SILENT_FLAGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
INNO_AUTOSTART_TASK_FLAG = "/TASKS=autostart"
INNO_DIR_FLAG_PREFIX = "/DIR="

REG_PROTOCOL_KEY = r"Software\Classes\modsync"
REG_PROTOCOL_COMMAND_KEY = r"Software\Classes\modsync\shell\open\command"
REG_PROTOCOL_VALUE_DATA = "URL:ModSync Invite Protocol"
REG_PROTOCOL_MARKER_NAME = "URL Protocol"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_RUN_VALUE_NAME = "ModSync"

EXIT_CODE_SUCCESS = 0
POLL_INTERVAL_FAST = 0.05
POLL_INTERVAL_DEFAULT = 0.1
TIMEOUT_CLI = 45.0
TIMEOUT_INSTALLER = 90.0
TIMEOUT_SERVER_START = 30.0


def read_hkcu_value(subkey: str, value_name: str = "") -> str | None:
    """Read a string value from HKCU, returning None if the key or value does not exist."""
    if sys.platform != "win32":
        raise RuntimeError("winreg is only available on Windows")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, value_name)
            return str(val)
    except FileNotFoundError:
        return None


def hkcu_key_exists(subkey: str) -> bool:
    """Return True if an HKCU registry key exists."""
    if sys.platform != "win32":
        raise RuntimeError("winreg is only available on Windows")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ):
            return True
    except FileNotFoundError:
        return False


def run_inno_uninstaller(unins_exe: Path, *, timeout: float = TIMEOUT_CLI) -> int:
    """Run an Inno Setup unins000.exe silently and wait for its phase-2 %TEMP% child process."""
    proc = subprocess.Popen(
        [str(unins_exe), *INNO_SILENT_FLAGS],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tracked_procs: dict[int, psutil.Process] = {}
    completed = False
    try:
        try:
            tracked_procs[proc.pid] = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            pass

        deadline = time.monotonic() + timeout
        # Poll closely while Phase 1 spawns the Phase 2 _iu*.tmp child in %TEMP%
        while proc.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out after {timeout:.1f}s waiting for {unins_exe.name} phase 1"
                )
            for pid in list(get_process_tree_pids(proc.pid)):
                if pid not in tracked_procs:
                    try:
                        tracked_procs[pid] = psutil.Process(pid)
                    except psutil.NoSuchProcess:
                        pass
            try:
                proc.wait(timeout=min(POLL_INTERVAL_FAST, remaining))
            except subprocess.TimeoutExpired:
                pass

        phase1_rc = proc.returncode if proc.returncode is not None else EXIT_CODE_SUCCESS
        children = [p for pid, p in tracked_procs.items() if pid != proc.pid]
        if not children:
            completed = True
            return phase1_rc

        remaining = max(0.0, deadline - time.monotonic())
        gone, alive = psutil.wait_procs(children, timeout=remaining)
        if alive:
            for p in alive:
                terminate_process_tree(p.pid)
            raise TimeoutError(
                f"Inno uninstaller Phase 2 timed out after {timeout:.1f}s: {unins_exe}"
            )
        for p in gone:
            rc = getattr(p, "returncode", None)
            if rc not in (None, EXIT_CODE_SUCCESS):
                completed = True
                return int(rc)
        completed = True
        return phase1_rc
    finally:
        if not completed:
            terminate_process_tree(proc)
            for pid in tracked_procs:
                if pid != proc.pid:
                    terminate_process_tree(pid)


def default_install_dir() -> Path:
    """Return the default per-user Inno Setup installation path under %LOCALAPPDATA%."""
    localappdata = os.environ.get(ENV_LOCALAPPDATA) or str(Path.home() / "AppData" / "Local")
    return Path(localappdata) / "Programs" / APP_DISPLAY_NAME


def user_startup_script_path() -> Path:
    """Return the legacy Start Menu Startup ModSync.bat path cleaned up by the uninstaller."""
    appdata = os.environ.get(ENV_APPDATA) or str(Path.home() / "AppData" / "Roaming")
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / WIN_STARTUP_SCRIPT_NAME
    )


@dataclass
class WindowsInstallerHarness:
    """Encapsulates ModSync-Setup.exe install, registry assertions, and uninstaller lifecycle."""

    installer_path: Path
    install_dir: Path = field(default_factory=default_install_dir)
    startup_script: Path = field(default_factory=user_startup_script_path)

    @property
    def installed_exe(self) -> Path:
        return self.install_dir / WIN_APP_EXE_NAME

    @property
    def uninstaller_exe(self) -> Path:
        return self.install_dir / WIN_UNINSTALLER_EXE_NAME

    @property
    def old_leftover_path(self) -> Path:
        return self.install_dir / f"{WIN_APP_EXE_NAME}{OLD_BINARY_SUFFIX}"

    @property
    def new_leftover_path(self) -> Path:
        return self.install_dir / f"{NEW_BINARY_PREFIX}{WIN_APP_EXE_NAME}{NEW_BINARY_SUFFIX}"

    def install_silent(
        self,
        *,
        autostart: bool = True,
        target_dir: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run ModSync-Setup.exe silently with optional autostart task and target directory."""
        args: list[str] = [str(self.installer_path), *INNO_SILENT_FLAGS]
        if autostart:
            args.append(INNO_AUTOSTART_TASK_FLAG)
        if target_dir is not None:
            args.append(f"{INNO_DIR_FLAG_PREFIX}{target_dir}")
        return run_with_tree_timeout(
            args,
            timeout=TIMEOUT_INSTALLER,
        )

    def uninstall_silent(self) -> int:
        """Run the installed unins000.exe silently and return its exit code."""
        return run_inno_uninstaller(self.uninstaller_exe)

    def uninstall_if_present(self, *, assert_clean: bool = False) -> None:
        """Cleanly remove an existing installation if unins000.exe is present."""
        if self.uninstaller_exe.is_file():
            rc = self.uninstall_silent()
            if assert_clean and rc != EXIT_CODE_SUCCESS:
                raise AssertionError(
                    f"Pre-existing installation uninstall failed with exit code {rc}: "
                    f"{self.uninstaller_exe}"
                )

    def assert_installed_and_registered(self) -> None:
        """Assert binary, uninstaller, protocol handler, and autostart registry keys exist."""
        assert self.installed_exe.is_file(), f"Expected installed binary at {self.installed_exe}"
        assert self.uninstaller_exe.is_file(), f"Expected uninstaller at {self.uninstaller_exe}"

        assert hkcu_key_exists(REG_PROTOCOL_KEY), (
            f"Expected HKCU protocol registry key {REG_PROTOCOL_KEY!r} to exist"
        )
        protocol_data = read_hkcu_value(REG_PROTOCOL_KEY, "")
        assert protocol_data == REG_PROTOCOL_VALUE_DATA, (
            f"Expected HKCU {REG_PROTOCOL_KEY!r} default value {REG_PROTOCOL_VALUE_DATA!r}, "
            f"got {protocol_data!r}"
        )
        marker_val = read_hkcu_value(REG_PROTOCOL_KEY, REG_PROTOCOL_MARKER_NAME)
        assert marker_val == "", (
            f"Expected HKCU {REG_PROTOCOL_KEY!r}\\{REG_PROTOCOL_MARKER_NAME!r} == '', "
            f"got {marker_val!r}"
        )
        expected_cmd = f'"{self.installed_exe}" "%1"'
        actual_cmd = read_hkcu_value(REG_PROTOCOL_COMMAND_KEY, "")
        assert actual_cmd == expected_cmd, (
            f"Expected HKCU {REG_PROTOCOL_COMMAND_KEY!r} == {expected_cmd!r}, got {actual_cmd!r}"
        )
        expected_run = f'"{self.installed_exe}"'
        actual_run = read_hkcu_value(REG_RUN_KEY, REG_RUN_VALUE_NAME)
        assert actual_run == expected_run, (
            f"Expected HKCU {REG_RUN_KEY!r}\\{REG_RUN_VALUE_NAME!r} == {expected_run!r}, "
            f"got {actual_run!r}"
        )

    def seed_leftover_artifacts(
        self,
        old_payload: bytes,
        new_payload: bytes,
        *,
        include_startup_script: bool = True,
    ) -> None:
        """Seed simulated updater .old/.new leftovers and optional legacy Startup .bat for uninstall tests."""
        self.old_leftover_path.write_bytes(old_payload)
        self.new_leftover_path.write_bytes(new_payload)
        if include_startup_script:
            self.seed_startup_script()

    def seed_startup_script(self) -> None:
        """Create a legacy Start Menu Startup ModSync.bat script for uninstall cleanup tests."""
        self.startup_script.parent.mkdir(parents=True, exist_ok=True)
        self.startup_script.write_text(
            f'@echo off\nstart "" "{self.installed_exe}"\n',
            encoding="utf-8",
        )

    def assert_installation_intact(self) -> None:
        """Assert installation files, leftovers, startup script, and registry keys survived a blocked uninstall attempt."""
        assert self.installed_exe.is_file(), "ModSync.exe must remain intact after blocked uninstall"
        assert self.uninstaller_exe.is_file(), (
            "unins000.exe must remain intact after blocked uninstall"
        )
        assert self.old_leftover_path.is_file(), (
            "Leftover .old binary must remain intact after blocked uninstall"
        )
        assert self.new_leftover_path.is_file(), (
            "Leftover .new binary must remain intact after blocked uninstall"
        )
        assert self.startup_script.is_file(), (
            "Legacy Startup script must remain intact after blocked uninstall"
        )
        assert hkcu_key_exists(REG_PROTOCOL_KEY), (
            "Protocol registry key must remain intact after blocked uninstall"
        )
        assert read_hkcu_value(REG_RUN_KEY, REG_RUN_VALUE_NAME) == f'"{self.installed_exe}"', (
            "Run autostart registry value must remain intact after blocked uninstall"
        )

    def wait_for_complete_removal(self) -> None:
        """Wait for install_dir removal and verify all files, leftovers, and registry keys are gone."""
        wait_until(
            lambda: not self.install_dir.exists(),
            timeout=TIMEOUT_SERVER_START,
            interval=POLL_INTERVAL_DEFAULT,
            description="complete removal of {localappdata}\\Programs\\ModSync",
        )
        assert not self.installed_exe.exists(), (
            f"Installed executable still exists after uninstall: {self.installed_exe}"
        )
        assert not self.old_leftover_path.exists(), (
            f"Leftover .old binary still exists after uninstall: {self.old_leftover_path}"
        )
        assert not self.new_leftover_path.exists(), (
            f"Leftover .new binary still exists after uninstall: {self.new_leftover_path}"
        )
        assert not self.startup_script.exists(), (
            f"Legacy Startup script still exists after uninstall: {self.startup_script}"
        )
        assert not hkcu_key_exists(REG_PROTOCOL_KEY), (
            f"Protocol registry key still exists after uninstall: {REG_PROTOCOL_KEY!r}"
        )
        remaining_run = read_hkcu_value(REG_RUN_KEY, REG_RUN_VALUE_NAME)
        assert remaining_run is None, (
            f"Autostart registry value still exists after uninstall: {remaining_run!r}"
        )

    def cleanup(self) -> None:
        """Best-effort teardown of startup script and installation after test completion."""
        self.startup_script.unlink(missing_ok=True)
        self.uninstall_if_present()
