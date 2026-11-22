"""Unit tests for ModSync client SHA-256 verification, staging, and pruning."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from modsync_client.manifest import (
    HASH_CHUNK_SIZE,
    RemoteManifest,
    RemoteMod,
    compute_sha256,
    parse_manifest,
)
from modsync_client.syncer import MANAGED_STATE_FILENAME, ModSyncer, SyncStatus


class FakeTransport:
    """In-memory HTTP transport double for ModSyncer tests."""

    def __init__(
        self,
        manifest_payload: dict[str, Any],
        files: dict[str, bytes],
        *,
        get_json_error: Exception | None = None,
        download_error: Exception | None = None,
        partial_bytes_before_error: bytes | None = None,
    ) -> None:
        self.manifest_payload = manifest_payload
        self.files = files
        self.get_json_error = get_json_error
        self.download_error = download_error
        self.partial_bytes_before_error = partial_bytes_before_error
        self.requested_urls: list[str] = []
        self.downloads: list[str] = []
        self.closed = False

    def get_json(self, url: str) -> dict[str, Any]:
        self.requested_urls.append(url)
        if self.get_json_error is not None:
            raise self.get_json_error
        return self.manifest_payload

    def download_to(self, url: str, dest_path: Path) -> None:
        self.requested_urls.append(url)
        self.downloads.append(url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if self.download_error is not None:
            if self.partial_bytes_before_error is not None:
                dest_path.write_bytes(self.partial_bytes_before_error)
            raise self.download_error

        parsed_path = urlparse(url).path
        if url in self.files:
            dest_path.write_bytes(self.files[url])
            return
        if parsed_path in self.files:
            dest_path.write_bytes(self.files[parsed_path])
            return
        raise FileNotFoundError(f"Unexpected download URL: {url}")

    def close(self) -> None:
        self.closed = True


def _build_remote(
    files: dict[str, tuple[str, bytes]] | dict[str, bytes],
    version: str = "v1",
) -> tuple[dict[str, Any], dict[str, bytes]]:
    mods = []
    exact_files: dict[str, bytes] = {}
    for name, value in sorted(files.items()):
        category, payload = value if isinstance(value, tuple) else ("server-client", value)
        url_path = f"/api/mods/{category}/{name}"
        exact_files[url_path] = payload
        mods.append(
            {
                "filename": name,
                "category": category,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "url": url_path,
            }
        )
    return {"version": version, "mods": mods}, exact_files


def _write_managed_state(mods_dir: Path, names: list[str]) -> None:
    (mods_dir / MANAGED_STATE_FILENAME).write_text(
        json.dumps({"managed": names}, indent=2) + "\n",
        encoding="utf-8",
    )


def _make_forge_jar_bytes(mod_id: str, extra: str = "1.0.0") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "META-INF/mods.toml",
            f'modLoader="javafml"\n[[mods]]\nmodId="{mod_id}"\nversion="{extra}"\n',
        )
    return buf.getvalue()


@pytest.fixture
def make_syncer(mods_dir: Path, staging_dir: Path) -> Callable[..., ModSyncer]:
    """Build a ModSyncer bound to isolated temporary mods and staging directories."""

    def _factory(
        transport: FakeTransport,
        *,
        mc_running: Callable[[], bool] | bool = False,
        target_mods_dir: Path | None = None,
    ) -> ModSyncer:
        check = mc_running if callable(mc_running) else (lambda: mc_running)
        return ModSyncer(
            server_url="https://mods.example.com",
            mods_dir=target_mods_dir or mods_dir,
            staging_dir=staging_dir,
            transport=transport,
            mc_running_check=check,
        )

    return _factory


def test_sync_once_installs_new_mods_and_preserves_unmanaged(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "user-zoom.jar").write_bytes(b"personal-client-mod")
    manifest, files = _build_remote(
        {"create.jar": b"create-v1", "old-mod.jar": b"old-v1"},
        version="v1",
    )
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create.jar", "old-mod.jar")
    assert res.removed == ()
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"
    assert (mods_dir / "old-mod.jar").read_bytes() == b"old-v1"
    assert (mods_dir / "user-zoom.jar").read_bytes() == b"personal-client-mod"


def test_sync_once_is_noop_when_hashes_match(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    _write_managed_state(mods_dir, ["create.jar"])
    manifest, files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ()
    assert res.updated == ()
    assert res.removed == ()
    assert transport.downloads == []


def test_sync_once_updates_adds_and_prunes_managed_on_new_manifest(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    (mods_dir / "old-mod.jar").write_bytes(b"old-v1")
    (mods_dir / "user-zoom.jar").write_bytes(b"personal-client-mod")
    _write_managed_state(mods_dir, ["create.jar", "old-mod.jar"])
    manifest, files = _build_remote(
        {"create.jar": b"create-v2", "new-mod.jar": b"new-v1"},
        version="v2",
    )
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("new-mod.jar",)
    assert res.updated == ("create.jar",)
    assert res.removed == ("old-mod.jar",)
    assert not (mods_dir / "old-mod.jar").exists()
    assert (mods_dir / "create.jar").read_bytes() == b"create-v2"
    assert (mods_dir / "new-mod.jar").read_bytes() == b"new-v1"
    assert (mods_dir / "user-zoom.jar").read_bytes() == b"personal-client-mod"


def test_sync_replaces_unmanaged_duplicate_forge_mod_id(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create-6.0.7.jar").write_bytes(_make_forge_jar_bytes("create", "6.0.7"))
    (mods_dir / "zoomify-2.14.0.jar").write_bytes(_make_forge_jar_bytes("zoomify", "2.14.0"))
    create_v2_bytes = _make_forge_jar_bytes("create", "6.0.8")
    manifest, files = _build_remote({"create-6.0.8.jar": create_v2_bytes}, version="v1")
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create-6.0.8.jar",)
    assert res.removed == ("create-6.0.7.jar",)
    assert not (mods_dir / "create-6.0.7.jar").exists()
    assert (mods_dir / "create-6.0.8.jar").read_bytes() == create_v2_bytes
    assert (mods_dir / "zoomify-2.14.0.jar").is_file()


def test_sync_across_skipped_versions_prunes_all_removed_server_mods(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "user-zoom.jar").write_bytes(b"personal-client-mod")
    (mods_dir / "modA-1.0.jar").write_bytes(b"a1")
    (mods_dir / "modB-1.0.jar").write_bytes(b"b1")
    (mods_dir / "modC-1.0.jar").write_bytes(b"c1")
    (mods_dir / "old-client.jar").write_bytes(b"oc1")
    _write_managed_state(
        mods_dir,
        ["modA-1.0.jar", "modB-1.0.jar", "modC-1.0.jar", "old-client.jar"],
    )
    manifest, files = _build_remote(
        {
            "modB-3.0.jar": ("server-client", b"b3"),
            "modC-1.0.jar": ("server-client", b"c1"),
            "modE-1.0.jar": ("server-client", b"e1"),
        },
        version="v5",
    )
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

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
    assert json.loads((mods_dir / MANAGED_STATE_FILENAME).read_text(encoding="utf-8")) == {
        "managed": ["modB-3.0.jar", "modC-1.0.jar", "modE-1.0.jar"]
    }


def test_sync_once_skips_client_only_mods(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    manifest, files = _build_remote(
        {
            "create.jar": ("server-client", b"create-v1"),
            "oculus.jar": ("client-only", b"oculus-v1"),
        },
        version="v1",
    )
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create.jar",)
    assert (mods_dir / "create.jar").is_file()
    assert not (mods_dir / "oculus.jar").exists()


def test_install_recommended_installs_and_upgrades_client_only_without_touching_server_client(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    (mods_dir / "oculus.jar").write_bytes(b"oculus-v1")
    _write_managed_state(mods_dir, ["create.jar", "oculus.jar"])
    manifest, files = _build_remote(
        {
            "create.jar": ("server-client", b"create-remote-unused"),
            "oculus-v2.jar": ("client-only", b"oculus-v2"),
            "sodium.jar": ("client-only", b"sodium-v1"),
        },
        version="v2",
    )
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.install_recommended()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("oculus-v2.jar", "sodium.jar")
    assert res.removed == ("oculus.jar",)
    assert not (mods_dir / "oculus.jar").exists()
    assert (mods_dir / "oculus-v2.jar").read_bytes() == b"oculus-v2"
    assert (mods_dir / "sodium.jar").read_bytes() == b"sodium-v1"
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"


def test_sync_once_preserves_installed_client_only_mods(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    (mods_dir / "oculus.jar").write_bytes(b"oculus-v1")
    _write_managed_state(mods_dir, ["create.jar", "oculus.jar"])
    manifest, files = _build_remote(
        {
            "create.jar": ("server-client", b"create-v1"),
            "oculus.jar": ("client-only", b"oculus-v1"),
        },
        version="v1",
    )
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.removed == ()
    assert (mods_dir / "oculus.jar").read_bytes() == b"oculus-v1"


def test_sync_once_stages_without_modifying_mods_dir_when_mc_running(
    mods_dir: Path,
    staging_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    manifest, files = _build_remote(
        {"create.jar": b"create-v2", "oculus.jar": b"oculus-v1"},
        version="v2",
    )
    syncer = make_syncer(FakeTransport(manifest, files), mc_running=True)

    res = syncer.sync_once()

    assert res.status == SyncStatus.STAGED_WAITING_MC
    assert res.added == ("oculus.jar",)
    assert res.updated == ("create.jar",)
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"
    assert not (mods_dir / "oculus.jar").exists()
    assert (staging_dir / "create.jar").read_bytes() == b"create-v2"
    assert (staging_dir / "oculus.jar").read_bytes() == b"oculus-v1"


@pytest.mark.parametrize(
    ("stage_first", "mc_running"),
    [
        (False, False),
        (True, True),
    ],
    ids=["no-pending-sync", "minecraft-still-running"],
)
def test_try_apply_staged_returns_none_when_no_pending_or_mc_running(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
    stage_first: bool,
    mc_running: bool,
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    manifest, files = _build_remote({"create.jar": b"create-v2"}, version="v2")
    syncer = make_syncer(FakeTransport(manifest, files), mc_running=mc_running)
    if stage_first:
        syncer.sync_once()

    assert syncer.try_apply_staged() is None
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"


def test_try_apply_staged_applies_pending_changes_on_mc_exit(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    manifest, files = _build_remote(
        {"create.jar": b"create-v2", "oculus.jar": b"oculus-v1"},
        version="v2",
    )
    mc_running = True
    syncer = make_syncer(FakeTransport(manifest, files), mc_running=lambda: mc_running)
    syncer.sync_once()
    mc_running = False

    applied = syncer.try_apply_staged()

    assert applied is not None
    assert applied.status == SyncStatus.SYNCED
    assert (mods_dir / "create.jar").read_bytes() == b"create-v2"
    assert (mods_dir / "oculus.jar").read_bytes() == b"oculus-v1"


def test_sync_once_rejects_sha256_mismatch_and_cleans_part_file(
    mods_dir: Path,
    staging_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
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
    transport = FakeTransport(
        bad_manifest,
        {"/api/mods/server-client/create.jar": b"tampered!"},
    )
    syncer = make_syncer(transport)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        syncer.sync_once()

    assert not (mods_dir / "create.jar").exists()
    assert not (staging_dir / ".create.jar.part").exists()


def test_sync_once_propagates_get_json_error(
    make_syncer: Callable[..., ModSyncer],
) -> None:
    transport = FakeTransport({}, {}, get_json_error=RuntimeError("manifest 503"))
    syncer = make_syncer(transport)

    with pytest.raises(RuntimeError, match="manifest 503"):
        syncer.sync_once()


def test_sync_once_propagates_download_error_without_installing_mod(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    manifest, _files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    transport = FakeTransport(
        manifest,
        {},
        download_error=OSError("connection reset"),
        partial_bytes_before_error=b"partial-chunk",
    )
    syncer = make_syncer(transport)

    with pytest.raises(OSError, match="connection reset"):
        syncer.sync_once()

    assert not (mods_dir / "create.jar").exists()


def test_sync_once_cleans_stale_part_file_before_downloading(
    mods_dir: Path,
    staging_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    staging_dir.mkdir(parents=True)
    (staging_dir / ".create.jar.part").write_bytes(b"stale-partial-chunk")
    manifest, files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert not (staging_dir / ".create.jar.part").exists()
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"


def test_sync_once_handles_corrupt_managed_state_file(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / MANAGED_STATE_FILENAME).write_text("{corrupt json", encoding="utf-8")
    (mods_dir / "user-mod.jar").write_bytes(b"keep-me")
    manifest, files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create.jar",)
    assert (mods_dir / "user-mod.jar").read_bytes() == b"keep-me"
    assert json.loads((mods_dir / MANAGED_STATE_FILENAME).read_text(encoding="utf-8")) == {
        "managed": ["create.jar"]
    }


def test_sync_once_handles_corrupt_local_jar_during_mod_id_check(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "broken.jar").write_bytes(b"not-a-zip")
    bad_toml_buf = io.BytesIO()
    with zipfile.ZipFile(bad_toml_buf, "w") as archive:
        archive.writestr("META-INF/mods.toml", "not = [valid toml")
    (mods_dir / "broken-toml.jar").write_bytes(bad_toml_buf.getvalue())

    manifest, files = _build_remote(
        {"create.jar": _make_forge_jar_bytes("create", "1.0.0")},
        version="v1",
    )
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.removed == ()
    assert (mods_dir / "broken.jar").is_file()
    assert (mods_dir / "broken-toml.jar").is_file()


def test_sync_once_reuses_valid_prestaged_jar_without_downloading(
    mods_dir: Path,
    staging_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    staging_dir.mkdir(parents=True)
    (staging_dir / "create.jar").write_bytes(b"create-v1")
    manifest, files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.added == ("create.jar",)
    assert transport.downloads == []
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"


def test_sync_once_redownloads_when_prestaged_jar_is_corrupt(
    mods_dir: Path,
    staging_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    staging_dir.mkdir(parents=True)
    (staging_dir / "create.jar").write_bytes(b"corrupt-staged-bytes")
    manifest, files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    transport = FakeTransport(manifest, files)
    syncer = make_syncer(transport)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert transport.downloads == ["https://mods.example.com/api/mods/server-client/create.jar"]
    assert (mods_dir / "create.jar").read_bytes() == b"create-v1"


def test_sync_once_creates_missing_mods_dir_on_cold_start(
    tmp_path: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    missing_mods = tmp_path / "fresh-instance" / "mods"
    manifest, files = _build_remote({"create.jar": b"create-v1"}, version="v1")
    syncer = make_syncer(FakeTransport(manifest, files), target_mods_dir=missing_mods)

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert (missing_mods / "create.jar").read_bytes() == b"create-v1"


def test_sync_once_prunes_all_managed_mods_on_empty_manifest(
    mods_dir: Path,
    make_syncer: Callable[..., ModSyncer],
) -> None:
    (mods_dir / "create.jar").write_bytes(b"create-v1")
    (mods_dir / "user-zoom.jar").write_bytes(b"keep-me")
    _write_managed_state(mods_dir, ["create.jar"])
    manifest, files = _build_remote({}, version="v2")
    syncer = make_syncer(FakeTransport(manifest, files))

    res = syncer.sync_once()

    assert res.status == SyncStatus.SYNCED
    assert res.removed == ("create.jar",)
    assert not (mods_dir / "create.jar").exists()
    assert (mods_dir / "user-zoom.jar").read_bytes() == b"keep-me"


def test_parse_manifest_valid_payload() -> None:
    digest = "a" * 64
    parsed = parse_manifest(
        {
            "version": "v42",
            "mods": [
                {
                    "filename": "create+1.20.1.jar",
                    "category": "server-client",
                    "sha256": digest.upper(),
                    "size": 123,
                    "url": "/api/mods/server-client/create+1.20.1.jar",
                }
            ],
        }
    )

    assert parsed == RemoteManifest(
        version="v42",
        mods=(
            RemoteMod(
                filename="create+1.20.1.jar",
                category="server-client",
                sha256=digest,
                size=123,
                url="/api/mods/server-client/create+1.20.1.jar",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("bad_entry", "match_pattern"),
    [
        ("not-a-dict", "expected object"),
        (
            {
                "filename": "../evil.jar",
                "category": "server-client",
                "sha256": "a" * 64,
                "size": 1,
                "url": "/api/mods/server-client/evil.jar",
            },
            "Unsafe or invalid mod filename",
        ),
        (
            {
                "filename": "create.jar",
                "category": "server-client",
                "sha256": "not-a-sha",
                "size": 1,
                "url": "/api/mods/server-client/create.jar",
            },
            "Invalid sha256",
        ),
        (
            {
                "filename": "create.jar",
                "category": "server-client",
                "sha256": "a" * 64,
                "size": 1,
                "url": "",
            },
            "Missing download URL",
        ),
    ],
    ids=["non-dict-entry", "path-traversal-filename", "invalid-sha256", "empty-url"],
)
def test_parse_manifest_rejects_invalid_entries(
    bad_entry: object,
    match_pattern: str,
) -> None:
    with pytest.raises(ValueError, match=match_pattern):
        parse_manifest({"version": "evil", "mods": [bad_entry]})


def test_compute_sha256_hashes_multi_chunk_file(tmp_path: Path) -> None:
    payload = b"x" * (HASH_CHUNK_SIZE + 4096)
    target = tmp_path / "large.jar"
    target.write_bytes(payload)

    assert compute_sha256(target) == hashlib.sha256(payload).hexdigest()
