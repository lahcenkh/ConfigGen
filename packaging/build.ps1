<#
.SYNOPSIS
    Builds ConfigGen.exe and ConfigGen-CLI.exe with PyInstaller (§16).

.DESCRIPTION
    Wraps `pyinstaller packaging/ConfigGen.spec` from the repo root, so
    you don't have to remember the spec's path or juggle a venv by hand.
    Installs PyInstaller into the given Python environment if it isn't
    there already. The spec defines two independent one-folder builds
    (faster startup than --onefile, easier to inspect what actually
    shipped):

        dist\ConfigGen\ConfigGen.exe          windowed GUI
        dist\ConfigGen-CLI\ConfigGen-CLI.exe  console CLI

    Point the CLI exe's --dir (and similar) flags at wherever your
    project's schemas/templates/data actually live — e.g.
    ..\ConfigGen\resources\schemas if you want it to operate on the same
    project the GUI build below is seeded with.

    This only builds. It does not sign - run sign.ps1 afterward (or pass
    -Sign here to chain straight into it) - see that script's notes on
    what self-signing does and doesn't get you.

.PARAMETER Python
    Path to the Python interpreter to build with. Defaults to the repo's
    own .venv.

.PARAMETER Clean
    Remove any previous build/ and dist/ output first, for a from-scratch
    build (PyInstaller otherwise reuses its cache incrementally).

.PARAMETER Sign
    Run sign.ps1 against the freshly built GUI exe once the build finishes
    (the CLI exe is a dev/ops tool typically run from a trusted machine or
    CI, not double-clicked by an end user, so it isn't auto-signed here —
    pass its path to sign.ps1 yourself if you want that too).

.EXAMPLE
    ./packaging/build.ps1
    ./packaging/build.ps1 -Clean
    ./packaging/build.ps1 -Clean -Sign
    ./packaging/build.ps1 -Python C:\Python312\python.exe
#>

param(
    [string]$Python = ".venv\Scripts\python.exe",
    [switch]$Clean,
    [switch]$Sign
)

$ErrorActionPreference = "Stop"

# Repo root = this script's own parent directory's parent.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path $Python)) {
    Write-Error "Python not found at '$Python'. Create the venv first (python -m venv .venv; pip install -e `".[dev]`") or pass -Python."
    exit 1
}

if ($Clean) {
    Write-Host "Removing previous build/ and dist/ ..."
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

$pyinstallerVersion = & $Python -c "import PyInstaller; print(PyInstaller.__version__)" 2>$null
if (-not $pyinstallerVersion) {
    Write-Host "PyInstaller not found in this environment - installing it ..."
    & $Python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install PyInstaller."
        exit 1
    }
}

# Always regenerate, not just when missing - packaging\icon.ico is a
# rendered copy of resources\branding\logo.svg (tools/make_icon.py), and
# a stale copy left over from a previous build would otherwise get baked
# into the exe silently, with no error to catch it.
Write-Host "Generating packaging\icon.ico from resources\branding\logo.svg ..."
& $Python tools\make_icon.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to generate packaging\icon.ico."
    exit 1
}

# Same reasoning as icon.ico above: always regenerate, not just when
# missing, so each exe's Properties > Details tab (File description,
# version, copyright, ...) can never silently ship stale metadata from a
# version bump that forgot to rerun this. Writes both version_info.txt
# (GUI) and version_info_cli.txt (CLI).
Write-Host "Generating packaging\version_info*.txt from configgen.appinfo ..."
& $Python tools\make_version_info.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to generate packaging\version_info*.txt."
    exit 1
}

Write-Host "Building ConfigGen.exe and ConfigGen-CLI.exe ..."
& $Python -m PyInstaller packaging\ConfigGen.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit 1
}

$exePath = "dist\ConfigGen\ConfigGen.exe"
$cliExePath = "dist\ConfigGen-CLI\ConfigGen-CLI.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build finished but $exePath is missing - check the PyInstaller output above."
    exit 1
}
if (-not (Test-Path $cliExePath)) {
    Write-Error "Build finished but $cliExePath is missing - check the PyInstaller output above."
    exit 1
}

# schemas/templates/data are read AND WRITTEN by the running app (Template
# Editor creates/edits/deletes them, and writes version history alongside),
# so - unlike icon.ico/logo.svg - they're deliberately not in ConfigGen.spec's
# `datas` (that always lands inside _internal/, the wrong place for anything
# the app writes to; see paths.py). Copied here as a plain file copy, next
# to the exe, so a fresh build always ships the same starter content dev
# mode does. This overwrites dist\ConfigGen\resources every build - back up
# dist\ConfigGen\resources first if you've been running the built exe and
# want to keep schemas/templates you created there.
Write-Host "Copying starter schemas/templates/data next to the exe ..."
$distResources = "dist\ConfigGen\resources"
New-Item -ItemType Directory -Force -Path $distResources | Out-Null
foreach ($folder in @("schemas", "templates", "data")) {
    Copy-Item -Recurse -Force "resources\$folder" $distResources
}

# examples/ is the richer, self-contained example set (hooks/, real
# SQLite databases + queries.yaml, filters.py, the switch_trunk example)
# that resources/ alone doesn't ship - layered on top so the packaged app
# has fully working examples out of the box (a hook-backed schema like
# device_provisioning needs hooks/device_provisioning.py to actually
# render, not just its schema+template). examples/ wins on any filename
# collision with resources/ (e.g. device_provisioning.yaml exists in
# both) - same overwrite caveat as above: back up dist\ConfigGen\resources
# first if you want to keep changes made through the running app.
Write-Host "Copying examples/ content (data, hooks, schemas, templates, filters.py) on top ..."
foreach ($folder in @("data", "hooks", "schemas", "templates")) {
    $examplesFolder = "examples\$folder"
    if (Test-Path $examplesFolder) {
        Copy-Item -Recurse -Force $examplesFolder $distResources
    }
}
Copy-Item -Force "examples\filters.py" $distResources

# __pycache__ dirs (compiled hook bytecode) aren't meant to ship.
Get-ChildItem -Path $distResources -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

Write-Host ""
Write-Host "Built: $exePath"
Write-Host "Run it with:      .\$exePath"
Write-Host "Built: $cliExePath"
Write-Host "Run it with:      .\$cliExePath --help"

if ($Sign) {
    Write-Host ""
    & "$PSScriptRoot\sign.ps1" -ExePath $exePath
}
