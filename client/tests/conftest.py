"""Shared pytest fixtures for modsync_client tests."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from modsync_client.updater import UpdateInfo

_CLEARED_ENV_VARS = (
    "MODSYNC_SERVER_URL",
    "MODSYNC_MODS_DIR",
    "MODSYNC_CLIENT_TOKEN",
    "MODSYNC_UPDATE_REPO",
    "MODSYNC_GITHUB_API_URL",
)


@pytest.fixture(autouse=True)
def isolate_host_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate environment variables, home paths, and frozen state from the host."""
    for name in _CLEARED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    env_root = tmp_path / "env"
    home_dir = env_root / "home"
    home_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("APPDATA", str(env_root / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(env_root / "localappdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(env_root / "xdg"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home_dir))
    monkeypatch.delattr(sys, "frozen", raising=False)


@pytest.fixture
def mods_dir(tmp_path: Path) -> Path:
    """Create and return an isolated temporary mods directory."""
    directory = tmp_path / "mods"
    directory.mkdir()
    return directory


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    """Return an isolated temporary staging directory path."""
    return tmp_path / "staging"


@pytest.fixture
def make_sample_update() -> Callable[..., UpdateInfo]:
    """Return a factory building deterministic UpdateInfo objects for update tests."""

    def _build(
        asset_name: str = "ModSync-linux",
        html_url: str = "https://example.test/release",
    ) -> UpdateInfo:
        return UpdateInfo(
            version="9.9.9",
            tag_name="client-v9.9.9",
            html_url=html_url,
            asset_name=asset_name,
            download_url=f"https://example.test/{asset_name}",
            expected_sha256="a" * 64,
        )

    return _build
