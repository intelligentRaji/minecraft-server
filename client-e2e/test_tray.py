"""E2E smoke test verifying ModSync boots in system-tray mode and applies live WebSocket updates."""

from __future__ import annotations

from typing import Any

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import TIMEOUT_SYNC, ModSyncCli
from helpers.dialog_driver import BaseDialogDriver
from helpers.env import IsolatedClientEnv
from helpers.fake_github import DEFAULT_FAKE_RELEASE_VERSION, FakeGitHubReleasesServer
from helpers.fixtures import BinaryPayloads, DefaultMods, compute_sha256
from helpers.polling import FatalPollError, terminate_process_tree, wait_until


def test_tray_mode_boots_checks_updates_and_applies_live_ws_update(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """Tray mode boots with pystray, checks GitHub Releases without downloading, and applies WS reload updates."""
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
            initial_state: dict[str, Any] = {}

            def _initial_ready() -> bool:
                if proc.poll() is not None:
                    raise FatalPollError(
                        f"ModSync tray process exited early with code {proc.returncode}"
                    )
                has_create = (mods_dir / DefaultMods.CREATE_V1.filename).is_file()
                has_jei = (mods_dir / DefaultMods.JEI_V1.filename).is_file()
                clients = api_server.connected_clients()
                update_checked = fake_github.releases_path in fake_github.requests_seen
                initial_state.update(
                    {
                        "has_create": has_create,
                        "has_jei": has_jei,
                        "connected_clients": clients,
                        "update_checked": update_checked,
                        "requests_seen": list(fake_github.requests_seen),
                    }
                )
                return has_create and has_jei and clients >= 1 and update_checked

            try:
                wait_until(
                    _initial_ready,
                    timeout=TIMEOUT_SYNC,
                    description="tray mode initial sync, WS connection, and startup update check",
                )
            except TimeoutError as exc:
                raise TimeoutError(f"{exc}; last observed state={initial_state}") from exc

            assert fake_github.asset_path not in fake_github.requests_seen, (
                f"Startup update check must only notify, not download {fake_github.asset_path}; "
                f"requests_seen={fake_github.requests_seen}"
            )

            _, waystones_sha = api_server.write_mod(DefaultMods.WAYSTONES_V1)
            changed, notified_clients = api_server.reload()
            assert changed is True, "Expected /api/reload to detect new WAYSTONES_V1 mod"
            assert notified_clients >= 1, (
                f"Expected at least 1 connected WebSocket client to be notified, got {notified_clients}"
            )

            ws_state: dict[str, Any] = {}

            def _ws_updated() -> bool:
                if proc.poll() is not None:
                    raise FatalPollError(
                        f"ModSync tray process exited during WS update with code {proc.returncode}"
                    )
                waystones_path = mods_dir / DefaultMods.WAYSTONES_V1.filename
                exists = waystones_path.is_file()
                actual_sha = compute_sha256(waystones_path) if exists else None
                ws_state.update(
                    {
                        "waystones_exists": exists,
                        "actual_sha": actual_sha,
                        "expected_sha": waystones_sha,
                        "mods_dir_contents": sorted(p.name for p in mods_dir.iterdir()),
                    }
                )
                return exists and actual_sha == waystones_sha

            try:
                wait_until(
                    _ws_updated,
                    timeout=TIMEOUT_SYNC,
                    description="tray mode live WebSocket modpack update",
                )
            except TimeoutError as exc:
                raise TimeoutError(f"{exc}; last observed state={ws_state}") from exc

            assert proc.poll() is None, (
                f"Tray process should still be running after live update, exited with code {proc.returncode}"
            )
        finally:
            terminate_process_tree(proc)
