#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("auto", "x64", "arm64")]
    [string]$Arch = "auto",

    [string]$Version = "",
    [string]$ReleaseDate = "",
    [ValidateSet("", "Stable", "Beta", "Dev")]
    [string]$Channel = "",

    [switch]$ResetState,
    [switch]$PurgeLocalData,
    [switch]$DryRunReset,
    [switch]$SkipMsix,
    [switch]$AllowCrossArch,
    [switch]$Sign,
    [string]$CertThumbprint = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSCommandPath
$buildScript = Join-Path $projectRoot "build.ps1"

if (-not (Test-Path $buildScript)) {
    throw "build.ps1 not found: $buildScript"
}

$buildArgs = @("-Arch", $Arch)
if (-not [string]::IsNullOrWhiteSpace($Version))     { $buildArgs += @("-Version", $Version) }
if (-not [string]::IsNullOrWhiteSpace($ReleaseDate)) { $buildArgs += @("-ReleaseDate", $ReleaseDate) }
if (-not [string]::IsNullOrWhiteSpace($Channel))     { $buildArgs += @("-Channel", $Channel) }
if ($ResetState)    { $buildArgs += "-ResetState" }
if ($PurgeLocalData){ $buildArgs += "-PurgeLocalData" }
if ($DryRunReset)   { $buildArgs += "-DryRunReset" }
if ($SkipMsix)      { $buildArgs += "-SkipMsix" }
if ($AllowCrossArch){ $buildArgs += "-AllowCrossArch" }
if ($Sign)          { $buildArgs += "-Sign" }
if (-not [string]::IsNullOrWhiteSpace($CertThumbprint)) {
    $buildArgs += @("-CertThumbprint", $CertThumbprint)
}

Write-Host "Running Store release pipeline through build.ps1..."
& powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Store release pipeline failed."
}

Write-Host "Store release packaging complete."
