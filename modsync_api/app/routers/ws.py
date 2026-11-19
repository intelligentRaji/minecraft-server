"""WebSocket push endpoint."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from ..auth import extract_bearer_token, tokens_match
from ..config import Settings
from ..connection_manager import ConnectionManager
from ..deps import get_manager, get_settings, get_store
from ..manifest import ManifestStore

WS_EVENT_HELLO = "hello"
WS_EVENT_PING = "ping"
WS_EVENT_PONG = "pong"

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    store: ManifestStore = Depends(get_store),
    manager: ConnectionManager = Depends(get_manager),
) -> None:
    if not settings.client_token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="MODSYNC_CLIENT_TOKEN must be configured",
        )
        return
    token = extract_bearer_token(websocket.headers.get("authorization")) or websocket.query_params.get("token")
    if not tokens_match(token, settings.client_token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    if not await manager.connect(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Too many connections")
        return
    try:
        await manager.send_json(websocket, store.current.to_event(WS_EVENT_HELLO))
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=settings.ws_ping_interval)
                if msg == WS_EVENT_PING:
                    await manager.send_json(websocket, {"type": WS_EVENT_PONG})
            except TimeoutError:
                await manager.send_json(websocket, {"type": WS_EVENT_PING})
    except (WebSocketDisconnect, TimeoutError, RuntimeError, OSError):
        pass
    finally:
        await manager.disconnect(websocket)
