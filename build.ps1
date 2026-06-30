#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("auto", "x64", "arm64")]
    [string]$Arch = "auto",

    # Version info forwarded to build-core.ps1 (skips interactive prompt)
    [string]$Version     = "",
    [string]$ReleaseDate = "",
    [ValidateSet("", "Stable", "Beta", "Dev")]
    [string]$Channel     = "",

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
    if ($null -eq $arch) { $arch = "" }
    switch ($arch.ToUpperInvariant()) {
        "AMD64" { return "x64" }
        "ARM64" { return "arm64" }
        default { return $null }
    }
}

function Find-Msix {
    param([string]$DistDir, [string]$Arch)
    $hits = Get-ChildItem -Path $DistDir -Filter "DarkCalendar-*-$Arch.msix" -File -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending
    if ($hits) { return $hits[0].FullName }
    return $null
}

$projectRoot  = Split-Path -Parent $PSCommandPath
$buildScript  = Join-Path $projectRoot "build-core.ps1"
$uploadScript = Join-Path $projectRoot "make-store-upload.ps1"

if (-not (Test-Path $buildScript))  { throw "build-core.ps1 not found: $buildScript" }
if (-not (Test-Path $uploadScript)) { throw "make-store-upload.ps1 not found: $uploadScript" }

$hostArch   = Get-HostArch
if ([string]::IsNullOrWhiteSpace($hostArch)) { throw "Cannot determine host architecture." }
$targetArch = if ($Arch -eq "auto") { $hostArch } else { $Arch }

Write-Host ("Host: {0}   Target: {1}" -f $hostArch, $targetArch) -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

$buildArgs = @("-Arch", $targetArch)

# Forward version params — if all provided, build.ps1 skips interactive prompt
if (-not [string]::IsNullOrWhiteSpace($Version))     { $buildArgs += @("-Version",     $Version) }
if (-not [string]::IsNullOrWhiteSpace($ReleaseDate)) { $buildArgs += @("-ReleaseDate", $ReleaseDate) }
if (-not [string]::IsNullOrWhiteSpace($Channel))     { $buildArgs += @("-Channel",     $Channel) }

if (-not $SkipResetState) { $buildArgs += "-ResetState" }
if ($PurgeLocalData)      { $buildArgs += "-PurgeLocalData" }
if ($DryRunReset)         { $buildArgs += "-DryRunReset" }
if ($SkipMsix)            { $buildArgs += "-SkipMsix" }
if ($AllowCrossArch)      { $buildArgs += "-AllowCrossArch" }

& powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript @buildArgs
if ($LASTEXITCODE -ne 0) { throw "build-core.ps1 failed." }

if ($SkipMsix) {
    Write-Host "Payload ready. MSIX/upload skipped (-SkipMsix)."
    exit 0
}

# ---------------------------------------------------------------------------
# Locate produced MSIX (filename includes version)
# ---------------------------------------------------------------------------

$distDir      = Join-Path $projectRoot "dist\$targetArch"
$thisMsix     = Find-Msix -DistDir $distDir -Arch $targetArch
if (-not $thisMsix) { throw "MSIX not found in $distDir. Build may have failed." }
Write-Host "MSIX: $thisMsix" -ForegroundColor DarkGray

$otherArch    = if ($targetArch -eq "x64") { "arm64" } else { "x64" }
$otherDistDir = Join-Path $projectRoot "dist\$otherArch"
$otherMsix    = Find-Msix -DistDir $otherDistDir -Arch $otherArch

# ---------------------------------------------------------------------------
# Store upload
# ---------------------------------------------------------------------------

$uploadArgs = @("-ThisMsix", $thisMsix, "-ThisArch", $targetArch)
if ($otherMsix) {
    Write-Host "$otherArch MSIX found — combined upload." -ForegroundColor DarkGray
    $uploadArgs += @("-OtherMsix", $otherMsix)
} else {
    Write-Warning "$otherArch MSIX not found — single-arch upload."
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $uploadScript @uploadArgs
if ($LASTEXITCODE -ne 0) { throw "make-store-upload.ps1 failed." }

Write-Host ""
Write-Host "Store release complete. Check release\store\" -ForegroundColor Green
