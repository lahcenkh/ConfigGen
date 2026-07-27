# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec (§16). Build from the repo root with:

    pyinstaller packaging/ConfigGen.spec

Produces a single windowed exe at dist/ConfigGen/ConfigGen.exe (one-folder
build — faster startup than --onefile, and easier to inspect what shipped).
The entry point is run_configgen.py, a plain top-level script with only
absolute imports (§19: a relative import or package __main__.py fails
once frozen).
"""

from pathlib import Path

# SPECPATH is injected by PyInstaller itself at exec time and points at
# this file's own directory (packaging/), so the repo root is its parent.
ROOT = Path(SPECPATH).parent  # noqa: F821

block_cipher = None

a = Analysis(
    [str(ROOT / "run_configgen.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "packaging" / "icon.ico"), "packaging"),
        (str(ROOT / "resources" / "data" / "README.txt"), "resources/data"),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name="ConfigGen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ConfigGen",
)
