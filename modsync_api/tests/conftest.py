"""Shared pytest fixtures for modsync_api tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def modpack_dir(tmp_path: Path) -> Path:
    root = tmp_path / "modpack"
    (root / "server-client").mkdir(parents=True)
    (root / "client-only").mkdir(parents=True)
    (root / "server-only").mkdir(parents=True)
    return root
