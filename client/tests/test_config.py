"""Unit tests for ModSync client configuration, URL building, and CLI resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from modsync_client.config import Config, build_ws_url, load_config, save_config
from modsync_client.main import build_parser
from modsync_client.onboarding import resolve_or_setup_config


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
