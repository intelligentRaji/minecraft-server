"""E2E smoke test verifying ModSync boots in system-tray mode and applies live WebSocket updates."""

from __future__ import annotations

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import TIMEOUT_SYNC, ModSyncCli
from helpers.dialog_driver import BaseDialogDriver
from helpers.env import IsolatedClientEnv
from helpers.fake_github import DEFAULT_FAKE_RELEASE_VERSION, FakeGitHubReleasesServer
from helpers.fixtures import BinaryPayloads, DefaultMods, compute_sha256
from helpers.polling import FatalPollError, terminate_process_tree, wait_until


def test_tray_mode_boots_and_applies_live_ws_update(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """Tray mode boots with pystray, runs startup update check, and applies live WS reload updates."""
    mods_dir = isolated_env.mods_dir

    with FakeGitHubReleasesServer(
        version=DEFAULT_FAKE_RELEASE_VERSION,
        asset_name=client_cli.release_asset_name,
        asset_payload=BinaryPayloads.VALID_RELEASE,
    ) as fake_github:
        proc = client_cli.start_tray(
            server_url=api_server.server_url,
            token=api_server.client_token,
            github_api_url=fake_github.base_url,
            env_overrides=dialog_driver.prepare_env(isolated_env.env),
        )
        try:

            def _initial_ready() -> bool:
                if proc.poll() is not None:
                    raise FatalPollError(
                        f"ModSync tray process exited early with code {proc.returncode}"
                    )
                return (
                    (mods_dir / DefaultMods.CREATE_V1.filename).is_file()
                    and (mods_dir / DefaultMods.JEI_V1.filename).is_file()
                    and api_server.connected_clients() >= 1
                    and fake_github.releases_path in fake_github.requests_seen
                )

            wait_until(
                _initial_ready,
                timeout=TIMEOUT_SYNC,
                description="tray mode initial sync, WS connection, and startup update check",
            )
            assert fake_github.releases_path in fake_github.requests_seen

            _, waystones_sha = api_server.write_mod(DefaultMods.WAYSTONES_V1)
            changed, notified_clients = api_server.reload()
            assert changed is True
            assert notified_clients >= 1

            def _ws_updated() -> bool:
                if proc.poll() is not None:
                    raise FatalPollError(
                        f"ModSync tray process exited during WS update with code {proc.returncode}"
                    )
                waystones_path = mods_dir / DefaultMods.WAYSTONES_V1.filename
                return waystones_path.is_file() and compute_sha256(waystones_path) == waystones_sha

            wait_until(
                _ws_updated,
                timeout=TIMEOUT_SYNC,
                description="tray mode live WebSocket modpack update",
            )
            assert proc.poll() is None, "Tray process should still be running after live update"
        finally:
            terminate_process_tree(proc)
