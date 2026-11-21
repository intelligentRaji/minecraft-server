"""Self-update check and binary replacement via GitHub Releases."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from modsync_client import __version__
from modsync_client.manifest import compute_sha256

logger = logging.getLogger("modsync_client.updater")

DEFAULT_GITHUB_REPO = "intelligentRaji/minecraft-server"
DEFAULT_GITHUB_API_URL = "https://api.github.com"
RELEASE_TAG_PREFIX = "client-v"
CHECKSUMS_ASSET_NAME = "checksums.txt"
REQUEST_TIMEOUT_SECONDS = 15.0
DOWNLOAD_TIMEOUT_SECONDS = 120.0
_SHA256_LINE_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$")


@dataclass(frozen=True)
class UpdateInfo:
    """Metadata for an available ModSync client release."""

    version: str
    tag_name: str
    html_url: str
    asset_name: str
    download_url: str
    expected_sha256: str = ""


def get_update_repo() -> str:
    """Return the GitHub owner/repo checked for ModSync client releases."""
    return os.environ.get("MODSYNC_UPDATE_REPO", DEFAULT_GITHUB_REPO).strip() or DEFAULT_GITHUB_REPO


def get_github_api_url() -> str:
    """Return the GitHub REST API base URL used for client update checks."""
    return (
        os.environ.get("MODSYNC_GITHUB_API_URL", DEFAULT_GITHUB_API_URL).strip().rstrip("/")
        or DEFAULT_GITHUB_API_URL
    )


def parse_version(raw: str) -> tuple[int, ...]:
    """Parse a release tag or semantic version string into an integer tuple."""
    text = raw.strip()
    if text.startswith(RELEASE_TAG_PREFIX):
        text = text[len(RELEASE_TAG_PREFIX) :]
    elif text.startswith(("v", "V")):
        text = text[1:]
    if not text:
        raise ValueError(f"Empty version string: {raw!r}")
    parts: list[int] = []
    for segment in text.split("."):
        if not segment.isdigit():
            raise ValueError(f"Unsupported version format: {raw!r}")
        parts.append(int(segment))
    return tuple(parts)


def is_newer_version(candidate: str, current: str) -> bool:
    """Return True if candidate version is strictly newer than current version."""
    try:
        cand_tuple = parse_version(candidate)
        curr_tuple = parse_version(current)
    except ValueError:
        return False
    max_len = max(len(cand_tuple), len(curr_tuple))
    cand_padded = cand_tuple + (0,) * (max_len - len(cand_tuple))
    curr_padded = curr_tuple + (0,) * (max_len - len(curr_tuple))
    return cand_padded > curr_padded


def platform_asset_name(platform: str = sys.platform) -> str | None:
    """Return the expected GitHub Release binary filename for the given OS."""
    if platform == "win32":
        return "ModSync.exe"
    if platform.startswith("linux"):
        return "ModSync-linux"
    return None


def parse_checksums_text(text: str) -> dict[str, str]:
    """Parse sha256sum output into a {filename: sha256_hex} mapping."""
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        match = _SHA256_LINE_RE.match(line.strip())
        if match:
            digest, filename = match.groups()
            checksums[Path(filename).name] = digest.lower()
    return checksums


def _fetch_checksum(
    http: httpx.Client,
    assets: list[dict[str, Any]],
    asset_name: str,
) -> str:
    checksums_asset = next(
        (a for a in assets if a.get("name") == CHECKSUMS_ASSET_NAME and a.get("browser_download_url")),
        None,
    )
    if checksums_asset is None:
        return ""
    try:
        resp = http.get(str(checksums_asset["browser_download_url"]), timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return parse_checksums_text(resp.text).get(asset_name, "")
    except Exception as exc:
        logger.warning("Could not fetch %s: %s", CHECKSUMS_ASSET_NAME, exc)
        return ""


def check_for_update(
    current_version: str = __version__,
    *,
    repo: str | None = None,
    platform: str = sys.platform,
    client: httpx.Client | None = None,
) -> UpdateInfo | None:
    """Query GitHub Releases and return UpdateInfo if a newer client binary exists."""
    asset_name = platform_asset_name(platform)
    if asset_name is None:
        return None

    target_repo = repo or get_update_repo()
    api_url = f"{get_github_api_url()}/repos/{target_repo}/releases?per_page=10"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"ModSync/{current_version}",
    }

    owns_client = client is None
    http = client if client is not None else httpx.Client(follow_redirects=True, headers=headers)
    try:
        resp = http.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        releases = resp.json()
        if not isinstance(releases, list):
            return None

        best: tuple[tuple[int, ...], dict[str, Any], dict[str, Any]] | None = None
        for rel in releases:
            if not isinstance(rel, dict) or rel.get("draft") or rel.get("prerelease"):
                continue
            tag = str(rel.get("tag_name", "")).strip()
            if not tag.startswith(RELEASE_TAG_PREFIX):
                continue
            if not is_newer_version(tag, current_version):
                continue
            assets = rel.get("assets") or []
            matched_asset = next(
                (a for a in assets if isinstance(a, dict) and a.get("name") == asset_name),
                None,
            )
            if matched_asset is None or not matched_asset.get("browser_download_url"):
                continue
            parsed_ver = parse_version(tag)
            if best is None or parsed_ver > best[0]:
                best = (parsed_ver, rel, matched_asset)

        if best is None:
            return None

        _, rel, asset = best
        tag = str(rel["tag_name"]).strip()
        version_str = tag[len(RELEASE_TAG_PREFIX) :]
        expected_sha = _fetch_checksum(http, rel.get("assets") or [], asset_name)
        return UpdateInfo(
            version=version_str,
            tag_name=tag,
            html_url=str(rel.get("html_url", "")),
            asset_name=asset_name,
            download_url=str(asset["browser_download_url"]),
            expected_sha256=expected_sha,
        )
    finally:
        if owns_client:
            http.close()


def cleanup_old_binary(executable_path: Path | None = None) -> None:
    """Remove leftover .old binary left after a Windows in-place update."""
    target = executable_path or (Path(sys.executable) if getattr(sys, "frozen", False) else None)
    if target is None:
        return
    old_path = target.with_name(f"{target.name}.old")
    try:
        old_path.unlink(missing_ok=True)
    except OSError:
        pass


def download_and_apply_update(
    update: UpdateInfo,
    *,
    executable_path: Path | None = None,
    platform: str = sys.platform,
    client: httpx.Client | None = None,
) -> Path:
    """Download an update binary, verify SHA-256 when available, and replace the executable."""
    if executable_path is None:
        if not getattr(sys, "frozen", False):
            raise RuntimeError("In-place updates only apply to standalone frozen binaries.")
        target = Path(sys.executable).resolve()
    else:
        target = executable_path

    tmp_path = target.with_name(f".{target.name}.new")
    tmp_path.unlink(missing_ok=True)

    owns_client = client is None
    http = client if client is not None else httpx.Client(follow_redirects=True)
    try:
        with http.stream("GET", update.download_url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
            resp.raise_for_status()
            with tmp_path.open("wb") as handle:
                for chunk in resp.iter_bytes():
                    handle.write(chunk)

        if update.expected_sha256:
            actual_sha = compute_sha256(tmp_path)
            if actual_sha.lower() != update.expected_sha256.lower():
                tmp_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Update SHA-256 mismatch for {update.asset_name}: "
                    f"expected {update.expected_sha256}, got {actual_sha}"
                )

        if platform == "win32":
            old_path = target.with_name(f"{target.name}.old")
            old_path.unlink(missing_ok=True)
            if target.exists():
                os.replace(target, old_path)
            os.replace(tmp_path, target)
        else:
            os.chmod(tmp_path, 0o755)
            os.replace(tmp_path, target)
        return target
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        if owns_client:
            http.close()


def relaunch_executable(executable_path: Path | None = None) -> None:
    """Start the newly updated executable in a detached process."""
    target = executable_path or Path(sys.executable).resolve()
    kwargs: dict[str, Any] = {"close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(target)], **kwargs)
