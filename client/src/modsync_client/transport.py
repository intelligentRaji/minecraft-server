"""HTTP transport protocol and httpx-backed implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

DEFAULT_HTTP_TIMEOUT_SECONDS = 60.0
DOWNLOAD_CHUNK_SIZE = 65536


class HttpTransport(Protocol):
    """Minimal HTTP transport interface for fetching manifests and downloading jars."""

    def get_json(self, url: str) -> dict[str, Any]: ...

    def download_to(self, url: str, dest_path: Path) -> None: ...


class HttpxTransport:
    """Production HTTP transport backed by httpx."""

    def __init__(
        self,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        client_token: str = "",
    ) -> None:
        import httpx

        headers = {"Authorization": f"Bearer {client_token}"} if client_token else {}
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )

    def get_json(self, url: str) -> dict[str, Any]:
        resp = self._client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Manifest response must be a JSON object")
        return data

    def download_to(self, url: str, dest_path: Path) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest_path.open("wb") as handle:
                for chunk in resp.iter_bytes(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    handle.write(chunk)

    def close(self) -> None:
        self._client.close()
