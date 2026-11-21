"""Shared pytest fixtures for ModSync cross-platform E2E tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from helpers.api_server import ModSyncTestServer, create_started_server
from helpers.client_cli import (
    LINUX_APP_EXE_NAME,
    LINUX_LOCAL_EXE_NAME,
    ModSyncCli,
)
from helpers.dialog_driver import BaseDialogDriver, create_dialog_driver, is_ci_environment
from helpers.env import IsolatedClientEnv, ProcessSpawner, build_local_loopback_env
from helpers.polling import terminate_process_tree, wait_until
from helpers.win_installer import (
    INNO_DIR_FLAG_PREFIX,
    INNO_SILENT_FLAGS,
    TIMEOUT_INSTALLER,
    WIN_APP_EXE_NAME,
    WIN_INSTALLER_EXE_NAME,
    WIN_UNINSTALLER_EXE_NAME,
    run_inno_uninstaller,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIST_DIR = REPO_ROOT / "client" / "dist"

ENV_MODSYNC_BIN = "MODSYNC_BIN"
ENV_MODSYNC_INSTALLER = "MODSYNC_INSTALLER"
ENV_HOME = "HOME"
ENV_USERPROFILE = "USERPROFILE"
ENV_APPDATA = "APPDATA"
ENV_LOCALAPPDATA = "LOCALAPPDATA"
ENV_XDG_CONFIG_HOME = "XDG_CONFIG_HOME"
ENV_MODSYNC_SERVER_URL = "MODSYNC_SERVER_URL"
ENV_MODSYNC_MODS_DIR = "MODSYNC_MODS_DIR"
ENV_MODSYNC_CLIENT_TOKEN = "MODSYNC_CLIENT_TOKEN"
ENV_MODSYNC_UPDATE_REPO = "MODSYNC_UPDATE_REPO"
ENV_MODSYNC_GITHUB_API_URL = "MODSYNC_GITHUB_API_URL"

APP_DISPLAY_NAME = "ModSync"
APP_NAME_LOWER = "modsync"
CONFIG_FILENAME = "config.json"
MINECRAFT_DOT_DIR = ".minecraft"
MODS_SUBDIR_NAME = "mods"
EXIT_CODE_SUCCESS = 0
EXTRACTION_CLEANUP_TIMEOUT_SECONDS = 15.0


@pytest.fixture(scope="session")
def modsync_installer() -> Path | None:
    """Resolve the built Windows Inno Setup installer (ModSync-Setup.exe) when on Windows."""
    env_installer = os.environ.get(ENV_MODSYNC_INSTALLER, "").strip()
    if env_installer:
        path = Path(env_installer).resolve()
        if not path.is_file():
            pytest.fail(f"{ENV_MODSYNC_INSTALLER} points to missing file: {path}")
        return path

    default_installer = CLIENT_DIST_DIR / WIN_INSTALLER_EXE_NAME
    if default_installer.is_file():
        return default_installer
    return None


@pytest.fixture(scope="session")
def modsync_bin(
    tmp_path_factory: pytest.TempPathFactory,
    modsync_installer: Path | None,
) -> Path:
    """Resolve the packaged ModSync client executable under test.

    - On Windows, prefers extracting the installed `ModSync.exe` payload directly from
      `ModSync-Setup.exe` (into an isolated session directory that is immediately
      uninstalled after copying the binary out) unless `MODSYNC_BIN` is explicitly set.
    - On Linux, resolves `MODSYNC_BIN`, `client/dist/ModSync-linux`, or `client/dist/ModSync`.
    """
    env_bin = os.environ.get(ENV_MODSYNC_BIN, "").strip()
    if env_bin:
        path = Path(env_bin).resolve()
        if not path.is_file():
            pytest.fail(f"{ENV_MODSYNC_BIN} points to missing executable: {path}")
        return path

    if sys.platform == "win32":
        if modsync_installer is not None:
            session_dir = tmp_path_factory.mktemp("modsync_extracted")
            install_dir = session_dir / "install"
            bin_copy_dir = session_dir / "bin"
            bin_copy_dir.mkdir(parents=True, exist_ok=True)
            unins_exe = install_dir / WIN_UNINSTALLER_EXE_NAME
            try:
                res = subprocess.run(
                    [
                        str(modsync_installer),
                        *INNO_SILENT_FLAGS,
                        f"{INNO_DIR_FLAG_PREFIX}{install_dir}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_INSTALLER,
                )
                if res.returncode != EXIT_CODE_SUCCESS:
                    pytest.fail(
                        f"Failed to extract {WIN_APP_EXE_NAME} from {modsync_installer} "
                        f"(rc={res.returncode}): {res.stderr}"
                    )
                installed_exe = install_dir / WIN_APP_EXE_NAME
                if not installed_exe.is_file():
                    pytest.fail(f"Expected {installed_exe} after running {modsync_installer}")
                copied_exe = bin_copy_dir / WIN_APP_EXE_NAME
                shutil.copy2(installed_exe, copied_exe)
            finally:
                if unins_exe.is_file():
                    unins_rc = run_inno_uninstaller(unins_exe)
                    assert unins_rc == EXIT_CODE_SUCCESS, (
                        f"Temporary uninstaller {unins_exe} failed with exit code {unins_rc}"
                    )
                    wait_until(
                        lambda: not install_dir.exists(),
                        timeout=EXTRACTION_CLEANUP_TIMEOUT_SECONDS,
                        description="temporary installer extraction cleanup",
                    )
            return copied_exe

        fallback_win = CLIENT_DIST_DIR / WIN_APP_EXE_NAME
        if fallback_win.is_file():
            return fallback_win
        pytest.fail(
            f"Neither {ENV_MODSYNC_INSTALLER} ({CLIENT_DIST_DIR / WIN_INSTALLER_EXE_NAME}) nor "
            f"{ENV_MODSYNC_BIN} ({fallback_win}) was found."
        )

    for candidate in (
        CLIENT_DIST_DIR / LINUX_APP_EXE_NAME,
        CLIENT_DIST_DIR / LINUX_LOCAL_EXE_NAME,
    ):
        if candidate.is_file():
            return candidate

    pytest.fail(
        f"ModSync Linux binary not found in {CLIENT_DIST_DIR / LINUX_APP_EXE_NAME} or "
        f"{CLIENT_DIST_DIR / LINUX_LOCAL_EXE_NAME}. Run `make client-build` or set {ENV_MODSYNC_BIN}."
    )


@pytest.fixture()
def api_server(tmp_path: Path) -> Iterator[ModSyncTestServer]:
    """Start an ephemeral modsync_api server with fixture server-client & client-only mods."""
    server = create_started_server(tmp_path / "modpack")
    try:
        yield server
    finally:
        server.close()


@pytest.fixture()
def isolated_env(tmp_path: Path) -> IsolatedClientEnv:
    """Create isolated HOME/APPDATA/XDG_CONFIG_HOME and a pre-seeded detectable .minecraft dir."""
    root = tmp_path / "client_env"
    home_dir = root / "home"
    appdata_dir = root / "AppData" / "Roaming"
    localappdata_dir = root / "AppData" / "Local"
    xdg_config_dir = root / "xdg_config"
    mods_dir = root / "target_mods"

    for directory in (home_dir, appdata_dir, localappdata_dir, xdg_config_dir, mods_dir):
        directory.mkdir(parents=True, exist_ok=True)

    # Create a detectable .minecraft/mods folder so detect_minecraft_dirs() finds it first
    if sys.platform == "win32":
        detected_mc_dir = appdata_dir / MINECRAFT_DOT_DIR
        config_path = appdata_dir / APP_DISPLAY_NAME / CONFIG_FILENAME
    else:
        detected_mc_dir = home_dir / MINECRAFT_DOT_DIR
        config_path = xdg_config_dir / APP_NAME_LOWER / CONFIG_FILENAME
    (detected_mc_dir / MODS_SUBDIR_NAME).mkdir(parents=True, exist_ok=True)

    env = build_local_loopback_env()
    for var in (
        ENV_MODSYNC_SERVER_URL,
        ENV_MODSYNC_MODS_DIR,
        ENV_MODSYNC_CLIENT_TOKEN,
        ENV_MODSYNC_UPDATE_REPO,
        ENV_MODSYNC_GITHUB_API_URL,
    ):
        env.pop(var, None)
    env[ENV_HOME] = str(home_dir)
    env[ENV_USERPROFILE] = str(home_dir)
    env[ENV_APPDATA] = str(appdata_dir)
    env[ENV_LOCALAPPDATA] = str(localappdata_dir)
    env[ENV_XDG_CONFIG_HOME] = str(xdg_config_dir)

    return IsolatedClientEnv(
        root=root,
        home_dir=home_dir,
        appdata_dir=appdata_dir,
        localappdata_dir=localappdata_dir,
        xdg_config_dir=xdg_config_dir,
        config_path=config_path,
        mods_dir=mods_dir,
        detected_mc_dir=detected_mc_dir,
        env=env,
    )


@pytest.fixture()
def process_spawner(tmp_path: Path) -> Iterator[ProcessSpawner]:
    """Spawn client processes and guarantee process-tree teardown after each test."""
    spawned: list[subprocess.Popen[str]] = []

    def _spawn(
        args: Sequence[str | Path],
        *,
        env: dict[str, str] | None = None,
        stdin: Any = subprocess.DEVNULL,
        stdout: Any = subprocess.DEVNULL,
        stderr: Any = subprocess.DEVNULL,
    ) -> subprocess.Popen[str]:
        proc = subprocess.Popen(
            [str(a) for a in args],
            cwd=str(tmp_path),
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        spawned.append(proc)
        return proc

    try:
        yield _spawn
    finally:
        first_error: BaseException | None = None
        for proc in reversed(spawned):
            try:
                if proc.poll() is None:
                    terminate_process_tree(proc)
                else:
                    for pipe in (proc.stdin, proc.stdout, proc.stderr):
                        if pipe is not None:
                            try:
                                pipe.close()
                            except (OSError, ValueError):
                                pass
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


@pytest.fixture()
def client_cli(
    modsync_bin: Path,
    isolated_env: IsolatedClientEnv,
    process_spawner: ProcessSpawner,
    tmp_path: Path,
) -> ModSyncCli:
    """Provide the ModSyncCli harness bound to the isolated test environment."""
    return ModSyncCli(
        binary=modsync_bin,
        isolated_env=isolated_env,
        spawner=process_spawner,
        cwd=tmp_path,
    )


@pytest.fixture()
def dialog_driver() -> Iterator[BaseDialogDriver]:
    """Provide platform GUI dialog automation driver (or fail in CI / skip locally if missing)."""
    try:
        driver = create_dialog_driver()
    except Exception as exc:
        if is_ci_environment():
            pytest.fail(f"GUI dialog driver failed to initialize in CI: {exc}")
        pytest.skip(f"GUI dialog driver unavailable in local environment: {exc}")
    try:
        yield driver
    finally:
        driver.close()
