"""Windows-only E2E tests for ModSync-Setup.exe Inno Setup installer and uninstaller lifecycle."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import (
    EXIT_CODE_SUCCESS,
    FLAG_CONFIG,
    FLAG_HEADLESS,
    FLAG_MODS_DIR,
    FLAG_SERVER_URL,
    FLAG_TOKEN,
    TIMEOUT_SYNC,
)
from helpers.env import IsolatedClientEnv, ProcessSpawner
from helpers.fixtures import BinaryPayloads
from helpers.polling import FatalPollError, terminate_process_tree, wait_until
from helpers.win_installer import WIN_INSTALLER_EXE_NAME, WindowsInstallerHarness

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows Inno Setup installer E2E tests only run on Windows",
)


@pytest.fixture()
def installed_modsync(modsync_installer: Path | None) -> Iterator[WindowsInstallerHarness]:
    """Silently install ModSync-Setup.exe into {localappdata}\\Programs\\ModSync and clean up."""
    if modsync_installer is None or not modsync_installer.is_file():
        pytest.fail(f"{WIN_INSTALLER_EXE_NAME} not found (set MODSYNC_INSTALLER or build installer)")

    installer = WindowsInstallerHarness(installer_path=modsync_installer)
    installer.startup_script.unlink(missing_ok=True)
    installer.uninstall_if_present(assert_clean=True)

    try:
        install_res = installer.install_silent(autostart=True)
        assert install_res.returncode == EXIT_CODE_SUCCESS, (
            f"Installer failed (rc={install_res.returncode}): "
            f"stdout={install_res.stdout!r}, stderr={install_res.stderr!r}"
        )
        yield installer
    finally:
        installer.cleanup()


def test_windows_silent_install_and_clean_uninstall(
    installed_modsync: WindowsInstallerHarness,
) -> None:
    """Verify silent install registration and full uninstaller cleanup of leftovers and registry keys."""
    installed_modsync.assert_installed_and_registered()
    installed_modsync.seed_leftover_artifacts(
        BinaryPayloads.LEFTOVER_OLD_BINARY,
        BinaryPayloads.LEFTOVER_NEW_BINARY,
        include_startup_script=True,
    )

    clean_rc = installed_modsync.uninstall_silent()
    assert clean_rc == EXIT_CODE_SUCCESS, (
        f"Expected uninstaller exit code {EXIT_CODE_SUCCESS}, got {clean_rc}"
    )
    installed_modsync.wait_for_complete_removal()


def test_windows_uninstaller_blocks_while_modsync_is_running(
    installed_modsync: WindowsInstallerHarness,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
    process_spawner: ProcessSpawner,
) -> None:
    """Verify uninstaller refuses to remove ModSync while the installed ModSync.exe is running."""
    installed_modsync.seed_leftover_artifacts(
        BinaryPayloads.LEFTOVER_OLD_BINARY,
        BinaryPayloads.LEFTOVER_NEW_BINARY,
        include_startup_script=True,
    )

    running_proc = process_spawner(
        [
            installed_modsync.installed_exe,
            FLAG_HEADLESS,
            FLAG_SERVER_URL,
            api_server.server_url,
            FLAG_TOKEN,
            api_server.client_token,
            FLAG_MODS_DIR,
            isolated_env.mods_dir,
            FLAG_CONFIG,
            isolated_env.config_path,
        ],
        env=isolated_env.env,
    )
    try:

        def _connected() -> bool:
            if running_proc.poll() is not None:
                raise FatalPollError(
                    f"Installed ModSync.exe exited early with code {running_proc.returncode}"
                )
            return api_server.connected_clients() >= 1

        wait_until(
            _connected,
            timeout=TIMEOUT_SYNC,
            description="installed ModSync.exe connected to modsync_api",
        )

        blocked_rc = installed_modsync.uninstall_silent()
        assert blocked_rc != EXIT_CODE_SUCCESS, (
            "Expected uninstaller to exit non-zero while ModSync.exe is running"
        )
        assert running_proc.poll() is None, (
            f"Running ModSync.exe must not be killed by blocked uninstall (rc={running_proc.returncode})"
        )
        installed_modsync.assert_installation_intact()
    finally:
        terminate_process_tree(running_proc)
