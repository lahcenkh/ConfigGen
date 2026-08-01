<#
.SYNOPSIS
    Builds ConfigGen.exe with PyInstaller (§16).

.DESCRIPTION
    Wraps `pyinstaller packaging/ConfigGen.spec` from the repo root, so
    you don't have to remember the spec's path or juggle a venv by hand.
    Installs PyInstaller into the given Python environment if it isn't
    there already. Output lands at dist/ConfigGen/ConfigGen.exe (a
    one-folder build, not --onefile - faster startup, easier to inspect
    what actually shipped).

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
    Run sign.ps1 against the freshly built exe once the build finishes.

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

if (-not (Test-Path "packaging\icon.ico")) {
    Write-Host "No packaging\icon.ico yet - generating it ..."
    & $Python tools\make_icon.py
}

Write-Host "Building ConfigGen.exe ..."
& $Python -m PyInstaller packaging\ConfigGen.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit 1
}

$exePath = "dist\ConfigGen\ConfigGen.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build finished but $exePath is missing - check the PyInstaller output above."
    exit 1
}

Write-Host ""
Write-Host "Built: $exePath"
Write-Host "Run it with:  .\$exePath"

if ($Sign) {
    Write-Host ""
    & "$PSScriptRoot\sign.ps1" -ExePath $exePath
}
