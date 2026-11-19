"""Environment-driven configuration for ModSync API."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODPACK_DIR = "/modpack"
DEFAULT_WS_PING_INTERVAL = "25.0"


def _parse_positive_float(env_name: str, default: str) -> float:
    raw = os.environ.get(env_name, default)
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{env_name} must be a finite number > 0, got {raw!r}")
    return value


@dataclass(frozen=True)
class Settings:
    """Validated runtime configuration loaded from environment variables."""

    modpack_dir: Path
    admin_token: str
    client_token: str
    ws_ping_interval: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            modpack_dir=Path(os.environ.get("MODPACK_DIR", DEFAULT_MODPACK_DIR)),
            admin_token=os.environ.get("MODSYNC_ADMIN_TOKEN", "").strip(),
            client_token=os.environ.get("MODSYNC_CLIENT_TOKEN", "").strip(),
            ws_ping_interval=_parse_positive_float("MODSYNC_WS_PING_INTERVAL", DEFAULT_WS_PING_INTERVAL),
        )
