"""FastAPI WebSocket and HTTP modpack distribution server."""

from __future__ import annotations

import asyncio
import hmac
import logging
import math
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse

from .manifest import MOD_DOWNLOAD_PREFIX, Manifest, ManifestStore, validate_jar_request

logger = logging.getLogger("modsync_api")

BEARER_PREFIX = "bearer "
DEFAULT_MODPACK_DIR = "/modpack"
DEFAULT_WS_PING_INTERVAL = "25.0"
JAR_CACHE_MAX_AGE_SECONDS = 3600
JAR_MEDIA_TYPE = "application/java-archive"
MAX_WS_CONNECTIONS = 100
WS_SEND_TIMEOUT_SECONDS = 5.0
WS_EVENT_HELLO = "hello"
WS_EVENT_MODS_UPDATED = "mods_updated"
WS_EVENT_PING = "ping"
WS_EVENT_PONG = "pong"


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX) :].strip()
    return ""


def _tokens_match(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _verify_http_token(
    provided: str | None,
    expected: str,
    *,
    missing_detail: str,
    invalid_detail: str,
    www_authenticate: str | None = None,
) -> None:
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=missing_detail,
        )
    if not _tokens_match(provided, expected):
        headers = {"WWW-Authenticate": www_authenticate} if www_authenticate else None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=invalid_detail,
            headers=headers,
        )


def _parse_positive_float(env_name: str, default: str) -> float:
    raw = os.environ.get(env_name, default)
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{env_name} must be a finite number > 0, got {raw!r}")
    return value


def _format_etag(value: str) -> str:
    return f'"{value}"'


def _manifest_event(event_type: str, manifest: Manifest) -> dict[str, Any]:
    return {
        "type": event_type,
        "version": manifest.version,
        "mod_count": len(manifest.mods),
    }


class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts modpack update events."""

    def __init__(self, max_connections: int = MAX_WS_CONNECTIONS) -> None:
        self._max_connections = max_connections
        self._connections: dict[WebSocket, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> bool:
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                return False
            self._connections[websocket] = asyncio.Lock()
        try:
            await websocket.accept()
        except Exception:
            await self.disconnect(websocket)
            raise
        return True

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def send_json(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        async with self._lock:
            send_lock = self._connections.get(websocket)
        if send_lock is None:
            raise WebSocketDisconnect()
        async with send_lock:
            await asyncio.wait_for(websocket.send_json(payload), timeout=WS_SEND_TIMEOUT_SECONDS)

    async def broadcast(self, payload: dict[str, Any]) -> int:
        async with self._lock:
            targets = list(self._connections.keys())
        if not targets:
            return 0

        results = await asyncio.gather(
            *(self.send_json(ws, payload) for ws in targets),
            return_exceptions=True,
        )
        notified = 0
        stale: list[WebSocket] = []
        for ws, outcome in zip(targets, results):
            if isinstance(outcome, BaseException):
                stale.append(ws)
            else:
                notified += 1

        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.pop(ws, None)
        return notified

    @property
    def client_count(self) -> int:
        return len(self._connections)


async def _refresh_and_notify(
    store: ManifestStore,
    manager: ConnectionManager,
) -> tuple[Manifest, bool, int]:
    manifest, changed = await asyncio.to_thread(store.refresh)
    notified = 0
    if changed:
        notified = await manager.broadcast(_manifest_event(WS_EVENT_MODS_UPDATED, manifest))
    return manifest, changed, notified


def create_app() -> FastAPI:
    """Create configured FastAPI instance."""
    resolved_modpack = Path(os.environ.get("MODPACK_DIR", DEFAULT_MODPACK_DIR))
    resolved_admin_token = os.environ.get("MODSYNC_ADMIN_TOKEN", "").strip()
    resolved_client_token = os.environ.get("MODSYNC_CLIENT_TOKEN", "").strip()
    ws_ping_interval = _parse_positive_float("MODSYNC_WS_PING_INTERVAL", DEFAULT_WS_PING_INTERVAL)

    store = ManifestStore(resolved_modpack)
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        await asyncio.to_thread(store.refresh)
        yield

    fastapi_app = FastAPI(title="ModSync API", version="0.1.0", lifespan=lifespan)

    def _require_client_auth(authorization: str | None = Header(default=None)) -> None:
        _verify_http_token(
            _extract_bearer_token(authorization),
            resolved_client_token,
            missing_detail="MODSYNC_CLIENT_TOKEN must be configured",
            invalid_detail="Invalid or missing client token",
            www_authenticate="Bearer",
        )

    def _require_admin_auth(x_admin_token: str | None = Header(default=None)) -> None:
        _verify_http_token(
            x_admin_token,
            resolved_admin_token,
            missing_detail="MODSYNC_ADMIN_TOKEN must be configured to use /api/reload",
            invalid_detail="Invalid or missing X-Admin-Token",
        )

    @fastapi_app.get("/health")
    async def health() -> dict[str, Any]:
        manifest = store.current
        return {
            "status": "ok",
            "manifest_version": manifest.version,
            "mod_count": len(manifest.mods),
            "connected_clients": manager.client_count,
        }

    @fastapi_app.get("/api/manifest", dependencies=[Depends(_require_client_auth)])
    async def get_manifest(
        if_none_match: str | None = Header(default=None),
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
    @fastapi_app.get(f"{MOD_DOWNLOAD_PREFIX}/{{category}}/{{filename}}", dependencies=[Depends(_require_client_auth)])
    async def download_mod(category: str, filename: str) -> FileResponse:
        jar_path = validate_jar_request(resolved_modpack, category, filename)
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

    @fastapi_app.post("/api/reload", dependencies=[Depends(_require_admin_auth)])
    async def reload_manifest() -> dict[str, Any]:
        manifest, changed, notified = await _refresh_and_notify(store, manager)
        return {
            "changed": changed,
            "version": manifest.version,
            "mod_count": len(manifest.mods),
            "notified_clients": notified,
        }

    @fastapi_app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if not resolved_client_token:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="MODSYNC_CLIENT_TOKEN must be configured",
            )
            return
        token = _extract_bearer_token(websocket.headers.get("authorization")) or websocket.query_params.get("token")
        if not _tokens_match(token, resolved_client_token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return

        if not await manager.connect(websocket):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Too many connections")
            return
        try:
            await manager.send_json(websocket, _manifest_event(WS_EVENT_HELLO, store.current))
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=ws_ping_interval)
                    if msg == WS_EVENT_PING:
                        await manager.send_json(websocket, {"type": WS_EVENT_PONG})
                except TimeoutError:
                    await manager.send_json(websocket, {"type": WS_EVENT_PING})
        except (WebSocketDisconnect, TimeoutError, RuntimeError, OSError):
            pass
        finally:
            await manager.disconnect(websocket)

    return fastapi_app


app = create_app()
