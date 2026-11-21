"""Unit tests for ModSync client configuration, invite URI parsing, and CLI resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from modsync_client.config import (
    Config,
    build_invite_url,
    build_ws_url,
    load_config,
    parse_server_input,
    resolve_mods_dir,
    save_config,
)
from modsync_client.main import build_parser
from modsync_client.onboarding import prompt_config_cli, resolve_or_setup_config


def test_build_ws_url() -> None:
    assert build_ws_url("https://mods.example.com/") == "wss://mods.example.com/ws"
    assert (
        build_ws_url("http://127.0.0.1:8080", "tok123")
        == "ws://127.0.0.1:8080/ws?token=tok123"
    )
    assert build_ws_url("wss://mods.example.com/ws") == "wss://mods.example.com/ws"


@pytest.mark.parametrize("bad_url", ["", "ftp://invalid", "https://", "not-a-url"])
def test_build_ws_url_rejects_invalid_urls(bad_url: str) -> None:
    with pytest.raises(ValueError, match="Invalid server URL"):
        build_ws_url(bad_url)


def test_config_persistence_and_properties(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    assert load_config(cfg_path) is None

    cfg = Config(server_url="https://mods.example.com/", mods_dir=str(tmp_path / "mods"))
    assert cfg.normalized_server_url == "https://mods.example.com"
    assert cfg.mods_path == tmp_path / "mods"

    save_config(cfg, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded == cfg


def test_resolve_or_setup_config_from_cli_and_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "config.json"
    parser = build_parser()

    monkeypatch.setenv("MODSYNC_SERVER_URL", "https://env.example.com/")
    monkeypatch.setenv("MODSYNC_MODS_DIR", str(tmp_path / "env-mods"))
    monkeypatch.setenv("MODSYNC_CLIENT_TOKEN", "env-token")

    args = parser.parse_args(["--config", str(cfg_path), "--headless"])
    resolved_env = resolve_or_setup_config(args)
    assert resolved_env == Config(
        server_url="https://env.example.com",
        mods_dir=str(tmp_path / "env-mods"),
        client_token="env-token",
    )

    override_args = parser.parse_args(
        [
            "--config",
            str(cfg_path),
            "--server-url",
            "https://cli.example.com/",
            "--token",
            "cli-token",
        ]
    )
    resolved_override = resolve_or_setup_config(override_args)
    assert resolved_override.server_url == "https://cli.example.com"
    assert resolved_override.client_token == "cli-token"
    assert resolved_override.mods_dir == str(tmp_path / "env-mods")


def test_resolve_mods_dir_from_minecraft_folders(tmp_path: Path) -> None:
    direct_mods = tmp_path / "profile" / "mods"
    assert resolve_mods_dir(direct_mods) == direct_mods

    modrinth_profile = tmp_path / "ModrinthProfile"
    modrinth_profile.mkdir()
    assert resolve_mods_dir(modrinth_profile) == modrinth_profile / "mods"

    prism_instance = tmp_path / "PrismInstance"
    (prism_instance / ".minecraft" / "mods").mkdir(parents=True)
    assert resolve_mods_dir(prism_instance) == prism_instance / ".minecraft" / "mods"

    dot_mc_only = tmp_path / "PlainInstance"
    (dot_mc_only / ".minecraft").mkdir(parents=True)
    assert resolve_mods_dir(dot_mc_only) == dot_mc_only / ".minecraft" / "mods"


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


def test_build_and_parse_invite_url() -> None:
    invite = build_invite_url("https://mods.example.com/", "secret-123")
    assert invite == "modsync://connect?url=https%3A%2F%2Fmods.example.com&token=secret-123"
    assert parse_server_input(invite) == ("https://mods.example.com", "secret-123")

    no_token_invite = build_invite_url("http://localhost:8080")
    assert parse_server_input(no_token_invite) == ("http://localhost:8080", None)
    assert parse_server_input("https://mods.example.com/") == ("https://mods.example.com", None)

    for bad in ("", "modsync://connect", "modsync://connect?url=ftp://bad", "not-a-url"):
        with pytest.raises(ValueError):
            parse_server_input(bad)


def test_resolve_or_setup_config_with_invite_uri(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    mods_dir = tmp_path / "mods"
    invite = build_invite_url("https://mods.example.com", "invite-tok")

    args = build_parser().parse_args([invite, "--config", str(cfg_path), "--mods-dir", str(mods_dir)])
    resolved = resolve_or_setup_config(args)
    assert resolved == Config(
        server_url="https://mods.example.com",
        mods_dir=str(mods_dir),
        client_token="invite-tok",
    )

    new_invite = build_invite_url("https://new.example.com", "new-tok")
    update_args = build_parser().parse_args([new_invite, "--config", str(cfg_path)])
    updated = resolve_or_setup_config(update_args)
    assert updated == Config(
        server_url="https://new.example.com",
        mods_dir=str(mods_dir),
        client_token="new-tok",
    )


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
    import modsync_client.onboarding as onboarding

    monkeypatch.setattr(onboarding, "prompt_config_gui", lambda *_a, **_kw: None)
    with pytest.raises(SystemExit) as exc_info:
        onboarding.setup_gui_or_cli(None)
    assert exc_info.value.code == 0


def test_prompt_config_gui_steps_and_cancellations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import sys
    import types
    import modsync_client.onboarding as onboarding

    invite = build_invite_url("https://mods.example.com", "gui-tok")
    mc_dir = tmp_path / "Instance"
    mc_dir.mkdir()

    def _install_fake_tk(
        askstring_replies: list[str | None],
        askokcancel_reply: bool = True,
        askdirectory_reply: str = "",
    ) -> list[tuple[str, str]]:
        errors_shown: list[tuple[str, str]] = []
        replies = iter(askstring_replies)

        fake_tk = types.ModuleType("tkinter")

        class FakeRoot:
            def withdraw(self) -> None:
                pass

            def attributes(self, *_a: object) -> None:
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

    # Step 1 cancel
    _install_fake_tk([None])
    with pytest.raises(SystemExit) as exc1:
        onboarding.setup_gui_or_cli(None)
    assert exc1.value.code == 0

    # Invalid invite -> error dialog -> Step 2 cancel
    errors = _install_fake_tk(["ftp://bad", invite], askokcancel_reply=False)
    with pytest.raises(SystemExit) as exc2:
        onboarding.setup_gui_or_cli(None)
    assert exc2.value.code == 0
    assert len(errors) == 1
    assert errors[0][0] == "Invalid Invite Link"

    # Step 3 cancel (folder picker cancelled)
    _install_fake_tk([invite], askokcancel_reply=True, askdirectory_reply="")
    with pytest.raises(SystemExit) as exc3:
        onboarding.setup_gui_or_cli(None)
    assert exc3.value.code == 0

    # Full completion
    _install_fake_tk([invite], askokcancel_reply=True, askdirectory_reply=str(mc_dir))
    cfg = onboarding.setup_gui_or_cli(None)
    assert cfg == Config(
        server_url="https://mods.example.com",
        mods_dir=str(mc_dir / "mods"),
        client_token="gui-tok",
    )


