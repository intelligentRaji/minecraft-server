"""Tests for ModSync client CLI and entry point execution."""

from __future__ import annotations

import logging
import runpy
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest

import modsync_client.main as cli_main
import modsync_client.onboarding as onboarding
import modsync_client.updater as updater
from modsync_client.config import Config
from modsync_client.syncer import SyncResult, SyncStatus
from modsync_client.updater import UpdateInfo


def _raise(exc: BaseException) -> Callable[..., NoReturn]:
    def _raiser(*_args: object, **_kwargs: object) -> NoReturn:
        raise exc

    return _raiser


def _sample_update() -> UpdateInfo:
    return UpdateInfo(
        version="9.9.9",
        tag_name="client-v9.9.9",
        html_url="https://example.test/release",
        asset_name="ModSync-linux",
        download_url="https://example.test/ModSync-linux",
        expected_sha256="a" * 64,
    )


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
) -> None:
    update = _sample_update()
    applied: list[UpdateInfo] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(cli_main, "download_and_apply_update", applied.append)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    rc = cli_main.main(["--update"])

    assert rc == 0
    assert applied == [update]
    assert "9.9.9" in capsys.readouterr().out


def test_cli_update_rejects_non_frozen_binary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: _sample_update())

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
) -> None:
    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: _sample_update())
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

    class FakeSyncer:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_once(self) -> SyncResult:
            events.append("sync_once")
            return SyncResult(status=status, version="v1", mod_count=1, message="sync finished")

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncer", FakeSyncer)

    rc = cli_main.main(["--sync-once"])

    assert rc == expected_rc
    assert events == ["sync_once", "close"]
    assert "sync finished" in capsys.readouterr().out


def test_cli_sync_once_closes_syncer_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    closed: list[bool] = []

    class FailingSyncer:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_once(self) -> SyncResult:
            raise RuntimeError("boom")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncer", FailingSyncer)

    with pytest.raises(RuntimeError, match="boom"):
        cli_main.main(["--sync-once"])

    assert closed == [True]


def test_cli_install_recommended_runs_recommended_and_closes_syncer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[str] = []

    class FakeSyncer:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def install_recommended(self) -> SyncResult:
            events.append("install_recommended")
            return SyncResult(
                status=SyncStatus.SYNCED,
                version="v1",
                mod_count=2,
                message="installed optional",
            )

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncer", FakeSyncer)

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

    class FakeService:
        def __init__(self, service_cfg: Config, *, on_status: Any = None) -> None:
            events.append(("init", service_cfg))

        async def run(self) -> None:
            events.append("run")

        def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncService", FakeService)

    rc = cli_main.main(["--headless"])

    assert rc == 0
    assert events == [("init", cfg), "run"]


def test_cli_headless_stops_service_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    events: list[str] = []

    class FakeService:
        def __init__(self, _cfg: Config, *, on_status: Any = None) -> None:
            pass

        async def run(self) -> None:
            raise KeyboardInterrupt

        def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "resolve_or_setup_config", lambda _args: cfg)
    monkeypatch.setattr(cli_main, "ModSyncService", FakeService)

    rc = cli_main.main(["--headless"])

    assert rc == 0
    assert events == ["stop"]


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
