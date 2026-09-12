# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

windows_dir = Path(SPECPATH).resolve()
repo_root = windows_dir.parents[1]

hiddenimports = []
for package in ("uvicorn", "fastapi", "starlette", "pydantic"):
    hiddenimports += collect_submodules(package)

a = Analysis(
    [str(windows_dir / "sidecar_entry.py")],
    pathex=[str(windows_dir)],
    binaries=[],
    datas=[(str(repo_root / "standalone" / "schema.sql"), "standalone")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pmposhan-bridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
