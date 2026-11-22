"""Unit tests for ModSyncTrayApp without requiring a live X11/Windows display."""

from __future__ import annotations

import importlib
import sys
import threading
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from modsync_client import __version__
from modsync_client.config import Config
from modsync_client.syncer import SyncResult, SyncStatus
from modsync_client.updater import UpdateInfo


class FakeMenuItem:
    """Minimal pystray.MenuItem double supporting callable text, checked, and enabled."""

    def __init__(
        self,
        text: Any,
        action: Any,
        checked: Any = None,
        enabled: Any = True,
    ) -> None:
        self._text = text
        self.action = action
        self._checked = checked
        self._enabled = enabled

    def __call__(self, icon: Any = None) -> None:
        if callable(self.action):
            self.action(icon, self)

    @property
    def text(self) -> str:
        return str(self._text(self)) if callable(self._text) else str(self._text)

    @property
    def checked(self) -> bool:
        return bool(self._checked(self)) if callable(self._checked) else bool(self._checked)

    @property
    def enabled(self) -> bool:
        return bool(self._enabled(self)) if callable(self._enabled) else bool(self._enabled)


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
        self.notifications.append((message, title or self.title))

    def run(self, setup: Any = None) -> None:
        self.run_calls += 1
        if setup is not None:
            setup(self)

    def stop(self) -> None:
        self.stop_calls += 1


class FakeService:
    """Fake ModSyncService capturing control calls from ModSyncTrayApp."""

    def __init__(
        self,
        config: Config,
        *,
        on_status: Any = None,
        staging_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.on_status = on_status
        self.staging_dir = staging_dir
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
        self.request_sync()

    def stop(self) -> None:
        self.stop_calls += 1

    async def run(self) -> None:
        return None


def _sample_update(asset_name: str = "ModSync-linux", html_url: str = "https://example.test/release") -> UpdateInfo:
    return UpdateInfo(
        version="9.9.9",
        tag_name="client-v9.9.9",
        html_url=html_url,
        asset_name=asset_name,
        download_url=f"https://example.test/{asset_name}",
        expected_sha256="a" * 64,
    )


def _find_menu_item(app: Any, label: str) -> FakeMenuItem:
    for item in app.icon.menu.items:
        if item.text == label:
            return item
    raise AssertionError(f"Menu item {label!r} not found")


@pytest.fixture
def tray_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Any, Any, Config, Path]]:
    """Provide an isolated modsync_client.tray module backed by fake pystray and ModSyncService."""
    monkeypatch.setattr(sys, "platform", "linux")

    fake_pystray = types.ModuleType("pystray")
    fake_pystray.Icon = FakeIcon  # type: ignore[attr-defined]
    fake_pystray.Menu = FakeMenu  # type: ignore[attr-defined]
    fake_pystray.MenuItem = FakeMenuItem  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)

    orig_tray = sys.modules.pop("modsync_client.tray", None)
    try:
        tray_mod = importlib.import_module("modsync_client.tray")
        monkeypatch.setattr(tray_mod, "ModSyncService", FakeService)

        cfg = Config(server_url="https://mods.example", mods_dir=str(tmp_path / "mods"))
        cfg_path = tmp_path / "config.json"

        def _make_app() -> Any:
            return tray_mod.ModSyncTrayApp(cfg, cfg_path)

        yield tray_mod, _make_app, cfg, cfg_path
    finally:
        sys.modules.pop("modsync_client.tray", None)
        if orig_tray is not None:
            sys.modules["modsync_client.tray"] = orig_tray


