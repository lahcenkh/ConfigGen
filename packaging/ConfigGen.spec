# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec (§16). Build from the repo root with:

    pyinstaller packaging/ConfigGen.spec

Produces two independent one-folder builds (faster startup than --onefile,
and easier to inspect what shipped):

  - dist/ConfigGen/ConfigGen.exe          windowed GUI (console=False)
  - dist/ConfigGen-CLI/ConfigGen-CLI.exe  console CLI (console=True)

They're built as two separate Analysis/EXE/COLLECT pipelines rather than
merged into one folder (PyInstaller's MERGE()) on purpose: MERGE gives
every merged executable onefile semantics — even in a onedir build, it'd
extract the GUI's shared dependencies into a temp directory on every CLI
invocation, which is exactly the startup-latency problem onedir was chosen
to avoid in the first place. The CLI's own dependency graph (configgen.cli
-> core/*, no configgen.ui, no PySide6/Qt — confirmed by grepping for
PySide6 imports) is a strict, much smaller subset of the GUI's, so the
duplication this costs is small.

Each entry point (run_configgen.py / run_configgen_cli.py) is a plain
top-level script with only absolute imports (§19: a relative import or
package __main__.py fails once frozen).
"""

from pathlib import Path

# SPECPATH is injected by PyInstaller itself at exec time and points at
# this file's own directory (packaging/), so the repo root is its parent.
ROOT = Path(SPECPATH).parent  # noqa: F821

block_cipher = None

# -- GUI build (windowed) ----------------------------------------------------

a = Analysis(
    [str(ROOT / "run_configgen.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    # Static, read-only assets only (paths.bundled_assets_dir()). The
    # user-facing content directory (schemas/templates/data — read AND
    # written by Template Editor) is deliberately NOT bundled here: `datas`
    # always lands inside PyInstaller's _internal/ folder, which is the
    # wrong place for anything the app writes to (see paths.resources_dir()'s
    # docstring). build.ps1 copies that content next to the exe separately,
    # as a plain file copy, after this spec runs.
    datas=[
        (str(ROOT / "packaging" / "icon.ico"), "packaging"),
        (str(ROOT / "resources" / "branding" / "logo.svg"), "resources/branding"),
        *[(str(p), "docs") for p in sorted((ROOT / "docs").glob("*.md"))],
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
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ConfigGen",
)

# -- CLI build (console) ------------------------------------------------------

a_cli = Analysis(
    [str(ROOT / "run_configgen_cli.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    # No icon/logo/docs datas here — those only back GUI-only surfaces
    # (window icon, login/sidebar logo, the in-app Help browser), none of
    # which the CLI has.
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="ConfigGen-CLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ROOT / "packaging" / "icon.ico"),
    version=str(ROOT / "packaging" / "version_info_cli.txt"),
)

coll_cli = COLLECT(
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=False,
    name="ConfigGen-CLI",
)
