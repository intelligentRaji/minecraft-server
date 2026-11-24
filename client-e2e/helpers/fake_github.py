"""Local fake GitHub Releases HTTP server for testing ModSync --update E2E."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

GITHUB_DEFAULT_REPO = "intelligentRaji/minecraft-server"
GITHUB_RELEASE_TAG_PREFIX = "client-v"
GITHUB_CHECKSUMS_ASSET = "checksums.txt"
GITHUB_RELEASES_PATH_TEMPLATE = "/repos/{repo}/releases"
GITHUB_ASSETS_PREFIX = "/assets"
DEFAULT_FAKE_RELEASE_VERSION = "99.0.0"
INVALID_SHA256_HEX = "0" * 64

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_ASSET_NAME = "ModSync.exe" if sys.platform == "win32" else "ModSync-linux"
SHUTDOWN_TIMEOUT_SECONDS = 5.0


@dataclass
class FakeGitHubReleasesServer:
    """Serves a local /repos/<owner>/<repo>/releases API, checksums.txt, and asset binary."""

    version: str = DEFAULT_FAKE_RELEASE_VERSION
    asset_name: str = DEFAULT_ASSET_NAME
    asset_payload: bytes = b""
    checksum_override: str | None = None
    repo: str = GITHUB_DEFAULT_REPO
    _server: ThreadingHTTPServer | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _thread_started: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _requests_seen: list[str] = field(default_factory=list, init=False)
    _user_agents_seen: list[str] = field(default_factory=list, init=False)

    @property
    def requests_seen(self) -> list[str]:
        with self._lock:
            return list(self._requests_seen)

    @property
    def user_agents_seen(self) -> list[str]:
        with self._lock:
            return list(self._user_agents_seen)

    @property
    def releases_path(self) -> str:
        return GITHUB_RELEASES_PATH_TEMPLATE.format(repo=self.repo)

    @property
    def checksums_path(self) -> str:
        return f"{GITHUB_ASSETS_PREFIX}/{GITHUB_CHECKSUMS_ASSET}"

    @property
    def asset_path(self) -> str:
        return f"{GITHUB_ASSETS_PREFIX}/{self.asset_name}"

    @property
    def base_url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        host_str = host.decode("ascii") if isinstance(host, bytes) else str(host)
        return f"http://{host_str}:{port}"

    @property
    def expected_sha256(self) -> str:
        return hashlib.sha256(self.asset_payload).hexdigest()

    def start(self) -> None:
        owner_server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                user_agent = str(self.headers.get("User-Agent", "")).strip()
                with owner_server._lock:
                    owner_server._requests_seen.append(path)
                    owner_server._user_agents_seen.append(user_agent)

                if path == owner_server.releases_path:
                    tag = f"{GITHUB_RELEASE_TAG_PREFIX}{owner_server.version}"
                    body = json.dumps(
                        [
                            {
                                "tag_name": tag,
                                "draft": False,
                                "prerelease": False,
                                "html_url": f"{owner_server.base_url}/releases/tag/{tag}",
                                "assets": [
                                    {
                                        "name": owner_server.asset_name,
                                        "browser_download_url": (
                                            f"{owner_server.base_url}{owner_server.asset_path}"
                                        ),
                                    },
                                    {
                                        "name": GITHUB_CHECKSUMS_ASSET,
                                        "browser_download_url": (
                                            f"{owner_server.base_url}{owner_server.checksums_path}"
                                        ),
                                    },
                                ],
                            }
                        ]
                    ).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if path == owner_server.checksums_path:
                    digest = owner_server.checksum_override or owner_server.expected_sha256
                    body = f"{digest}  {owner_server.asset_name}\n".encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if path == owner_server.asset_path:
                    body = owner_server.asset_payload
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                self.send_error(HTTPStatus.NOT_FOUND)

        self._server = ThreadingHTTPServer((LOOPBACK_HOST, 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="fake-github-releases",
        )
        self._thread_started = False
        try:
            self._thread.start()
            self._thread_started = True
        except BaseException:
            self._server.server_close()
            self._server = None
            self._thread = None
            raise

    def close(self) -> None:
        server = self._server
        thread = self._thread
        thread_started = self._thread_started
        self._server = None
        self._thread = None
        self._thread_started = False
        try:
            if server is not None:
                try:
                    if thread_started:
                        server.shutdown()
                finally:
                    server.server_close()
        finally:
            if thread is not None and thread.is_alive():
                thread.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)

    def __enter__(self) -> FakeGitHubReleasesServer:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
