"""Healthcheck endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..connection_manager import ConnectionManager
from ..deps import get_manager, get_store
from ..manifest import ManifestStore

router = APIRouter()


@router.get("/health")
async def health(
    store: ManifestStore = Depends(get_store),
    manager: ConnectionManager = Depends(get_manager),
) -> dict[str, Any]:
    manifest = store.current
    return {
        "status": "ok",
        "manifest_version": manifest.version,
        "mod_count": len(manifest.mods),
        "connected_clients": manager.client_count,
    }
