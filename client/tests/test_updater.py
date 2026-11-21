"""Unit tests for GitHub Releases self-update checks and atomic replacement."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from modsync_client.updater import (
    UpdateInfo,
    check_for_update,
    cleanup_old_binary,
    download_and_apply_update,
    is_newer_version,
    parse_checksums_text,
    parse_version,
)


def test_version_parsing_and_comparison() -> None:
    assert parse_version("client-v0.2.1") == (0, 2, 1)
    assert parse_version("v1.0.0") == (1, 0, 0)
    assert is_newer_version("client-v0.2.0", "0.1.0") is True
    assert is_newer_version("client-v0.1.0", "0.1.0") is False
    assert is_newer_version("client-v0.1.0", "0.2.0") is False
    assert is_newer_version("bad-tag", "0.1.0") is False


def test_parse_checksums_text() -> None:
    digest = "a" * 64
    parsed = parse_checksums_text(f"{digest}  ModSync.exe\n{'b' * 64} *artifacts/ModSync-linux\n")
    assert parsed == {
        "ModSync.exe": digest,
        "ModSync-linux": "b" * 64,
    }


def test_check_for_update_selects_newest_matching_release() -> None:
    exe_bytes = b"fake-windows-binary"
    exe_sha = hashlib.sha256(exe_bytes).hexdigest()
    checksums_body = f"{exe_sha}  ModSync.exe\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases"):
            return httpx.Response(
                200,
                json=[
                    {"tag_name": "server-v9.9.9", "draft": False, "prerelease": False, "assets": []},
                    {"tag_name": "client-v0.9.0", "draft": True, "prerelease": False, "assets": []},
                    {
                        "tag_name": "client-v0.2.0",
                        "draft": False,
                        "prerelease": False,
                        "html_url": "https://github.com/org/repo/releases/tag/client-v0.2.0",
                        "assets": [
                            {
                                "name": "ModSync.exe",
                                "browser_download_url": "https://downloads.example/ModSync.exe",
                            },
                            {
                                "name": "checksums.txt",
                                "browser_download_url": "https://downloads.example/checksums.txt",
                            },
                        ],
                    },
                ],
            )
        if request.url.path.endswith("/checksums.txt"):
            return httpx.Response(200, text=checksums_body)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        update = check_for_update("0.1.0", repo="org/repo", platform="win32", client=client)
        assert update == UpdateInfo(
            version="0.2.0",
            tag_name="client-v0.2.0",
            html_url="https://github.com/org/repo/releases/tag/client-v0.2.0",
            asset_name="ModSync.exe",
            download_url="https://downloads.example/ModSync.exe",
            expected_sha256=exe_sha,
        )
        assert check_for_update("0.2.0", repo="org/repo", platform="win32", client=client) is None


def test_download_and_apply_update_verifies_sha256_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "ModSync.exe"
    target.write_bytes(b"old-binary")
    new_bytes = b"new-binary-content"
    new_sha = hashlib.sha256(new_bytes).hexdigest()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=new_bytes)

    update = UpdateInfo(
        version="0.2.0",
        tag_name="client-v0.2.0",
        html_url="https://example/release",
        asset_name="ModSync.exe",
        download_url="https://downloads.example/ModSync.exe",
        expected_sha256=new_sha,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        download_and_apply_update(update, executable_path=target, platform="win32", client=client)

    assert target.read_bytes() == new_bytes
    old_backup = tmp_path / "ModSync.exe.old"
    assert old_backup.read_bytes() == b"old-binary"
    cleanup_old_binary(target)
    assert not old_backup.exists()

    bad_update = UpdateInfo(
        version="0.2.1",
        tag_name="client-v0.2.1",
        html_url="https://example/release",
        asset_name="ModSync.exe",
        download_url="https://downloads.example/ModSync.exe",
        expected_sha256="0" * 64,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            download_and_apply_update(
                bad_update, executable_path=target, platform="win32", client=client
            )
    assert target.read_bytes() == new_bytes


def test_get_github_api_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from modsync_client.updater import DEFAULT_GITHUB_API_URL, get_github_api_url

    monkeypatch.delenv("MODSYNC_GITHUB_API_URL", raising=False)
    assert get_github_api_url() == DEFAULT_GITHUB_API_URL

    monkeypatch.setenv("MODSYNC_GITHUB_API_URL", "http://127.0.0.1:9999/")
    assert get_github_api_url() == "http://127.0.0.1:9999"

