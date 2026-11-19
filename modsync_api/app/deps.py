"""Typed FastAPI dependency providers backed by app.state."""

from __future__ import annotations

from starlette.requests import HTTPConnection

from .config import Settings
from .connection_manager import ConnectionManager
from .manifest import ManifestStore


def get_settings(conn: HTTPConnection) -> Settings:
    return conn.app.state.settings


def get_store(conn: HTTPConnection) -> ManifestStore:
    return conn.app.state.store


def get_manager(conn: HTTPConnection) -> ConnectionManager:
    return conn.app.state.manager
