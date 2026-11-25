"""FastAPI HTTP & WebSocket integration tests for modsync_api."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app

ADMIN_TOKEN = "secret-admin"
CLIENT_TOKEN = "secret-client"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}
CLIENT_HEADERS = {"Authorization": f"Bearer {CLIENT_TOKEN}"}


@pytest.fixture(autouse=True)
def seeded_modpack_env(modpack_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (modpack_dir / "server-client" / "create.jar").write_bytes(b"create-jar-payload")
    (modpack_dir / "client-only" / "oculus.jar").write_bytes(b"oculus-jar-payload")
    (modpack_dir / "server-only" / "luckperms.jar").write_bytes(b"server-only-payload")

    monkeypatch.setenv("MODPACK_DIR", str(modpack_dir))
    monkeypatch.setenv("MODSYNC_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("MODSYNC_CLIENT_TOKEN", CLIENT_TOKEN)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _assert_ws_rejected(client: TestClient, path: str = "/ws", headers: dict[str, str] | None = None) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(path, headers=headers or {}),
    ):
        pass
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_manifest_etag_and_mod_download(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == status.HTTP_200_OK
    assert health.json()["mod_count"] == 2

    resp = client.get("/api/manifest", headers=CLIENT_HEADERS)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers["cache-control"] == "no-cache"
    data = resp.json()
    assert data["mod_count"] == 2
    assert [m["filename"] for m in data["mods"]] == ["create.jar", "oculus.jar"]
    etag = resp.headers["etag"]

    not_modified = client.get("/api/manifest", headers={**CLIENT_HEADERS, "If-None-Match": etag})
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED

    jar_resp = client.get("/api/mods/server-client/create.jar", headers=CLIENT_HEADERS)
    assert jar_resp.status_code == status.HTTP_200_OK
    assert jar_resp.content == b"create-jar-payload"
    assert jar_resp.headers["etag"] == f'"{hashlib.sha256(b"create-jar-payload").hexdigest()}"'

    # server-only mods must never be served
    server_only_resp = client.get("/api/mods/server-only/luckperms.jar", headers=CLIENT_HEADERS)
    assert server_only_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer wrong-token"},
        [(b"authorization", b"Bearer \xe9")],
    ],
)
def test_client_http_endpoints_reject_invalid_auth(
    client: TestClient,
    headers: dict[str, str] | list[tuple[bytes, bytes]],
) -> None:
    for path in ("/api/manifest", "/api/mods/server-client/create.jar"):
        resp = client.get(path, headers=headers)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert resp.headers.get("www-authenticate") == "Bearer"


def test_websocket_auth_ping_and_reload_broadcast(client: TestClient, modpack_dir: Path) -> None:
    _assert_ws_rejected(client)
    _assert_ws_rejected(client, "/ws?token=wrong")
    _assert_ws_rejected(client, "/ws?token=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82")

    # Bearer header auth works alongside ?token=
    with client.websocket_connect("/ws", headers=CLIENT_HEADERS) as ws_header:
        assert ws_header.receive_json()["type"] == "hello"
        ws_header.send_text("ping")
        assert ws_header.receive_json() == {"type": "pong"}

    with client.websocket_connect(f"/ws?token={CLIENT_TOKEN}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["mod_count"] == 2
        initial_version = hello["version"]

        assert client.post("/api/reload").status_code == status.HTTP_401_UNAUTHORIZED
        bad_hdr_resp = client.post("/api/reload", headers={"X-Admin-Token": "wrong"})
        assert bad_hdr_resp.status_code == status.HTTP_401_UNAUTHORIZED
        invalid_bytes_resp = client.post("/api/reload", headers=[(b"x-admin-token", b"\xe9")])
        assert invalid_bytes_resp.status_code == status.HTTP_401_UNAUTHORIZED

        # Unchanged reload reports changed=False and notifies 0 clients
        unchanged = client.post("/api/reload", headers=ADMIN_HEADERS)
        assert unchanged.status_code == status.HTTP_200_OK
        assert unchanged.json()["changed"] is False
        assert unchanged.json()["notified_clients"] == 0

        # Adding a client-only jar updates /api/manifest without broadcasting WS mods_updated
        (modpack_dir / "client-only" / "jade.jar").write_bytes(b"jade-payload")
        client_only_reload = client.post("/api/reload", headers=ADMIN_HEADERS)
        assert client_only_reload.status_code == status.HTTP_200_OK
        assert client_only_reload.json()["changed"] is False
        assert client_only_reload.json()["notified_clients"] == 0
        assert len(client.get("/api/manifest", headers=CLIENT_HEADERS).json()["mods"]) == 3

        # Adding a server-client jar triggers changed=True and WS mods_updated broadcast
        (modpack_dir / "server-client" / "waystones.jar").write_bytes(b"waystones-payload")
        reloaded = client.post("/api/reload", headers=ADMIN_HEADERS)
        assert reloaded.status_code == status.HTTP_200_OK
        body = reloaded.json()
        assert body["changed"] is True
        assert body["notified_clients"] == 1
        assert body["version"] != initial_version

        event = ws.receive_json()
        assert event["type"] == "mods_updated"
        assert event["version"] == body["version"]
        assert event["mod_count"] == 4


def test_reload_requires_admin_token_even_on_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODSYNC_ADMIN_TOKEN", raising=False)
    with TestClient(create_app()) as unconfigured_client:
        assert unconfigured_client.post("/api/reload").status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_client_endpoints_fail_closed_without_client_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODSYNC_CLIENT_TOKEN", raising=False)
    with TestClient(create_app()) as unconfigured_client:
        assert unconfigured_client.get("/api/manifest").status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        dl_resp = unconfigured_client.get("/api/mods/server-client/create.jar")
        assert dl_resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        _assert_ws_rejected(unconfigured_client)


@pytest.mark.parametrize("bad_interval", ["0", "-1", "nan"])
def test_rejects_invalid_ws_ping_interval(monkeypatch: pytest.MonkeyPatch, bad_interval: str) -> None:
    monkeypatch.setenv("MODSYNC_WS_PING_INTERVAL", bad_interval)
    with pytest.raises(ValueError, match="MODSYNC_WS_PING_INTERVAL"):
        create_app()
