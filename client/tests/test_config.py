"""Unit tests for ModSync client configuration, invite URI parsing, and onboarding."""

from __future__ import annotations

import io
import sys
import types
from collections.abc import Callable
from pathlib import Path

import pytest

import modsync_client.onboarding as onboarding
from modsync_client.config import (
    Config,
    build_invite_url,
    build_ws_url,
    default_data_dir,
    load_config,
    parse_server_input,
    resolve_mods_dir,
    save_config,
)
from modsync_client.main import build_parser
from modsync_client.onboarding import prompt_config_cli, resolve_or_setup_config


@pytest.fixture(autouse=True)
def _disable_host_mc_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent onboarding tests from scanning the host filesystem for launchers."""
    monkeypatch.setattr(onboarding, "detect_minecraft_dirs", list)


@pytest.fixture
def install_fake_tk(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[tuple[str, str]]]:
    """Install fake tkinter modules into sys.modules and return recorded errors."""

    def _install(
        askstring_replies: list[str | None],
        *,
        askokcancel_reply: bool = True,
        askdirectory_reply: str = "",
    ) -> list[tuple[str, str]]:
        errors_shown: list[tuple[str, str]] = []
        replies = iter(askstring_replies)

        fake_tk = types.ModuleType("tkinter")

        class FakeRoot:
            def withdraw(self) -> None:
                pass

            def attributes(self, *_args: object) -> None:
                pass

            def update_idletasks(self) -> None:
                pass

            def destroy(self) -> None:
                pass

        fake_tk.Tk = FakeRoot  # type: ignore[attr-defined]

        fake_simple = types.ModuleType("tkinter.simpledialog")
        fake_simple.askstring = lambda *_a, **_kw: next(replies, None)  # type: ignore[attr-defined]

        fake_msg = types.ModuleType("tkinter.messagebox")
        fake_msg.showerror = lambda title, msg, **_kw: errors_shown.append((title, msg))  # type: ignore[attr-defined]
        fake_msg.askokcancel = lambda *_a, **_kw: askokcancel_reply  # type: ignore[attr-defined]

        fake_file = types.ModuleType("tkinter.filedialog")
        fake_file.askdirectory = lambda *_a, **_kw: askdirectory_reply  # type: ignore[attr-defined]

        fake_tk.simpledialog = fake_simple  # type: ignore[attr-defined]
        fake_tk.messagebox = fake_msg  # type: ignore[attr-defined]
        fake_tk.filedialog = fake_file  # type: ignore[attr-defined]

        monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
        monkeypatch.setitem(sys.modules, "tkinter.simpledialog", fake_simple)
        monkeypatch.setitem(sys.modules, "tkinter.messagebox", fake_msg)
        monkeypatch.setitem(sys.modules, "tkinter.filedialog", fake_file)
        return errors_shown

    return _install


@pytest.mark.parametrize(
    ("server_url", "token", "expected"),
    [
        ("https://mods.example.com/", "", "wss://mods.example.com/ws"),
        ("http://127.0.0.1:8080", "tok123", "ws://127.0.0.1:8080/ws?token=tok123"),
        ("wss://mods.example.com/ws", "", "wss://mods.example.com/ws"),
        ("https://mods.example.com/sub/", "", "wss://mods.example.com/sub/ws"),
        (
            "https://mods.example.com/sub?v=2",
            "",
            "wss://mods.example.com/sub/ws?v=2",
        ),
        (
            "https://mods.example.com/sub?v=2",
            "tok123",
            "wss://mods.example.com/sub/ws?token=tok123",
        ),
    ],
)
def test_build_ws_url(server_url: str, token: str, expected: str) -> None:
    assert build_ws_url(server_url, token) == expected


@pytest.mark.parametrize("bad_url", ["", "ftp://invalid", "https://", "not-a-url"])
def test_build_ws_url_rejects_invalid_urls(bad_url: str) -> None:
    with pytest.raises(ValueError, match="Invalid server URL"):
        build_ws_url(bad_url)


def test_load_config_returns_none_when_file_missing(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.json") is None


def test_load_config_returns_none_for_non_dict_json(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('["not", "a", "dict"]', encoding="utf-8")

    assert load_config(cfg_path) is None


def test_config_properties() -> None:
    cfg = Config(server_url="  https://mods.example.com/ ", mods_dir="~/minecraft/mods")

    assert cfg.normalized_server_url == "https://mods.example.com"
    assert cfg.mods_path == Path.home() / "minecraft" / "mods"


@pytest.mark.parametrize(
    "raw",
    [
        {"server_url": "", "mods_dir": "/mods"},
        {"server_url": "   ", "mods_dir": "/mods"},
        {"server_url": "https://mods.example.com", "mods_dir": ""},
        {"server_url": "https://mods.example.com"},
        {"mods_dir": "/mods"},
    ],
)
def test_config_from_dict_rejects_blank_required_fields(raw: dict[str, object]) -> None:
    assert Config.from_dict(raw) is None


def test_save_and_load_config_roundtrip(tmp_path: Path) -> None:
    cfg_path = tmp_path / "nested" / "config.json"
    cfg = Config(
        server_url="https://mods.example.com",
        mods_dir=str(tmp_path / "mods"),
        client_token="secret",
        poll_fallback_seconds=120,
    )

    saved_path = save_config(cfg, cfg_path)

    assert saved_path == cfg_path
    assert load_config(cfg_path) == cfg


@pytest.mark.parametrize(
    ("platform", "env_overrides", "expected_parts"),
    [
        ("win32", {"APPDATA": "/custom/appdata"}, ("/custom/appdata", "ModSync")),
        ("win32", {"APPDATA": None}, ("AppData", "Roaming", "ModSync")),
        ("darwin", {}, ("Library", "Application Support", "ModSync")),
        ("linux", {"XDG_CONFIG_HOME": "/custom/xdg"}, ("/custom/xdg", "modsync")),
        ("linux", {"XDG_CONFIG_HOME": None}, (".config", "modsync")),
    ],
    ids=[
        "win32-appdata-env",
        "win32-home-fallback",
        "darwin",
        "linux-xdg-env",
        "linux-home-fallback",
    ],
)
def test_default_data_dir(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    env_overrides: dict[str, str | None],
    expected_parts: tuple[str, ...],
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    for key, value in env_overrides.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    result = default_data_dir()

    if expected_parts[0].startswith("/"):
        assert result == Path(*expected_parts)
    else:
        assert result == Path.home().joinpath(*expected_parts)


@pytest.mark.parametrize(
    ("selected_rel", "existing_subpath", "expected_rel"),
    [
        ("profile/mods", None, "profile/mods"),
        ("profile/Mods", None, "profile/Mods"),
        ("ModrinthProfile", None, "ModrinthProfile/mods"),
        ("ATInstance", "minecraft/mods", "ATInstance/minecraft/mods"),
        ("PrismInstance", ".minecraft/mods", "PrismInstance/.minecraft/mods"),
        ("PlainInstance", ".minecraft", "PlainInstance/.minecraft/mods"),
    ],
    ids=[
        "direct-mods",
        "case-insensitive-Mods",
        "modrinth-profile",
        "minecraft-mods-subdir",
        "dot-minecraft-mods-subdir",
        "dot-minecraft-without-mods",
    ],
)
def test_resolve_mods_dir(
    tmp_path: Path,
    selected_rel: str,
    existing_subpath: str | None,
    expected_rel: str,
) -> None:
    selected = tmp_path / selected_rel
    if existing_subpath is not None:
        (selected / existing_subpath).mkdir(parents=True)
    elif selected.name.lower() != "mods":
        selected.mkdir(parents=True)

    assert resolve_mods_dir(selected) == tmp_path / expected_rel


@pytest.mark.parametrize(
    ("server_url", "token", "expected"),
    [
        (
            "https://mods.example.com/",
            "secret-123",
            "modsync://connect?url=https%3A%2F%2Fmods.example.com&token=secret-123",
        ),
        (
            "http://localhost:8080",
            "",
            "modsync://connect?url=http%3A%2F%2Flocalhost%3A8080",
        ),
        (
            "  https://mods.example.com/  ",
            "  tok  ",
            "modsync://connect?url=https%3A%2F%2Fmods.example.com&token=tok",
        ),
    ],
)
def test_build_invite_url(server_url: str, token: str, expected: str) -> None:
    assert build_invite_url(server_url, token) == expected


@pytest.mark.parametrize("bad_url", ["", "ftp://bad", "https://", "not-a-url"])
def test_build_invite_url_rejects_invalid_urls(bad_url: str) -> None:
    with pytest.raises(ValueError, match="Invalid server URL"):
        build_invite_url(bad_url)


@pytest.mark.parametrize(
    ("raw_input", "expected"),
    [
        (
            "modsync://connect?url=https%3A%2F%2Fmods.example.com&token=secret-123",
            ("https://mods.example.com", "secret-123"),
        ),
        (
            "modsync://connect?url=http%3A%2F%2Flocalhost%3A8080",
            ("http://localhost:8080", None),
        ),
        ("https://mods.example.com/", ("https://mods.example.com", None)),
        ("http://127.0.0.1:8080", ("http://127.0.0.1:8080", None)),
    ],
)
def test_parse_server_input(raw_input: str, expected: tuple[str, str | None]) -> None:
    assert parse_server_input(raw_input) == expected


@pytest.mark.parametrize(
    "bad_input",
    ["", "   ", "modsync://connect", "modsync://connect?url=ftp://bad", "not-a-url"],
)
def test_parse_server_input_rejects_invalid_inputs(bad_input: str) -> None:
    with pytest.raises(ValueError):
        parse_server_input(bad_input)


def test_resolve_or_setup_config_falls_back_to_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("MODSYNC_SERVER_URL", "https://env.example.com/")
    monkeypatch.setenv("MODSYNC_MODS_DIR", str(tmp_path / "env-mods"))
    monkeypatch.setenv("MODSYNC_CLIENT_TOKEN", "env-token")

    args = build_parser().parse_args(["--config", str(cfg_path), "--headless"])
    resolved = resolve_or_setup_config(args)

    expected = Config(
        server_url="https://env.example.com",
        mods_dir=str(tmp_path / "env-mods"),
        client_token="env-token",
    )
    assert resolved == expected
    assert load_config(cfg_path) == expected


def test_resolve_or_setup_config_applies_cli_overrides_to_saved_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    initial = Config(
        server_url="https://saved.example.com",
        mods_dir=str(tmp_path / "saved-mods"),
        client_token="saved-token",
    )
    save_config(initial, cfg_path)

    args = build_parser().parse_args(
        [
            "--config",
            str(cfg_path),
            "--server-url",
            "https://cli.example.com/",
            "--token",
            "cli-token",
        ]
    )
    resolved = resolve_or_setup_config(args)

    expected = Config(
        server_url="https://cli.example.com",
        mods_dir=str(tmp_path / "saved-mods"),
        client_token="cli-token",
    )
    assert resolved == expected
    assert load_config(cfg_path) == expected


def test_resolve_or_setup_config_with_invite_uri_initial_setup(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    target_mods = tmp_path / "mods"
    invite = build_invite_url("https://mods.example.com", "invite-tok")

    args = build_parser().parse_args(
        [invite, "--config", str(cfg_path), "--mods-dir", str(target_mods)]
    )
    resolved = resolve_or_setup_config(args)

    expected = Config(
        server_url="https://mods.example.com",
        mods_dir=str(target_mods),
        client_token="invite-tok",
    )
    assert resolved == expected
    assert load_config(cfg_path) == expected


def test_resolve_or_setup_config_with_invite_uri_updates_saved_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    target_mods = tmp_path / "mods"
    save_config(
        Config(
            server_url="https://old.example.com",
            mods_dir=str(target_mods),
            client_token="old-tok",
        ),
        cfg_path,
    )

    new_invite = build_invite_url("https://new.example.com", "new-tok")
    args = build_parser().parse_args([new_invite, "--config", str(cfg_path)])
    updated = resolve_or_setup_config(args)

    expected = Config(
        server_url="https://new.example.com",
        mods_dir=str(target_mods),
        client_token="new-tok",
    )
    assert updated == expected
    assert load_config(cfg_path) == expected


def test_resolve_or_setup_config_with_setup_flag_reprompts_and_saves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "config.json"
    existing = Config(
        server_url="https://old.example.com",
        mods_dir=str(tmp_path / "old-mods"),
        client_token="old-tok",
    )
    save_config(existing, cfg_path)
    reprompted = Config(
        server_url="https://fresh.example.com",
        mods_dir=str(tmp_path / "fresh-mods"),
        client_token="fresh-tok",
    )
    seen_existing: list[Config | None] = []

    def _fake_prompt(cfg: Config | None, **_kwargs: object) -> Config:
        seen_existing.append(cfg)
        return reprompted

    monkeypatch.setattr(onboarding, "prompt_config_cli", _fake_prompt)
    args = build_parser().parse_args(["--config", str(cfg_path), "--setup", "--headless"])
    resolved = resolve_or_setup_config(args)

    assert seen_existing == [existing]
    assert resolved == reprompted
    assert load_config(cfg_path) == reprompted


def test_resolve_or_setup_config_with_server_url_and_mods_dir_saves_directly(
    tmp_path: Path,
) -> None:
    cfg_path = tmp_path / "config.json"
    save_config(
        Config(
            server_url="https://old.example.com",
            mods_dir=str(tmp_path / "old-mods"),
            client_token="kept-token",
        ),
        cfg_path,
    )
    new_mods = tmp_path / "new-mods"
    args = build_parser().parse_args(
        [
            "--config",
            str(cfg_path),
            "--server-url",
            "https://direct.example.com/",
            "--mods-dir",
            str(new_mods),
        ]
    )

    resolved = resolve_or_setup_config(args)

    expected = Config(
        server_url="https://direct.example.com",
        mods_dir=str(new_mods),
        client_token="kept-token",
    )
    assert resolved == expected
    assert load_config(cfg_path) == expected


def test_resolve_or_setup_config_headless_non_tty_without_config_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "missing.json"
    monkeypatch.setattr(onboarding, "_is_interactive_tty", lambda: False)
    args = build_parser().parse_args(["--config", str(cfg_path), "--headless"])

    with pytest.raises(SystemExit, match="No config found"):
        resolve_or_setup_config(args)


def test_prompt_config_cli_skips_url_when_preset_url_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc_folder = tmp_path / "MyInstance"
    mc_folder.mkdir()
    prompts: list[str] = []

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return str(mc_folder)

    monkeypatch.setattr("builtins.input", fake_input)
    cfg = prompt_config_cli(
        None,
        preset_url="https://mods.example.com/",
        preset_token="preset-token",
    )

    assert len(prompts) == 1
    assert "Minecraft folder" in prompts[0]
    assert cfg == Config(
        server_url="https://mods.example.com",
        mods_dir=str(mc_folder / "mods"),
        client_token="preset-token",
    )


def test_prompt_config_cli_requires_url_on_first_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    with pytest.raises(SystemExit, match="Server URL or invite link is required"):
        prompt_config_cli(None)


def test_prompt_config_cli_requires_minecraft_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    with pytest.raises(SystemExit, match="Minecraft folder path is required"):
        prompt_config_cli(None, preset_url="https://mods.example.com")


@pytest.mark.parametrize("exc_type", [EOFError, KeyboardInterrupt])
def test_prompt_config_cli_cancellation_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    exc_type: type[BaseException],
) -> None:
    def raise_cancel(_prompt: str = "") -> str:
        raise exc_type()

    monkeypatch.setattr("builtins.input", raise_cancel)

    with pytest.raises(SystemExit) as exc_info:
        prompt_config_cli(None)
    assert exc_info.value.code == 0


def test_setup_gui_or_cli_cancellation_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(onboarding, "prompt_config_gui", lambda *_a, **_kw: None)

    with pytest.raises(SystemExit) as exc_info:
        onboarding.setup_gui_or_cli(None)
    assert exc_info.value.code == 0


def test_setup_gui_or_cli_falls_back_to_cli_in_tty_when_gui_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected = Config(server_url="https://mods.example.com", mods_dir=str(tmp_path / "mods"))

    def _unavailable_gui(*_args: object, **_kwargs: object) -> None:
        onboarding._last_gui_unavailable = True
        return None

    monkeypatch.setattr(onboarding, "prompt_config_gui", _unavailable_gui)
    monkeypatch.setattr(onboarding, "_is_interactive_tty", lambda: True)
    monkeypatch.setattr(onboarding, "prompt_config_cli", lambda *_a, **_kw: expected)

    assert onboarding.setup_gui_or_cli(None) == expected


def test_prompt_config_gui_step1_cancel_returns_none(
    install_fake_tk: Callable[..., list[tuple[str, str]]],
) -> None:
    install_fake_tk([None])

    assert onboarding.prompt_config_gui(None) is None


def test_prompt_config_gui_invalid_invite_shows_error_and_allows_retry_cancel(
    install_fake_tk: Callable[..., list[tuple[str, str]]],
) -> None:
    errors = install_fake_tk(["ftp://bad", None])

    result = onboarding.prompt_config_gui(None)

    assert result is None
    assert len(errors) == 1
    assert errors[0][0] == "Invalid Invite Link"


def test_prompt_config_gui_step3_cancel_returns_none(
    install_fake_tk: Callable[..., list[tuple[str, str]]],
) -> None:
    invite = build_invite_url("https://mods.example.com", "gui-tok")
    install_fake_tk([invite], askokcancel_reply=True, askdirectory_reply="")

    assert onboarding.prompt_config_gui(None) is None


def test_prompt_config_gui_completion_returns_config(
    install_fake_tk: Callable[..., list[tuple[str, str]]],
    tmp_path: Path,
) -> None:
    invite = build_invite_url("https://mods.example.com", "gui-tok")
    mc_dir = tmp_path / "Instance"
    mc_dir.mkdir()
    install_fake_tk([invite], askokcancel_reply=True, askdirectory_reply=str(mc_dir))

    cfg = onboarding.prompt_config_gui(None)

    assert cfg == Config(
        server_url="https://mods.example.com",
        mods_dir=str(mc_dir / "mods"),
        client_token="gui-tok",
    )


def test_resolve_or_setup_config_setup_invalid_invite_exits_nonzero_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(sys, "stdin", io.StringIO("modsync://connect?url=ftp://invalid\n"))
    args = build_parser().parse_args(["--config", str(cfg_path), "--setup", "--headless"])

    with pytest.raises(SystemExit) as exc_info:
        resolve_or_setup_config(args)

    assert exc_info.value.code not in (None, 0)
    assert "Invalid" in str(exc_info.value)
    assert not cfg_path.exists()


def test_resolve_or_setup_config_setup_eof_preserves_existing_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "config.json"
    save_config(
        Config(
            server_url="https://saved.example.com",
            mods_dir=str(tmp_path / "mods"),
            client_token="keep-token",
        ),
        cfg_path,
    )
    original_bytes = cfg_path.read_bytes()

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    args = build_parser().parse_args(["--config", str(cfg_path), "--setup", "--headless"])

    with pytest.raises(SystemExit) as exc_info:
        resolve_or_setup_config(args)

    assert exc_info.value.code == 0
    assert cfg_path.read_bytes() == original_bytes
