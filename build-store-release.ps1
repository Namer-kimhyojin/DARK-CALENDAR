[CmdletBinding()]
param(
    [ValidateSet("auto", "x64", "arm64")]
    [string]$Arch = "auto",
    [switch]$SkipResetState,
    [switch]$PurgeLocalData,
    [switch]$DryRunReset,
    [switch]$SkipMsix,
    [switch]$AllowCrossArch
)

$ErrorActionPreference = "Stop"

function Get-HostArch {
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ([string]::IsNullOrWhiteSpace($arch) -and -not [string]::IsNullOrWhiteSpace($env:PROCESSOR_ARCHITEW6432)) {
        $arch = $env:PROCESSOR_ARCHITEW6432
    }
    if ($null -eq $arch) {
        $arch = ""
    }
    $arch = $arch.ToUpperInvariant()
    switch ($arch) {
        "AMD64" { return "x64" }
        "ARM64" { return "arm64" }
        default { return $null }
    }
}

$projectRoot = Split-Path -Parent $PSCommandPath
$buildScript = Join-Path $projectRoot "build.ps1"
$uploadScript = Join-Path $projectRoot "make-store-upload.ps1"
$x64Package = Join-Path $projectRoot "dist\x64\DarkCalendar-x64.msix"
$arm64Package = Join-Path $projectRoot "dist\arm64\DarkCalendar-arm64.msix"

if (-not (Test-Path $buildScript)) {
    throw "build.ps1 not found: $buildScript"
}
if (-not (Test-Path $uploadScript)) {
    throw "make-store-upload.ps1 not found: $uploadScript"
}

$hostArch = Get-HostArch
if ([string]::IsNullOrWhiteSpace($hostArch)) {
    throw "Unable to determine host architecture."
}

$targetArch = if ($Arch -eq "auto") { $hostArch } else { $Arch }

Write-Host "Host architecture: $hostArch"
Write-Host "Target build architecture: $targetArch"

$buildArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $buildScript,
    "-Arch",
    $targetArch
)
if (-not $SkipResetState) {
    $buildArgs += "-ResetState"
}
if ($PurgeLocalData) {
    $buildArgs += "-PurgeLocalData"
}
if ($DryRunReset) {
    $buildArgs += "-DryRunReset"
}
if ($SkipMsix) {
    $buildArgs += "-SkipMsix"
}
if ($AllowCrossArch) {
    $buildArgs += "-AllowCrossArch"
}

Write-Host "Running native Store build..."
& powershell @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Native Store build failed."
}

if ($SkipMsix) {
    Write-Host "Native payload created. MSIX/upload generation skipped."
    exit 0
}

$uploadArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $uploadScript
)

if ($targetArch -eq "x64") {
    if (Test-Path $arm64Package) {
        Write-Host "arm64 MSIX detected. Creating combined Store upload for x64 + arm64."
    } else {
        Write-Warning "arm64 MSIX not found. Creating x64-only Store upload. Build arm64 on an ARM64 runner later, then rerun this script or .\\make-store-upload.ps1 for a Surface-native bundle."
        $uploadArgs += "-X64Only"
    }
} else {
    if (Test-Path $x64Package) {
        Write-Host "x64 MSIX detected. Creating combined Store upload for x64 + arm64."
    } else {
        Write-Warning "x64 MSIX not found. Creating arm64-only Store upload. Build x64 on an x64 runner later, then rerun this script or .\\make-store-upload.ps1 for a combined Store bundle."
        $uploadArgs += "-Arm64Only"
    }
}

& powershell @uploadArgs
if ($LASTEXITCODE -ne 0) {
    throw "Store upload file generation failed."
}

Write-Host "Store release packaging complete."
