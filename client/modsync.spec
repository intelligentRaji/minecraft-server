# pyright: reportUndefinedVariable=false
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

project_root = Path(SPECPATH)
src_dir = project_root / "src"


def _build_windows_version_file() -> str | None:
    if sys.platform != "win32":
        return None
    import pyinstaller_versionfile

    with (project_root / "pyproject.toml").open("rb") as handle:
        app_version = str(tomllib.load(handle)["project"]["version"]).strip()

    version_file = project_root / "build" / "versionfile.txt"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    pyinstaller_versionfile.create_versionfile(
        output_file=str(version_file),
        version=app_version,
        company_name="Minecraft Server ModSync",
        file_description="ModSync Background Minecraft Modpack Synchronizer",
        internal_name="ModSync",
        original_filename="ModSync.exe",
        product_name="ModSync",
    )
    return str(version_file)


a = Analysis(
    [str(src_dir / "modsync_client" / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pystray._win32",
        "pystray._xorg",
        "pystray._appindicator",
        "PIL._tkinter_finder",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ModSync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=(sys.platform != "win32"),
    disable_windowed_traceback=False,
    version=_build_windows_version_file(),
)
