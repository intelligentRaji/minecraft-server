"""WebSocket connection tracking and safe concurrent broadcasting."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

MAX_WS_CONNECTIONS = 100
WS_SEND_TIMEOUT_SECONDS = 5.0


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
        for ws, outcome in zip(targets, results, strict=True):
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
