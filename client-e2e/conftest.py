"""Shared pytest fixtures for ModSync cross-platform E2E tests."""

from __future__ import annotations

import os
import re
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
from helpers.polling import run_with_tree_timeout, terminate_process_tree
from helpers.win_installer import (
    WIN_APP_EXE_NAME,
    WIN_INSTALLER_EXE_NAME,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = REPO_ROOT / "client"
CLIENT_DIST_DIR = CLIENT_DIR / "dist"
V99_ENTRY_SCRIPT = Path(__file__).resolve().parent / "fixtures" / "v99_entry.py"

ENV_MODSYNC_BIN = "MODSYNC_BIN"
ENV_MODSYNC_V99_BIN = "MODSYNC_V99_BIN"
ENV_MODSYNC_INSTALLER = "MODSYNC_INSTALLER"
ENV_MODSYNC_E2E_ARTIFACTS_DIR = "MODSYNC_E2E_ARTIFACTS_DIR"
ENV_VIRTUAL_ENV = "VIRTUAL_ENV"
ENV_UV_PROJECT_ENVIRONMENT = "UV_PROJECT_ENVIRONMENT"
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

OPT_USE_LIVE_DISPLAY = "--use-live-display"
OPT_RUN_WIN_INSTALLER = "--run-win-installer"

APP_DISPLAY_NAME = "ModSync"
APP_NAME_LOWER = "modsync"
CONFIG_FILENAME = "config.json"
STAGING_SUBDIR_NAME = "staging"
MINECRAFT_DOT_DIR = ".minecraft"
MODS_SUBDIR_NAME = "mods"
EXIT_CODE_SUCCESS = 0
LOG_SECTION_MAX_CHARS = 8000

PYINSTALLER_HIDDEN_IMPORTS = (
    "pystray._win32",
    "pystray._xorg",
    "pystray._appindicator",
    "PIL._tkinter_finder",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.simpledialog",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom CLI flags for GUI display selection and host Windows installer tests."""
    parser.addoption(
        OPT_USE_LIVE_DISPLAY,
        action="store_true",
        default=False,
        help="Attach Linux GUI E2E tests to the existing DISPLAY instead of starting Xvfb.",
    )
    parser.addoption(
        OPT_RUN_WIN_INSTALLER,
        action="store_true",
        default=False,
        help="Run Windows host-mutating Inno Setup installer E2E tests.",
    )


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
def modsync_bin() -> Path:
    """Resolve the packaged ModSync client executable directly without touching host installer state."""
    env_bin = os.environ.get(ENV_MODSYNC_BIN, "").strip()
    if env_bin:
        path = Path(env_bin).resolve()
        if not path.is_file():
            pytest.fail(f"{ENV_MODSYNC_BIN} points to missing executable: {path}")
        return path

    if sys.platform == "win32":
        win_bin = CLIENT_DIST_DIR / WIN_APP_EXE_NAME
        if win_bin.is_file():
            return win_bin
        pytest.fail(
            f"ModSync Windows binary not found at {win_bin}. "
            f"Run PyInstaller build or set {ENV_MODSYNC_BIN}."
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


def _skip_or_fail_missing_builder(reason: str) -> None:
    if is_ci_environment():
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def updated_modsync_bin(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Resolve or build a runnable v99.0.0 ModSync standalone binary for update/relaunch E2E."""
    env_v99 = os.environ.get(ENV_MODSYNC_V99_BIN, "").strip()
    if env_v99:
        path = Path(env_v99).resolve()
        if not path.is_file():
            pytest.fail(f"{ENV_MODSYNC_V99_BIN} points to missing executable: {path}")
        return path

    uv_exe = shutil.which("uv")
    if not uv_exe:
        _skip_or_fail_missing_builder("uv is not available to build v99.0.0 ModSync test binary.")

    client_venv = CLIENT_DIR / ".venv"
    has_client_venv = client_venv.is_dir()
    if not has_client_venv and not is_ci_environment():
        _skip_or_fail_missing_builder(
            f"Client virtualenv not found at {client_venv}. "
            "Run `uv --directory client sync --group dev` or set MODSYNC_V99_BIN."
        )

    assert uv_exe is not None
    run_cmd = [uv_exe, "--directory", str(CLIENT_DIR), "run"]
    if has_client_venv:
        run_cmd.append("--no-sync")

    clean_env = os.environ.copy()
    clean_env.pop(ENV_VIRTUAL_ENV, None)
    clean_env.pop(ENV_UV_PROJECT_ENVIRONMENT, None)

    probe = run_with_tree_timeout(
        [*run_cmd, "python", "-c", "import PyInstaller"],
        cwd=CLIENT_DIR,
        env=clean_env,
        timeout=30.0,
    )
    if probe.returncode != EXIT_CODE_SUCCESS:
        _skip_or_fail_missing_builder(
            f"PyInstaller is unavailable in {CLIENT_DIR} (rc={probe.returncode}): {probe.stderr.strip()}"
        )

    build_root = tmp_path_factory.mktemp("v99_build")
    dist_dir = build_root / "dist"
    work_dir = build_root / "work"
    spec_dir = build_root / "spec"
    pyi_cmd: list[str] = [
        *run_cmd,
        "pyinstaller",
        str(V99_ENTRY_SCRIPT),
        "--onefile",
        "--clean",
        "--noconfirm",
        "--name",
        APP_DISPLAY_NAME,
        "--paths",
        str(CLIENT_DIR / "src"),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
    ]
    if sys.platform == "win32":
        pyi_cmd.append("--noconsole")
    for hidden in PYINSTALLER_HIDDEN_IMPORTS:
        pyi_cmd.extend(("--hidden-import", hidden))

    res = run_with_tree_timeout(pyi_cmd, cwd=CLIENT_DIR, env=clean_env, timeout=180.0)
    if res.returncode != EXIT_CODE_SUCCESS:
        pytest.fail(
            f"Failed to build v99.0.0 ModSync test binary (rc={res.returncode}):\n"
            f"stdout={res.stdout}\nstderr={res.stderr}"
        )

    out_name = WIN_APP_EXE_NAME if sys.platform == "win32" else LINUX_LOCAL_EXE_NAME
    built_bin = dist_dir / out_name
    if not built_bin.is_file():
        pytest.fail(f"Expected built v99.0.0 binary at {built_bin}")
    return built_bin


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
    staging_dir = config_path.parent / STAGING_SUBDIR_NAME
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
        staging_dir=staging_dir,
        mods_dir=mods_dir,
        detected_mc_dir=detected_mc_dir,
        env=env,
    )


@pytest.fixture()
def process_spawner(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[ProcessSpawner]:
    """Spawn client processes with per-test log files and guarantee process-tree teardown."""
    spawned: list[subprocess.Popen[str]] = []
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tracked_logs: list[Path] = []
    setattr(request.node, "_e2e_logs_dir", logs_dir)
    setattr(request.node, "_e2e_log_paths", tracked_logs)
    counter = 0

    def _spawn(
        args: Sequence[str | Path],
        *,
        env: dict[str, str] | None = None,
        stdin: Any = subprocess.DEVNULL,
        stdout: Any = None,
        stderr: Any = None,
        log_name: str | None = None,
    ) -> subprocess.Popen[str]:
        nonlocal counter
        prefix = log_name or f"proc_{counter}"
        counter += 1

        opened: list[Any] = []
        effective_stdout = stdout
        effective_stderr = stderr
        if effective_stdout is None:
            out_path = logs_dir / f"{prefix}.stdout.log"
            effective_stdout = out_path.open("w", encoding="utf-8", errors="replace")
            opened.append(effective_stdout)
            tracked_logs.append(out_path)
        elif hasattr(effective_stdout, "name"):
            tracked_logs.append(Path(str(effective_stdout.name)))

        if effective_stderr is None:
            err_path = logs_dir / f"{prefix}.stderr.log"
            effective_stderr = err_path.open("w", encoding="utf-8", errors="replace")
            opened.append(effective_stderr)
            tracked_logs.append(err_path)
        elif hasattr(effective_stderr, "name"):
            tracked_logs.append(Path(str(effective_stderr.name)))

        try:
            proc = subprocess.Popen(
                [str(a) for a in args],
                cwd=str(tmp_path),
                env=env,
                stdin=stdin,
                stdout=effective_stdout,
                stderr=effective_stderr,
                text=True,
            )
        finally:
            for handle in opened:
                try:
                    handle.close()
                except OSError:
                    pass
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
        log_dir=tmp_path / "logs",
    )


@pytest.fixture()
def dialog_driver(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[BaseDialogDriver]:
    """Provide platform GUI dialog automation driver (or fail in CI / skip locally if missing)."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    setattr(request.node, "_e2e_logs_dir", logs_dir)
    use_live = bool(request.config.getoption(OPT_USE_LIVE_DISPLAY))
    try:
        driver = create_dialog_driver(use_live_display=use_live, log_dir=logs_dir)
    except Exception as exc:
        if is_ci_environment():
            pytest.fail(f"GUI dialog driver failed to initialize in CI: {exc}")
        pytest.skip(f"GUI dialog driver unavailable in local environment: {exc}")
    try:
        yield driver
    finally:
        driver.close()


def _collect_failure_files(item: pytest.Item, logs_dir: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if logs_dir is not None and logs_dir.is_dir():
        candidates.extend(sorted(logs_dir.iterdir()))
    candidates.extend(getattr(item, "_e2e_log_paths", []))
    funcargs = getattr(item, "funcargs", {})
    api_server = funcargs.get("api_server")
    if api_server is not None:
        candidates.extend(getattr(api_server, "log_paths", []))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if not isinstance(path, Path) or not path.is_file():
            continue
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    """Attach per-test logs and failure screenshots on setup/call failures."""
    outcome = yield
    report = outcome.get_result()
    if report.when not in ("setup", "call") or not report.failed:
        return

    funcargs = getattr(item, "funcargs", {})
    logs_dir: Path | None = getattr(item, "_e2e_logs_dir", None)
    if logs_dir is None:
        tmp_path = funcargs.get("tmp_path")
        if isinstance(tmp_path, Path):
            logs_dir = tmp_path / "logs"

    driver = funcargs.get("dialog_driver")
    if isinstance(driver, BaseDialogDriver) and logs_dir is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        try:
            driver.capture_screenshot(logs_dir / f"{report.when}_failure.png")
        except Exception:
            pass

    files = _collect_failure_files(item, logs_dir)
    for file_path in files:
        if file_path.suffix == ".log":
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as exc:
                report.sections.append((f"E2E log: {file_path.name}", f"<unreadable: {exc}>"))
                continue
            if text:
                tail = (
                    f"...[truncated]\n{text[-LOG_SECTION_MAX_CHARS:]}"
                    if len(text) > LOG_SECTION_MAX_CHARS
                    else text
                )
                report.sections.append((f"E2E log: {file_path.name}", tail))

    artifacts_root = os.environ.get(ENV_MODSYNC_E2E_ARTIFACTS_DIR, "").strip()
    if artifacts_root and files:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid).strip("_") or "test"
        dest_dir = Path(artifacts_root) / safe_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        for file_path in files:
            try:
                shutil.copy2(file_path, dest_dir / file_path.name)
            except OSError:
                pass
