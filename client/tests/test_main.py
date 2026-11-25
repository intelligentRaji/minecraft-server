"""Tests for ModSync client CLI and entry point execution."""

from __future__ import annotations

import logging
import runpy
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest

import modsync_client.main as cli_main
import modsync_client.onboarding as onboarding
import modsync_client.updater as updater
from modsync_client.config import Config
from modsync_client.syncer import SyncResult, SyncStatus
from modsync_client.updater import UpdateInfo
from modsync_client.ws_client import StatusCallback


def _raise(exc: BaseException) -> Callable[..., NoReturn]:
    def _raiser(*_args: object, **_kwargs: object) -> NoReturn:
        raise exc

    return _raiser


class _FakeSyncer:
    """Configurable ModSyncer double recording lifecycle calls for CLI tests."""

    def __init__(
        self,
        *,
        result: SyncResult | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
        **_kwargs: object,
    ) -> None:
        self._result = result or SyncResult(
            status=SyncStatus.SYNCED,
            version="v1",
            mod_count=1,
            message="sync finished",
        )
        self._error = error
        self._events = events

    @classmethod
    def factory(
        cls,
        *,
        result: SyncResult | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> Callable[..., _FakeSyncer]:
        def _build(**kwargs: object) -> _FakeSyncer:
            return cls(result=result, error=error, events=events, **kwargs)

        return _build

    def sync_once(self) -> SyncResult:
        if self._events is not None:
            self._events.append("sync_once")
        if self._error is not None:
            raise self._error
        return self._result

    def install_recommended(self) -> SyncResult:
        if self._events is not None:
            self._events.append("install_recommended")
        if self._error is not None:
            raise self._error
        return self._result

    def close(self) -> None:
        if self._events is not None:
            self._events.append("close")


class _FakeService:
    """Minimal ModSyncService double capturing CLI headless lifecycle calls."""

    def __init__(
        self,
        config: Config,
        *,
        on_status: StatusCallback | None = None,
        events: list[object] | None = None,
        run_error: BaseException | None = None,
    ) -> None:
        self._events = events
        self._run_error = run_error
        self.on_status = on_status
        if self._events is not None:
            self._events.append(("init", config))

    @classmethod
    def factory(
        cls,
        *,
        events: list[object] | None = None,
        run_error: BaseException | None = None,
    ) -> Callable[..., _FakeService]:
        def _build(
            config: Config,
            *,
            on_status: StatusCallback | None = None,
        ) -> _FakeService:
            return cls(config, on_status=on_status, events=events, run_error=run_error)

        return _build

    async def run(self) -> None:
        if self._events is not None:
            self._events.append("run")
        if self._run_error is not None:
            raise self._run_error

    def stop(self) -> None:
        if self._events is not None:
            self._events.append("stop")


@pytest.fixture(autouse=True)
def stub_logging_basic_config(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Stub logging.basicConfig and return captured keyword arguments."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: calls.append(kwargs))
    return calls


def test_main_script_runs_tray_without_parent_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Running main.py as __main__ (e.g. PyInstaller) must not use relative imports."""
    ran_with: list[tuple[Config, Path]] = []
    config = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    config_path = tmp_path / "config.json"

    class FakeTrayApp:
        def __init__(self, cfg: Config, cfg_path: Path) -> None:
            self._cfg = cfg
            self._cfg_path = cfg_path

        def run(self) -> None:
            ran_with.append((self._cfg, self._cfg_path))

    fake_tray = types.ModuleType("modsync_client.tray")
    fake_tray.ModSyncTrayApp = FakeTrayApp  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modsync_client.tray", fake_tray)
    monkeypatch.setattr(updater, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(onboarding, "resolve_or_setup_config", lambda _args: config)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])

    main_path = Path(cli_main.__file__).resolve()
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(main_path), run_name="__main__")

    assert exc_info.value.code == 0
    assert ran_with == [(config, config_path)]


def test_cli_update_up_to_date_skips_config_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: None)
    monkeypatch.setattr(
        cli_main,
        "resolve_or_setup_config",
        lambda _args: pytest.fail("resolve_or_setup_config should not be called for --update"),
    )

    rc = cli_main.main(["--update"])

    assert rc == 0
    assert "already up to date" in capsys.readouterr().out


def test_cli_update_applies_update_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_sample_update: Callable[..., UpdateInfo],
) -> None:
    update = make_sample_update()
    applied: list[UpdateInfo] = []
    relaunched: list[bool] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(cli_main, "download_and_apply_update", applied.append)
    monkeypatch.setattr(cli_main, "relaunch_executable", lambda: relaunched.append(True))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    rc = cli_main.main(["--update"])

    assert rc == 0
    assert applied == [update]
    assert relaunched == []
    assert "9.9.9" in capsys.readouterr().out


def test_cli_update_with_relaunch_calls_relaunch_executable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_sample_update: Callable[..., UpdateInfo],
) -> None:
    update = make_sample_update()
    events: list[object] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(
        cli_main,
        "download_and_apply_update",
        lambda upd: events.append(("apply", upd)),
    )
    monkeypatch.setattr(cli_main, "relaunch_executable", lambda: events.append("relaunch"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    rc = cli_main.main(["--update", "--relaunch"])

    assert rc == 0
    assert events == [("apply", update), "relaunch"]
    assert "9.9.9" in capsys.readouterr().out


def test_cli_update_rejects_non_frozen_binary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_sample_update: Callable[..., UpdateInfo],
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: make_sample_update())

    rc = cli_main.main(["--update"])

    assert rc == 1
    assert "standalone frozen binaries" in capsys.readouterr().err


def test_cli_update_returns_one_on_check_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", _raise(RuntimeError("network down")))

    rc = cli_main.main(["--update"])

    assert rc == 1
    assert "network down" in capsys.readouterr().err


def test_cli_update_returns_one_on_download_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_sample_update: Callable[..., UpdateInfo],
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: make_sample_update())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        cli_main,
        "download_and_apply_update",
        _raise(PermissionError("read-only dir")),
    )

    rc = cli_main.main(["--update"])

    assert rc == 1
    assert "read-only dir" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("status", "expected_rc"),
    [(SyncStatus.SYNCED, 0), (SyncStatus.ERROR, 1)],
)
def test_cli_sync_once_returns_status_exit_code_and_closes_syncer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status: SyncStatus,
    expected_rc: int,
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[str] = []
    result = SyncResult(status=status, version="v1", mod_count=1, message="sync finished")

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncer", _FakeSyncer.factory(result=result, events=events))

    rc = cli_main.main(["--sync-once"])

    assert rc == expected_rc
    assert events == ["sync_once", "close"]
    assert "sync finished" in capsys.readouterr().out


def test_cli_sync_once_closes_syncer_and_returns_one_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[str] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(
        cli_main,
        "ModSyncer",
        _FakeSyncer.factory(error=RuntimeError("boom"), events=events),
    )

    rc = cli_main.main(["--sync-once"])

    assert rc == 1
    assert "boom" in capsys.readouterr().err
    assert events == ["sync_once", "close"]


def test_cli_invalid_invite_uri_exits_cleanly_without_unhandled_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(
            [
                "ftp://not-a-valid-invite",
                "--sync-once",
                "--config",
                str(tmp_path / "config.json"),
            ]
        )

    assert "Unsupported" in str(exc_info.value) or "Invalid" in str(exc_info.value)


def test_cli_install_recommended_runs_recommended_and_closes_syncer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[str] = []
    result = SyncResult(
        status=SyncStatus.SYNCED,
        version="v1",
        mod_count=2,
        message="installed optional",
    )

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncer", _FakeSyncer.factory(result=result, events=events))

    rc = cli_main.main(["--install-recommended"])

    assert rc == 0
    assert events == ["install_recommended", "close"]
    assert "installed optional" in capsys.readouterr().out


def test_cli_headless_runs_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[object] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncService", _FakeService.factory(events=events))

    rc = cli_main.main(["--headless"])

    assert rc == 0
    assert events == [("init", cfg), "run"]


def test_cli_headless_stops_service_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[object] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(
        cli_main,
        "ModSyncService",
        _FakeService.factory(events=events, run_error=KeyboardInterrupt()),
    )

    rc = cli_main.main(["--headless"])

    assert rc == 0
    assert events == [("init", cfg), "run", "stop"]


@pytest.mark.parametrize(
    ("argv", "expected_level"),
    [
        (["--update"], logging.INFO),
        (["--update", "--verbose"], logging.DEBUG),
    ],
)
def test_cli_logging_level_reflects_verbose_flag(
    monkeypatch: pytest.MonkeyPatch,
    stub_logging_basic_config: list[dict[str, object]],
    argv: list[str],
    expected_level: int,
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: None)

    cli_main.main(argv)

    assert len(stub_logging_basic_config) == 1
    assert stub_logging_basic_config[0]["level"] == expected_level


def test_main_calls_cleanup_old_binary_on_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    exe_path = tmp_path / "ModSync.exe"
    exe_path.write_bytes(b"current-exe")
    old_path = tmp_path / "ModSync.exe.old"
    old_path.write_bytes(b"stale-old-binary")

    cleanup_calls: list[bool] = []
    real_cleanup = updater.cleanup_old_binary

    def _spy_cleanup() -> None:
        cleanup_calls.append(True)
        real_cleanup()

    monkeypatch.setattr(sys, "executable", str(exe_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli_main, "cleanup_old_binary", _spy_cleanup)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: None)

    rc = cli_main.main(["--update"])

    assert rc == 0
    assert cleanup_calls == [True]
    assert not old_path.exists()


def test_cli_sync_once_auth_error_leaves_mods_dir_untouched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    existing_jar = mods_dir / "personal-minimap.jar"
    existing_payload = b"user-jar-bytes"
    existing_jar.write_bytes(existing_payload)

    cfg = Config(
        server_url="https://mods.example",
        mods_dir=str(mods_dir),
        client_token="wrong-token",
    )
    auth_error_result = SyncResult(
        status=SyncStatus.ERROR,
        version="",
        mod_count=0,
        message="Unauthorized (401)",
    )

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncer", _FakeSyncer.factory(result=auth_error_result))

    rc = cli_main.main(["--sync-once"])

    assert rc == 1
    assert [p.name for p in mods_dir.iterdir()] == ["personal-minimap.jar"]
    assert existing_jar.read_bytes() == existing_payload


def test_cli_setup_headless_eof_exits_zero_without_writing_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr("builtins.input", _raise(EOFError()))

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--setup", "--headless", "--sync-once", "--config", str(cfg_path)])

    assert exc_info.value.code == 0
    assert not cfg_path.exists()
