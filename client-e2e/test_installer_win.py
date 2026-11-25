"""Windows-only E2E tests for ModSync-Setup.exe Inno Setup installer and uninstaller lifecycle."""

from __future__ import annotations

import os
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
from helpers.dialog_driver import is_ci_environment
from helpers.env import IsolatedClientEnv, ProcessSpawner
from helpers.fixtures import BinaryPayloads
from helpers.polling import FatalPollError, terminate_process_tree, wait_until
from helpers.win_installer import WIN_INSTALLER_EXE_NAME, WindowsInstallerHarness

ENV_ALLOW_HOST_INSTALLER = "MODSYNC_E2E_ALLOW_HOST_INSTALLER"
OPT_RUN_WIN_INSTALLER = "--run-win-installer"
TRUTHY_VALUES = frozenset({"1", "true", "yes"})

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows Inno Setup installer E2E tests only run on Windows",
)


@pytest.fixture(autouse=True)
def _require_host_installer_opt_in(request: pytest.FixtureRequest) -> None:
    """Gate host-mutating Windows installer tests behind explicit opt-in or CI flag."""
    cli_enabled = bool(request.config.getoption(OPT_RUN_WIN_INSTALLER))
    env_enabled = os.environ.get(ENV_ALLOW_HOST_INSTALLER, "").strip().lower() in TRUTHY_VALUES
    if not (cli_enabled or env_enabled):
        pytest.skip(
            f"Windows installer E2E mutates host %LOCALAPPDATA%/HKCU; pass {OPT_RUN_WIN_INSTALLER} "
            f"or set {ENV_ALLOW_HOST_INSTALLER}=1 to run."
        )


@pytest.fixture
def installed_modsync(
    modsync_installer: Path | None,
    tmp_path: Path,
) -> Iterator[WindowsInstallerHarness]:
    """Silently install ModSync-Setup.exe into {localappdata}\\Programs\\ModSync and clean up."""
    if modsync_installer is None or not modsync_installer.is_file():
        pytest.fail(f"{WIN_INSTALLER_EXE_NAME} not found (set MODSYNC_INSTALLER or build installer)")

    installer = WindowsInstallerHarness(installer_path=modsync_installer)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not is_ci_environment() and (
        installer.install_dir.exists() or installer.uninstaller_exe.is_file()
    ):
        pytest.fail(
            f"Refusing to overwrite pre-existing ModSync installation at {installer.install_dir} "
            "outside CI. Uninstall it manually before running host installer tests."
        )

    installer.startup_script.unlink(missing_ok=True)
    installer.uninstall_if_present(
        assert_clean=True,
        log_path=logs_dir / "pre_uninstall.log",
    )

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
    tmp_path: Path,
) -> None:
    """Verify silent install registration and full uninstaller cleanup of leftovers and registry keys."""
    installed_modsync.assert_installed_and_registered()
    installed_modsync.seed_leftover_artifacts(
        BinaryPayloads.LEFTOVER_OLD_BINARY,
        BinaryPayloads.LEFTOVER_NEW_BINARY,
        include_startup_script=True,
    )

    clean_log = tmp_path / "logs" / "clean_uninstall.log"
    clean_rc = installed_modsync.uninstall_silent(log_path=clean_log)
    assert clean_rc == EXIT_CODE_SUCCESS, (
        f"Expected uninstaller exit code {EXIT_CODE_SUCCESS}, got {clean_rc}; "
        f"log={installed_modsync.read_last_uninstall_log()!r}"
    )
    installed_modsync.wait_for_complete_removal()


def test_windows_uninstaller_blocks_while_modsync_is_running(
    installed_modsync: WindowsInstallerHarness,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
    process_spawner: ProcessSpawner,
    tmp_path: Path,
) -> None:
    """Verify uninstaller refuses to remove ModSync while the installed ModSync.exe is running."""
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
        log_name="installed_modsync_running",
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

        # Seed leftovers after ModSync.exe startup so cleanup_old_binary() doesn't delete .old itself.
        installed_modsync.seed_leftover_artifacts(
            BinaryPayloads.LEFTOVER_OLD_BINARY,
            BinaryPayloads.LEFTOVER_NEW_BINARY,
            include_startup_script=True,
        )

        blocked_log = tmp_path / "logs" / "blocked_uninstall.log"
        blocked_rc = installed_modsync.uninstall_silent(log_path=blocked_log)
        assert blocked_rc != EXIT_CODE_SUCCESS, (
            "Expected uninstaller to exit non-zero while ModSync.exe is running; "
            f"log={installed_modsync.read_last_uninstall_log()!r}"
        )
        assert running_proc.poll() is None, (
            f"Running ModSync.exe must not be killed by blocked uninstall (rc={running_proc.returncode})"
        )
        installed_modsync.assert_installation_intact()
    finally:
        terminate_process_tree(running_proc)
