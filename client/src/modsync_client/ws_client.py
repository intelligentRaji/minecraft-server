"""Persistent WebSocket listener and background sync coordinator."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import websockets

from .config import Config, build_ws_url, default_staging_dir
from .syncer import ModSyncer, SyncResult, SyncStatus

logger = logging.getLogger("modsync_client.ws")

StatusCallback = Callable[[SyncStatus, str, SyncResult | None], None]


class _WebSocketConn(Protocol):
    async def recv(self) -> str | bytes: ...

    async def send(self, message: str) -> None: ...


WS_EVENT_HELLO = "hello"
WS_EVENT_MODS_UPDATED = "mods_updated"
WS_EVENT_PING = "ping"
WS_EVENT_PONG = "pong"

WS_OPEN_TIMEOUT_SECONDS = 15
WS_PING_INTERVAL_SECONDS = 30
WS_PING_TIMEOUT_SECONDS = 20
WS_CLOSE_TIMEOUT_SECONDS = 5

INITIAL_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 60.0
POLL_TICK_SECONDS = 5.0
MIN_POLL_FALLBACK_SECONDS = 30


class ModSyncService:
    """Runs persistent WebSocket listener + fallback polling + staged-update monitor."""

    def __init__(
        self,
        config: Config,
        *,
        on_status: StatusCallback | None = None,
        staging_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.on_status = on_status
        self.staging_dir = staging_dir or default_staging_dir()
        self.syncer = self._create_syncer(config)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._sync_event: asyncio.Event | None = None
        self._recommended_event: asyncio.Event | None = None
        self._sync_lock: asyncio.Lock | None = None
        self._last_result: SyncResult | None = None

    def _create_syncer(self, config: Config) -> ModSyncer:
        return ModSyncer(
            server_url=config.normalized_server_url,
            mods_dir=config.mods_path,
            staging_dir=self.staging_dir,
            client_token=config.client_token,
        )

    def _emit(self, status: SyncStatus, message: str, result: SyncResult | None = None) -> None:
        if result is not None:
            self._last_result = result
        if self.on_status is not None:
            try:
                self.on_status(status, message, result)
            except Exception:
                logger.exception("Status callback failed")

    def request_sync(self) -> None:
        """Thread-safe trigger to run sync_once immediately."""
        if self._loop is not None and self._sync_event is not None:
            self._loop.call_soon_threadsafe(self._sync_event.set)

    def request_install_recommended(self) -> None:
        """Thread-safe trigger to install optional client-only mods on demand."""
        if self._loop is not None and self._recommended_event is not None:
            self._loop.call_soon_threadsafe(self._recommended_event.set)

    def stop(self) -> None:
        """Thread-safe request to shut down background loops."""
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def reconfigure(self, new_config: Config) -> None:
        """Update config and trigger a reconnect/sync cycle."""
        self.config = new_config
        self.syncer.close()
        self.syncer = self._create_syncer(new_config)
        self._last_result = None
        self.request_sync()

    async def _run_sync_action(self, reason: str, action: Callable[[], SyncResult]) -> None:
        assert self._sync_lock is not None
        async with self._sync_lock:
            self._emit(SyncStatus.SYNCING, f"Checking mods ({reason})...", self._last_result)
            try:
                result = await asyncio.to_thread(action)
                self._emit(result.status, result.message, result)
                logger.info("Sync [%s]: %s", reason, result.message)
            except Exception as exc:
                msg = f"Sync error: {exc}"
                self._emit(SyncStatus.ERROR, msg, self._last_result)
                logger.warning("Sync [%s] failed: %s", reason, exc)

    async def _perform_sync(self, reason: str) -> None:
        await self._run_sync_action(reason, self.syncer.sync_once)

    async def _perform_recommended_install(self) -> None:
        await self._run_sync_action("recommended", self.syncer.install_recommended)

    async def _receive_next_event(self, ws: _WebSocketConn) -> dict[str, Any] | None:
        assert self._stop_event is not None
        recv_task = asyncio.create_task(ws.recv())
        stop_task = asyncio.create_task(self._stop_event.wait())
        _, pending = await asyncio.wait(
            {recv_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        if self._stop_event.is_set():
            return None

        raw = recv_task.result()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    async def _handle_ws_event(self, ws: _WebSocketConn, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == WS_EVENT_HELLO:
            remote_ver = event.get("version")
            if self._last_result is None or self._last_result.version != remote_ver:
                await self._perform_sync("ws:hello")
        elif event_type == WS_EVENT_MODS_UPDATED:
            logger.info("Received instant update push: version=%s", event.get("version"))
            await self._perform_sync("ws:push")
        elif event_type == WS_EVENT_PING:
            await ws.send(WS_EVENT_PONG)

    async def _consume_ws_session(self, ws: _WebSocketConn) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            event = await self._receive_next_event(ws)
            if event is None:
                break
            if event:
                await self._handle_ws_event(ws, event)

    async def _wait_reconnect_backoff(self, backoff: float) -> float:
        assert self._stop_event is not None
        jitter = random.uniform(0.0, 1.0)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=backoff + jitter)
        return min(backoff * 2.0, MAX_BACKOFF_SECONDS)

    async def _ws_loop(self) -> None:
        assert self._stop_event is not None
        backoff = INITIAL_BACKOFF_SECONDS
        while not self._stop_event.is_set():
            ws_url = build_ws_url(self.config.normalized_server_url, self.config.client_token)
            try:
                logger.info("Connecting WebSocket to %s", ws_url.split("?")[0])
                async with websockets.connect(
                    ws_url,
                    open_timeout=WS_OPEN_TIMEOUT_SECONDS,
                    ping_interval=WS_PING_INTERVAL_SECONDS,
                    ping_timeout=WS_PING_TIMEOUT_SECONDS,
                    close_timeout=WS_CLOSE_TIMEOUT_SECONDS,
                ) as ws:
                    backoff = INITIAL_BACKOFF_SECONDS
                    logger.info("WebSocket connected")
                    await self._consume_ws_session(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("WebSocket disconnected (%s); reconnecting in %.1fs", exc, backoff)
                if self._last_result is None:
                    self._emit(SyncStatus.ERROR, f"Disconnected ({exc})", None)
                backoff = await self._wait_reconnect_backoff(backoff)

    async def _try_apply_pending_staged(self) -> None:
        if self._last_result is None or self._last_result.status != SyncStatus.STAGED_WAITING_MC:
            return
        try:
            applied = await asyncio.to_thread(self.syncer.try_apply_staged)
            if applied is not None:
                self._emit(applied.status, applied.message, applied)
                logger.info("Applied staged update: %s", applied.message)
        except Exception as exc:
            self._emit(SyncStatus.ERROR, f"Apply error: {exc}", self._last_result)

    async def _wait_for_next_tick(self, timeout: float) -> bool:
        assert self._stop_event is not None
        assert self._sync_event is not None
        assert self._recommended_event is not None
        waiters = {
            asyncio.create_task(self._sync_event.wait()),
            asyncio.create_task(self._recommended_event.wait()),
            asyncio.create_task(self._stop_event.wait()),
        }
        done, pending = await asyncio.wait(
            waiters,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        return not done

    async def _poll_and_stage_loop(self) -> None:
        assert self._stop_event is not None
        assert self._sync_event is not None
        assert self._recommended_event is not None
        elapsed = 0.0
        while not self._stop_event.is_set():
            if self._sync_event.is_set():
                self._sync_event.clear()
                elapsed = 0.0
                await self._perform_sync("manual")
                continue

            if self._recommended_event.is_set():
                self._recommended_event.clear()
                await self._perform_recommended_install()
                continue

            await self._try_apply_pending_staged()

            poll_interval = max(MIN_POLL_FALLBACK_SECONDS, self.config.poll_fallback_seconds)
            if elapsed >= poll_interval:
                elapsed = 0.0
                await self._perform_sync("poll")

            if await self._wait_for_next_tick(POLL_TICK_SECONDS):
                elapsed += POLL_TICK_SECONDS

    async def run(self) -> None:
        """Run WebSocket listener and fallback/staging loops until stopped."""
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._sync_event = asyncio.Event()
        self._recommended_event = asyncio.Event()
        self._sync_lock = asyncio.Lock()

        await self._perform_sync("startup")
        try:
            await asyncio.gather(self._ws_loop(), self._poll_and_stage_loop())
        finally:
            self.syncer.close()
