"""ModSync client CLI/process harness encapsulating flags, binaries, and exit contracts."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .dialog_driver import BaseDialogDriver
from .env import IsolatedClientEnv, ProcessSpawner

FLAG_VERSION = "--version"
FLAG_HELP = "--help"
FLAG_HEADLESS = "--headless"
FLAG_SYNC_ONCE = "--sync-once"
FLAG_INSTALL_RECOMMENDED = "--install-recommended"
FLAG_SETUP = "--setup"
FLAG_UPDATE = "--update"
FLAG_SERVER_URL = "--server-url"
FLAG_MODS_DIR = "--mods-dir"
FLAG_TOKEN = "--token"
FLAG_CONFIG = "--config"

ENV_MODSYNC_GITHUB_API_URL = "MODSYNC_GITHUB_API_URL"
ENV_DISPLAY = "DISPLAY"

APP_DISPLAY_NAME = "ModSync"
WIN_APP_EXE_NAME = "ModSync.exe"
LINUX_APP_EXE_NAME = "ModSync-linux"
LINUX_LOCAL_EXE_NAME = "ModSync"
OLD_BINARY_SUFFIX = ".old"

EXIT_CODE_SUCCESS = 0
EXIT_CODE_FAILURE = 1
STDERR_TKINTER_MISSING = "No module named 'tkinter'"
TRACEBACK_MARKER = "Traceback"

TIMEOUT_CLI = 30.0
TIMEOUT_SYNC = 20.0
TIMEOUT_DIALOG = 15.0


@dataclass
class ModSyncCli:
    """High-level test harness for invoking the packaged ModSync client binary."""

    binary: Path
    isolated_env: IsolatedClientEnv
    spawner: ProcessSpawner
    cwd: Path

    @property
    def platform_asset_name(self) -> str:
        """Return the GitHub release asset filename expected on the current platform."""
        return WIN_APP_EXE_NAME if sys.platform == "win32" else LINUX_APP_EXE_NAME

    @property
    def release_asset_name(self) -> str:
        """Return the GitHub release asset filename expected on the current platform."""
        return self.platform_asset_name

    def old_binary_path(self, binary: Path | None = None) -> Path:
        """Return the Windows `.old` backup path corresponding to a binary."""
        target = binary or self.binary
        return target.with_name(f"{target.name}{OLD_BINARY_SUFFIX}")

    def _run(
        self,
        args: Sequence[str | Path],
        *,
        binary: Path | None = None,
        env: dict[str, str] | None = None,
        stdin_input: str | None = None,
        timeout: float = TIMEOUT_CLI,
    ) -> subprocess.CompletedProcess[str]:
        target_bin = binary or self.binary
        cmd = [str(target_bin), *(str(a) for a in args)]
        return subprocess.run(
            cmd,
            cwd=str(self.cwd),
            env=env if env is not None else self.isolated_env.env,
            input=stdin_input,
            stdin=None if stdin_input is not None else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def version(
        self,
        *,
        binary: Path | None = None,
        timeout: float = TIMEOUT_CLI,
    ) -> subprocess.CompletedProcess[str]:
        """Run `ModSync --version`."""
        return self._run([FLAG_VERSION], binary=binary, timeout=timeout)

    def sync_once(
        self,
        *,
        server_url: str | None = None,
        token: str | None = None,
        invite_url: str | None = None,
        mods_dir: Path | None = None,
        config_path: Path | None = None,
        timeout: float = TIMEOUT_SYNC,
    ) -> subprocess.CompletedProcess[str]:
        """Run `ModSync --sync-once` with optional server, token, invite, and config overrides."""
        args: list[str | Path] = []
        if invite_url is not None:
            args.append(invite_url)
        args.append(FLAG_SYNC_ONCE)
        if server_url is not None:
            args.extend((FLAG_SERVER_URL, server_url))
        if token is not None:
            args.extend((FLAG_TOKEN, token))
        if mods_dir is not None:
            args.extend((FLAG_MODS_DIR, mods_dir))
        cfg = config_path if config_path is not None else self.isolated_env.config_path
        args.extend((FLAG_CONFIG, cfg))
        return self._run(args, timeout=timeout)

    def install_recommended(
        self,
        *,
        config_path: Path | None = None,
        timeout: float = TIMEOUT_SYNC,
    ) -> subprocess.CompletedProcess[str]:
        """Run `ModSync --install-recommended` against persisted config."""
        cfg = config_path if config_path is not None else self.isolated_env.config_path
        return self._run([FLAG_INSTALL_RECOMMENDED, FLAG_CONFIG, cfg], timeout=timeout)

    def update(
        self,
        *,
        github_api_url: str,
        binary: Path | None = None,
        timeout: float = TIMEOUT_CLI,
    ) -> subprocess.CompletedProcess[str]:
        """Run `ModSync --update` pointed at a local fake GitHub API base URL."""
        env = dict(self.isolated_env.env)
        env[ENV_MODSYNC_GITHUB_API_URL] = github_api_url
        return self._run([FLAG_UPDATE], binary=binary, env=env, timeout=timeout)

    def setup_cli(
        self,
        *,
        stdin_input: str,
        config_path: Path | None = None,
        timeout: float = TIMEOUT_SYNC,
    ) -> subprocess.CompletedProcess[str]:
        """Run CLI onboarding (`--setup --headless --sync-once`) with scripted stdin."""
        cfg = config_path if config_path is not None else self.isolated_env.config_path
        return self._run(
            [FLAG_SETUP, FLAG_HEADLESS, FLAG_SYNC_ONCE, FLAG_CONFIG, cfg],
            stdin_input=stdin_input,
            timeout=timeout,
        )

    def start_headless(
        self,
        *,
        server_url: str,
        token: str,
        mods_dir: Path | None = None,
        config_path: Path | None = None,
        binary: Path | None = None,
    ) -> subprocess.Popen[str]:
        """Spawn long-running `--headless` sync/WebSocket daemon via the test spawner."""
        target_bin = binary or self.binary
        target_mods = mods_dir if mods_dir is not None else self.isolated_env.mods_dir
        cfg = config_path if config_path is not None else self.isolated_env.config_path
        return self.spawner(
            [
                target_bin,
                FLAG_HEADLESS,
                FLAG_SERVER_URL,
                server_url,
                FLAG_TOKEN,
                token,
                FLAG_MODS_DIR,
                target_mods,
                FLAG_CONFIG,
                cfg,
            ],
            env=self.isolated_env.env,
        )

    def start_tray(
        self,
        *,
        server_url: str,
        token: str,
        github_api_url: str,
        env_overrides: dict[str, str] | None = None,
        mods_dir: Path | None = None,
        config_path: Path | None = None,
    ) -> subprocess.Popen[str]:
        """Spawn ModSync in tray mode (no --headless, no --sync-once) via the test spawner."""
        target_mods = mods_dir if mods_dir is not None else self.isolated_env.mods_dir
        cfg = config_path if config_path is not None else self.isolated_env.config_path
        env = dict(self.isolated_env.env)
        if env_overrides:
            env.update(env_overrides)
        env[ENV_MODSYNC_GITHUB_API_URL] = github_api_url
        return self.spawner(
            [
                self.binary,
                FLAG_SERVER_URL,
                server_url,
                FLAG_TOKEN,
                token,
                FLAG_MODS_DIR,
                target_mods,
                FLAG_CONFIG,
                cfg,
            ],
            env=env,
        )

    def supports_tkinter(self, *, env: dict[str, str] | None = None) -> bool:
        """Probe whether the packaged binary includes a working tkinter module."""
        if sys.platform == "win32":
            return True
        source_env = env if env is not None else self.isolated_env.env
        probe_env = {k: v for k, v in source_env.items() if k != ENV_DISPLAY}
        res = self._run(
            [FLAG_CONFIG, self.cwd / "probe-missing.json"],
            env=probe_env,
            timeout=TIMEOUT_DIALOG,
        )
        return STDERR_TKINTER_MISSING not in res.stderr

    def launch_gui_setup(
        self,
        *,
        dialog_driver: BaseDialogDriver,
        config_path: Path | None = None,
    ) -> subprocess.Popen[str]:
        """Spawn GUI onboarding (`--setup --sync-once`) under the active dialog driver's env."""
        env = dialog_driver.prepare_env(self.isolated_env.env)
        cfg = config_path if config_path is not None else self.isolated_env.config_path
        return self.spawner(
            [self.binary, FLAG_SETUP, FLAG_SYNC_ONCE, FLAG_CONFIG, cfg],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
