"""Cross-platform E2E tests for ModSync packaged binary CLI, sync, invite URI, and WebSocket push."""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import (
    APP_DISPLAY_NAME,
    EXIT_CODE_FAILURE,
    EXIT_CODE_SUCCESS,
    TIMEOUT_SYNC,
    ModSyncCli,
)
from helpers.env import IsolatedClientEnv
from helpers.fake_github import (
    DEFAULT_FAKE_RELEASE_VERSION,
    INVALID_SHA256_HEX,
    FakeGitHubReleasesServer,
)
from helpers.fixtures import (
    BinaryPayloads,
    DefaultMods,
    InvalidInputs,
    PersistedConfigSnapshot,
    compute_sha256,
)
from helpers.polling import terminate_process_tree, wait_until


def test_binary_version_executes_standalone(client_cli: ModSyncCli) -> None:
    """Built PyInstaller binary executes outside the source tree and exits 0 on --version."""
    result = client_cli.version()
    assert result.returncode == EXIT_CODE_SUCCESS
    if sys.platform != "win32":
        assert APP_DISPLAY_NAME in result.stdout


def test_sync_once_downloads_mandatory_verifies_sha256_and_prunes_stale(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """--sync-once downloads server-client mods, skips client-only/server-only, and prunes stale managed mods."""
    mods_dir = isolated_env.mods_dir

    unmanaged_jar = mods_dir / DefaultMods.UNMANAGED_USER_FILENAME
    unmanaged_jar.write_bytes(DefaultMods.UNMANAGED_USER_PAYLOAD)

    outdated_create = mods_dir / DefaultMods.CREATE_OUTDATED_LOCAL.filename
    outdated_create.write_bytes(DefaultMods.CREATE_OUTDATED_LOCAL.jar_bytes())

    api_server.write_mod(DefaultMods.TEMPORARY_V1)
    api_server.reload()

    res1 = client_cli.sync_once(
        server_url=api_server.server_url,
        token=api_server.client_token,
        mods_dir=mods_dir,
    )
    assert res1.returncode == EXIT_CODE_SUCCESS, f"stderr: {res1.stderr}"

    expected_initial = (DefaultMods.CREATE_V1, DefaultMods.JEI_V1, DefaultMods.TEMPORARY_V1)
    for mod in expected_initial:
        jar_path = mods_dir / mod.filename
        assert jar_path.is_file(), f"Expected mandatory mod {mod.filename} to be downloaded"
        assert compute_sha256(jar_path) == api_server.expected_hashes[mod.key]

    assert not outdated_create.exists()
    assert unmanaged_jar.read_bytes() == DefaultMods.UNMANAGED_USER_PAYLOAD

    assert not (mods_dir / DefaultMods.OCULUS_V1.filename).exists()
    assert not (mods_dir / DefaultMods.LUCKPERMS_V1.filename).exists()

    api_server.remove_mod(DefaultMods.TEMPORARY_V1)
    _, new_create_sha = api_server.write_mod(DefaultMods.CREATE_V1_PATCH)
    api_server.reload()

    res2 = client_cli.sync_once()
    assert res2.returncode == EXIT_CODE_SUCCESS, f"stderr: {res2.stderr}"
    assert not (mods_dir / DefaultMods.TEMPORARY_V1.filename).exists()
    assert compute_sha256(mods_dir / DefaultMods.CREATE_V1_PATCH.filename) == new_create_sha
    assert unmanaged_jar.read_bytes() == DefaultMods.UNMANAGED_USER_PAYLOAD


def test_install_recommended_and_invite_uri_resolution(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """modsync:// invite URI persists config and --install-recommended installs client-only mods."""
    mods_dir = isolated_env.mods_dir
    cfg_path = isolated_env.config_path
    invite_uri = api_server.build_invite_url(include_token=True)

    sync_res = client_cli.sync_once(invite_url=invite_uri, mods_dir=mods_dir)
    assert sync_res.returncode == EXIT_CODE_SUCCESS, f"stderr: {sync_res.stderr}"
    assert cfg_path.is_file()

    saved_cfg = PersistedConfigSnapshot.from_file(cfg_path)
    assert saved_cfg.server_url == api_server.server_url
    assert saved_cfg.client_token == api_server.client_token
    assert saved_cfg.mods_dir == mods_dir
    assert (mods_dir / DefaultMods.CREATE_V1.filename).is_file()
    assert not (mods_dir / DefaultMods.OCULUS_V1.filename).exists()

    rec_res = client_cli.install_recommended()
    assert rec_res.returncode == EXIT_CODE_SUCCESS, f"stderr: {rec_res.stderr}"
    oculus_path = mods_dir / DefaultMods.OCULUS_V1.filename
    assert oculus_path.is_file()
    assert compute_sha256(oculus_path) == api_server.expected_hashes[DefaultMods.OCULUS_V1.key]

    sync_again = client_cli.sync_once()
    assert sync_again.returncode == EXIT_CODE_SUCCESS
    assert oculus_path.is_file()


def test_sync_once_with_invalid_auth_token_exits_nonzero(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """Running --sync-once with an invalid token exits with code 1 without corrupting mods_dir."""
    res = client_cli.sync_once(
        server_url=api_server.server_url,
        token=InvalidInputs.CLIENT_TOKEN,
        mods_dir=isolated_env.mods_dir,
    )
    assert res.returncode == EXIT_CODE_FAILURE
    assert list(isolated_env.mods_dir.iterdir()) == []


def test_headless_websocket_push_syncs_server_modpack_updates_live(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """--headless connects via WebSocket, performs initial sync, and applies live push updates on /api/reload."""
    mods_dir = isolated_env.mods_dir

    proc = client_cli.start_headless(
        server_url=api_server.server_url,
        token=api_server.client_token,
    )
    try:
        wait_until(
            lambda: (
                (mods_dir / DefaultMods.CREATE_V1.filename).is_file()
                and (mods_dir / DefaultMods.JEI_V1.filename).is_file()
                and api_server.connected_clients() >= 1
            ),
            timeout=TIMEOUT_SYNC,
            description="initial headless sync and WebSocket connection",
        )

        _, waystones_sha = api_server.write_mod(DefaultMods.WAYSTONES_V1)
        _, create_v2_sha = api_server.write_mod(DefaultMods.CREATE_V2)
        api_server.remove_mod(DefaultMods.JEI_V1)

        changed, notified_clients = api_server.reload()
        assert changed is True
        assert notified_clients >= 1

        wait_until(
            lambda: (
                (mods_dir / DefaultMods.WAYSTONES_V1.filename).is_file()
                and compute_sha256(mods_dir / DefaultMods.WAYSTONES_V1.filename) == waystones_sha
                and compute_sha256(mods_dir / DefaultMods.CREATE_V2.filename) == create_v2_sha
                and not (mods_dir / DefaultMods.JEI_V1.filename).exists()
            ),
            timeout=TIMEOUT_SYNC,
            description="WebSocket push modpack update applied to mods_dir",
        )

        assert proc.poll() is None, "Headless daemon should still be running"
    finally:
        terminate_process_tree(proc)


def test_cli_update_rejects_checksum_mismatch_and_applies_valid_release(
    client_cli: ModSyncCli,
    tmp_path: Path,
) -> None:
    """--update verifies SHA-256 against a local fake GitHub server and atomically replaces the binary."""
    asset_name = client_cli.platform_asset_name
    target_bin = tmp_path / asset_name
    shutil.copy2(client_cli.binary, target_bin)
    original_sha = compute_sha256(target_bin)

    with FakeGitHubReleasesServer(
        version=DEFAULT_FAKE_RELEASE_VERSION,
        asset_name=asset_name,
        asset_payload=BinaryPayloads.TAMPERED_RELEASE,
        checksum_override=INVALID_SHA256_HEX,
    ) as bad_server:
        bad_res = client_cli.update(github_api_url=bad_server.base_url, binary=target_bin)
        assert bad_res.returncode == EXIT_CODE_FAILURE
        assert compute_sha256(target_bin) == original_sha

    with FakeGitHubReleasesServer(
        version=DEFAULT_FAKE_RELEASE_VERSION,
        asset_name=asset_name,
        asset_payload=BinaryPayloads.VALID_RELEASE,
    ) as good_server:
        ok_res = client_cli.update(github_api_url=good_server.base_url, binary=target_bin)
        assert ok_res.returncode == EXIT_CODE_SUCCESS, f"stderr: {ok_res.stderr}"
        assert target_bin.read_bytes() == BinaryPayloads.VALID_RELEASE
        assert good_server.releases_path in good_server.requests_seen
        assert good_server.checksums_path in good_server.requests_seen
        assert good_server.asset_path in good_server.requests_seen
        if sys.platform == "win32":
            assert client_cli.old_binary_path(target_bin).is_file()
        else:
            assert bool(target_bin.stat().st_mode & stat.S_IXUSR)

    cleanup_bin = tmp_path / f"cleanup-{asset_name}"
    shutil.copy2(client_cli.binary, cleanup_bin)
    stale_old = client_cli.old_binary_path(cleanup_bin)
    stale_old.write_bytes(BinaryPayloads.STALE_OLD_BINARY)
    ver_res = client_cli.version(binary=cleanup_bin)
    assert ver_res.returncode == EXIT_CODE_SUCCESS
    assert not stale_old.exists()
