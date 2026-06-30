[CmdletBinding()]
param(
    [string]$Version,
    [string]$PackageVersion,
    [string]$ReleaseDate,
    [ValidateSet("auto", "x64", "arm64")]
    [string]$Arch = "auto",
    [switch]$SkipBuild,
    [switch]$SkipResetState,
    [switch]$PurgeLocalData,
    [switch]$DryRunReset,
    [switch]$SkipMsix,
    [switch]$AllowCrossArch
)

$ErrorActionPreference = "Stop"

function Read-RequiredValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt,
        [string]$DefaultValue
    )

    if ([string]::IsNullOrWhiteSpace($DefaultValue)) {
        do {
            $value = Read-Host $Prompt
        } while ([string]::IsNullOrWhiteSpace($value))
        return $value.Trim()
    }

    $value = Read-Host "$Prompt [$DefaultValue]"
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $DefaultValue.Trim()
    }
    return $value.Trim()
}

function Test-AppVersion {
    param([Parameter(Mandatory = $true)][string]$Value)
    return $Value -match '^\d+\.\d+\.\d+$'
}

function Test-PackageVersion {
    param([Parameter(Mandatory = $true)][string]$Value)
    return $Value -match '^\d+\.\d+\.\d+\.\d+$'
}

function Test-ReleaseDate {
    param([Parameter(Mandatory = $true)][string]$Value)
    return $Value -match '^\d{4}-\d{2}-\d{2}$'
}

function Get-CurrentAppVersion {
    param([Parameter(Mandatory = $true)][string]$MetadataPath)
    $text = [System.IO.File]::ReadAllText($MetadataPath, [System.Text.UTF8Encoding]::new($false, $true))
    $match = [regex]::Match($text, '(?m)^APP_VERSION\s*=\s*["'']([^"'']+)["'']')
    if (-not $match.Success) {
        throw "APP_VERSION not found in $MetadataPath"
    }
    return $match.Groups[1].Value
}

function Get-CurrentPackageVersion {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)
    [xml]$xml = Get-Content -Path $ManifestPath -Encoding UTF8
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("f", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    $identity = $xml.SelectSingleNode("/f:Package/f:Identity", $ns)
    if ($null -eq $identity) {
        throw "Identity node not found in AppxManifest.xml"
    }
    return $identity.Version
}

