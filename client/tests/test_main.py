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
