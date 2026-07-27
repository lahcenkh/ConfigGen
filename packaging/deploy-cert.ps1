<#
.SYNOPSIS
    Trusts ConfigGen's self-signed code-signing certificate on this PC
    (§16), so Windows stops warning about the exe sign.ps1 produced.

.DESCRIPTION
    A self-signed certificate isn't chained to a public Certificate
    Authority, so no other machine trusts it by default - each PC that
    will run the signed exe needs this script (or the equivalent manual
    steps) run once, with an elevated (Administrator) PowerShell session,
    to add the certificate to its Trusted Root store. This does not make
    ConfigGen "verified" in any general sense; it only tells *this* machine
    to trust *this specific* certificate. Only a paid EV code-signing
    certificate from a public CA is trusted automatically, on every
    machine, without this step - see sign.ps1's notes.

.PARAMETER CertPath
    Path to the exported .cer file (see sign.ps1's "Export it for other
    machines" step).

.EXAMPLE
    # From an elevated PowerShell prompt:
    ./packaging/deploy-cert.ps1 -CertPath packaging\ConfigGen.cer
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$CertPath
)

$ErrorActionPreference = "Stop"

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run this script from an elevated (Administrator) PowerShell session."
    exit 1
}

if (-not (Test-Path $CertPath)) {
    Write-Error "Certificate file not found at '$CertPath'."
    exit 1
}

Write-Host "Importing $CertPath into the machine's Trusted Root store ..."
Import-Certificate -FilePath $CertPath -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null

Write-Host "Done. ConfigGen builds signed with the matching certificate will"
Write-Host "no longer show an 'unknown publisher' warning on this PC."