function Set-PythonStringConstant {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $encoding = [System.Text.UTF8Encoding]::new($false, $true)
    $text = [System.IO.File]::ReadAllText($Path, $encoding)
    if ($text -notmatch '^\s*# -\*- coding: utf-8 -\*-') {
        $text = "# -*- coding: utf-8 -*-`r`n" + $text
    }

    $escapedName = [regex]::Escape($Name)
    $pattern = "(?m)^($escapedName\s*=\s*)[""'][^""']*[""']"
    if ($text -notmatch $pattern) {
        throw "$Name not found in $Path"
    }
    $replacement = "`${1}`"$Value`""
    $text = [regex]::Replace($text, $pattern, $replacement, 1)
    [System.IO.File]::WriteAllText($Path, $text, $encoding)
}

function Set-AppxManifestVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Version
    )

    [xml]$xml = Get-Content -Path $Path -Encoding UTF8
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("f", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    $identity = $xml.SelectSingleNode("/f:Package/f:Identity", $ns)
    if ($null -eq $identity) {
        throw "Identity node not found in AppxManifest.xml"
    }
    $identity.SetAttribute("Version", $Version)

    $settings = [System.Xml.XmlWriterSettings]::new()
    $settings.Encoding = [System.Text.UTF8Encoding]::new($false)
    $settings.Indent = $true
    $settings.NewLineChars = "`r`n"
    $settings.OmitXmlDeclaration = $false

    $writer = [System.Xml.XmlWriter]::Create($Path, $settings)
    try {
        $xml.Save($writer)
    } finally {
        $writer.Close()
    }
}

$projectRoot = Split-Path -Parent $PSCommandPath
$metadataPath = Join-Path $projectRoot "calendar_app\app_metadata.py"
$manifestPath = Join-Path $projectRoot "AppxManifest.xml"
$releaseScript = Join-Path $projectRoot "build-store-release.ps1"

if (-not (Test-Path $metadataPath)) {
    throw "App metadata file not found: $metadataPath"
}
if (-not (Test-Path $manifestPath)) {
    throw "AppxManifest.xml not found: $manifestPath"
}
if (-not (Test-Path $releaseScript)) {
    throw "Store release script not found: $releaseScript"
}

$currentVersion = Get-CurrentAppVersion -MetadataPath $metadataPath
$currentPackageVersion = Get-CurrentPackageVersion -ManifestPath $manifestPath

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Read-RequiredValue -Prompt "앱 코드 버전 입력 (예: 3.1.1)" -DefaultValue $currentVersion
}
if (-not (Test-AppVersion -Value $Version)) {
    throw "앱 버전은 major.minor.patch 형식이어야 합니다. 예: 3.1.1"
}

$defaultPackageVersion = "$Version.0"
if ([string]::IsNullOrWhiteSpace($PackageVersion)) {
    $PackageVersion = Read-RequiredValue -Prompt "스토어 패키지 버전 입력 (예: $defaultPackageVersion)" -DefaultValue $defaultPackageVersion
}
if (-not (Test-PackageVersion -Value $PackageVersion)) {
    throw "스토어 패키지 버전은 major.minor.patch.revision 형식이어야 합니다. 예: 3.1.1.0"
}

if ([string]::IsNullOrWhiteSpace($ReleaseDate)) {
    $ReleaseDate = Read-RequiredValue -Prompt "릴리스 날짜 입력 (YYYY-MM-DD)" -DefaultValue (Get-Date -Format "yyyy-MM-dd")
}
if (-not (Test-ReleaseDate -Value $ReleaseDate)) {
    throw "릴리스 날짜는 YYYY-MM-DD 형식이어야 합니다. 예: 2026-06-27"
}

Write-Host ""
Write-Host "변경 예정:"
Write-Host "  APP_VERSION: $currentVersion -> $Version"
Write-Host "  APP_RELEASE_DATE: $ReleaseDate"
Write-Host "  AppxManifest Identity Version: $currentPackageVersion -> $PackageVersion"
Write-Host "  Build arch: $Arch"
Write-Host ""

$confirm = Read-Host "버전 반영 후 스토어 배포 파일 생성을 진행할까요? (Y/N)"
if ($confirm -notin @("Y", "y", "YES", "yes")) {
    Write-Host "Cancelled."
    exit 0
}

Set-PythonStringConstant -Path $metadataPath -Name "APP_VERSION" -Value $Version
Set-PythonStringConstant -Path $metadataPath -Name "APP_RELEASE_DATE" -Value $ReleaseDate
Set-AppxManifestVersion -Path $manifestPath -Version $PackageVersion

Write-Host ""
Write-Host "버전 정보가 반영되었습니다."
Write-Host "  $metadataPath"
Write-Host "  $manifestPath"

if ($SkipBuild) {
    Write-Host "SkipBuild 옵션으로 빌드는 실행하지 않았습니다."
    exit 0
}

$releaseArgs = @("-Arch", $Arch)
if ($SkipResetState) { $releaseArgs += "-SkipResetState" }
if ($PurgeLocalData) { $releaseArgs += "-PurgeLocalData" }
if ($DryRunReset) { $releaseArgs += "-DryRunReset" }
if ($SkipMsix) { $releaseArgs += "-SkipMsix" }
if ($AllowCrossArch) { $releaseArgs += "-AllowCrossArch" }

Write-Host ""
Write-Host "스토어 배포 파일 생성을 시작합니다..."
& $releaseScript @releaseArgs
if ($LASTEXITCODE -ne 0) {
    throw "Store release packaging failed."
}

Write-Host ""
Write-Host "완료: release\store 폴더의 .msixupload 파일을 확인하세요."
