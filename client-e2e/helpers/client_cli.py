"""ModSync client CLI/process harness encapsulating flags, binaries, and exit contracts."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from .dialog_driver import BaseDialogDriver
from .env import IsolatedClientEnv, ProcessSpawner
from .polling import get_process_tree_pids, run_with_tree_timeout, terminate_process_tree, wait_until
from .win_job import WinJobProcessTracker

FLAG_VERSION = "--version"
FLAG_HELP = "--help"
FLAG_HEADLESS = "--headless"
FLAG_SYNC_ONCE = "--sync-once"
FLAG_INSTALL_RECOMMENDED = "--install-recommended"
FLAG_SETUP = "--setup"
FLAG_UPDATE = "--update"
FLAG_RELAUNCH = "--relaunch"
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

TIMEOUT_CLI = 45.0
TIMEOUT_SYNC = 45.0
TIMEOUT_DIALOG = 30.0

_LINUX_SUBREAPER_SCRIPT = """
import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

libc = ctypes.CDLL("libc.so.6", use_last_error=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_last_error(), "prctl(PR_SET_CHILD_SUBREAPER) failed")

rc_file = Path(sys.argv[1])
cmd = sys.argv[2:]
proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
rc = proc.wait()
tmp_rc = rc_file.with_suffix(".tmp")
tmp_rc.write_text(str(rc), encoding="utf-8")
os.replace(tmp_rc, rc_file)

stop = False


def _on_term(_sig: int, _frame: object) -> None:
    global stop
    stop = True


signal.signal(signal.SIGTERM, _on_term)
signal.signal(signal.SIGINT, _on_term)

while not stop:
    try:
        pid, _ = os.waitpid(-1, os.WNOHANG)
        if pid > 0:
            continue
    except ChildProcessError:
        pass
    time.sleep(0.1)
