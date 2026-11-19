# -*- mode: python ; coding: utf-8 -*-
# pyright: reportUndefinedVariable=false
import sys
from pathlib import Path

project_root = Path(SPECPATH)
src_dir = project_root / "src"

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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=(sys.platform != "win32"),
    disable_windowed_traceback=False,
)
