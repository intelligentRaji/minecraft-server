"""Shared pytest fixtures for modsync_client tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def mods_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "mods"
    directory.mkdir()
    return directory


@pytest.fixture()
def staging_dir(tmp_path: Path) -> Path:
    return tmp_path / "staging"