""".strip()


@dataclass
class TrackedRelaunch:
    """Handle for a tracked `--update --relaunch` invocation and its detached child."""

    stdout_log: Path
    stderr_log: Path
    _wrapper_proc: subprocess.Popen[str] | None = None
    _rc_file: Path | None = None
    _win_tracker: WinJobProcessTracker | None = None
    _win_parent_pid: int | None = None

    def wait_parent(self, timeout: float = TIMEOUT_CLI) -> int:
        """Wait for the initial `--update --relaunch` process to exit and return its code."""
        if self._win_tracker is not None and self._win_parent_pid is not None:
            return self._win_tracker.wait_for_pid(self._win_parent_pid, timeout=timeout)

        assert self._wrapper_proc is not None
        assert self._rc_file is not None
        wrapper = self._wrapper_proc
        rc_file = self._rc_file

        def _done() -> bool:
            if rc_file.is_file():
                return True
            if wrapper.poll() is not None:
                raise RuntimeError(
                    f"Subreaper wrapper exited early (rc={wrapper.returncode}): "
                    f"stderr={self.read_stderr()!r}"
                )
            return False

        wait_until(
            _done,
            timeout=timeout,
            interval=0.05,
            description="--update --relaunch parent exit",
        )
        return int(rc_file.read_text(encoding="utf-8").strip())

    def is_child_running(self) -> bool:
        """Return True if at least one relaunched descendant process is still running."""
        if self._win_tracker is not None and self._win_parent_pid is not None:
            self._win_tracker.refresh_tracked_pids()
            return any(
                pid != self._win_parent_pid and self._win_tracker.is_pid_alive(pid)
                for pid in self._win_tracker.pids
            )

        assert self._wrapper_proc is not None
        if self._wrapper_proc.poll() is not None:
            return False
        child_pids = get_process_tree_pids(self._wrapper_proc.pid) - {self._wrapper_proc.pid}
        for pid in child_pids:
            try:
                if psutil.Process(pid).is_running():
                    return True
            except psutil.NoSuchProcess:
                continue
        return False

    def read_stderr(self) -> str:
        if not self.stderr_log.is_file():
            return ""
        return self.stderr_log.read_text(encoding="utf-8", errors="replace")

    def read_stdout(self) -> str:
        if not self.stdout_log.is_file():
            return ""
        return self.stdout_log.read_text(encoding="utf-8", errors="replace")

    def terminate(self) -> None:
        if self._win_tracker is not None:
            self._win_tracker.close()
        if self._wrapper_proc is not None and self._wrapper_proc.poll() is None:
            terminate_process_tree(self._wrapper_proc)

    def __enter__(self) -> TrackedRelaunch:
        return self

    def __exit__(self, *_args: object) -> None:
        self.terminate()


@dataclass
class ModSyncCli:
    """High-level test harness for invoking the packaged ModSync client binary."""

    binary: Path
    isolated_env: IsolatedClientEnv
    spawner: ProcessSpawner
    cwd: Path
    log_dir: Path = field(default_factory=Path)
    _log_counter: int = field(default=0, init=False)
    _proc_logs: dict[int, tuple[Path, Path]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.log_dir == Path():
            self.log_dir = self.cwd / "logs"

    def _next_log_name(self, prefix: str) -> str:
        idx = self._log_counter
        self._log_counter += 1
        return f"{prefix}_{idx}"

    def get_log_paths(self, proc_or_pid: subprocess.Popen[str] | int) -> tuple[Path, Path]:
        """Return (stdout_log, stderr_log) recorded for a spawned process."""
        pid = proc_or_pid.pid if isinstance(proc_or_pid, subprocess.Popen) else int(proc_or_pid)
        return self._proc_logs[pid]

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
        return run_with_tree_timeout(
            cmd,
            cwd=self.cwd,
            env=env if env is not None else self.isolated_env.env,
            stdin_input=stdin_input,
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

    def _build_env(
        self,
        *,
        env_overrides: dict[str, str] | None = None,
        github_api_url: str | None = None,
    ) -> dict[str, str]:
        env = dict(self.isolated_env.env)
        if env_overrides:
            env.update(env_overrides)
        if github_api_url is not None:
            env[ENV_MODSYNC_GITHUB_API_URL] = github_api_url
        return env

    def update(
        self,
        *,
        github_api_url: str,
        binary: Path | None = None,
        timeout: float = TIMEOUT_CLI,
    ) -> subprocess.CompletedProcess[str]:
        """Run `ModSync --update` pointed at a local fake GitHub API base URL."""
        return self._run(
            [FLAG_UPDATE],
            binary=binary,
            env=self._build_env(github_api_url=github_api_url),
            timeout=timeout,
        )

    def spawn_tracked_relaunch(
        self,
        *,
        github_api_url: str,
        binary: Path,
        env_overrides: dict[str, str] | None = None,
    ) -> TrackedRelaunch:
        """Spawn `ModSync --update --relaunch` with OS-level tracking of its detached child."""
        env = self._build_env(env_overrides=env_overrides, github_api_url=github_api_url)
        log_name = self._next_log_name("relaunch")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stdout_log = self.log_dir / f"{log_name}.stdout.log"
        stderr_log = self.log_dir / f"{log_name}.stderr.log"

        if sys.platform == "win32":
            tracker = WinJobProcessTracker()
            try:
                parent_pid = tracker.spawn(
                    [str(binary), FLAG_UPDATE, FLAG_RELAUNCH],
                    cwd=self.cwd,
                    env=env,
                    stdout=stdout_log,
                    stderr=stderr_log,
                )
            except BaseException:
                tracker.close()
                raise
            return TrackedRelaunch(
                stdout_log=stdout_log,
                stderr_log=stderr_log,
                _win_tracker=tracker,
                _win_parent_pid=parent_pid,
            )

        rc_file = self.log_dir / f"{log_name}.rc"
        wrapper_proc = self.spawner(
            [
                sys.executable,
                "-c",
                _LINUX_SUBREAPER_SCRIPT,
                rc_file,
                binary,
                FLAG_UPDATE,
                FLAG_RELAUNCH,
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            log_name=log_name,
        )
        self._proc_logs[wrapper_proc.pid] = (stdout_log, stderr_log)
        return TrackedRelaunch(
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            _wrapper_proc=wrapper_proc,
            _rc_file=rc_file,
        )

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

    def _spawn_logged(
        self,
        args: Sequence[str | Path],
        *,
        env: dict[str, str],
        prefix: str,
    ) -> subprocess.Popen[str]:
        log_name = self._next_log_name(prefix)
        stdout_log = self.log_dir / f"{log_name}.stdout.log"
        stderr_log = self.log_dir / f"{log_name}.stderr.log"
        proc = self.spawner(
            args,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            log_name=log_name,
        )
        self._proc_logs[proc.pid] = (stdout_log, stderr_log)
        return proc

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
        return self._spawn_logged(
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
            prefix="headless",
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
        env = self._build_env(env_overrides=env_overrides, github_api_url=github_api_url)
        return self._spawn_logged(
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
            prefix="tray",
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
        return self._spawn_logged(
            [self.binary, FLAG_SETUP, FLAG_SYNC_ONCE, FLAG_CONFIG, cfg],
            env=env,
            prefix="gui_setup",
        )
