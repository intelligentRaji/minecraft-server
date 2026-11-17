"""Persistent WebSocket listener and background sync coordinator."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Callable

import websockets

from .config import AppConfig, build_ws_url, default_staging_dir
from .syncer import ModSyncer, SyncResult, SyncStatus

logger = logging.getLogger("modsync_client.ws")

StatusCallback = Callable[[SyncStatus, str, SyncResult | None], None]


class ModSyncService:
    """Runs persistent WebSocket listener + fallback polling + staged-update monitor."""

    def __init__(
        self,
        config: AppConfig,
        *,
        on_status: StatusCallback | None = None,
        staging_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.on_status = on_status
        self.staging_dir = staging_dir or default_staging_dir()
        self.syncer = ModSyncer(
            server_url=config.normalized_server_url,
            mods_dir=config.mods_path,
            staging_dir=self.staging_dir,
        )

        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._sync_event: asyncio.Event | None = None
        self._sync_lock: asyncio.Lock | None = None
        self._last_result: SyncResult | None = None

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

    def stop(self) -> None:
        """Thread-safe request to shut down background loops."""
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def reconfigure(self, new_config: AppConfig) -> None:
        """Update config and trigger a reconnect/sync cycle."""
        self.config = new_config
        self.syncer.close()
        self.syncer = ModSyncer(
            server_url=new_config.normalized_server_url,
            mods_dir=new_config.mods_path,
            staging_dir=self.staging_dir,
        )
        self._last_result = None
        self.request_sync()

    async def _perform_sync(self, reason: str) -> None:
        assert self._sync_lock is not None
        async with self._sync_lock:
            self._emit(SyncStatus.SYNCING, f"Checking mods ({reason})...", self._last_result)
            try:
                result = await asyncio.to_thread(self.syncer.sync_once)
                self._emit(result.status, result.message, result)
                logger.info("Sync [%s]: %s", reason, result.message)
            except Exception as exc:
                msg = f"Sync error: {exc}"
                self._emit(SyncStatus.ERROR, msg, self._last_result)
                logger.warning("Sync [%s] failed: %s", reason, exc)

    async def _ws_loop(self) -> None:
        assert self._stop_event is not None
        backoff = 2.0
        while not self._stop_event.is_set():
            ws_url = build_ws_url(self.config.normalized_server_url, self.config.client_token)
            try:
                logger.info("Connecting WebSocket to %s", ws_url.split("?")[0])
                async with websockets.connect(
                    ws_url,
                    open_timeout=15,
                    ping_interval=30,
                    ping_timeout=20,
                    close_timeout=5,
                ) as ws:
                    backoff = 2.0
                    logger.info("WebSocket connected")
                    while not self._stop_event.is_set():
                        recv_task = asyncio.create_task(ws.recv())
                        stop_task = asyncio.create_task(self._stop_event.wait())
                        done, pending = await asyncio.wait(
                            {recv_task, stop_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()

                        if self._stop_event.is_set():
                            break

                        raw = recv_task.result()
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type")
                        if event_type == "hello":
                            remote_ver = event.get("version")
                            if self._last_result is None or self._last_result.version != remote_ver:
                                await self._perform_sync("ws:hello")
                        elif event_type == "mods_updated":
                            logger.info("Received instant update push: version=%s", event.get("version"))
                            await self._perform_sync("ws:push")
                        elif event_type == "ping":
                            await ws.send("pong")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("WebSocket disconnected (%s); reconnecting in %.1fs", exc, backoff)
                if self._last_result is None:
                    self._emit(SyncStatus.ERROR, f"Disconnected ({exc})", None)
                jitter = random.uniform(0.0, 1.0)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff + jitter)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2.0, 60.0)

    async def _poll_and_stage_loop(self) -> None:
        assert self._stop_event is not None
        assert self._sync_event is not None
        elapsed = 0.0
        tick = 5.0
        while not self._stop_event.is_set():
            if self._sync_event.is_set():
                self._sync_event.clear()
                elapsed = 0.0
                await self._perform_sync("manual")
                continue

            if (
                self._last_result is not None
                and self._last_result.status == SyncStatus.STAGED_WAITING_MC
            ):
                try:
                    applied = await asyncio.to_thread(self.syncer.try_apply_staged)
                    if applied is not None:
                        self._emit(applied.status, applied.message, applied)
                        logger.info("Applied staged update: %s", applied.message)
                except Exception as exc:
                    self._emit(SyncStatus.ERROR, f"Apply error: {exc}", self._last_result)

            if elapsed >= max(30, self.config.poll_fallback_seconds):
                elapsed = 0.0
                await self._perform_sync("poll")

            sync_wait = asyncio.create_task(self._sync_event.wait())
            stop_wait = asyncio.create_task(self._stop_event.wait())
            done, pending = await asyncio.wait(
                {sync_wait, stop_wait},
                timeout=tick,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if not done:
                elapsed += tick

    async def run(self) -> None:
        """Run WebSocket listener and fallback/staging loops until stopped."""
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._sync_event = asyncio.Event()
        self._sync_lock = asyncio.Lock()

        await self._perform_sync("startup")
        try:
            await asyncio.gather(self._ws_loop(), self._poll_and_stage_loop())
        finally:
            self.syncer.close()
