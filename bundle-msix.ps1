#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$X64Msix,
    [Parameter(Mandatory)][string]$Arm64Msix,
    [Parameter(Mandatory)][string]$OutputBundle
)

$ErrorActionPreference = "Stop"

function Find-MakeAppx {
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ([string]::IsNullOrWhiteSpace($programFilesX86)) { $programFilesX86 = "C:\Program Files (x86)" }
    $kitsRoot = Join-Path $programFilesX86 "Windows Kits\10\bin"
    if (-not (Test-Path $kitsRoot)) { return $null }

    $preferred = Get-ChildItem -Path $kitsRoot -Recurse -File -Filter "makeappx.exe" |
        Where-Object { $_.FullName -match "\\x64\\makeappx\.exe$" } |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($preferred) { return $preferred.FullName }

    $fallback = Get-ChildItem -Path $kitsRoot -Recurse -File -Filter "makeappx.exe" |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($fallback) { return $fallback.FullName }
    return $null
}

if (-not (Test-Path $X64Msix))   { throw "x64 MSIX not found: $X64Msix" }
if (-not (Test-Path $Arm64Msix)) { throw "arm64 MSIX not found: $Arm64Msix" }

$makeappx = Find-MakeAppx
if (-not $makeappx) { throw "makeappx.exe not found. Install Windows SDK." }

$bundleDir = Split-Path -Parent $OutputBundle
if (-not (Test-Path $bundleDir)) { New-Item -Path $bundleDir -ItemType Directory | Out-Null }
if (Test-Path $OutputBundle)     { Remove-Item -Force $OutputBundle }

$staging = Join-Path $bundleDir "staging"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -Path $staging -ItemType Directory | Out-Null

Copy-Item -Path $X64Msix   -Destination (Join-Path $staging (Split-Path -Leaf $X64Msix))   -Force
Copy-Item -Path $Arm64Msix -Destination (Join-Path $staging (Split-Path -Leaf $Arm64Msix)) -Force

& $makeappx bundle /d $staging /p $OutputBundle /o
if ($LASTEXITCODE -ne 0) { throw "makeappx bundle failed." }

Remove-Item -Recurse -Force $staging
Write-Host "MSIX bundle: $OutputBundle"
