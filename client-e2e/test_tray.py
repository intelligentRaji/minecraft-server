"""E2E tests for ModSync system-tray boot, v99.0.0 self-update relaunch, and live WS push."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import (
    EXIT_CODE_SUCCESS,
    TIMEOUT_SYNC,
    TRACEBACK_MARKER,
    ModSyncCli,
)
from helpers.dialog_driver import BaseDialogDriver, is_ci_environment
from helpers.env import IsolatedClientEnv
from helpers.fake_github import DEFAULT_FAKE_RELEASE_VERSION, FakeGitHubReleasesServer
from helpers.fixtures import (
    CFG_KEY_CLIENT_TOKEN,
    CFG_KEY_MODS_DIR,
    CFG_KEY_SERVER_URL,
    BinaryPayloads,
    DefaultMods,
    compute_sha256,
)
from helpers.polling import FatalPollError, terminate_process_tree, wait_until

TRAY_CRASH_MARKERS = (
    "ImportError",
    "ModuleNotFoundError",
    "[PYI-",
    TRACEBACK_MARKER,
    "Failed to dock icon",
    "AssertionError",
)


def _require_system_tray(dialog_driver: BaseDialogDriver) -> None:
    if sys.platform != "win32" and not dialog_driver.has_system_tray:
        msg = "X11 system tray (tint2) is unavailable in this environment"
        if is_ci_environment():
            pytest.fail(msg)
        pytest.skip(msg)


def _assert_clean_tray_logs(stderr_text: str, *, context: str) -> None:
    for marker in TRAY_CRASH_MARKERS:
        assert marker not in stderr_text, (
            f"Unexpected tray error marker {marker!r} in {context} stderr:\n{stderr_text}"
        )


def test_self_update_relaunch_boots_tray_cleanly_without_pyinstaller_env_leak(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    updated_modsync_bin: Path,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
    tmp_path: Path,
) -> None:
    """Self-updating to v99.0.0 and relaunching must boot tray mode cleanly without env leaks."""
    _require_system_tray(dialog_driver)

    target_bin = tmp_path / "relaunch-e2e" / client_cli.platform_asset_name
    target_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(client_cli.binary, target_bin)

    isolated_env.config_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_env.config_path.write_text(
        json.dumps(
            {
                CFG_KEY_SERVER_URL: api_server.server_url,
                CFG_KEY_MODS_DIR: str(isolated_env.mods_dir),
                CFG_KEY_CLIENT_TOKEN: api_server.client_token,
            }
        ),
        encoding="utf-8",
    )

    expected_user_agent = f"ModSync/{DEFAULT_FAKE_RELEASE_VERSION}"
    with (
        FakeGitHubReleasesServer(
            version=DEFAULT_FAKE_RELEASE_VERSION,
            asset_name=client_cli.platform_asset_name,
            asset_payload=updated_modsync_bin.read_bytes(),
        ) as fake_github,
        client_cli.spawn_tracked_relaunch(
            github_api_url=fake_github.base_url,
            binary=target_bin,
            env_overrides=dialog_driver.prepare_env(isolated_env.env),
        ) as relaunch,
    ):
        rc = relaunch.wait_parent()
        assert rc == EXIT_CODE_SUCCESS, (
            f"--update --relaunch failed (rc={rc}): {relaunch.read_stderr()!r}"
        )

        def _relaunched_ready() -> bool:
            stderr_text = relaunch.read_stderr()
            for marker in TRAY_CRASH_MARKERS:
                if marker in stderr_text:
                    raise FatalPollError(f"Relaunched ModSync tray crashed:\n{stderr_text}")
            return (
                relaunch.is_child_running()
                and api_server.connected_clients() >= 1
                and expected_user_agent in fake_github.user_agents_seen
            )

        try:
            wait_until(
                _relaunched_ready,
                timeout=TIMEOUT_SYNC,
                description="relaunched v99.0.0 tray process to boot, check updates, and connect WS",
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"{exc}; user_agents={fake_github.user_agents_seen!r}, "
                f"stderr={relaunch.read_stderr()!r}"
            ) from exc

        _assert_clean_tray_logs(relaunch.read_stderr(), context="relaunched tray")


def test_tray_mode_boots_checks_updates_and_applies_live_ws_update(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    api_server: ModSyncTestServer,
    isolated_env: IsolatedClientEnv,
) -> None:
    """Tray mode docks on tint2/Windows, checks GitHub Releases without downloading, and applies WS reload updates."""
    _require_system_tray(dialog_driver)
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
        _, stderr_log = client_cli.get_log_paths(proc)
        try:
            initial_state: dict[str, Any] = {}

            def _initial_ready() -> bool:
                stderr_text = (
                    stderr_log.read_text(encoding="utf-8", errors="replace")
                    if stderr_log.is_file()
                    else ""
                )
                for marker in TRAY_CRASH_MARKERS:
                    if marker in stderr_text:
                        raise FatalPollError(f"ModSync tray crashed during startup:\n{stderr_text}")
                if proc.poll() is not None:
                    raise FatalPollError(
                        f"ModSync tray process exited early with code {proc.returncode}: {stderr_text!r}"
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
                        "requests_seen": fake_github.requests_seen,
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
            stderr_text = (
                stderr_log.read_text(encoding="utf-8", errors="replace")
                if stderr_log.is_file()
                else ""
            )
            _assert_clean_tray_logs(stderr_text, context="tray mode")
        finally:
            terminate_process_tree(proc)
