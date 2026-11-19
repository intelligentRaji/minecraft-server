"""Unit tests for ModSync client SHA-256 verification, staging, and pruning."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from modsync_client.manifest import parse_manifest
from modsync_client.syncer import ModSyncer, SyncStatus


class FakeTransport:
    """In-memory HTTP transport double for ModSyncer tests."""

    def __init__(self, manifest_payload: dict[str, Any], files: dict[str, bytes]) -> None:
        self.manifest_payload = manifest_payload
        self.files = files
        self.downloads: list[str] = []

    def get_json(self, _url: str) -> dict[str, Any]:
        return self.manifest_payload

    def download_to(self, url: str, dest_path: Path) -> None:
        self.downloads.append(url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        for key, payload in self.files.items():
            if url.endswith(key):
                dest_path.write_bytes(payload)
                return
        raise FileNotFoundError(f"Unexpected download URL: {url}")


def _manifest_for(
    files: dict[str, tuple[str, bytes]] | dict[str, bytes],
    version: str = "v1",
) -> dict[str, Any]:
    mods = []
    for name, value in sorted(files.items()):
        category, payload = value if isinstance(value, tuple) else ("server-client", value)
        mods.append(
            {
                "filename": name,
                "category": category,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "url": f"/api/mods/{category}/{name}",
            }
        )
    return {"version": version, "mods": mods}


def test_initial_sync_update_and_prune(mods_dir: Path, staging_dir: Path) -> None:
    (mods_dir / "old-mod.jar").write_bytes(b"stale")
    remote_files = {
        "create.jar": b"create-v1",
        "jade.jar": b"jade-v1",
    }
    transport = FakeTransport(_manifest_for(remote_files, "v1"), remote_files)
    syncer = ModSyncer(
        server_url="https://mods.example.com",
        mods_dir=mods_dir,
        staging_dir=staging_dir,
        transport=transport,
        mc_running_check=lambda: False,
    )

    res = syncer.sync_once()
    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create.jar", "jade.jar")
    assert res.removed == ("old-mod.jar",)
    assert not (mods_dir / "old-mod.jar").exists()
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"

    # Second sync is a no-op with 0 downloads
    transport.downloads.clear()
    res2 = syncer.sync_once()
    assert res2.status == SyncStatus.SYNCED
    assert transport.downloads == []


def test_stages_when_minecraft_running_then_applies_on_exit(
    mods_dir: Path,
    staging_dir: Path,
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    remote_files = {"create.jar": b"create-v2", "oculus.jar": b"oculus-v1"}
    transport = FakeTransport(_manifest_for(remote_files, "v2"), remote_files)

    mc_running = True
    syncer = ModSyncer(
        server_url="https://mods.example.com",
        mods_dir=mods_dir,
        staging_dir=staging_dir,
        transport=transport,
        mc_running_check=lambda: mc_running,
    )

    res = syncer.sync_once()
    assert res.status == SyncStatus.STAGED_WAITING_MC
    # Live mods_dir must remain untouched while Minecraft is open
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"
    assert not (mods_dir / "oculus.jar").exists()
    assert syncer.try_apply_staged() is None

    # Once Minecraft exits, try_apply_staged moves staged files atomically
    mc_running = False
    applied = syncer.try_apply_staged()
    assert applied is not None
    assert applied.status == SyncStatus.SYNCED
    assert (mods_dir / "create.jar").read_bytes() == b"create-v2"
    assert (mods_dir / "oculus.jar").read_bytes() == b"oculus-v1"


def test_rejects_sha256_mismatch(mods_dir: Path, staging_dir: Path) -> None:
    bad_manifest = {
        "version": "bad",
        "mods": [
            {
                "filename": "create.jar",
                "category": "server-client",
                "sha256": "0" * 64,
                "size": 9,
                "url": "/api/mods/server-client/create.jar",
            }
        ],
    }
    transport = FakeTransport(bad_manifest, {"create.jar": b"tampered!"})
    syncer = ModSyncer(
        server_url="https://mods.example.com",
        mods_dir=mods_dir,
        staging_dir=staging_dir,
        transport=transport,
        mc_running_check=lambda: False,
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        syncer.sync_once()
    assert not (mods_dir / "create.jar").exists()


@pytest.mark.parametrize(
    "bad_entry",
    [
        {
            "filename": "../evil.jar",
            "category": "server-client",
            "sha256": "a" * 64,
            "size": 1,
            "url": "/api/mods/server-client/evil.jar",
        },
        {
            "filename": "create.jar",
            "category": "server-client",
            "sha256": "not-a-sha",
            "size": 1,
            "url": "/api/mods/server-client/create.jar",
        },
        {
            "filename": "create.jar",
            "category": "server-client",
            "sha256": "a" * 64,
            "size": 1,
            "url": "",
        },
    ],
)
def test_parse_manifest_rejects_invalid_entries(bad_entry: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_manifest({"version": "evil", "mods": [bad_entry]})


def test_sync_once_skips_client_only_until_install_recommended(
    mods_dir: Path,
    staging_dir: Path,
) -> None:
    manifest = _manifest_for(
        {
            "create.jar": ("server-client", b"create-v1"),
            "oculus.jar": ("client-only", b"oculus-v1"),
        },
        version="v1",
    )
    transport = FakeTransport(
        manifest,
        {"create.jar": b"create-v1", "oculus.jar": b"oculus-v1"},
    )
    syncer = ModSyncer(
        server_url="https://mods.example.com",
        mods_dir=mods_dir,
        staging_dir=staging_dir,
        transport=transport,
        mc_running_check=lambda: False,
    )

    # Auto-sync installs only server-client mods
    res = syncer.sync_once()
    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create.jar",)
    assert (mods_dir / "create.jar").is_file()
    assert not (mods_dir / "oculus.jar").exists()

    # Clicking "Install Recommended Client Mods" installs client-only mods
    rec_res = syncer.install_recommended()
    assert rec_res.status == SyncStatus.SYNCED
    assert rec_res.added == ("oculus.jar",)
    assert (mods_dir / "oculus.jar").is_file()

    # Subsequent server-client syncs preserve already-installed client-only mods
    res2 = syncer.sync_once()
    assert res2.removed == ()
    assert (mods_dir / "oculus.jar").is_file()

    # Upgrading/replacing a client-only jar replaces the old jar while keeping server-client mods
    transport.manifest_payload = _manifest_for(
        {
            "create.jar": ("server-client", b"create-v1"),
            "oculus-v2.jar": ("client-only", b"oculus-v2"),
        },
        version="v1",
    )
    transport.files["oculus-v2.jar"] = b"oculus-v2"
    rec_res2 = syncer.install_recommended()
    assert rec_res2.added == ("oculus-v2.jar",)
    assert rec_res2.removed == ("oculus.jar",)
    assert not (mods_dir / "oculus.jar").exists()
    assert (mods_dir / "oculus-v2.jar").read_bytes() == b"oculus-v2"
    assert (mods_dir / "create.jar").is_file()
