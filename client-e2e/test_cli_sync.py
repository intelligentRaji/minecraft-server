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
from helpers.polling import FatalPollError, terminate_process_tree, wait_until


def _dir_contents(path: Path) -> list[str]:
    return sorted(p.name for p in path.iterdir())


def test_binary_version_executes_standalone(client_cli: ModSyncCli) -> None:
    """Built PyInstaller binary executes outside the source tree and exits 0 on --version."""
    result = client_cli.version()
    assert result.returncode == EXIT_CODE_SUCCESS, (
        f"Expected exit code {EXIT_CODE_SUCCESS}, got {result.returncode}; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    # Windows ModSync.exe is built with console=False so --version emits no console stdout.
    if sys.platform != "win32":
        assert APP_DISPLAY_NAME in result.stdout, (
            f"Expected {APP_DISPLAY_NAME!r} in stdout={result.stdout!r}, stderr={result.stderr!r}"
        )


def test_sync_once_downloads_mandatory_and_excludes_other_categories(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """--sync-once downloads server-client mods with valid SHA-256 and excludes client-only/server-only."""
    mods_dir = isolated_env.mods_dir

    res = client_cli.sync_once(
        server_url=api_server.server_url,
        token=api_server.client_token,
        mods_dir=mods_dir,
    )
    assert res.returncode == EXIT_CODE_SUCCESS, (
        f"--sync-once failed (rc={res.returncode}): stdout={res.stdout!r}, stderr={res.stderr!r}"
    )

    contents = _dir_contents(mods_dir)
    for mod in (DefaultMods.CREATE_V1, DefaultMods.JEI_V1):
        jar_path = mods_dir / mod.filename
        assert jar_path.is_file(), (
            f"Expected mandatory mod {mod.filename} in {mods_dir} (found {contents})"
        )
        actual_sha = compute_sha256(jar_path)
        expected_sha = api_server.expected_hashes[mod.key]
        assert actual_sha == expected_sha, (
            f"SHA-256 mismatch for {mod.filename}: expected {expected_sha}, got {actual_sha}"
        )

    assert not (mods_dir / DefaultMods.OCULUS_V1.filename).exists(), (
        f"Client-only mod {DefaultMods.OCULUS_V1.filename} must not be installed by --sync-once "
        f"(found {contents})"
    )
    assert not (mods_dir / DefaultMods.LUCKPERMS_V1.filename).exists(), (
        f"Server-only mod {DefaultMods.LUCKPERMS_V1.filename} must not be installed on client "
        f"(found {contents})"
    )


def test_sync_once_incremental_sync_updates_prunes_and_preserves_unmanaged(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """--sync-once prunes outdated/removed managed mods, updates changed JARs, and preserves unmanaged mods."""
    mods_dir = isolated_env.mods_dir

    unmanaged_jar = mods_dir / DefaultMods.UNMANAGED_USER_FILENAME
    unmanaged_jar.write_bytes(DefaultMods.UNMANAGED_USER_PAYLOAD)

    outdated_create = mods_dir / DefaultMods.CREATE_OUTDATED_LOCAL.filename
    outdated_create.write_bytes(DefaultMods.CREATE_OUTDATED_LOCAL.jar_bytes())

    api_server.write_mod(DefaultMods.TEMPORARY_V1)
    changed_init, _ = api_server.reload()
    assert changed_init is True, "Expected initial api_server.reload() to detect new TEMPORARY_V1 mod"

    res1 = client_cli.sync_once(
        server_url=api_server.server_url,
        token=api_server.client_token,
        mods_dir=mods_dir,
    )
    assert res1.returncode == EXIT_CODE_SUCCESS, (
        f"Initial --sync-once failed (rc={res1.returncode}): "
        f"stdout={res1.stdout!r}, stderr={res1.stderr!r}"
    )

    for mod in (DefaultMods.CREATE_V1, DefaultMods.JEI_V1, DefaultMods.TEMPORARY_V1):
        jar_path = mods_dir / mod.filename
        assert jar_path.is_file(), (
            f"Expected {mod.filename} in {mods_dir} after initial sync (found {_dir_contents(mods_dir)})"
        )
        assert compute_sha256(jar_path) == api_server.expected_hashes[mod.key], (
            f"SHA-256 mismatch for {mod.filename} after initial sync"
        )

    assert not outdated_create.exists(), (
        f"Expected outdated {outdated_create.name} to be pruned (found {_dir_contents(mods_dir)})"
    )
    assert unmanaged_jar.read_bytes() == DefaultMods.UNMANAGED_USER_PAYLOAD, (
        f"Unmanaged mod {unmanaged_jar.name} was modified during initial sync"
    )

    api_server.remove_mod(DefaultMods.TEMPORARY_V1)
    _, new_create_sha = api_server.write_mod(DefaultMods.CREATE_V1_PATCH)
    changed_patch, _ = api_server.reload()
    assert changed_patch is True, "Expected incremental api_server.reload() to detect modpack diff"

    res2 = client_cli.sync_once()
    assert res2.returncode == EXIT_CODE_SUCCESS, (
        f"Incremental --sync-once failed (rc={res2.returncode}): "
        f"stdout={res2.stdout!r}, stderr={res2.stderr!r}"
    )
    assert not (mods_dir / DefaultMods.TEMPORARY_V1.filename).exists(), (
        f"Removed mod {DefaultMods.TEMPORARY_V1.filename} was not pruned "
        f"(found {_dir_contents(mods_dir)})"
    )
    patched_path = mods_dir / DefaultMods.CREATE_V1_PATCH.filename
    assert patched_path.is_file(), (
        f"Expected updated {patched_path.name} in {mods_dir} (found {_dir_contents(mods_dir)})"
    )
    assert compute_sha256(patched_path) == new_create_sha, (
        f"Expected updated SHA-256 {new_create_sha} for {patched_path.name}, "
        f"got {compute_sha256(patched_path)}"
    )
    assert unmanaged_jar.read_bytes() == DefaultMods.UNMANAGED_USER_PAYLOAD, (
        f"Unmanaged mod {unmanaged_jar.name} was modified during incremental sync"
    )


def test_invite_uri_persists_config_and_syncs(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """modsync:// invite URI persists config.json and syncs mandatory mods."""
    mods_dir = isolated_env.mods_dir
    cfg_path = isolated_env.config_path
    invite_uri = api_server.build_invite_url(include_token=True)

    sync_res = client_cli.sync_once(invite_url=invite_uri, mods_dir=mods_dir)
    assert sync_res.returncode == EXIT_CODE_SUCCESS, (
        f"Invite URI --sync-once failed (rc={sync_res.returncode}): "
        f"stdout={sync_res.stdout!r}, stderr={sync_res.stderr!r}"
    )
    assert cfg_path.is_file(), f"Expected persisted config at {cfg_path}"

    saved_cfg = PersistedConfigSnapshot.from_file(cfg_path)
    assert saved_cfg.server_url == api_server.server_url
    assert saved_cfg.client_token == api_server.client_token
    assert saved_cfg.mods_dir == mods_dir
    contents = _dir_contents(mods_dir)
    assert (mods_dir / DefaultMods.CREATE_V1.filename).is_file(), (
        f"Expected {DefaultMods.CREATE_V1.filename} in {mods_dir} (found {contents})"
    )
    assert (mods_dir / DefaultMods.JEI_V1.filename).is_file(), (
        f"Expected {DefaultMods.JEI_V1.filename} in {mods_dir} (found {contents})"
    )
    assert not (mods_dir / DefaultMods.OCULUS_V1.filename).exists(), (
        f"Client-only mod must not be installed by --sync-once (found {contents})"
    )
    assert not (mods_dir / DefaultMods.LUCKPERMS_V1.filename).exists(), (
        f"Server-only mod must not be installed on client (found {contents})"
    )


def test_install_recommended_downloads_client_only_and_sync_preserves_it(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """--install-recommended installs client-only mods and subsequent --sync-once preserves them."""
    mods_dir = isolated_env.mods_dir

    sync_res = client_cli.sync_once(
        server_url=api_server.server_url,
        token=api_server.client_token,
        mods_dir=mods_dir,
    )
    assert sync_res.returncode == EXIT_CODE_SUCCESS, (
        f"Initial --sync-once failed (rc={sync_res.returncode}): "
        f"stdout={sync_res.stdout!r}, stderr={sync_res.stderr!r}"
    )
    oculus_path = mods_dir / DefaultMods.OCULUS_V1.filename
    assert not oculus_path.exists(), (
        f"Client-only {oculus_path.name} should not exist before --install-recommended "
        f"(found {_dir_contents(mods_dir)})"
    )

    rec_res = client_cli.install_recommended()
    assert rec_res.returncode == EXIT_CODE_SUCCESS, (
        f"--install-recommended failed (rc={rec_res.returncode}): "
        f"stdout={rec_res.stdout!r}, stderr={rec_res.stderr!r}"
    )
    assert oculus_path.is_file(), (
        f"Expected {oculus_path.name} in {mods_dir} after --install-recommended "
        f"(found {_dir_contents(mods_dir)})"
    )
    expected_oculus_sha = api_server.expected_hashes[DefaultMods.OCULUS_V1.key]
    assert compute_sha256(oculus_path) == expected_oculus_sha, (
        f"SHA-256 mismatch for {oculus_path.name} after --install-recommended"
    )

    sync_again = client_cli.sync_once()
    assert sync_again.returncode == EXIT_CODE_SUCCESS, (
        f"Follow-up --sync-once failed (rc={sync_again.returncode}): "
        f"stdout={sync_again.stdout!r}, stderr={sync_again.stderr!r}"
    )
    assert oculus_path.is_file(), (
        f"Expected {oculus_path.name} to be preserved after --sync-once (found {_dir_contents(mods_dir)})"
    )
    assert compute_sha256(oculus_path) == expected_oculus_sha, (
        f"SHA-256 of {oculus_path.name} changed after follow-up --sync-once"
    )


def test_sync_once_with_invalid_auth_token_exits_nonzero(
    client_cli: ModSyncCli,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """Running --sync-once with an invalid token exits with code 1 and leaves mods_dir untouched."""
    mods_dir = isolated_env.mods_dir
    unmanaged_jar = mods_dir / DefaultMods.UNMANAGED_USER_FILENAME
    unmanaged_jar.write_bytes(DefaultMods.UNMANAGED_USER_PAYLOAD)

    res = client_cli.sync_once(
        server_url=api_server.server_url,
        token=InvalidInputs.CLIENT_TOKEN,
        mods_dir=mods_dir,
    )
    assert res.returncode == EXIT_CODE_FAILURE, (
        f"Expected exit code {EXIT_CODE_FAILURE}, got {res.returncode}; "
        f"stdout={res.stdout!r}, stderr={res.stderr!r}"
    )
    contents = _dir_contents(mods_dir)
    assert contents == [DefaultMods.UNMANAGED_USER_FILENAME], (
        f"Expected only {DefaultMods.UNMANAGED_USER_FILENAME} in {mods_dir}, found {contents}"
    )
    assert unmanaged_jar.read_bytes() == DefaultMods.UNMANAGED_USER_PAYLOAD, (
        f"Unmanaged mod {unmanaged_jar.name} was altered on failed auth sync"
    )


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

        def _initial_synced() -> bool:
            if proc.poll() is not None:
                raise FatalPollError(
                    f"Headless process exited early during initial sync with code {proc.returncode}"
                )
            return (
                (mods_dir / DefaultMods.CREATE_V1.filename).is_file()
                and (mods_dir / DefaultMods.JEI_V1.filename).is_file()
                and api_server.connected_clients() >= 1
            )

        wait_until(
            _initial_synced,
            timeout=TIMEOUT_SYNC,
            description="initial headless sync and WebSocket connection",
        )

        _, waystones_sha = api_server.write_mod(DefaultMods.WAYSTONES_V1)
        _, create_v2_sha = api_server.write_mod(DefaultMods.CREATE_V2)
        api_server.remove_mod(DefaultMods.JEI_V1)

        changed, notified_clients = api_server.reload()
        assert changed is True, "Expected /api/reload to report changed=True after modpack mutation"
        assert notified_clients >= 1, (
            f"Expected at least 1 connected WebSocket client to be notified, got {notified_clients}"
        )

        def _push_applied() -> bool:
            if proc.poll() is not None:
                raise FatalPollError(
                    f"Headless process exited early during live push with code {proc.returncode}"
                )
            waystones_path = mods_dir / DefaultMods.WAYSTONES_V1.filename
            create_path = mods_dir / DefaultMods.CREATE_V2.filename
            return (
                waystones_path.is_file()
                and create_path.is_file()
                and compute_sha256(waystones_path) == waystones_sha
                and compute_sha256(create_path) == create_v2_sha
                and not (mods_dir / DefaultMods.JEI_V1.filename).exists()
            )

        wait_until(
            _push_applied,
            timeout=TIMEOUT_SYNC,
            description="WebSocket push modpack update applied to mods_dir",
        )

        assert proc.poll() is None, (
            f"Headless daemon should still be running, exited with code {proc.returncode}"
        )
    finally:
        terminate_process_tree(proc)


def test_cli_update_rejects_checksum_mismatch(
    client_cli: ModSyncCli,
    tmp_path: Path,
) -> None:
    """--update aborts with exit code 1 and leaves the existing binary untouched when SHA-256 fails."""
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
        assert bad_res.returncode == EXIT_CODE_FAILURE, (
            f"Expected exit code {EXIT_CODE_FAILURE}, got {bad_res.returncode}; "
            f"stdout={bad_res.stdout!r}, stderr={bad_res.stderr!r}"
        )
        actual_sha = compute_sha256(target_bin)
        assert actual_sha == original_sha, (
            f"Binary {target_bin.name} was modified despite checksum mismatch "
            f"(expected {original_sha}, got {actual_sha})"
        )


def test_cli_update_applies_valid_release(
    client_cli: ModSyncCli,
    tmp_path: Path,
) -> None:
    """--update verifies SHA-256 against GitHub Releases API and atomically replaces the binary."""
    asset_name = client_cli.platform_asset_name
    target_bin = tmp_path / asset_name
    shutil.copy2(client_cli.binary, target_bin)

    with FakeGitHubReleasesServer(
        version=DEFAULT_FAKE_RELEASE_VERSION,
        asset_name=asset_name,
        asset_payload=BinaryPayloads.VALID_RELEASE,
    ) as good_server:
        ok_res = client_cli.update(github_api_url=good_server.base_url, binary=target_bin)
        assert ok_res.returncode == EXIT_CODE_SUCCESS, (
            f"--update failed (rc={ok_res.returncode}): "
            f"stdout={ok_res.stdout!r}, stderr={ok_res.stderr!r}"
        )
        assert target_bin.read_bytes() == BinaryPayloads.VALID_RELEASE, (
            f"Replaced binary {target_bin.name} contents did not match VALID_RELEASE payload"
        )
        assert good_server.releases_path in good_server.requests_seen, (
            f"Expected {good_server.releases_path} in {good_server.requests_seen}"
        )
        assert good_server.checksums_path in good_server.requests_seen, (
            f"Expected {good_server.checksums_path} in {good_server.requests_seen}"
        )
        assert good_server.asset_path in good_server.requests_seen, (
            f"Expected {good_server.asset_path} in {good_server.requests_seen}"
        )
        if sys.platform == "win32":
            old_path = client_cli.old_binary_path(target_bin)
            assert old_path.is_file(), f"Expected Windows .old backup at {old_path}"
        else:
            mode = target_bin.stat().st_mode
            assert bool(mode & stat.S_IXUSR), (
                f"Expected executable permission bit (S_IXUSR) on {target_bin}, got mode {oct(mode)}"
            )


def test_startup_cleans_up_stale_old_binary(
    client_cli: ModSyncCli,
    tmp_path: Path,
) -> None:
    """Launching ModSync removes any leftover .old backup binary from a prior self-update."""
    cleanup_bin = tmp_path / f"cleanup-{client_cli.platform_asset_name}"
    shutil.copy2(client_cli.binary, cleanup_bin)
    stale_old = client_cli.old_binary_path(cleanup_bin)
    stale_old.write_bytes(BinaryPayloads.STALE_OLD_BINARY)

    ver_res = client_cli.version(binary=cleanup_bin)
    assert ver_res.returncode == EXIT_CODE_SUCCESS, (
        f"--version failed (rc={ver_res.returncode}): "
        f"stdout={ver_res.stdout!r}, stderr={ver_res.stderr!r}"
    )
    assert not stale_old.exists(), f"Expected stale backup {stale_old} to be removed on startup"
