<#
.SYNOPSIS
    Self-signs the built ConfigGen.exe with a locally-generated code-signing
    certificate, and timestamps the signature (§16).

.DESCRIPTION
    This is the honest, zero-cost path: a self-signed certificate stops
    Windows from flagging the exe as *unsigned*, and a timestamp keeps the
    signature valid after the cert itself expires. It does NOT clear
    Windows SmartScreen on a machine that hasn't explicitly trusted the
    certificate first (see deploy-cert.ps1) — only a paid EV (Extended
    Validation) code-signing certificate from a public CA does that
    automatically, everywhere, out of the box. For a public/open-source
    tool, the zero-friction alternative is simply telling users to run
    ConfigGen from source (`python run_configgen.py`) instead of trusting
    a signed exe from an unknown publisher.

.PARAMETER ExePath
    Path to the exe to sign. Defaults to the PyInstaller COLLECT output.

.EXAMPLE
    ./packaging/sign.ps1
    ./packaging/sign.ps1 -ExePath dist/ConfigGen/ConfigGen.exe
#>

param(
    [string]$ExePath = "dist/ConfigGen/ConfigGen.exe",
    [string]$CertSubject = "CN=ConfigGen Self-Signed",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ExePath)) {
    Write-Error "Exe not found at '$ExePath' - build it first with 'pyinstaller packaging/ConfigGen.spec'."
    exit 1
}

# Reuse an existing self-signed cert in CurrentUser\My if one with this
# subject already exists, instead of minting a new one (and a new
# fingerprint that deploy-cert.ps1 users would have to re-trust) every run.
$cert = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object { $_.Subject -eq $CertSubject } |
    Select-Object -First 1

if (-not $cert) {
    Write-Host "No existing '$CertSubject' certificate found - creating one."
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $CertSubject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyExportPolicy Exportable `
        -KeyUsage DigitalSignature `
        -NotAfter (Get-Date).AddYears(3)
    Write-Host "Created certificate with thumbprint $($cert.Thumbprint)."
    Write-Host "Export it for other machines with:"
    Write-Host "  Export-Certificate -Cert Cert:\CurrentUser\My\$($cert.Thumbprint) -FilePath packaging\ConfigGen.cer"
}

Write-Host "Signing $ExePath ..."
$result = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert -TimestampServer $TimestampUrl

if ($result.Status -ne "Valid") {
    Write-Error "Signing finished with status '$($result.Status)': $($result.StatusMessage)"
    exit 1
}

Write-Host "Signed successfully. Verify with:"
Write-Host "  Get-AuthenticodeSignature '$ExePath'"
