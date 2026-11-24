"""Build-time helpers for version syncing, Windows Defender exclusions, and Inno Setup."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

CLIENT_INIT_PATH = Path("client/src/modsync_client/__init__.py")
DEFAULT_ISCC_PATH = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")


def sync_client_version(version: str, *, init_path: Path = CLIENT_INIT_PATH) -> Path:
    """Synchronize client/src/modsync_client/__init__.py __version__ with the build version."""
    content = (
        '"""ModSync background client package."""\n\n'
        f'__version__ = "{version.strip()}"\n'
    )
    init_path.write_text(content, encoding="utf-8")
    return init_path


def windows_defender_exclusion_paths() -> list[str]:
    """Collect deduplicated workspace and temp paths for Windows Defender exclusions."""
    candidates: list[str] = []
    for var in ("GITHUB_WORKSPACE", "TEMP", "TMP"):
        val = os.environ.get(var, "").strip()
        if val:
            candidates.append(val)

    unique: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normcase(path)
        if norm not in seen:
            seen.add(norm)
            unique.append(path)
    return unique


def exclude_windows_defender_paths(paths: list[str] | None = None) -> None:
    """Best-effort Windows Defender exclusion registration on ephemeral CI runners."""
    targets = paths if paths is not None else windows_defender_exclusion_paths()
    for path in targets:
        res = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                "Add-MpPreference -ExclusionPath $args[0] -ErrorAction Stop",
                path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            print(f"::warning::Could not add Defender exclusion for {path}: {detail}")


def find_iscc_executable() -> str:
    """Locate Inno Setup ISCC.exe, installing it via Chocolatey if absent on the runner."""
    discovered = shutil.which("iscc")
    if discovered:
        return discovered
    if DEFAULT_ISCC_PATH.is_file():
        return str(DEFAULT_ISCC_PATH)
    subprocess.run(["choco", "install", "innosetup", "-y"], check=True)
    return str(DEFAULT_ISCC_PATH)


def build_windows_installer(version: str, *, client_dir: Path = Path("client")) -> None:
    """Compile ModSync-Setup.exe with Inno Setup using the exact build version."""
    iscc = find_iscc_executable()
    subprocess.run(
        [iscc, f"/DMyAppVersion={version.strip()}", "installer.iss"],
        cwd=client_dir,
        check=True,
    )
