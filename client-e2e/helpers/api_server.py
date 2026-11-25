"""Local ephemeral modsync_api test server harness for client E2E tests."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .env import build_local_loopback_env
from .fixtures import MODPACK_CATEGORIES, DefaultMods, ModFixture, compute_sha256
from .polling import FatalPollError, terminate_process_tree, wait_until

ENV_MODPACK_DIR = "MODPACK_DIR"
ENV_MODSYNC_ADMIN_TOKEN = "MODSYNC_ADMIN_TOKEN"
ENV_MODSYNC_CLIENT_TOKEN = "MODSYNC_CLIENT_TOKEN"
ENV_MODSYNC_WS_PING_INTERVAL = "MODSYNC_WS_PING_INTERVAL"
ENV_VIRTUAL_ENV = "VIRTUAL_ENV"
ENV_UV_PROJECT_ENVIRONMENT = "UV_PROJECT_ENVIRONMENT"

ENDPOINT_HEALTH = "/health"
ENDPOINT_MANIFEST = "/api/manifest"
ENDPOINT_RELOAD = "/api/reload"

HEADER_AUTHORIZATION = "Authorization"
BEARER_PREFIX = "Bearer "
HEADER_ADMIN_TOKEN = "X-Admin-Token"

HEALTH_STATUS_KEY = "status"
HEALTH_STATUS_OK = "ok"
HEALTH_CONNECTED_CLIENTS_KEY = "connected_clients"
RELOAD_CHANGED_KEY = "changed"
RELOAD_NOTIFIED_CLIENTS_KEY = "notified_clients"

INVITE_URI_PREFIX = "modsync://connect"
PARAM_URL = "url"
PARAM_TOKEN = "token"

LOOPBACK_HOST = "127.0.0.1"
UVICORN_APP_TARGET = "app.main:app"
UVICORN_LOG_LEVEL = "warning"
UVICORN_LOG_FILENAME_TEMPLATE = "modsync_api_uvicorn_{idx}.log"
TEST_WS_PING_INTERVAL = "2.0"

DEFAULT_ADMIN_TOKEN = "e2e-admin-secret-token"
DEFAULT_CLIENT_TOKEN = "e2e-client-secret-token"

JAR_TMP_SUFFIX = ".jar.tmp"
SERVER_START_TIMEOUT_SECONDS = 15.0
REQUEST_TIMEOUT_SECONDS = 5.0
SERVER_POLL_INTERVAL_SECONDS = 0.1

REPO_ROOT = Path(__file__).resolve().parents[2]
MODSYNC_API_DIR = REPO_ROOT / "modsync_api"


def _allocate_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        return int(sock.getsockname()[1])


@dataclass
class ModSyncTestServer:
    """Manages an ephemeral uvicorn instance running modsync_api against a temp modpack."""

    modpack_dir: Path
    port: int
    admin_token: str = DEFAULT_ADMIN_TOKEN
    client_token: str = DEFAULT_CLIENT_TOKEN
    process: subprocess.Popen[str] | None = field(default=None, init=False)
    expected_hashes: dict[tuple[str, str], str] = field(default_factory=dict, init=False)
    _start_index: int = field(default=0, init=False)
    log_paths: list[Path] = field(default_factory=list, init=False)

    @property
    def server_url(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.port}"

    def build_invite_url(self, *, include_token: bool = True) -> str:
        params: dict[str, str] = {PARAM_URL: self.server_url}
        if include_token and self.client_token:
            params[PARAM_TOKEN] = self.client_token
        return f"{INVITE_URI_PREFIX}?{urlencode(params)}"

    def write_mod(self, mod: ModFixture) -> tuple[Path, str]:
        """Create or overwrite a fixture mod JAR in its modpack category atomically."""
        cat_dir = self.modpack_dir / mod.category
        cat_dir.mkdir(parents=True, exist_ok=True)
        jar_path = cat_dir / mod.filename
        payload = mod.jar_bytes()
        tmp_path = jar_path.with_suffix(JAR_TMP_SUFFIX)
        tmp_path.write_bytes(payload)
        os.replace(tmp_path, jar_path)
        digest = compute_sha256(payload)
        self.expected_hashes[mod.key] = digest
        return jar_path, digest

    def remove_mod(self, mod: ModFixture) -> None:
        """Delete a fixture mod JAR from its modpack category."""
        jar_path = self.modpack_dir / mod.category / mod.filename
        jar_path.unlink(missing_ok=True)
        self.expected_hashes.pop(mod.key, None)

    def start(self) -> None:
        """Seed initial modpack layout, launch uvicorn via modsync_api/.venv, and wait for /health."""
        api_venv = MODSYNC_API_DIR / ".venv"
        if not api_venv.is_dir():
            raise RuntimeError(
                f"modsync_api virtualenv not found at {api_venv}. "
                "Run `uv --directory modsync_api sync` before running client-e2e."
            )
        uv_exe = shutil.which("uv")
        if not uv_exe:
            raise RuntimeError("uv executable not found on PATH (required to launch modsync_api).")

        for category in MODPACK_CATEGORIES:
            (self.modpack_dir / category).mkdir(parents=True, exist_ok=True)

        if not self.expected_hashes:
            for mod in DefaultMods.INITIAL_SERVER_SEED:
                self.write_mod(mod)

        env = build_local_loopback_env()
        env.pop(ENV_VIRTUAL_ENV, None)
        env.pop(ENV_UV_PROJECT_ENVIRONMENT, None)
        env[ENV_MODPACK_DIR] = str(self.modpack_dir)
        env[ENV_MODSYNC_ADMIN_TOKEN] = self.admin_token
        env[ENV_MODSYNC_CLIENT_TOKEN] = self.client_token
        env[ENV_MODSYNC_WS_PING_INTERVAL] = TEST_WS_PING_INTERVAL

        idx = self._start_index
        self._start_index += 1
        log_path = self.modpack_dir.parent / UVICORN_LOG_FILENAME_TEMPLATE.format(idx=idx)
        self.log_paths.append(log_path)
        with log_path.open("w", encoding="utf-8") as log_file:
            self.process = subprocess.Popen(
                [
                    uv_exe,
                    "--directory",
                    str(MODSYNC_API_DIR),
                    "run",
                    "--no-sync",
                    "uvicorn",
                    UVICORN_APP_TARGET,
                    "--host",
                    LOOPBACK_HOST,
                    "--port",
                    str(self.port),
                    "--log-level",
                    UVICORN_LOG_LEVEL,
                ],
                cwd=str(MODSYNC_API_DIR),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

        def _is_healthy() -> bool:
            if self.process is not None and self.process.poll() is not None:
                self.process.wait(timeout=REQUEST_TIMEOUT_SECONDS)
                log_output = (
                    log_path.read_text(encoding="utf-8", errors="replace")
                    if log_path.is_file()
                    else ""
                )
                raise FatalPollError(
                    f"modsync_api uvicorn exited early (code={self.process.returncode}):\n"
                    f"LOG:\n{log_output}"
                )
            with httpx.Client(trust_env=False, timeout=1.0) as client:
                resp = client.get(f"{self.server_url}{ENDPOINT_HEALTH}")
            return (
                resp.status_code == HTTPStatus.OK
                and resp.json().get(HEALTH_STATUS_KEY) == HEALTH_STATUS_OK
            )

        try:
            wait_until(
                _is_healthy,
                timeout=SERVER_START_TIMEOUT_SECONDS,
                interval=SERVER_POLL_INTERVAL_SECONDS,
                description=f"modsync_api {ENDPOINT_HEALTH}",
            )
        except BaseException:
            self.close()
            raise

    def health(self) -> dict[str, Any]:
        with httpx.Client(trust_env=False, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(f"{self.server_url}{ENDPOINT_HEALTH}")
        resp.raise_for_status()
        return dict(resp.json())

    def connected_clients(self) -> int:
        """Return the number of active WebSocket clients reported by /health."""
        return int(self.health().get(HEALTH_CONNECTED_CLIENTS_KEY, 0))

    def manifest(self) -> dict[str, Any]:
        headers = (
            {HEADER_AUTHORIZATION: f"{BEARER_PREFIX}{self.client_token}"}
            if self.client_token
            else {}
        )
        with httpx.Client(trust_env=False, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(f"{self.server_url}{ENDPOINT_MANIFEST}", headers=headers)
        resp.raise_for_status()
        return dict(resp.json())

    def reload(self) -> tuple[bool, int]:
        """Trigger /api/reload and return (changed, notified_clients)."""
        with httpx.Client(trust_env=False, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.post(
                f"{self.server_url}{ENDPOINT_RELOAD}",
                headers={HEADER_ADMIN_TOKEN: self.admin_token},
            )
        resp.raise_for_status()
        data = resp.json()
        return bool(data[RELOAD_CHANGED_KEY]), int(data[RELOAD_NOTIFIED_CLIENTS_KEY])

    def close(self) -> None:
        if self.process is not None:
            terminate_process_tree(self.process, timeout=REQUEST_TIMEOUT_SECONDS)
            self.process = None


def create_started_server(modpack_dir: Path) -> ModSyncTestServer:
    """Create and start a ModSyncTestServer on an ephemeral port."""
    server = ModSyncTestServer(modpack_dir=modpack_dir, port=_allocate_free_port())
    server.start()
    return server
