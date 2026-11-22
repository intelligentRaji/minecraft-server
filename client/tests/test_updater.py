"""Unit tests for GitHub Releases self-update checks and atomic replacement."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

import modsync_client.updater as updater
from modsync_client.updater import (
    DEFAULT_GITHUB_API_URL,
    DEFAULT_GITHUB_REPO,
    UpdateInfo,
    check_for_update,
    cleanup_old_binary,
    download_and_apply_update,
    get_github_api_url,
    get_update_repo,
    is_newer_version,
    parse_checksums_text,
    parse_version,
    relaunch_executable,
)


def _release_payload(
    tag_name: str,
    *,
    asset_name: str = "ModSync.exe",
    draft: bool = False,
    prerelease: bool = False,
    include_checksums: bool = True,
) -> dict[str, Any]:
    assets = [
        {
            "name": asset_name,
            "browser_download_url": f"https://downloads.example/{tag_name}/{asset_name}",
        }
    ]
    if include_checksums:
        assets.append(
            {
                "name": "checksums.txt",
                "browser_download_url": f"https://downloads.example/{tag_name}/checksums.txt",
            }
        )
    return {
        "tag_name": tag_name,
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"https://github.com/org/repo/releases/tag/{tag_name}",
        "assets": assets,
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("client-v0.2.1", (0, 2, 1)),
        ("v1.0.0", (1, 0, 0)),
        ("V2.10.3", (2, 10, 3)),
        ("0.1.0", (0, 1, 0)),
    ],
)
def test_parse_version_valid(raw: str, expected: tuple[int, ...]) -> None:
    assert parse_version(raw) == expected


@pytest.mark.parametrize("bad_version", ["", "v", "client-v", "bad-tag", "1.2.beta"])
def test_parse_version_invalid_raises(bad_version: str) -> None:
    with pytest.raises(ValueError):
        parse_version(bad_version)


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("client-v0.2.0", "0.1.0", True),
        ("client-v0.10.0", "0.2.0", True),
        ("client-v0.1.0", "0.1.0", False),
        ("client-v0.1.0", "0.2.0", False),
        ("bad-tag", "0.1.0", False),
    ],
)
def test_is_newer_version(candidate: str, current: str, expected: bool) -> None:
    assert is_newer_version(candidate, current) is expected


def test_parse_checksums_text() -> None:
    digest = "a" * 64
    parsed = parse_checksums_text(f"{digest}  ModSync.exe\n{'b' * 64} *artifacts/ModSync-linux\n")

    assert parsed == {
        "ModSync.exe": digest,
        "ModSync-linux": "b" * 64,
    }


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        (None, DEFAULT_GITHUB_API_URL),
        ("http://127.0.0.1:9999/", "http://127.0.0.1:9999"),
        ("   ", DEFAULT_GITHUB_API_URL),
    ],
)
def test_get_github_api_url_override(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
    expected: str,
) -> None:
    if env_value is not None:
        monkeypatch.setenv("MODSYNC_GITHUB_API_URL", env_value)

    assert get_github_api_url() == expected


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        (None, DEFAULT_GITHUB_REPO),
        ("custom-org/custom-repo", "custom-org/custom-repo"),
        ("  ", DEFAULT_GITHUB_REPO),
    ],
)
def test_get_update_repo(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
    expected: str,
) -> None:
    if env_value is not None:
        monkeypatch.setenv("MODSYNC_UPDATE_REPO", env_value)

    assert get_update_repo() == expected


def test_check_for_update_returns_none_on_unsupported_platform() -> None:
    def fail_if_called(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP client should not be called on unsupported platforms")

    with httpx.Client(transport=httpx.MockTransport(fail_if_called)) as client:
        assert check_for_update("0.1.0", repo="org/repo", platform="darwin", client=client) is None


def test_check_for_update_returns_none_when_up_to_date() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=[_release_payload("client-v0.2.0")])
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check_for_update("0.2.0", repo="org/repo", platform="win32", client=client) is None


def test_check_for_update_skips_non_client_draft_and_prerelease() -> None:
    releases = [
        _release_payload("server-v9.9.9"),
        _release_payload("client-v0.9.0", draft=True),
        _release_payload("client-v0.8.0", prerelease=True),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=releases)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check_for_update("0.1.0", repo="org/repo", platform="win32", client=client) is None


def test_check_for_update_selects_highest_semver_release() -> None:
    exe_sha = hashlib.sha256(b"v0.10.0-binary").hexdigest()
    releases = [
        _release_payload("client-v0.2.0"),
        _release_payload("client-v0.10.0"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=releases)
        if request.url.path == "/client-v0.10.0/checksums.txt":
            return httpx.Response(200, text=f"{exe_sha}  ModSync.exe\n")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        update = check_for_update("0.1.0", repo="org/repo", platform="win32", client=client)

    assert update == UpdateInfo(
        version="0.10.0",
        tag_name="client-v0.10.0",
        html_url="https://github.com/org/repo/releases/tag/client-v0.10.0",
        asset_name="ModSync.exe",
        download_url="https://downloads.example/client-v0.10.0/ModSync.exe",
        expected_sha256=exe_sha,
    )


def test_check_for_update_without_checksums_asset_returns_empty_sha256() -> None:
    releases = [_release_payload("client-v0.2.0", include_checksums=False)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=releases)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        update = check_for_update("0.1.0", repo="org/repo", platform="win32", client=client)

    assert update is not None
    assert update.version == "0.2.0"
    assert update.expected_sha256 == ""


def test_download_and_apply_update_win32_replaces_and_creates_old_backup(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ModSync.exe"
    target.write_bytes(b"old-binary")
    new_bytes = b"new-binary-content"
    update = UpdateInfo(
        version="0.2.0",
        tag_name="client-v0.2.0",
        html_url="https://example/release",
        asset_name="ModSync.exe",
        download_url="https://downloads.example/ModSync.exe",
        expected_sha256=hashlib.sha256(new_bytes).hexdigest(),
    )

    with httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=new_bytes))
    ) as client:
        download_and_apply_update(update, executable_path=target, platform="win32", client=client)

    assert target.read_bytes() == new_bytes
    assert (tmp_path / "ModSync.exe.old").read_bytes() == b"old-binary"


def test_download_and_apply_update_linux_replaces_with_executable_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "ModSync-linux"
    target.write_bytes(b"old-linux")
    new_bytes = b"new-linux-binary"
    update = UpdateInfo(
        version="0.2.0",
        tag_name="client-v0.2.0",
        html_url="https://example/release",
        asset_name="ModSync-linux",
        download_url="https://downloads.example/ModSync-linux",
        expected_sha256=hashlib.sha256(new_bytes).hexdigest(),
    )

    chmod_calls: list[tuple[Path, int]] = []
    real_chmod = os.chmod

    def spy_chmod(path: Path | str, mode: int) -> None:
        chmod_calls.append((Path(path), mode))
        real_chmod(path, mode)

    monkeypatch.setattr(updater.os, "chmod", spy_chmod)

    with httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=new_bytes))
    ) as client:
        download_and_apply_update(update, executable_path=target, platform="linux", client=client)

    expected_mode = 0o755
    assert target.read_bytes() == new_bytes
    assert chmod_calls == [(tmp_path / ".ModSync-linux.new", expected_mode)]
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == expected_mode
    assert not (tmp_path / "ModSync-linux.old").exists()


def test_download_and_apply_update_sha256_mismatch_preserves_target_and_removes_tmp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ModSync.exe"
    target.write_bytes(b"old-binary")
    bad_update = UpdateInfo(
        version="0.2.1",
        tag_name="client-v0.2.1",
        html_url="https://example/release",
        asset_name="ModSync.exe",
        download_url="https://downloads.example/ModSync.exe",
        expected_sha256="0" * 64,
    )

    with httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=b"tampered"))
    ) as client:
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            download_and_apply_update(
                bad_update, executable_path=target, platform="win32", client=client
            )

    assert target.read_bytes() == b"old-binary"
    assert not (tmp_path / ".ModSync.exe.new").exists()


def test_download_and_apply_update_http_error_preserves_target_and_removes_tmp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ModSync.exe"
    target.write_bytes(b"old-binary")
    update = UpdateInfo(
        version="0.2.1",
        tag_name="client-v0.2.1",
        html_url="https://example/release",
        asset_name="ModSync.exe",
        download_url="https://downloads.example/ModSync.exe",
    )

    with httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(502))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            download_and_apply_update(
                update, executable_path=target, platform="win32", client=client
            )

    assert target.read_bytes() == b"old-binary"
    assert not (tmp_path / ".ModSync.exe.new").exists()


def test_download_and_apply_update_rejects_non_frozen_without_executable_path() -> None:
    update = UpdateInfo(
        version="0.2.1",
        tag_name="client-v0.2.1",
        html_url="https://example/release",
        asset_name="ModSync-linux",
        download_url="https://downloads.example/ModSync-linux",
    )

    with pytest.raises(RuntimeError, match="standalone frozen binaries"):
        download_and_apply_update(update)


def test_cleanup_old_binary_removes_old_file(tmp_path: Path) -> None:
    target = tmp_path / "ModSync.exe"
    old_backup = tmp_path / "ModSync.exe.old"
    old_backup.write_bytes(b"old-binary")

    cleanup_old_binary(target)

    assert not old_backup.exists()


def test_cleanup_old_binary_noop_when_not_frozen(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_exe = tmp_path / "python"
    old_backup = tmp_path / "python.old"
    old_backup.write_bytes(b"keep-me")
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    cleanup_old_binary()

    assert old_backup.is_file()


def test_cleanup_old_binary_ignores_unlink_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "ModSync.exe"
    old_backup = tmp_path / "ModSync.exe.old"
    old_backup.write_bytes(b"locked")

    def _deny_unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("file in use")

    monkeypatch.setattr(Path, "unlink", _deny_unlink)

    cleanup_old_binary(target)
    assert old_backup.is_file()


def test_relaunch_executable_posix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "ModSync-linux"
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))

    relaunch_executable(target)

    assert calls == [([str(target)], {"close_fds": True})]


def test_relaunch_executable_win32(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "ModSync.exe"
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))

    relaunch_executable(target)

    assert calls == [
        (
            [str(target)],
            {"close_fds": True, "creationflags": 0x00000008 | 0x00000200},
        )
    ]
