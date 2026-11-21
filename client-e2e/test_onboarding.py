"""Cross-platform E2E tests for ModSync CLI and Tkinter GUI onboarding & cancellation flows."""

from __future__ import annotations

import pytest

from helpers.api_server import ModSyncTestServer
from helpers.client_cli import EXIT_CODE_SUCCESS, TRACEBACK_MARKER, ModSyncCli
from helpers.dialog_driver import BaseDialogDriver
from helpers.env import IsolatedClientEnv
from helpers.fixtures import DefaultMods, InvalidInputs
from helpers.onboarding_wizard import OnboardingWizard

# ---------------------------------------------------------------------------
# CLI Onboarding & Cancellation E2E (--setup --headless)
# ---------------------------------------------------------------------------


def test_cli_onboarding_rejects_invalid_invite_link(
    client_cli: ModSyncCli,
    isolated_env: IsolatedClientEnv,
) -> None:
    """CLI onboarding (--setup --headless) rejects malformed invite links and does not write config."""
    res = client_cli.setup_cli(
        stdin_input=f"{InvalidInputs.CLI_INVALID_INVITE}\n{isolated_env.mods_dir}\n",
    )
    assert res.returncode != EXIT_CODE_SUCCESS
    assert TRACEBACK_MARKER not in res.stderr
    assert not isolated_env.config_path.exists()


@pytest.mark.parametrize(
    "stdin_payload",
    [
        "",
        InvalidInputs.FALLBACK_SERVER_LINE,
    ],
)
def test_cli_onboarding_eof_cancellation_exits_zero_without_traceback(
    client_cli: ModSyncCli,
    isolated_env: IsolatedClientEnv,
    stdin_payload: str,
) -> None:
    """Cancelling CLI onboarding via EOF at any step exits cleanly with code 0 and no traceback."""
    isolated_env.clear_detected_minecraft_dirs()

    res = client_cli.setup_cli(stdin_input=stdin_payload)
    assert res.returncode == EXIT_CODE_SUCCESS, (
        f"Expected exit code {EXIT_CODE_SUCCESS} on cancellation, got {res.returncode}: {res.stderr}"
    )
    assert TRACEBACK_MARKER not in res.stderr
    assert not isolated_env.config_path.exists()


# ---------------------------------------------------------------------------
# GUI Onboarding & Cancellation E2E (Xvfb on Linux, desktop session on Windows)
# ---------------------------------------------------------------------------


def test_gui_onboarding_cancel_at_step1_invite_dialog_exits_zero(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
) -> None:
    """Closing/cancelling the Step 1 invite-link dialog exits cleanly with code 0."""
    with OnboardingWizard.launch(client_cli, dialog_driver) as wizard:
        wizard.cancel_invite_step()
        wizard.assert_cancelled_cleanly()


def test_gui_onboarding_invalid_invite_shows_error_then_cancel_exits_zero(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
) -> None:
    """Entering an invalid invite link shows 'Invalid Invite Link', and cancelling retry exits 0."""
    with OnboardingWizard.launch(client_cli, dialog_driver) as wizard:
        wizard.submit_invite(InvalidInputs.GUI_INVALID_INVITE)
        wizard.acknowledge_invalid_invite_error()
        wizard.cancel_invite_step()
        wizard.assert_cancelled_cleanly()


def test_gui_onboarding_cancel_at_step2_folder_notice_exits_zero(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    api_server: ModSyncTestServer,
) -> None:
    """Cancelling/closing the Step 2 pre-folder confirmation dialog exits cleanly with code 0."""
    with OnboardingWizard.launch(client_cli, dialog_driver) as wizard:
        wizard.submit_invite(api_server.build_invite_url())
        wizard.cancel_folder_notice()
        wizard.assert_cancelled_cleanly()


def test_gui_onboarding_cancel_at_step3_directory_picker_exits_zero(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    api_server: ModSyncTestServer,
) -> None:
    """Cancelling/closing the Step 3 'Select Minecraft folder' picker exits cleanly with code 0."""
    with OnboardingWizard.launch(client_cli, dialog_driver) as wizard:
        wizard.submit_invite(api_server.build_invite_url())
        wizard.confirm_folder_notice()
        wizard.cancel_folder_picker()
        wizard.assert_cancelled_cleanly()


def test_gui_onboarding_full_completion_saves_config_and_syncs(
    client_cli: ModSyncCli,
    dialog_driver: BaseDialogDriver,
    api_server: ModSyncTestServer,
) -> None:
    """Completing all 3 GUI onboarding steps saves config.json and syncs mandatory mods."""
    with OnboardingWizard.launch(client_cli, dialog_driver) as wizard:
        wizard.submit_invite(api_server.build_invite_url())
        wizard.confirm_folder_notice()
        wizard.accept_folder_picker()

        saved = wizard.assert_completed_successfully()
    assert saved.server_url == api_server.server_url
    assert saved.client_token == api_server.client_token
    assert (saved.mods_dir / DefaultMods.CREATE_V1.filename).is_file()
    assert (saved.mods_dir / DefaultMods.JEI_V1.filename).is_file()
