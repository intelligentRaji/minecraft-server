"""Tests for ModSync client entry point execution."""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path

import pytest

from modsync_client.config import Config


def test_main_script_runs_tray_without_parent_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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

    import modsync_client.onboarding as onboarding
    import modsync_client.updater as updater

    monkeypatch.setattr(updater, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(onboarding, "resolve_or_setup_config", lambda _args: config)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])

    main_path = Path(__file__).resolve().parents[1] / "src" / "modsync_client" / "main.py"
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(main_path), run_name="__main__")

    assert exc_info.value.code == 0
    assert ran_with == [(config, config_path)]


def test_cli_update_up_to_date_skips_config_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import modsync_client.main as cli_main

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: None)
    monkeypatch.setattr(
        cli_main,
        "resolve_or_setup_config",
        lambda _args: pytest.fail("resolve_or_setup_config should not be called for --update"),
    )

    rc = cli_main.main(["--update"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "already up to date" in captured.out


def test_cli_update_applies_update_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import modsync_client.main as cli_main
    from modsync_client.updater import UpdateInfo

    update = UpdateInfo(
        version="9.9.9",
        tag_name="client-v9.9.9",
        html_url="https://example.test/release",
        asset_name="ModSync-linux",
        download_url="https://example.test/ModSync-linux",
        expected_sha256="a" * 64,
    )
    applied: list[UpdateInfo] = []

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(cli_main, "download_and_apply_update", applied.append)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    rc = cli_main.main(["--update"])
    captured = capsys.readouterr()
    assert rc == 0
    assert applied == [update]
    assert "9.9.9" in captured.out


def test_cli_update_handles_non_frozen_and_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import modsync_client.main as cli_main
    from modsync_client.updater import UpdateInfo

    update = UpdateInfo(
        version="9.9.9",
        tag_name="client-v9.9.9",
        html_url="https://example.test/release",
        asset_name="ModSync-linux",
        download_url="https://example.test/ModSync-linux",
    )

    monkeypatch.setattr(cli_main, "cleanup_old_binary", lambda: None)
    monkeypatch.setattr(cli_main, "check_for_update", lambda _ver: update)
    monkeypatch.delattr(sys, "frozen", raising=False)

    rc = cli_main.main(["--update"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "standalone frozen binaries" in err

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        cli_main,
        "download_and_apply_update",
        lambda _u: (_ for _ in ()).throw(PermissionError("read-only dir")),
    )
    rc2 = cli_main.main(["--update"])
    err2 = capsys.readouterr().err
    assert rc2 == 1
    assert "read-only dir" in err2

    monkeypatch.setattr(
        cli_main,
        "check_for_update",
        lambda _ver: (_ for _ in ()).throw(RuntimeError("network down")),
    )
    rc3 = cli_main.main(["--update"])
    err3 = capsys.readouterr().err
    assert rc3 == 1
    assert "network down" in err3

