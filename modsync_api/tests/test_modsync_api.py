"""FastAPI HTTP & WebSocket integration tests for modsync_api."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.main import create_app  # noqa: E402


@pytest.fixture()
def modpack_dir(tmp_path: Path) -> Path:
    root = tmp_path / "modpack"
    (root / "server-client").mkdir(parents=True)
    (root / "client-only").mkdir(parents=True)
    (root / "server-only").mkdir(parents=True)
    (root / "server-client" / "create.jar").write_bytes(b"create-jar-payload")
    (root / "client-only" / "oculus.jar").write_bytes(b"oculus-jar-payload")
    (root / "server-only" / "luckperms.jar").write_bytes(b"server-only-payload")
    return root


def test_manifest_etag_and_mod_download(modpack_dir: Path) -> None:
    app = create_app(modpack_dir=modpack_dir, admin_token="secret-admin", watch_interval=0)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["mod_count"] == 2

        resp = client.get("/api/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mod_count"] == 2
        assert [m["filename"] for m in data["mods"]] == ["create.jar", "oculus.jar"]
        etag = resp.headers["etag"]

        not_modified = client.get("/api/manifest", headers={"If-None-Match": etag})
        assert not_modified.status_code == 304

        jar_resp = client.get("/api/mods/server-client/create.jar")
        assert jar_resp.status_code == 200
        assert jar_resp.content == b"create-jar-payload"
        assert jar_resp.headers["etag"] == f'"{hashlib.sha256(b"create-jar-payload").hexdigest()}"'

        # server-only mods must never be served
        assert client.get("/api/mods/server-only/luckperms.jar").status_code == 404


def test_websocket_hello_and_reload_broadcast(modpack_dir: Path) -> None:
    app = create_app(modpack_dir=modpack_dir, admin_token="secret-admin", watch_interval=0)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["mod_count"] == 2
            initial_version = hello["version"]

            # Unauthorized reload rejected
            unauth = client.post("/api/reload")
            assert unauth.status_code == 401

            # Add new jar and trigger reload -> WS receives instant mods_updated event
            (modpack_dir / "client-only" / "jade.jar").write_bytes(b"jade-payload")
            reloaded = client.post("/api/reload", headers={"X-Admin-Token": "secret-admin"})
            assert reloaded.status_code == 200
            body = reloaded.json()
            assert body["changed"] is True
            assert body["notified_clients"] == 1
            assert body["version"] != initial_version

            event = ws.receive_json()
            assert event["type"] == "mods_updated"
            assert event["version"] == body["version"]
            assert event["mod_count"] == 3
