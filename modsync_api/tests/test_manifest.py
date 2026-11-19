"""Unit tests for deterministic modpack manifest generation and path validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.manifest import ManifestStore, validate_jar_request


def test_ignores_server_only_and_hashes_client_mods(modpack_dir: Path) -> None:
    sc_jar = modpack_dir / "server-client" / "create-1.20.1.jar"
    co_jar = modpack_dir / "client-only" / "embeddium-0.3.jar"
    so_jar = modpack_dir / "server-only" / "chunky-1.3.jar"
    sc_jar.write_bytes(b"create-bytes")
    co_jar.write_bytes(b"embeddium-bytes")
    so_jar.write_bytes(b"chunky-bytes")

    store = ManifestStore(modpack_dir)
    manifest, changed = store.refresh()
    assert not changed  # initial load has no previous version
    assert [m.filename for m in manifest.mods] == ["create-1.20.1.jar", "embeddium-0.3.jar"]

    expected_sha = hashlib.sha256(b"create-bytes").hexdigest()
    assert manifest.mods[0].sha256 == expected_sha
    assert manifest.mods[0].url == "/api/mods/server-client/create-1.20.1.jar"

    # Refresh again without changes -> changed=False, identical version
    manifest2, changed2 = store.refresh()
    assert not changed2
    assert manifest.version == manifest2.version

    # Add a new client-only jar -> recommended_version changes, mandatory server version stays unchanged
    added_jar = modpack_dir / "client-only" / "appleskin.jar"
    added_jar.write_bytes(b"apple-bytes")
    manifest3, server_changed3 = store.refresh()
    assert not server_changed3
    assert manifest3.version == manifest.version
    assert manifest3.recommended_version != manifest.recommended_version
    assert len(manifest3.mods) == 3

    # Delete client-only jar -> recommended_version reverts and stat cache prunes removed entry
    added_jar.unlink()
    manifest4, server_changed4 = store.refresh()
    assert not server_changed4
    assert manifest4.recommended_version == manifest.recommended_version
    assert ("client-only", "appleskin.jar") not in store._stat_cache

    # Add a new server-client jar -> server_changed=True and mandatory version changes
    (modpack_dir / "server-client" / "waystones.jar").write_bytes(b"waystones-bytes")
    manifest5, server_changed5 = store.refresh()
    assert server_changed5
    assert manifest5.version != manifest.version


def test_keeps_same_filename_across_client_categories(modpack_dir: Path) -> None:
    (modpack_dir / "server-client" / "shared.jar").write_bytes(b"server-client-copy")
    (modpack_dir / "client-only" / "shared.jar").write_bytes(b"client-only-copy")

    manifest, _ = ManifestStore(modpack_dir).refresh()
    assert [(m.category, m.filename) for m in manifest.mods] == [
        ("client-only", "shared.jar"),
        ("server-client", "shared.jar"),
    ]


def test_missing_modpack_dir_returns_empty_manifest(tmp_path: Path) -> None:
    manifest, changed = ManifestStore(tmp_path / "does-not-exist").refresh()
    assert not changed
    assert manifest.mods == ()


@pytest.mark.parametrize(
    ("category", "filename"),
    [
        ("server-only", "secret-admin.jar"),
        ("unknown", "ok-mod+1.20.1.jar"),
        ("server-client", "../server-only/secret-admin.jar"),
        ("server-client", "not-a-jar.txt"),
        ("server-client", "missing.jar"),
        ("server-client", "bad name.jar"),
    ],
)
def test_validate_jar_request_blocks_invalid_paths(
    modpack_dir: Path,
    category: str,
    filename: str,
) -> None:
    (modpack_dir / "server-only" / "secret-admin.jar").write_bytes(b"secret")
    (modpack_dir / "server-client" / "ok-mod+1.20.1.jar").write_bytes(b"ok")

    assert validate_jar_request(modpack_dir, category, filename) is None


def test_validate_jar_request_accepts_valid_jar(modpack_dir: Path) -> None:
    target = modpack_dir / "server-client" / "ok-mod+1.20.1.jar"
    target.write_bytes(b"ok")
    resolved = validate_jar_request(modpack_dir, "server-client", "ok-mod+1.20.1.jar")
    assert resolved == target.resolve()


def test_blocks_symlinked_jars_and_symlinked_category_dirs(modpack_dir: Path) -> None:
    real_jar = modpack_dir / "server-client" / "real.jar"
    real_jar.write_bytes(b"real")
    (modpack_dir / "server-client" / "intra-link.jar").symlink_to(real_jar)

    secret_jar = modpack_dir / "server-only" / "secret.jar"
    secret_jar.write_bytes(b"secret")
    (modpack_dir / "client-only").rmdir()
    (modpack_dir / "client-only").symlink_to(modpack_dir / "server-only")

    assert validate_jar_request(modpack_dir, "server-client", "intra-link.jar") is None
    assert validate_jar_request(modpack_dir, "client-only", "secret.jar") is None

    manifest, _ = ManifestStore(modpack_dir).refresh()
    assert [(m.category, m.filename) for m in manifest.mods] == [("server-client", "real.jar")]
