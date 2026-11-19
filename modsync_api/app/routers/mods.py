"""Manifest, mod download, and reload endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse

from ..auth import require_admin_auth, require_client_auth
from ..config import Config
from ..connection_manager import ConnectionManager
from ..deps import get_config, get_manager, get_store
from ..manifest import MOD_DOWNLOAD_PREFIX, ManifestStore, validate_jar_request

JAR_CACHE_MAX_AGE_SECONDS = 3600
JAR_MEDIA_TYPE = "application/java-archive"
WS_EVENT_MODS_UPDATED = "mods_updated"

router = APIRouter()


def _format_etag(value: str) -> str:
    return f'"{value}"'


@router.get("/api/manifest", dependencies=[Depends(require_client_auth)])
async def get_manifest(
    if_none_match: str | None = Header(default=None),
    store: ManifestStore = Depends(get_store),
) -> Response:
    manifest = store.current
    etag_value = f"{manifest.version}-{manifest.recommended_version}"
    etag = _format_etag(etag_value)
    if if_none_match is not None and if_none_match.strip() in {etag, etag_value}:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    return JSONResponse(
        content=manifest.to_dict(),
        headers={
            "ETag": etag,
            "Cache-Control": "no-cache",
        },
    )


# category is str (not ClientCategory) so invalid categories return 404 rather than 422
@router.get(f"{MOD_DOWNLOAD_PREFIX}/{{category}}/{{filename}}", dependencies=[Depends(require_client_auth)])
async def download_mod(
    category: str,
    filename: str,
    config: Config = Depends(get_config),
    store: ManifestStore = Depends(get_store),
) -> FileResponse:
    jar_path = validate_jar_request(config.modpack_dir, category, filename)
    if jar_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mod file not found")

    entry = store.current.find_mod(category, filename)
    headers = {"Cache-Control": f"public, max-age={JAR_CACHE_MAX_AGE_SECONDS}"}
    if entry is not None:
        headers["ETag"] = _format_etag(entry.sha256)

    return FileResponse(
        path=jar_path,
        media_type=JAR_MEDIA_TYPE,
        filename=jar_path.name,
        headers=headers,
    )


@router.post("/api/reload", dependencies=[Depends(require_admin_auth)])
async def reload_manifest(
    store: ManifestStore = Depends(get_store),
    manager: ConnectionManager = Depends(get_manager),
) -> dict[str, Any]:
    manifest, changed = await asyncio.to_thread(store.refresh)
    notified = 0
    if changed:
        notified = await manager.broadcast(manifest.to_event(WS_EVENT_MODS_UPDATED))
    return {
        "changed": changed,
        "version": manifest.version,
        "mod_count": len(manifest.mods),
        "notified_clients": notified,
    }