def test_menu_status_item_is_disabled_and_reflects_status_text(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()
    status_item = app.icon.menu.items[0]

    assert status_item.enabled is False
    assert status_item.action is None
    assert status_item.text == "Status: Starting..."

    app.status_text = "Up to date"
    assert status_item.text == "Status: Up to date"


def test_menu_items_exclude_autostart_on_linux(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()

    labels = [item.text for item in app.icon.menu.items[1:]]

    assert labels == [
        "Sync Now",
        "Install Recommended Client Mods",
        "Open Mods Folder",
        "Configure...",
        "Check for Updates...",
        "Quit",
    ]


def test_menu_items_include_autostart_on_win32_with_checked_state(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(tray_mod, "is_windows_autostart_enabled", lambda: True)

    app = make_app()
    labels = [item.text for item in app.icon.menu.items[1:]]
    autostart_item = _find_menu_item(app, "Start with Windows")

    assert labels == [
        "Sync Now",
        "Install Recommended Client Mods",
        "Open Mods Folder",
        "Configure...",
        "Check for Updates...",
        "Start with Windows",
        "Quit",
    ]
    assert autostart_item.checked is True


def test_status_update_sets_status_icon_badge_and_updates_menu(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    badge_colors: list[str] = []
    monkeypatch.setattr(
        tray_mod,
        "make_badge_icon",
        lambda color: badge_colors.append(color) or f"badge:{color}",
    )
    app = make_app()

    app.service.on_status(SyncStatus.SYNCING, "Checking mods...", None)

    assert app.status == SyncStatus.SYNCING
    assert app.status_text == "Checking mods..."
    assert app.icon.icon == f"badge:{tray_mod.STATUS_COLORS[SyncStatus.SYNCING]}"
    assert badge_colors[-1] == tray_mod.STATUS_COLORS[SyncStatus.SYNCING]
    assert app.icon.update_menu_calls == 1


def test_status_update_truncates_long_tray_title(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    app = make_app()
    long_msg = "x" * (tray_mod.MAX_TRAY_TITLE_LENGTH + 40)

    app.service.on_status(SyncStatus.SYNCING, long_msg, None)

    assert len(app.icon.title) == tray_mod.MAX_TRAY_TITLE_LENGTH
    assert app.icon.title.startswith("ModSync — ")


def test_status_update_with_empty_result_does_not_notify(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()
    empty_res = SyncResult(status=SyncStatus.SYNCED, version="v1", mod_count=2)

    app.service.on_status(SyncStatus.SYNCED, "No changes", empty_res)

    assert app.icon.notifications == []


def test_status_update_deduplicates_notifications_for_same_status_and_version(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()
    added_res = SyncResult(
        status=SyncStatus.SYNCED,
        version="v2",
        mod_count=3,
        added=("create.jar",),
    )

    app.service.on_status(SyncStatus.SYNCED, "Added create.jar", added_res)
    app.service.on_status(SyncStatus.SYNCED, "Added create.jar again", added_res)

    assert app.icon.notifications == [("Added create.jar", "ModSync")]


def test_status_update_notifies_again_when_version_changes(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()
    v2_res = SyncResult(status=SyncStatus.SYNCED, version="v2", mod_count=3, added=("create.jar",))
    v3_res = SyncResult(status=SyncStatus.SYNCED, version="v3", mod_count=3, updated=("jei.jar",))

    app.service.on_status(SyncStatus.SYNCED, "Added create.jar", v2_res)
    app.service.on_status(SyncStatus.SYNCED, "Updated jei.jar", v3_res)

    assert app.icon.notifications == [
        ("Added create.jar", "ModSync"),
        ("Updated jei.jar", "ModSync"),
    ]


def test_menu_sync_now_requests_sync(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()

    _find_menu_item(app, "Sync Now")(app.icon)

    assert app.service.sync_requests == 1


def test_menu_install_recommended_requests_install(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()

    _find_menu_item(app, "Install Recommended Client Mods")(app.icon)

    assert app.service.install_recommended_requests == 1


def test_menu_open_folder_opens_mods_path(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, cfg, _ = tray_env
    opened_paths: list[Path] = []
    monkeypatch.setattr(tray_mod, "open_folder", opened_paths.append)
    app = make_app()

    _find_menu_item(app, "Open Mods Folder")(app.icon)

    assert opened_paths == [cfg.mods_path]


def test_menu_configure_cancelled_leaves_config_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, cfg, _ = tray_env
    saved_configs: list[tuple[Config, Path]] = []
    monkeypatch.setattr(tray_mod, "save_config", lambda c, p: saved_configs.append((c, p)))
    monkeypatch.setattr(tray_mod, "prompt_config_gui", lambda _existing: None)
    app = make_app()

    _find_menu_item(app, "Configure...")(app.icon)

    assert app.config == cfg
    assert saved_configs == []
    assert app.service.reconfigured_configs == []


def test_menu_configure_confirmed_saves_and_reconfigures_service(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
    tmp_path: Path,
) -> None:
    tray_mod, make_app, _, cfg_path = tray_env
    saved_configs: list[tuple[Config, Path]] = []
    new_cfg = Config(server_url="https://new.example", mods_dir=str(tmp_path / "new-mods"))
    monkeypatch.setattr(tray_mod, "save_config", lambda c, p: saved_configs.append((c, p)))
    monkeypatch.setattr(tray_mod, "prompt_config_gui", lambda _existing: new_cfg)
    app = make_app()

    _find_menu_item(app, "Configure...")(app.icon)

    assert app.config == new_cfg
    assert saved_configs == [(new_cfg, cfg_path)]
    assert app.service.reconfigured_configs == [new_cfg]
    assert app.service.sync_requests == 1


@pytest.mark.parametrize(
    ("initial_state", "expected_new_state"),
    [(False, True), (True, False)],
)
def test_menu_autostart_toggle_updates_setting_and_refreshes_menu(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
    initial_state: bool,
    expected_new_state: bool,
) -> None:
    tray_mod, make_app, _, _ = tray_env
    autostart_calls: list[bool] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(tray_mod, "is_windows_autostart_enabled", lambda: initial_state)
    monkeypatch.setattr(
        tray_mod,
        "set_windows_autostart",
        lambda enabled: autostart_calls.append(enabled) or enabled,
    )
    app = make_app()

    _find_menu_item(app, "Start with Windows")(app.icon)

    assert autostart_calls == [expected_new_state]
    assert app.icon.update_menu_calls == 1


def test_menu_check_updates_triggers_interactive_check(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()
    called = threading.Event()
    interactive_flags: list[bool] = []

    def _fake_check(*, interactive: bool) -> None:
        interactive_flags.append(interactive)
        called.set()

    monkeypatch.setattr(app, "_run_update_check", _fake_check)

    _find_menu_item(app, "Check for Updates...")(app.icon)

    assert called.wait(timeout=2.0)
    assert interactive_flags == [True]


def test_menu_quit_stops_service_and_icon(
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    _, make_app, _, _ = tray_env
    app = make_app()

    _find_menu_item(app, "Quit")(app.icon)

    assert app.service.stop_calls == 1
    assert app.icon.stop_calls == 1


def test_run_starts_worker_and_startup_update_check_then_stops_service_on_exit(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    worker_ran = threading.Event()
    update_checked = threading.Event()

    async def _fake_service_run(_self: Any) -> None:
        worker_ran.set()

    monkeypatch.setattr(FakeService, "run", _fake_service_run)
    monkeypatch.setattr(
        tray_mod,
        "check_for_update",
        lambda _ver: update_checked.set() or None,
    )
    app = make_app()

    app.run()

    assert app.icon.run_calls == 1
    assert worker_ran.wait(timeout=2.0)
    assert update_checked.wait(timeout=2.0)
    assert app.service.stop_calls == 1


def test_run_stops_and_joins_service_even_when_icon_run_raises(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    update_checked = threading.Event()
    monkeypatch.setattr(
        tray_mod,
        "check_for_update",
        lambda _ver: update_checked.set() or None,
    )
    app = make_app()
    def _fail_run(_setup: Any = None) -> None:
        raise RuntimeError("tray backend failed")

    monkeypatch.setattr(app.icon, "run", _fail_run)

    with pytest.raises(RuntimeError, match="tray backend failed"):
        app.run()

    assert update_checked.wait(timeout=2.0)
    assert app.service.stop_calls == 1


def test_run_update_check_non_interactive_notifies_when_update_available(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    app = make_app()
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: _sample_update())
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


def test_run_update_check_non_interactive_silent_when_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    app = make_app()
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: None)
    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda *_a, **_kw: pytest.fail("_show_info_dialog must not run when interactive=False"),
    )

    app._run_update_check(interactive=False)

    assert app.icon.notifications == []


def test_run_update_check_non_interactive_ignores_check_error(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    app = make_app()

    def _boom(_ver: str) -> UpdateInfo | None:
        raise RuntimeError("offline")

    monkeypatch.setattr(tray_mod, "check_for_update", _boom)
    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda *_a, **_kw: pytest.fail("_show_info_dialog must not run when interactive=False"),
    )

    app._run_update_check(interactive=False)

    assert app.icon.notifications == []


def test_run_update_check_interactive_shows_info_when_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    dialogs: list[tuple[str, str, bool]] = []
    app = make_app()
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: None)
    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda title, message, *, error=False: dialogs.append((title, message, error)),
    )

    app._run_update_check(interactive=True)

    assert len(dialogs) == 1
    assert dialogs[0][0] == "ModSync Update Check"
    assert __version__ in dialogs[0][1]
    assert dialogs[0][2] is False


def test_run_update_check_interactive_shows_error_on_check_failure(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    dialogs: list[tuple[str, str, bool]] = []
    app = make_app()

    def _boom(_ver: str) -> UpdateInfo | None:
        raise RuntimeError("network offline")

    monkeypatch.setattr(tray_mod, "check_for_update", _boom)
    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda title, message, *, error=False: dialogs.append((title, message, error)),
    )

    app._run_update_check(interactive=True)

    assert len(dialogs) == 1
    assert dialogs[0][0] == "ModSync Update Check"
    assert "network offline" in dialogs[0][1]
    assert dialogs[0][2] is True


def test_run_update_check_interactive_declined_prompt_does_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    opened_urls: list[str] = []
    downloaded: list[UpdateInfo] = []
    app = make_app()
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: _sample_update())
    monkeypatch.setattr(app, "_prompt_update_dialog", lambda _upd: False)
    monkeypatch.setattr(tray_mod.webbrowser, "open", opened_urls.append)
    monkeypatch.setattr(tray_mod, "download_and_apply_update", downloaded.append)

    app._run_update_check(interactive=True)

    assert opened_urls == []
    assert downloaded == []
    assert app.service.stop_calls == 0


def test_run_update_check_interactive_non_frozen_confirmed_opens_release_url(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    opened_urls: list[str] = []
    update = _sample_update(html_url="https://github.com/org/repo/releases/tag/client-v9.9.9")
    app = make_app()
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(app, "_prompt_update_dialog", lambda _upd: True)
    monkeypatch.setattr(tray_mod.webbrowser, "open", opened_urls.append)

    app._run_update_check(interactive=True)

    assert opened_urls == ["https://github.com/org/repo/releases/tag/client-v9.9.9"]
    assert app.service.stop_calls == 0


def test_run_update_check_interactive_frozen_confirmed_installs_and_relaunches(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    update = _sample_update(asset_name="ModSync.exe")
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


def test_run_update_check_interactive_frozen_download_failure_shows_error_dialog(
    monkeypatch: pytest.MonkeyPatch,
    tray_env: tuple[Any, Any, Config, Path],
) -> None:
    tray_mod, make_app, _, _ = tray_env
    update = _sample_update(asset_name="ModSync.exe")
    dialogs: list[tuple[str, str, bool]] = []
    app = make_app()

    def _fail_download(_upd: UpdateInfo) -> Path:
        raise PermissionError("access denied")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(tray_mod, "check_for_update", lambda _ver: update)
    monkeypatch.setattr(app, "_prompt_update_dialog", lambda _upd: True)
    monkeypatch.setattr(tray_mod, "download_and_apply_update", _fail_download)
    monkeypatch.setattr(
        app,
        "_show_info_dialog",
        lambda title, message, *, error=False: dialogs.append((title, message, error)),
    )

    app._run_update_check(interactive=True)

    assert len(dialogs) == 1
    assert dialogs[0][0] == "ModSync Update Failed"
    assert "access denied" in dialogs[0][1]
    assert dialogs[0][2] is True
    assert app.service.stop_calls == 0
    assert app.icon.stop_calls == 0
