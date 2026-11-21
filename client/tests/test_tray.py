"""Unit tests for ModSyncTrayApp without requiring a live X11/Windows display."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from modsync_client import __version__
from modsync_client.config import Config
from modsync_client.syncer import SyncResult, SyncStatus
from modsync_client.updater import UpdateInfo


class FakeMenuItem:
    """Minimal pystray.MenuItem double supporting static or callable text/checked."""

    def __init__(
        self,
        text: Any,
        action: Any,
        checked: Any = None,
        enabled: bool = True,
    ) -> None:
        self._text = text
        self.action = action
        self.checked = checked
        self.enabled = enabled

    @property
    def text(self) -> str:
        return str(self._text(self)) if callable(self._text) else str(self._text)

    def is_checked(self) -> bool:
        return bool(self.checked(self)) if callable(self.checked) else bool(self.checked)


class FakeMenu:
    """Minimal pystray.Menu double retaining its ordered FakeMenuItem list."""

    def __init__(self, *items: FakeMenuItem) -> None:
        self.items = list(items)


class FakeIcon:
    """Minimal pystray.Icon double capturing menu refreshes, notifications, and lifecycle."""

    def __init__(self, name: str, icon: Any, title: str, menu: FakeMenu | None = None) -> None:
        self.name = name
        self.icon = icon
        self.title = title
        self.menu = menu
        self.update_menu_calls = 0
        self.notifications: list[tuple[str, str]] = []
        self.run_calls = 0
        self.stop_calls = 0

    def update_menu(self) -> None:
        self.update_menu_calls += 1

    def notify(self, message: str, title: str | None = None) -> None:
        self.notifications.append((message, title or ""))

    def run(self) -> None:
        self.run_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


class FakeService:
    """Fake ModSyncService capturing control calls from ModSyncTrayApp."""

    def __init__(self, config: Config, *, on_status: Any = None) -> None:
        self.config = config
        self.on_status = on_status
        self.sync_requests = 0
        self.install_recommended_requests = 0
        self.reconfigured_configs: list[Config] = []
        self.stop_calls = 0

    def request_sync(self) -> None:
        self.sync_requests += 1

    def request_install_recommended(self) -> None:
        self.install_recommended_requests += 1

    def reconfigure(self, config: Config) -> None:
        self.config = config
        self.reconfigured_configs.append(config)

    def stop(self) -> None:
        self.stop_calls += 1

    async def run(self) -> None:
        return None


@pytest.fixture()
def tray_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Any, Any, Config, Path]:
    """Provide ModSyncTrayApp module and factory backed by fake pystray and ModSyncService."""
    fake_pystray = types.ModuleType("pystray")
    fake_pystray.Icon = FakeIcon  # type: ignore[attr-defined]
    fake_pystray.Menu = FakeMenu  # type: ignore[attr-defined]
    fake_pystray.MenuItem = FakeMenuItem  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)

    import modsync_client.tray as tray_mod

    monkeypatch.setattr(tray_mod, "pystray", fake_pystray)
    monkeypatch.setattr(tray_mod, "ModSyncService", FakeService)

    cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
    cfg_path = tmp_path / "config.json"

    def _make_app() -> Any:
        return tray_mod.ModSyncTrayApp(cfg, cfg_path)

    return tray_mod, _make_app, cfg, cfg_path


def test_build_menu_items_and_platform_autostart_visibility(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env

    monkeypatch.setattr(sys, "platform", "linux")
    linux_app = make_app()
    linux_items = linux_app.icon.menu.items
    assert linux_items[0].enabled is False
    assert linux_items[0].action is None
    assert linux_items[0].text == "Status: Starting..."
    linux_app.status_text = "Up to date"
    assert linux_items[0].text == "Status: Up to date"

    linux_labels = [item.text for item in linux_items[1:]]
    assert linux_labels == [
        "Sync Now",
        "Install Recommended Client Mods",
        "Open Mods Folder",
        "Configure...",
        "Check for Updates...",
        "Quit",
    ]
    assert "Start with Windows" not in linux_labels

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(tray_mod, "is_windows_autostart_enabled", lambda: True)
    win_app = make_app()
    win_items = win_app.icon.menu.items
    win_labels = [item.text for item in win_items[1:]]
    assert win_labels == [
        "Sync Now",
        "Install Recommended Client Mods",
        "Open Mods Folder",
        "Configure...",
        "Check for Updates...",
        "Start with Windows",
        "Quit",
    ]
    autostart_item = win_items[-2]
    assert autostart_item.is_checked() is True


def test_on_status_update_truncates_title_updates_icon_and_dedups_notifications(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    badge_colors: list[str] = []

    def _fake_badge(color: str) -> str:
        badge_colors.append(color)
        return f"badge:{color}"

    monkeypatch.setattr(tray_mod, "make_badge_icon", _fake_badge)
    app = make_app()

    long_msg = "x" * (tray_mod.MAX_TRAY_TITLE_LENGTH + 40)
    app._on_status_update(SyncStatus.SYNCING, long_msg, None)
    assert app.status == SyncStatus.SYNCING
    assert app.status_text == long_msg
    assert app.icon.icon == f"badge:{tray_mod.STATUS_COLORS[SyncStatus.SYNCING]}"
    assert badge_colors[-1] == tray_mod.STATUS_COLORS[SyncStatus.SYNCING]
    assert len(app.icon.title) == tray_mod.MAX_TRAY_TITLE_LENGTH
    assert app.icon.title.startswith("ModSync — ")
    assert app.icon.update_menu_calls == 1
    assert app.icon.notifications == []

    # Empty SyncResult changes must not emit a notification
    empty_res = SyncResult(status=SyncStatus.SYNCED, version="v1", mod_count=2)
    app._on_status_update(SyncStatus.SYNCED, "No changes", empty_res)
    assert app.icon.notifications == []

    # Non-empty changes notify once per status:version key
    added_res = SyncResult(
        status=SyncStatus.SYNCED,
        version="v2",
        mod_count=3,
        added=("create.jar",),
    )
    app._on_status_update(SyncStatus.SYNCED, "Added create.jar", added_res)
    app._on_status_update(SyncStatus.SYNCED, "Added create.jar again", added_res)
    assert app.icon.notifications == [("Added create.jar", "ModSync")]

    updated_res = SyncResult(
        status=SyncStatus.SYNCED,
        version="v3",
        mod_count=3,
        updated=("jei.jar",),
    )
    app._on_status_update(SyncStatus.SYNCED, "Updated jei.jar", updated_res)
    assert app.icon.notifications == [
        ("Added create.jar", "ModSync"),
        ("Updated jei.jar", "ModSync"),
    ]


def test_menu_callbacks_delegate_to_service_and_desktop(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
    tmp_path: Path,
) -> None:
    tray_mod, make_app, cfg, cfg_path = tray_env
    opened_paths: list[Path] = []
    saved_configs: list[tuple[Config, Path]] = []
    autostart_calls: list[bool] = []
    autostart_state = False

    monkeypatch.setattr(tray_mod, "open_folder", opened_paths.append)
    monkeypatch.setattr(tray_mod, "save_config", lambda c, p: saved_configs.append((c, p)))
    monkeypatch.setattr(tray_mod, "is_windows_autostart_enabled", lambda: autostart_state)

    def _fake_set_autostart(enabled: bool) -> bool:
        nonlocal autostart_state
        autostart_calls.append(enabled)
        autostart_state = enabled
        return enabled

    monkeypatch.setattr(tray_mod, "set_windows_autostart", _fake_set_autostart)

    app = make_app()

    app._on_sync_now(app.icon, None)
    assert app.service.sync_requests == 1

    app._on_install_recommended(app.icon, None)
    assert app.service.install_recommended_requests == 1

    app._on_open_folder(app.icon, None)
    assert opened_paths == [cfg.mods_path]

    # Cancelled configure dialog is a no-op
    monkeypatch.setattr(tray_mod, "prompt_config_gui", lambda _existing: None)
    app._on_configure(app.icon, None)
    assert app.config == cfg
    assert saved_configs == []
    assert app.service.reconfigured_configs == []

    # Confirmed configure dialog updates config, persists, and reconfigures service
    new_cfg = Config(server_url="https://new.example", mods_dir=str(tmp_path / "new-mods"))
    monkeypatch.setattr(tray_mod, "prompt_config_gui", lambda _existing: new_cfg)
    app._on_configure(app.icon, None)
    assert app.config == new_cfg
    assert saved_configs == [(new_cfg, cfg_path)]
    assert app.service.reconfigured_configs == [new_cfg]

    # Toggle autostart twice and verify update_menu is called each time
    app._on_toggle_autostart(app.icon, None)
    app._on_toggle_autostart(app.icon, None)
    assert autostart_calls == [True, False]
    assert app.icon.update_menu_calls == 2

    app._on_quit(app.icon, None)
    assert app.service.stop_calls == 1
    assert app.icon.stop_calls == 1


def test_run_update_check_non_interactive_notifies_without_dialogs(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    update = UpdateInfo(
        version="9.9.9",
        tag_name="client-v9.9.9",
        html_url="https://example.test/release",
        asset_name="ModSync-linux",
        download_url="https://example.test/ModSync-linux",
        expected_sha256="a" * 64,
    )
    app = make_app()

    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(
        app,
        "_prompt_update_dialog",
        lambda _upd: pytest.fail("_prompt_update_dialog must not run when interactive=False"),
    )
    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda *_a, **_kw: pytest.fail("_show_info_dialog must not run when interactive=False"),
    )

    app._run_update_check(interactive=False)
    assert len(app.icon.notifications) == 1
    assert "9.9.9" in app.icon.notifications[0][0]
    assert app.icon.notifications[0][1] == "ModSync Update"


def test_run_update_check_interactive_up_to_date_and_error_dialogs(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    dialogs: list[tuple[str, str, bool]] = []
    app = make_app()

    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda title, message, *, error=False: dialogs.append((title, message, error)),
    )

    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: None)
    app._run_update_check(interactive=True)
    assert len(dialogs) == 1
    assert dialogs[0][0] == "ModSync Update Check"
    assert __version__ in dialogs[0][1]
    assert dialogs[0][2] is False

    def _boom(_ver: str) -> UpdateInfo | None:
        raise RuntimeError("network offline")

    monkeypatch.setattr(tray_mod, "check_for_update", _boom)
    app._run_update_check(interactive=True)
    assert len(dialogs) == 2
    assert dialogs[1][0] == "ModSync Update Check"
    assert "network offline" in dialogs[1][1]
    assert dialogs[1][2] is True


def test_run_update_check_interactive_frozen_confirmed_installs_and_relaunches(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    update = UpdateInfo(
        version="9.9.9",
        tag_name="client-v9.9.9",
        html_url="https://example.test/release",
        asset_name="ModSync.exe",
        download_url="https://example.test/ModSync.exe",
        expected_sha256="b" * 64,
    )
    downloaded: list[UpdateInfo] = []
    relaunched: list[bool] = []
    app = make_app()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(app, "_prompt_update_dialog", lambda _upd: True)
    monkeypatch.setattr(tray_mod, "download_and_apply_update", downloaded.append)
    monkeypatch.setattr(tray_mod, "relaunch_executable", lambda: relaunched.append(True))

    app._run_update_check(interactive=True)
    assert downloaded == [update]
    assert relaunched == [True]
    assert app.service.stop_calls == 1
    assert app.icon.stop_calls == 1
