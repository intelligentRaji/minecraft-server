"""Unit tests for ModSync client SHA-256 verification, staging, and pruning."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
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


def _make_forge_jar_bytes(mod_id: str, extra: str = "1.0.0") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "META-INF/mods.toml",
            f'modLoader="javafml"\n[[mods]]\nmodId="{mod_id}"\nversion="{extra}"\n',
        )
    return buf.getvalue()


def test_sync_preserves_unknown_user_mods_and_prunes_managed(
    mods_dir: Path,
    staging_dir: Path,
) -> None:
    (mods_dir / "user-zoom.jar").write_bytes(b"personal-client-mod")
    remote_files = {
        "create.jar": b"create-v1",
        "old-mod.jar": b"old-v1",
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
    assert res.added == ("create.jar", "old-mod.jar")
    assert res.removed == ()
    assert (mods_dir / "user-zoom.jar").read_bytes() == b"personal-client-mod"
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"

    # Second sync is a no-op with 0 downloads
    transport.downloads.clear()
    res2 = syncer.sync_once()
    assert res2.status == SyncStatus.SYNCED
    assert transport.downloads == []

    # Server removes old-mod.jar, adds new-mod.jar, and updates create.jar
    remote_v2 = {
        "create.jar": b"create-v2",
        "new-mod.jar": b"new-v1",
    }
    transport.manifest_payload = _manifest_for(remote_v2, "v2")
    transport.files = remote_v2

    res3 = syncer.sync_once()
    assert res3.status == SyncStatus.SYNCED
    assert res3.added == ("new-mod.jar",)
    assert res3.updated == ("create.jar",)
    assert res3.removed == ("old-mod.jar",)
    assert not (mods_dir / "old-mod.jar").exists()
    assert (mods_dir / "new-mod.jar").read_bytes() == b"new-v1"
    assert (mods_dir / "create.jar").read_bytes() == b"create-v2"
    assert (mods_dir / "user-zoom.jar").read_bytes() == b"personal-client-mod"


def test_sync_replaces_unmanaged_duplicate_forge_mod_id(
    mods_dir: Path,
    staging_dir: Path,
) -> None:
    (mods_dir / "create-6.0.7.jar").write_bytes(_make_forge_jar_bytes("create", "6.0.7"))
    (mods_dir / "zoomify-2.14.0.jar").write_bytes(_make_forge_jar_bytes("zoomify", "2.14.0"))

    create_v2_bytes = _make_forge_jar_bytes("create", "6.0.8")
    remote_files = {"create-6.0.8.jar": create_v2_bytes}
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
    assert res.added == ("create-6.0.8.jar",)
    assert res.removed == ("create-6.0.7.jar",)
    assert not (mods_dir / "create-6.0.7.jar").exists()
    assert (mods_dir / "create-6.0.8.jar").read_bytes() == create_v2_bytes
    assert (mods_dir / "zoomify-2.14.0.jar").is_file()


def test_sync_across_skipped_versions_deletes_all_removed_server_mods(
    mods_dir: Path,
    staging_dir: Path,
) -> None:
    (mods_dir / "user-zoom.jar").write_bytes(b"personal-client-mod")
    v1_files: dict[str, tuple[str, bytes]] = {
        "modA-1.0.jar": ("server-client", b"a1"),
        "modB-1.0.jar": ("server-client", b"b1"),
        "modC-1.0.jar": ("server-client", b"c1"),
        "old-client.jar": ("client-only", b"oc1"),
    }
    transport = FakeTransport(
        _manifest_for(v1_files, "v1"),
        {name: data for name, (_cat, data) in v1_files.items()},
    )
    syncer = ModSyncer(
        server_url="https://mods.example.com",
        mods_dir=mods_dir,
        staging_dir=staging_dir,
        transport=transport,
        mc_running_check=lambda: False,
    )

    syncer.sync_once()
    syncer.install_recommended()

    managed_file = mods_dir / ".modsync-managed.json"
    assert json.loads(managed_file.read_text(encoding="utf-8")) == {
        "managed": ["modA-1.0.jar", "modB-1.0.jar", "modC-1.0.jar", "old-client.jar"]
    }

    # Client is offline for v2..v4 and next syncs directly at v5
    v5_files: dict[str, tuple[str, bytes]] = {
        "modB-3.0.jar": ("server-client", b"b3"),
        "modC-1.0.jar": ("server-client", b"c1"),
        "modE-1.0.jar": ("server-client", b"e1"),
    }
    transport.manifest_payload = _manifest_for(v5_files, "v5")
    transport.files = {name: data for name, (_cat, data) in v5_files.items()}

    res = syncer.sync_once()
    assert res.status == SyncStatus.SYNCED
    assert res.added == ("modB-3.0.jar", "modE-1.0.jar")
    assert res.removed == ("modA-1.0.jar", "modB-1.0.jar", "old-client.jar")
    assert not (mods_dir / "modA-1.0.jar").exists()
    assert not (mods_dir / "modB-1.0.jar").exists()
    assert not (mods_dir / "old-client.jar").exists()
    assert (mods_dir / "modB-3.0.jar").read_bytes() == b"b3"
    assert (mods_dir / "modC-1.0.jar").read_bytes() == b"c1"
    assert (mods_dir / "modE-1.0.jar").read_bytes() == b"e1"
    assert (mods_dir / "user-zoom.jar").read_bytes() == b"personal-client-mod"
    assert json.loads(managed_file.read_text(encoding="utf-8")) == {
        "managed": ["modB-3.0.jar", "modC-1.0.jar", "modE-1.0.jar"]
    }


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
