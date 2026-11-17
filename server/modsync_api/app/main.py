"""FastAPI WebSocket and HTTP modpack distribution server."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from .manifest import ManifestStore, validate_jar_request

logger = logging.getLogger("modsync_api")


class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts modpack update events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> int:
        async with self._lock:
            targets = list(self._connections)

        notified = 0
        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
                notified += 1
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.discard(ws)
        return notified

    @property
    def client_count(self) -> int:
        return len(self._connections)


def _is_loopback(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def create_app(
    *,
    modpack_dir: Path | None = None,
    admin_token: str | None = None,
    client_token: str | None = None,
    watch_interval: float | None = None,
    ws_ping_interval: float = 25.0,
) -> FastAPI:
    """Create configured FastAPI instance."""
    resolved_modpack = modpack_dir or Path(os.environ.get("MODPACK_DIR", "/modpack"))
    resolved_admin_token = admin_token if admin_token is not None else os.environ.get("MODSYNC_ADMIN_TOKEN", "")
    resolved_client_token = client_token if client_token is not None else os.environ.get("MODSYNC_CLIENT_TOKEN", "")
    resolved_watch = (
        watch_interval
        if watch_interval is not None
        else float(os.environ.get("MODSYNC_WATCH_INTERVAL", "3.0"))
    )

    store = ManifestStore(resolved_modpack)
    manager = ConnectionManager()

    async def _watch_modpack_loop() -> None:
        while True:
            await asyncio.sleep(resolved_watch)
            try:
                manifest, changed = await asyncio.to_thread(store.refresh)
                if changed:
                    notified = await manager.broadcast(
                        {
                            "type": "mods_updated",
                            "version": manifest.version,
                            "mod_count": len(manifest.mods),
                        }
                    )
                    logger.info(
                        "Detected modpack change -> version=%s (%d mods), notified %d client(s)",
                        manifest.version,
                        len(manifest.mods),
                        notified,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error while watching modpack directory")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(store.refresh)
        watcher_task: asyncio.Task[None] | None = None
        if resolved_watch > 0:
            watcher_task = asyncio.create_task(_watch_modpack_loop())
        try:
            yield
        finally:
            if watcher_task is not None:
                watcher_task.cancel()
                try:
                    await watcher_task
                except asyncio.CancelledError:
                    pass

    fastapi_app = FastAPI(title="ModSync API", version="0.1.0", lifespan=lifespan)
    fastapi_app.state.store = store
    fastapi_app.state.manager = manager

    @fastapi_app.get("/health")
    async def health() -> dict[str, Any]:
        manifest = store.current
        return {
            "status": "ok",
            "manifest_version": manifest.version,
            "mod_count": len(manifest.mods),
            "connected_clients": manager.client_count,
        }

    @fastapi_app.get("/api/manifest")
    async def get_manifest(
        response: Response,
        if_none_match: str | None = Header(default=None),
    ) -> Response:
        manifest = store.current
        etag = f'"{manifest.version}"'
        if if_none_match is not None and if_none_match.strip() in {etag, manifest.version}:
            return Response(status_code=304, headers={"ETag": etag})

        return JSONResponse(
            content=manifest.to_dict(),
            headers={
                "ETag": etag,
                "Cache-Control": "no-cache",
            },
        )

    @fastapi_app.get("/api/mods/{category}/{filename}")
    async def download_mod(category: str, filename: str) -> FileResponse:
        jar_path = validate_jar_request(resolved_modpack, category, filename)
        if jar_path is None:
            raise HTTPException(status_code=404, detail="Mod file not found")

        manifest = store.current
        etag = next((f'"{m.sha256}"' for m in manifest.mods if m.filename == filename and m.category == category), None)
        headers = {"Cache-Control": "public, max-age=3600"}
        if etag is not None:
            headers["ETag"] = etag

        return FileResponse(
            path=jar_path,
            media_type="application/java-archive",
            filename=jar_path.name,
            headers=headers,
        )

    @fastapi_app.post("/api/reload")
    async def reload_manifest(
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if resolved_admin_token:
            if not x_admin_token or not hmac.compare_digest(x_admin_token, resolved_admin_token):
                raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")
        else:
            client_host = request.client.host if request.client else None
            if not _is_loopback(client_host):
                raise HTTPException(
                    status_code=403,
                    detail="Reload requires MODSYNC_ADMIN_TOKEN for non-loopback requests",
                )

        manifest, changed = await asyncio.to_thread(store.refresh)
        notified = 0
        if changed:
            notified = await manager.broadcast(
                {
                    "type": "mods_updated",
                    "version": manifest.version,
                    "mod_count": len(manifest.mods),
                }
            )
        return {
            "changed": changed,
            "version": manifest.version,
            "mod_count": len(manifest.mods),
            "notified_clients": notified,
        }

    @fastapi_app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if resolved_client_token:
            token = websocket.query_params.get("token")
            auth_header = websocket.headers.get("authorization", "")
            if not token and auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            if not token or not hmac.compare_digest(token, resolved_client_token):
                await websocket.close(code=1008, reason="Unauthorized")
                return

        await manager.connect(websocket)
        try:
            manifest = store.current
            await websocket.send_json(
                {
                    "type": "hello",
                    "version": manifest.version,
                    "mod_count": len(manifest.mods),
                }
            )
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=ws_ping_interval)
                    if msg == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(websocket)

    return fastapi_app


app = create_app()
