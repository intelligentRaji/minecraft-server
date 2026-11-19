"""Typed FastAPI dependency providers backed by app.state."""

from __future__ import annotations

from starlette.requests import HTTPConnection

from .config import Config
from .connection_manager import ConnectionManager
from .manifest import ManifestStore


def get_config(conn: HTTPConnection) -> Config:
    return conn.app.state.config


def get_store(conn: HTTPConnection) -> ManifestStore:
    return conn.app.state.store


def get_manager(conn: HTTPConnection) -> ConnectionManager:
    return conn.app.state.manager
