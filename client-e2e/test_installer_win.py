"""Windows-only E2E tests for ModSync-Setup.exe Inno Setup installer and uninstaller lifecycle."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import EXIT_CODE_SUCCESS, TIMEOUT_SYNC, ModSyncCli
from helpers.fixtures import BinaryPayloads
from helpers.polling import terminate_process_tree, wait_until
from helpers.win_installer import WIN_INSTALLER_EXE_NAME, WindowsInstallerHarness

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows Inno Setup installer E2E tests only run on Windows",
)


def test_windows_installer_and_uninstaller_full_lifecycle(
    modsync_installer: Path | None,
    api_server: ModSyncTestServer,
    client_cli: ModSyncCli,
) -> None:
    """Verify silent install to {localappdata}\\Programs\\ModSync, registry keys, running-process lock, and full uninstall cleanup."""
    if modsync_installer is None or not modsync_installer.is_file():
        pytest.fail(f"{WIN_INSTALLER_EXE_NAME} not found (set MODSYNC_INSTALLER or build installer)")

    installer = WindowsInstallerHarness(installer_path=modsync_installer)
    installer.uninstall_if_present()

    try:
        install_res = installer.install_silent(autostart=True)
        assert install_res.returncode == EXIT_CODE_SUCCESS, f"Installer failed: {install_res.stderr}"
        installer.assert_installed_and_registered()

        installer.seed_leftover_artifacts(
            BinaryPayloads.LEFTOVER_OLD_BINARY,
            BinaryPayloads.LEFTOVER_NEW_BINARY,
        )

        running_proc = client_cli.start_headless(
            server_url=api_server.server_url,
            token=api_server.client_token,
            binary=installer.installed_exe,
        )
        try:
            wait_until(
                lambda: api_server.connected_clients() >= 1,
                timeout=TIMEOUT_SYNC,
                description="installed ModSync.exe connected to modsync_api",
            )

            blocked_rc = installer.uninstall_silent()
            assert blocked_rc != EXIT_CODE_SUCCESS, (
                "Expected uninstaller to exit non-zero while ModSync.exe is running"
            )
            assert running_proc.poll() is None, (
                "Running ModSync.exe must not be killed by blocked uninstall"
            )
            installer.assert_protocol_registration_intact()
        finally:
            terminate_process_tree(running_proc)

        clean_rc = installer.uninstall_silent()
        assert clean_rc == EXIT_CODE_SUCCESS, (
            f"Expected uninstaller exit code {EXIT_CODE_SUCCESS} after stopping ModSync.exe, got {clean_rc}"
        )

        installer.wait_for_complete_removal()
    finally:
        installer.cleanup()
