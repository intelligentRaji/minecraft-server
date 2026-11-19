"""FastAPI application factory and lifespan wiring for ModSync API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Config
from .connection_manager import ConnectionManager
from .manifest import ManifestStore
from .routers import health, mods, ws


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize app-wide manifest cache before serving requests."""
    await asyncio.to_thread(fastapi_app.state.store.refresh)
    yield


def create_app() -> FastAPI:
    """Create configured FastAPI instance."""
    config = Config.from_env()
    fastapi_app = FastAPI(title="ModSync API", version="0.1.0", lifespan=lifespan)
    fastapi_app.state.config = config
    fastapi_app.state.store = ManifestStore(config.modpack_dir)
    fastapi_app.state.manager = ConnectionManager()

    fastapi_app.include_router(health.router)
    fastapi_app.include_router(mods.router)
    fastapi_app.include_router(ws.router)
    return fastapi_app


app = create_app()
