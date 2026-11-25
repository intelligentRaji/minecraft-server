"""Isolated client filesystem environment and subprocess spawner protocol."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Protocol

ENV_NO_PROXY = "NO_PROXY"
ENV_NO_PROXY_LOWER = "no_proxy"
ENV_DISPLAY = "DISPLAY"
NO_PROXY_LOCALHOST = "127.0.0.1,localhost"
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

StdioTarget = int | IO[Any] | None


class ProcessSpawner(Protocol):
    """Callable fixture protocol for spawning tracked ModSync subprocesses."""

    def __call__(
        self,
        args: Sequence[str | Path],
        *,
        env: dict[str, str] | None = None,
        stdin: StdioTarget = subprocess.DEVNULL,
        stdout: StdioTarget = None,
        stderr: StdioTarget = None,
        log_name: str | None = None,
    ) -> subprocess.Popen[str]: ...


@dataclass
class IsolatedClientEnv:
    """Holds isolated filesystem paths and environment variables for a client E2E run."""

    root: Path
    home_dir: Path
    appdata_dir: Path
    localappdata_dir: Path
    xdg_config_dir: Path
    config_path: Path
    staging_dir: Path
    mods_dir: Path
    detected_mc_dir: Path
    env: dict[str, str]

    def clear_detected_minecraft_dirs(self) -> None:
        """Remove subdirectories inside detected_mc_dir so auto-detection finds nothing."""
        shutil.rmtree(self.detected_mc_dir, ignore_errors=True)


def build_local_loopback_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of env with proxy/DISPLAY variables removed and localhost bypassed."""
    env = dict(base_env) if base_env is not None else os.environ.copy()
    for proxy_var in PROXY_ENV_VARS:
        env.pop(proxy_var, None)
    env.pop(ENV_DISPLAY, None)
    env[ENV_NO_PROXY] = NO_PROXY_LOCALHOST
    env[ENV_NO_PROXY_LOWER] = NO_PROXY_LOCALHOST
    return env
