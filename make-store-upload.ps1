#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ThisMsix,
    [Parameter(Mandatory)][ValidateSet("x64","arm64")][string]$ThisArch,
    [string]$OtherMsix  = "",
    [string]$OutputDir  = "release\store"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSCommandPath
$releaseDir  = Join-Path $projectRoot $OutputDir

if (-not (Test-Path $releaseDir)) {
    New-Item -Path $releaseDir -ItemType Directory | Out-Null
}

if (-not (Test-Path $ThisMsix)) { throw "MSIX not found: $ThisMsix" }

$hasBoth = -not [string]::IsNullOrWhiteSpace($OtherMsix) -and (Test-Path $OtherMsix)

if ($hasBoth) {
    # Combined x64+arm64 → msixbundle → msixupload
    $bundleScript = Join-Path $projectRoot "bundle-msix.ps1"
    if (-not (Test-Path $bundleScript)) { throw "bundle-msix.ps1 not found: $bundleScript" }

    $bundlePath = Join-Path $releaseDir "DarkCalendar.msixbundle"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $bundleScript `
        -X64Msix   (if ($ThisArch -eq "x64")   { $ThisMsix }  else { $OtherMsix }) `
        -Arm64Msix (if ($ThisArch -eq "arm64") { $ThisMsix }  else { $OtherMsix }) `
        -OutputBundle $bundlePath
    if ($LASTEXITCODE -ne 0) { throw "bundle-msix.ps1 failed." }

    $uploadTmp = Join-Path $releaseDir "DarkCalendar_arm64_x64_upload.zip"
    $uploadOut = Join-Path $releaseDir "DarkCalendar_arm64_x64.msixupload"
    if (Test-Path $uploadTmp) { Remove-Item -Force $uploadTmp }
    if (Test-Path $uploadOut) { Remove-Item -Force $uploadOut }
    Compress-Archive -Path $bundlePath -DestinationPath $uploadTmp -Force
    Move-Item -Path $uploadTmp -Destination $uploadOut -Force
    Write-Host "Store upload (combined): $uploadOut"
} else {
    # Single-arch → msixupload
    $uploadTmp = Join-Path $releaseDir "DarkCalendar_${ThisArch}_upload.zip"
    $uploadOut = Join-Path $releaseDir "DarkCalendar_${ThisArch}.msixupload"
    if (Test-Path $uploadTmp) { Remove-Item -Force $uploadTmp }
    if (Test-Path $uploadOut) { Remove-Item -Force $uploadOut }
    Compress-Archive -Path $ThisMsix -DestinationPath $uploadTmp -Force
    Move-Item -Path $uploadTmp -Destination $uploadOut -Force
    Write-Host "Store upload ($ThisArch only): $uploadOut"
}
