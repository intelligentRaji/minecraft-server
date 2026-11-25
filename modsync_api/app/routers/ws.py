"""WebSocket push endpoint."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from ..auth import extract_bearer_token, tokens_match
from ..config import Config
from ..connection_manager import ConnectionManager
from ..deps import get_config, get_manager, get_store
from ..manifest import ManifestStore

WS_EVENT_HELLO = "hello"
WS_EVENT_PING = "ping"
WS_EVENT_PONG = "pong"

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    config: Annotated[Config, Depends(get_config)],
    store: Annotated[ManifestStore, Depends(get_store)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> None:
    if not config.client_token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="MODSYNC_CLIENT_TOKEN must be configured",
        )
        return
    token = extract_bearer_token(websocket.headers.get("authorization")) or websocket.query_params.get("token")
    if not tokens_match(token, config.client_token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    if not await manager.connect(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Too many connections")
        return
    try:
        await manager.send_json(websocket, store.current.to_event(WS_EVENT_HELLO))
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=config.ws_ping_interval)
                if msg == WS_EVENT_PING:
                    await manager.send_json(websocket, {"type": WS_EVENT_PONG})
            except TimeoutError:
                await manager.send_json(websocket, {"type": WS_EVENT_PING})
    except (WebSocketDisconnect, TimeoutError, RuntimeError, OSError):
        pass
    finally:
        await manager.disconnect(websocket)
