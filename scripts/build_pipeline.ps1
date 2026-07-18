#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("auto", "x64", "arm64")]
    [string]$Arch = "auto",

    [switch]$SkipMsix,
    [switch]$SkipUpload,
    [switch]$UploadOnly,
    [switch]$ValidateOnly,
    [switch]$ResetState,
    [switch]$SkipResetState,
    [switch]$PurgeLocalData,
    [switch]$DryRunReset,
    [switch]$AllowCrossArch,

    # Version override (skip interactive prompt when provided)
    [string]$Version        = "",
    [string]$PackageVersion = "",
    [string]$ReleaseDate    = "",
    [ValidateSet("", "Stable", "Beta", "Dev")]
    [string]$Channel        = "",

    # Code signing (optional)
    [switch]$Sign,
    [string]$CertThumbprint = "",

    # Output control
    [switch]$NoBanner,
    [switch]$NoLog,
    [switch]$NoChecksum,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$BuildStart = Get-Date

if ($Help) {
    Write-Host "Dark Calendar unified release build"
    Write-Host ""
    Write-Host "  build-release.bat [options]"
    Write-Host ""
    Write-Host "Common options:"
    Write-Host "  -Arch auto|x64|arm64       Target architecture (default: native host)"
    Write-Host "  -Version X.Y.Z             App version; omit for interactive prompt"
    Write-Host "  -PackageVersion X.Y.Z.W    Optional Store package version"
    Write-Host "  -ReleaseDate YYYY-MM-DD    Release date"
    Write-Host "  -Channel Stable|Beta|Dev   Release channel"
    Write-Host "  -ResetState                Reset project release state"
    Write-Host "  -PurgeLocalData            Also remove LOCALAPPDATA state (implies reset)"
    Write-Host "  -SkipMsix                  Build sanitized payload only"
    Write-Host "  -SkipUpload                Build MSIX without .msixupload"
    Write-Host "  -UploadOnly                Recreate upload from existing native MSIX"
    Write-Host "  -ValidateOnly              Run preflight checks without changing files"
    Write-Host "  -Sign [-CertThumbprint X]  Sign MSIX for sideload distribution"
    exit 0
}

if ($ValidateOnly) { $NoLog = $true }

# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------

function Write-Step {
    param([int]$Num, [int]$Total, [string]$Msg)
    $elapsed = [int](New-TimeSpan -Start $BuildStart -End (Get-Date)).TotalSeconds
    Write-Host ("[{0:D2}/{1:D2}] {2}  +{3}s" -f $Num, $Total, $Msg, $elapsed) -ForegroundColor Cyan
}

function Write-Ok   { param([string]$Msg) Write-Host "     OK  $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "   WARN  $Msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$Msg) Write-Host "   FAIL  $Msg" -ForegroundColor Red }
function Write-Info { param([string]$Msg) Write-Host "         $Msg" -ForegroundColor DarkGray }

# ---------------------------------------------------------------------------
# Tool / path discovery
# ---------------------------------------------------------------------------

function Find-MakeAppx {
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ([string]::IsNullOrWhiteSpace($programFilesX86)) { $programFilesX86 = "C:\Program Files (x86)" }
    $kitsRoot = Join-Path $programFilesX86 "Windows Kits\10\bin"
    if (-not (Test-Path $kitsRoot)) { return $null }

    $preferred = Get-ChildItem -Path $kitsRoot -Recurse -File -Filter "makeappx.exe" |
        Where-Object { $_.FullName -match "\\$Arch\\makeappx\.exe$" } |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($preferred) { return $preferred.FullName }

    $fallback = Get-ChildItem -Path $kitsRoot -Recurse -File -Filter "makeappx.exe" |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($fallback) { return $fallback.FullName }
    return $null
}

function Find-SignTool {
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ([string]::IsNullOrWhiteSpace($programFilesX86)) { $programFilesX86 = "C:\Program Files (x86)" }
    $kitsRoot = Join-Path $programFilesX86 "Windows Kits\10\bin"
    if (-not (Test-Path $kitsRoot)) { return $null }
    $hit = Get-ChildItem -Path $kitsRoot -Recurse -File -Filter "signtool.exe" |
        Where-Object { $_.FullName -match "\\$Arch\\signtool\.exe$" } |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

function Get-HostArch {
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ([string]::IsNullOrWhiteSpace($arch) -and -not [string]::IsNullOrWhiteSpace($env:PROCESSOR_ARCHITEW6432)) {
        $arch = $env:PROCESSOR_ARCHITEW6432
    }
    $arch = if ($null -eq $arch) { "" } else { $arch.ToUpperInvariant() }
    switch ($arch) {
        "AMD64"  { return "x64" }
        "ARM64"  { return "arm64" }
        default  { return $null }
    }
}

# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

function Set-ManifestArchitecture {
    param(
        [Parameter(Mandatory)][string]$ManifestPath,
        [Parameter(Mandatory)][ValidateSet("x64","arm64")][string]$TargetArch
    )
    [xml]$xml = Get-Content -Path $ManifestPath
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("f", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    $identity = $xml.SelectSingleNode("/f:Package/f:Identity", $ns)
    if ($null -eq $identity) { throw "Identity node not found in AppxManifest.xml" }
    $identity.SetAttribute("ProcessorArchitecture", $TargetArch)
    $xml.Save($ManifestPath)
}

# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------

function Run-OrThrow {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][string[]]$Args,
        [string]$WorkingDirectory
    )
    Write-Info "run: $Exe $($Args -join ' ')"
    if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        & $Exe @Args
    } else {
        Push-Location $WorkingDirectory
        try { & $Exe @Args } finally { Pop-Location }
    }
    if ($LASTEXITCODE -ne 0) { throw "Command exited with code $LASTEXITCODE" }
}

# ---------------------------------------------------------------------------
# Version extraction
# ---------------------------------------------------------------------------

function Get-AppVersion {
    param([string]$MetadataPath)
    if (-not (Test-Path $MetadataPath)) { return "0.0.0" }
    $line = Get-Content $MetadataPath | Where-Object { $_ -match 'APP_VERSION\s*=\s*"(.+)"' } | Select-Object -First 1
    if ($line -match 'APP_VERSION\s*=\s*"(.+)"') { return $Matches[1] }
    return "0.0.0"
}

function Get-AppField {
    param([string]$MetadataPath, [string]$Field)
    if (-not (Test-Path $MetadataPath)) { return "" }
    $line = Get-Content $MetadataPath | Where-Object { $_ -match "$Field\s*=\s*`"(.+)`"" } | Select-Object -First 1
    if ($line -match "$Field\s*=\s*`"(.+)`"") { return $Matches[1] }
    return ""
}

function Assert-VersionFormat {
    param([string]$Ver)
    if ($Ver -notmatch '^\d+\.\d+\.\d+$') {
        throw "Version must be MAJOR.MINOR.PATCH (e.g. 3.2.0). Got: '$Ver'"
    }
}

function Assert-PackageVersionFormat {
    param([string]$Ver)
    if ($Ver -notmatch '^\d+\.\d+\.\d+\.\d+$') {
        throw "PackageVersion must be MAJOR.MINOR.PATCH.REVISION (e.g. 3.2.0.0). Got: '$Ver'"
    }
}

# ---------------------------------------------------------------------------
# Version sync: write to all 3 locations
# ---------------------------------------------------------------------------

function Sync-AppVersion {
    param(
        [string]$MetadataPath,
        [string]$PyprojectPath,
        [string]$ManifestPath,
        [string]$VersionInfoPath,
        [string]$NewVersion,
        [string]$NewPackageVersion,
        [string]$NewDate,
        [string]$NewChannel
    )

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false, $true)

    # 1. app_metadata.py
    $content = Get-Content $MetadataPath -Raw -Encoding utf8
    $content = $content -replace '(APP_VERSION\s*=\s*)"[^"]+"', ('$1"' + $NewVersion + '"')
    $content = $content -replace '(APP_RELEASE_DATE\s*=\s*)"[^"]+"', ('$1"' + $NewDate + '"')
    $content = $content -replace '(APP_RELEASE_CHANNEL\s*=\s*)"[^"]+"', ('$1"' + $NewChannel + '"')
    [System.IO.File]::WriteAllText($MetadataPath, $content, $utf8NoBom)
    Write-Info "updated: app_metadata.py  ($NewVersion / $NewDate / $NewChannel)"

    # 2. pyproject.toml
    $pyproject = Get-Content $PyprojectPath -Raw -Encoding utf8
    $pyproject = [regex]::Replace(
        $pyproject,
        '(?m)^(version\s*=\s*)"[^"]+"',
        ('${1}"' + $NewVersion + '"'),
        1
    )
    [System.IO.File]::WriteAllText($PyprojectPath, $pyproject, $utf8NoBom)
    Write-Info "updated: pyproject.toml  ($NewVersion)"

    # 3. AppxManifest.xml
    $msixVer = $NewPackageVersion
    [xml]$xml = Get-Content -Path $ManifestPath -Encoding utf8
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("f", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    $identity = $xml.SelectSingleNode("/f:Package/f:Identity", $ns)
    if ($null -ne $identity) {
        $identity.SetAttribute("Version", $msixVer)
        $xml.Save($ManifestPath)
        Write-Info "updated: AppxManifest.xml  ($msixVer)"
    } else {
        Write-Warn "AppxManifest.xml Identity node not found — skipped"
    }

    # 4. version_info.txt
    $parts = $NewVersion -split '\.'
    $ma = [int]$parts[0]; $mi = [int]$parts[1]; $pa = [int]$parts[2]
    $tuple = "($ma, $mi, $pa, 0)"
    $verStr = "$NewVersion.0"
    $vi = Get-Content $VersionInfoPath -Raw -Encoding utf8
    $vi = $vi -replace 'filevers\s*=\s*\([^)]+\)', "filevers=$tuple"
    $vi = $vi -replace 'prodvers\s*=\s*\([^)]+\)', "prodvers=$tuple"
    $vi = $vi -replace "(StringStruct\('FileVersion',\s*')[^']+(')", "`${1}$verStr`$2"
    $vi = $vi -replace "(StringStruct\('ProductVersion',\s*')[^']+(')", "`${1}$verStr`$2"
    [System.IO.File]::WriteAllText($VersionInfoPath, $vi, $utf8NoBom)
    Write-Info "updated: version_info.txt  ($verStr)"
}

# ---------------------------------------------------------------------------
# Interactive version prompt (skipped when params supplied or -NoBanner/-CI)
# ---------------------------------------------------------------------------

function Invoke-VersionPrompt {
    param(
        [string]$MetadataPath,
        [ref]$OutVersion,
        [ref]$OutDate,
        [ref]$OutChannel
    )

    $curVer     = Get-AppField $MetadataPath "APP_VERSION"
    $curDate    = Get-AppField $MetadataPath "APP_RELEASE_DATE"
    $curChannel = Get-AppField $MetadataPath "APP_RELEASE_CHANNEL"
    $todayStr   = (Get-Date).ToString("yyyy-MM-dd")

    $sep = "  " + ("-" * 52)

    Write-Host ""
    Write-Host $sep -ForegroundColor DarkGray
    Write-Host "   VERSION INFO" -ForegroundColor Yellow
    Write-Host $sep -ForegroundColor DarkGray
    Write-Host ("   current  v{0,-10} [{1,-6}]  {2}" -f $curVer, $curChannel, $curDate) -ForegroundColor DarkGray
    Write-Host $sep -ForegroundColor DarkGray
    Write-Host ""

    # Version
    Write-Host "   Version  " -ForegroundColor DarkGray -NoNewline
    Write-Host "MAJOR.MINOR.PATCH" -ForegroundColor DarkCyan -NoNewline
    Write-Host ("  [Enter = {0}]" -f $curVer) -ForegroundColor DarkGray -NoNewline
    Write-Host " : " -NoNewline
    $inp    = Read-Host
    $newVer = if ([string]::IsNullOrWhiteSpace($inp)) { $curVer } else { $inp.Trim() }
    Assert-VersionFormat $newVer

    # Release date
    Write-Host "   Date     " -ForegroundColor DarkGray -NoNewline
    Write-Host "YYYY-MM-DD        " -ForegroundColor DarkCyan -NoNewline
    Write-Host ("  [Enter = {0}]" -f $todayStr) -ForegroundColor DarkGray -NoNewline
    Write-Host " : " -NoNewline
    $inp     = Read-Host
    $newDate = if ([string]::IsNullOrWhiteSpace($inp)) { $todayStr } else { $inp.Trim() }
    if ($newDate -notmatch '^\d{4}-\d{2}-\d{2}$') { throw "Date must be YYYY-MM-DD. Got: '$newDate'" }

    # Channel
    Write-Host "   Channel  " -ForegroundColor DarkGray -NoNewline
    Write-Host "Stable / Beta / Dev" -ForegroundColor DarkCyan -NoNewline
    Write-Host ("  [Enter = {0}]" -f $curChannel) -ForegroundColor DarkGray -NoNewline
    Write-Host " : " -NoNewline
    $inp        = Read-Host
    $newChannel = if ([string]::IsNullOrWhiteSpace($inp)) { $curChannel } else { $inp.Trim() }
    if ($newChannel -notin @("Stable", "Beta", "Dev")) { throw "Channel must be Stable, Beta, or Dev. Got: '$newChannel'" }

    Write-Host ""
    Write-Host $sep -ForegroundColor DarkGray
    Write-Host ("   BUILDING  v{0}  [{1}]  {2}" -f $newVer, $newChannel, $newDate) -ForegroundColor Green
    Write-Host $sep -ForegroundColor DarkGray
    Write-Host ""

    $OutVersion.Value  = $newVer
    $OutDate.Value     = $newDate
    $OutChannel.Value  = $newChannel
}

# ---------------------------------------------------------------------------
# Disk space check
# ---------------------------------------------------------------------------

function Assert-DiskSpace {
    param([string]$Path, [int]$MinimumGB = 3)
    try {
        $drive = Split-Path -Qualifier $Path
        $disk = Get-PSDrive -Name ($drive.TrimEnd(':')) -ErrorAction SilentlyContinue
        if ($null -eq $disk) { return }  # can't detect — skip
        $freeGB = [math]::Round($disk.Free / 1GB, 1)
        if ($freeGB -lt $MinimumGB) {
            Write-Warn "Low disk space: ${freeGB} GB free on $drive (need ~${MinimumGB} GB)"
        } else {
            Write-Info "disk free: ${freeGB} GB on $drive"
        }
    } catch { }
}

# ---------------------------------------------------------------------------
# Python preflight
# ---------------------------------------------------------------------------

function Test-PythonEnv {
    param([string]$Python)
    $ver = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "venv Python not executable: $Python" }
    Write-Info "Python $ver"

    $missing = @()
    foreach ($pkg in @("PyInstaller", "PyQt6")) {
        & $Python -c "import $pkg" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { $missing += $pkg }
    }
    if ($missing.Count -gt 0) {
        throw "Missing packages in venv: $($missing -join ', '). Run: pip install -r requirements.txt"
    }
    Write-Info "venv OK (PyInstaller, PyQt6 present)"
}

# Copy only files referenced by AppxManifest.xml to the MSIX root. The complete
# runtime Assets directory already lives under _internal via PyInstaller.
function Copy-ManifestAssets {
    param(
        [Parameter(Mandatory)][string]$ManifestPath,
        [Parameter(Mandatory)][string]$SourceRoot,
        [Parameter(Mandatory)][string]$DestinationRoot
    )

    [xml]$manifest = Get-Content $ManifestPath -Raw -Encoding utf8
    $assetPaths = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($node in $manifest.SelectNodes("//*")) {
        foreach ($attribute in $node.Attributes) {
            if ($attribute.LocalName -notmatch "(Logo|Image)$") { continue }
            $relative = [string]$attribute.Value
            if (-not $relative.StartsWith("Assets\", [System.StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
            [void]$assetPaths.Add($relative)
        }

        # Properties/Logo stores its asset path as element text rather than as
        # an attribute, so it must be collected separately from VisualElements.
        if ($node.LocalName -match "(Logo|Image)$") {
            $relative = ([string]$node.InnerText).Trim()
            if ($relative.StartsWith("Assets\", [System.StringComparison]::OrdinalIgnoreCase)) {
                [void]$assetPaths.Add($relative)
            }
        }
    }
    if ($assetPaths.Count -eq 0) { throw "No manifest asset references found." }

    foreach ($relative in $assetPaths) {
        $leaf = Split-Path -Leaf $relative
        $source = Join-Path $SourceRoot $leaf
        $destination = Join-Path $DestinationRoot $relative
        if (-not (Test-Path $source -PathType Leaf)) {
            throw "Manifest asset missing: $source"
        }
        $destinationDir = Split-Path -Parent $destination
        if (-not (Test-Path $destinationDir)) {
            New-Item -Path $destinationDir -ItemType Directory -Force | Out-Null
        }
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
    return $assetPaths.Count
}

# ---------------------------------------------------------------------------
# Store upload packaging
# ---------------------------------------------------------------------------

function Find-Msix {
    param(
        [Parameter(Mandatory)][string]$DistDir,
        [Parameter(Mandatory)][ValidateSet("x64", "arm64")][string]$TargetArch
    )
    $hits = Get-ChildItem -Path $DistDir -Filter "DarkCalendar-*-$TargetArch.msix" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($hits) { return $hits[0].FullName }
    return $null
}

function Get-MsixIdentity {
    param([Parameter(Mandatory)][string]$Path)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $archive = [System.IO.Compression.ZipFile]::OpenRead($resolved)
    try {
        $entry = $archive.GetEntry("AppxManifest.xml")
        if ($null -eq $entry) { throw "AppxManifest.xml missing from: $Path" }
        $reader = [System.IO.StreamReader]::new($entry.Open(), [System.Text.Encoding]::UTF8)
        try { [xml]$manifest = $reader.ReadToEnd() } finally { $reader.Dispose() }
        return [pscustomobject]@{
            Name = [string]$manifest.Package.Identity.Name
            Publisher = [string]$manifest.Package.Identity.Publisher
            Version = [string]$manifest.Package.Identity.Version
            Architecture = [string]$manifest.Package.Identity.ProcessorArchitecture
        }
    } finally {
        $archive.Dispose()
    }
}

function Assert-CompatiblePackages {
    param(
        [Parameter(Mandatory)][string]$X64Path,
        [Parameter(Mandatory)][string]$Arm64Path
    )

    $x64 = Get-MsixIdentity $X64Path
    $arm64 = Get-MsixIdentity $Arm64Path
    foreach ($field in @("Name", "Publisher", "Version")) {
        if ($x64.$field -ne $arm64.$field) {
            throw "MSIX identity mismatch ($field): x64='$($x64.$field)', arm64='$($arm64.$field)'"
        }
    }
    if ($x64.Architecture -ne "x64") {
        throw "Expected x64 package, found architecture '$($x64.Architecture)'."
    }
    if ($arm64.Architecture -ne "arm64") {
        throw "Expected arm64 package, found architecture '$($arm64.Architecture)'."
    }
}

function New-StoreUpload {
    param(
        [Parameter(Mandatory)][string]$ProjectRoot,
        [Parameter(Mandatory)][string]$ThisMsix,
        [Parameter(Mandatory)][ValidateSet("x64", "arm64")][string]$ThisArch
    )

    if (-not (Test-Path $ThisMsix -PathType Leaf)) {
        throw "MSIX not found: $ThisMsix"
    }

    $thisIdentity = Get-MsixIdentity $ThisMsix
    $packageVersion = $thisIdentity.Version
    Assert-PackageVersionFormat $packageVersion

    $releaseDir = Join-Path $ProjectRoot "release\store"
    if (-not (Test-Path $releaseDir)) {
        New-Item -Path $releaseDir -ItemType Directory -Force | Out-Null
    }

    $otherArch = if ($ThisArch -eq "x64") { "arm64" } else { "x64" }
    $otherMsix = Find-Msix -DistDir (Join-Path $ProjectRoot "dist\$otherArch") -TargetArch $otherArch

    if ($otherMsix) {
        $x64Msix = if ($ThisArch -eq "x64") { $ThisMsix } else { $otherMsix }
        $arm64Msix = if ($ThisArch -eq "arm64") { $ThisMsix } else { $otherMsix }
        Assert-CompatiblePackages -X64Path $x64Msix -Arm64Path $arm64Msix

        $makeappx = Find-MakeAppx
        if (-not $makeappx) { throw "makeappx.exe not found. Install Windows SDK." }

        $bundlePath = Join-Path $releaseDir "DarkCalendar-$packageVersion-arm64_x64.msixbundle"
        $staging = Join-Path $releaseDir ".bundle-staging"
        if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
        New-Item -Path $staging -ItemType Directory -Force | Out-Null
        try {
            Copy-Item -LiteralPath $x64Msix -Destination (Join-Path $staging (Split-Path -Leaf $x64Msix)) -Force
            Copy-Item -LiteralPath $arm64Msix -Destination (Join-Path $staging (Split-Path -Leaf $arm64Msix)) -Force
            if (Test-Path $bundlePath) { Remove-Item -LiteralPath $bundlePath -Force }
            Run-OrThrow -Exe $makeappx -Args @("bundle", "/d", $staging, "/p", $bundlePath, "/o") -WorkingDirectory $ProjectRoot
        } finally {
            if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
        }

        $uploadTmp = Join-Path $releaseDir "DarkCalendar-$packageVersion-arm64_x64_upload.zip"
        $uploadOut = Join-Path $releaseDir "DarkCalendar-$packageVersion-arm64_x64.msixupload"
        if (Test-Path $uploadTmp) { Remove-Item -LiteralPath $uploadTmp -Force }
        if (Test-Path $uploadOut) { Remove-Item -LiteralPath $uploadOut -Force }
        Compress-Archive -LiteralPath $bundlePath -DestinationPath $uploadTmp -Force
        Move-Item -LiteralPath $uploadTmp -Destination $uploadOut -Force
        Write-Ok "combined Store upload created"
        Write-Info $uploadOut
        return $uploadOut
    }

    Write-Warn "$otherArch MSIX not found - creating a single-architecture upload"
    $singleTmp = Join-Path $releaseDir "DarkCalendar-$packageVersion-${ThisArch}_upload.zip"
    $singleOut = Join-Path $releaseDir "DarkCalendar-$packageVersion-${ThisArch}.msixupload"
    if (Test-Path $singleTmp) { Remove-Item -LiteralPath $singleTmp -Force }
    if (Test-Path $singleOut) { Remove-Item -LiteralPath $singleOut -Force }
    Compress-Archive -LiteralPath $ThisMsix -DestinationPath $singleTmp -Force
    Move-Item -LiteralPath $singleTmp -Destination $singleOut -Force
    Write-Ok "$ThisArch Store upload created"
    Write-Info $singleOut
    return $singleOut
}

# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------

function New-Sha256File {
    param([string]$FilePath)
    $hash = (Get-FileHash -Path $FilePath -Algorithm SHA256).Hash
    $checksumFile = "$FilePath.sha256"
    "$hash  $(Split-Path -Leaf $FilePath)" | Out-File -FilePath $checksumFile -Encoding utf8 -NoNewline
    return $checksumFile
}

# ---------------------------------------------------------------------------
# Build log
# ---------------------------------------------------------------------------

$script:LogPath = $null
$script:LogBuffer = [System.Collections.Generic.List[string]]::new()

function Write-Log { param([string]$Line) $script:LogBuffer.Add($Line) }

function Flush-Log {
    if ($script:LogPath -and $script:LogBuffer.Count -gt 0) {
        $script:LogBuffer | Out-File -FilePath $script:LogPath -Encoding utf8 -Append
        $script:LogBuffer.Clear()
    }
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

$projectRoot    = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$venvPython     = Join-Path $projectRoot ".venv\Scripts\python.exe"
$resetScript    = Join-Path $projectRoot "scripts\reset_release_state.py"
$payloadScript  = Join-Path $projectRoot "build_store.py"
$specPath       = Join-Path $projectRoot "DarkCalendar.spec"
$manifestSource = Join-Path $projectRoot "AppxManifest.xml"
$assetsSource   = Join-Path $projectRoot "Assets"
$metadataFile   = Join-Path $projectRoot "calendar_app\app_metadata.py"
$pyprojectFile  = Join-Path $projectRoot "pyproject.toml"
$versionInfoFile = Join-Path $projectRoot "version_info.txt"
$widgetSkinModule = Join-Path $projectRoot "calendar_app\presentation\widgets\widget_mode_skins.py"
$logsDir        = Join-Path $projectRoot "build_logs"

$hostArch = Get-HostArch
if ([string]::IsNullOrWhiteSpace($hostArch)) {
    throw "Cannot determine host architecture."
}
if ($Arch -eq "auto") { $Arch = $hostArch }
if (-not $AllowCrossArch -and $hostArch -ne $Arch) {
    throw "Cross-arch blocked. Host='$hostArch' target='$Arch'. Use -AllowCrossArch to override."
}

$effectiveResetState = ($ResetState -or $PurgeLocalData -or $DryRunReset) -and -not $SkipResetState
$effectiveSign = $Sign -or -not [string]::IsNullOrWhiteSpace($CertThumbprint)

if ($UploadOnly) {
    if ($SkipUpload) { throw "-UploadOnly and -SkipUpload cannot be used together." }
    $existingMsix = Find-Msix -DistDir (Join-Path $projectRoot "dist\$Arch") -TargetArch $Arch
    if (-not $existingMsix) {
        throw "No existing $Arch MSIX found. Run build-release.bat first."
    }
    [void](New-StoreUpload -ProjectRoot $projectRoot -ThisMsix $existingMsix -ThisArch $Arch)
    exit 0
}

# ---------------------------------------------------------------------------
# Determine version (interactive unless all 3 params supplied or NoBanner)
# ---------------------------------------------------------------------------

$resolvedVersion = $Version
$resolvedDate    = $ReleaseDate
$resolvedChannel = $Channel

$allParamsGiven = (
    -not [string]::IsNullOrWhiteSpace($Version) -and
    -not [string]::IsNullOrWhiteSpace($ReleaseDate) -and
    -not [string]::IsNullOrWhiteSpace($Channel)
)

if (-not $allParamsGiven -and -not $NoBanner) {
    Invoke-VersionPrompt `
        -MetadataPath $metadataFile `
        -OutVersion   ([ref]$resolvedVersion) `
        -OutDate      ([ref]$resolvedDate) `
        -OutChannel   ([ref]$resolvedChannel)
} else {
    # Fill any gaps with current values from metadata
    $curVer     = Get-AppField $metadataFile "APP_VERSION"
    $curDate    = Get-AppField $metadataFile "APP_RELEASE_DATE"
    $curChannel = Get-AppField $metadataFile "APP_RELEASE_CHANNEL"
    if ([string]::IsNullOrWhiteSpace($resolvedVersion))  { $resolvedVersion  = $curVer }
    if ([string]::IsNullOrWhiteSpace($resolvedDate))     { $resolvedDate     = (Get-Date).ToString("yyyy-MM-dd") }
    if ([string]::IsNullOrWhiteSpace($resolvedChannel))  { $resolvedChannel  = $curChannel }
}

Assert-VersionFormat $resolvedVersion
if ($resolvedDate -notmatch '^\d{4}-\d{2}-\d{2}$') {
    throw "ReleaseDate must be YYYY-MM-DD. Got: '$resolvedDate'"
}

$resolvedPackageVersion = if ([string]::IsNullOrWhiteSpace($PackageVersion)) {
    "$resolvedVersion.0"
} else {
    $PackageVersion.Trim()
}
Assert-PackageVersionFormat $resolvedPackageVersion

$appVersion = $resolvedVersion

$distRoot      = Join-Path $projectRoot "dist\$Arch"
$buildRoot     = Join-Path $projectRoot "build\$Arch"
$appDir        = Join-Path $distRoot "DarkCalendar"
$manifestDest  = Join-Path $appDir "AppxManifest.xml"
$assetsDest    = Join-Path $appDir "Assets"
$msixOutput    = Join-Path $distRoot "DarkCalendar-$appVersion-$Arch.msix"

$TOTAL_STEPS   = if ($SkipMsix) { 8 } else { 11 }

# ---------------------------------------------------------------------------
# Log file setup
# ---------------------------------------------------------------------------

if (-not $NoLog) {
    if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Force -Path $logsDir | Out-Null }
    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $script:LogPath = Join-Path $logsDir "build_${timestamp}_${Arch}.log"
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

if (-not $NoBanner) {
    Write-Host ""
    Write-Host ("=" * 62) -ForegroundColor DarkGray
    Write-Host ("  Dark Calendar  v{0}  [{1}]" -f $appVersion, $Arch.ToUpper()) -ForegroundColor White
    Write-Host ("  Build started: {0}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")) -ForegroundColor DarkGray
    if ($script:LogPath) { Write-Host ("  Log: {0}" -f $script:LogPath) -ForegroundColor DarkGray }
    Write-Host ("=" * 62) -ForegroundColor DarkGray
    Write-Host ""
}

Write-Log "=== Dark Calendar Build Log ==="
Write-Log "Version : $appVersion"
Write-Log "Arch    : $Arch"
Write-Log "Started : $((Get-Date).ToString('o'))"
Write-Log ""

# ---------------------------------------------------------------------------
# STEP 1 — Preflight
# ---------------------------------------------------------------------------

Write-Step 1 $TOTAL_STEPS "Preflight checks"
Write-Log "[step 1] preflight"

foreach ($chk in @(
    @{ Path = $venvPython;    Name = "venv Python" },
    @{ Path = $specPath;      Name = "DarkCalendar.spec" },
    @{ Path = $manifestSource; Name = "AppxManifest.xml" },
    @{ Path = $assetsSource;  Name = "Assets/" },
    @{ Path = $payloadScript; Name = "build_store.py" }
    @{ Path = $pyprojectFile; Name = "pyproject.toml" }
    @{ Path = $widgetSkinModule; Name = "widget_mode_skins.py" }
)) {
    if (-not (Test-Path $chk.Path)) {
        Write-Fail $chk.Name
        throw "$($chk.Name) not found: $($chk.Path)"
    }
    Write-Info "found: $($chk.Name)"
}

Assert-DiskSpace -Path $projectRoot -MinimumGB 3
Test-PythonEnv -Python $venvPython

Write-Ok "preflight passed"
Write-Log "preflight OK"

if ($ValidateOnly) {
    Write-Host ""
    Write-Ok "release pipeline validation passed; no files were changed"
    Flush-Log
    exit 0
}

# ---------------------------------------------------------------------------
# STEP 2 — Sync version to all files
# ---------------------------------------------------------------------------

Write-Step 2 $TOTAL_STEPS "Sync version info"
Write-Log "[step 2] version sync — $resolvedVersion / $resolvedDate / $resolvedChannel"

Sync-AppVersion `
    -MetadataPath    $metadataFile `
    -PyprojectPath   $pyprojectFile `
    -ManifestPath    $manifestSource `
    -VersionInfoPath $versionInfoFile `
    -NewVersion      $resolvedVersion `
    -NewPackageVersion $resolvedPackageVersion `
    -NewDate         $resolvedDate `
    -NewChannel      $resolvedChannel

Write-Ok "v$resolvedVersion  [$resolvedChannel]  $resolvedDate"
Write-Log "version sync OK"

# ---------------------------------------------------------------------------
# STEP 3 — Reset state (optional)
# ---------------------------------------------------------------------------

Write-Step 3 $TOTAL_STEPS "Reset release state"
Write-Log "[step 3] reset state"

if ($effectiveResetState) {
    if (-not (Test-Path $resetScript)) { throw "Reset script not found: $resetScript" }
    $resetArgs = @($resetScript, "--project-dir", $projectRoot)
    if ($PurgeLocalData) { $resetArgs += "--purge-local-data" }
    if ($DryRunReset)    { $resetArgs += "--dry-run" }
    Run-OrThrow -Exe $venvPython -Args $resetArgs -WorkingDirectory $projectRoot
    Write-Ok "state reset done"
    Write-Log "state reset OK"
} else {
    Write-Info "skipped (pass -ResetState to enable)"
    Write-Log "skipped"
}

# ---------------------------------------------------------------------------
# STEP 4 — Clean previous dist/build
# ---------------------------------------------------------------------------

Write-Step 4 $TOTAL_STEPS "Clean previous output"
Write-Log "[step 4] clean"

# Kill any running DarkCalendar process that may lock build output
$killed = Get-Process -Name "DarkCalendar" -ErrorAction SilentlyContinue
if ($killed) {
    $killed | Stop-Process -Force
    Write-Info "stopped DarkCalendar.exe (was running)"
    Start-Sleep -Milliseconds 800
}

foreach ($dir in @($distRoot, $buildRoot)) {
    if (-not (Test-Path $dir)) { continue }
    $attempt = 0
    $removed = $false
    while ($attempt -lt 3 -and -not $removed) {
        $attempt++
        try {
            Remove-Item -Recurse -Force $dir -ErrorAction Stop
            $removed = $true
        } catch {
            if ($attempt -lt 3) {
                Write-Info "locked — retry $attempt/3 in 2s..."
                Start-Sleep -Seconds 2
            } else {
                throw "Cannot remove $dir after 3 attempts.`nClose DarkCalendar and any antivirus scan, then retry.`nError: $_"
            }
        }
    }
    Write-Info "removed: $dir"
    Write-Log "removed: $dir"
}
Write-Ok "clean done"

# ---------------------------------------------------------------------------
# STEP 5 — PyInstaller
# ---------------------------------------------------------------------------

Write-Step 5 $TOTAL_STEPS "PyInstaller"
Write-Log "[step 5] PyInstaller"

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath", $distRoot,
    "--workpath", $buildRoot,
    $specPath
)
Run-OrThrow -Exe $venvPython -Args $pyinstallerArgs -WorkingDirectory $projectRoot

if (-not (Test-Path $appDir)) { throw "Build output missing: $appDir" }

$exeSize = [math]::Round((Get-Item (Join-Path $appDir "DarkCalendar.exe")).Length / 1MB, 1)
Write-Ok "PyInstaller done  (exe: ${exeSize} MB)"
Write-Log "PyInstaller OK — exe ${exeSize} MB"

# ---------------------------------------------------------------------------
# STEP 6 — Copy Assets + Manifest
# ---------------------------------------------------------------------------

Write-Step 6 $TOTAL_STEPS "Copy assets & manifest"
Write-Log "[step 6] assets + manifest"

Copy-Item -Path $manifestSource -Destination $manifestDest -Force
Set-ManifestArchitecture -ManifestPath $manifestDest -TargetArch $Arch
Write-Info "manifest arch set to $Arch"

if (Test-Path $assetsDest) { Remove-Item -Recurse -Force $assetsDest }
$assetCount = Copy-ManifestAssets `
    -ManifestPath $manifestDest `
    -SourceRoot $assetsSource `
    -DestinationRoot $appDir

$legalFiles = @("LICENSE", "README.md", "SOURCE_OFFER.md", "THIRD_PARTY_NOTICES.md")
foreach ($legalFile in $legalFiles) {
    $legalSource = Join-Path $projectRoot $legalFile
    $legalDest = Join-Path $appDir $legalFile
    if (-not (Test-Path $legalSource)) {
        throw "Open-source notice missing from project root: $legalSource"
    }
    Copy-Item -LiteralPath $legalSource -Destination $legalDest -Force
    if (-not (Test-Path $legalDest)) {
        throw "Open-source notice missing from payload root: $legalDest"
    }
}

Write-Ok "copied ($assetCount manifest asset files, $($legalFiles.Count) open-source notices)"
Write-Log "assets+manifest+notices OK — $assetCount assets / $($legalFiles.Count) notices"

# ---------------------------------------------------------------------------
# STEP 7 — Store payload sanitisation
# ---------------------------------------------------------------------------

Write-Step 7 $TOTAL_STEPS "Store payload (clean DB, sanitise)"
Write-Log "[step 7] payload"

$payloadArgs = @($payloadScript, "--prepare-only", "--dist-dir", $appDir)
Run-OrThrow -Exe $venvPython -Args $payloadArgs -WorkingDirectory $projectRoot

$bundledDefaultDb = Join-Path $appDir "_internal\desk_calendar_default.db"
if (-not (Test-Path $bundledDefaultDb)) {
    throw "Sanitized bundled DB missing from runtime path: $bundledDefaultDb"
}
$staleRootDb = Join-Path $appDir "desk_calendar_default.db"
if (Test-Path $staleRootDb) {
    throw "Stale root default DB remains in payload: $staleRootDb"
}

Write-Ok "payload ready"
Write-Log "payload OK"

# ---------------------------------------------------------------------------
# STEP 8 — MSIX packaging
# ---------------------------------------------------------------------------

Write-Step 8 $TOTAL_STEPS "MSIX packaging"
Write-Log "[step 8] MSIX"

if ($SkipMsix) {
    Write-Info "skipped (-SkipMsix)"
    Write-Log "skipped"
} else {
    $makeappx = Find-MakeAppx
    if (-not $makeappx) {
        Write-Warn "makeappx.exe not found — MSIX skipped. Install Windows SDK."
        Write-Log "makeappx not found — skipped"
    } else {
        Write-Info "using: $makeappx"
        if (Test-Path $msixOutput) { Remove-Item -Force $msixOutput }

        $packArgs = @("pack", "/d", $appDir, "/p", $msixOutput, "/o")
        Run-OrThrow -Exe $makeappx -Args $packArgs -WorkingDirectory $projectRoot

        $msixMB = [math]::Round((Get-Item $msixOutput).Length / 1MB, 1)
        Write-Ok "MSIX created  (${msixMB} MB)"
        Write-Log "MSIX OK — ${msixMB} MB — $msixOutput"
    }
}

# ---------------------------------------------------------------------------
# STEP 9 — Code signing (optional)
# ---------------------------------------------------------------------------

if (-not $SkipMsix) {
    Write-Step 9 $TOTAL_STEPS "Code signing"
    Write-Log "[step 9] signing"

    if ($effectiveSign) {
        if (-not (Test-Path $msixOutput)) {
            Write-Warn "MSIX not found — signing skipped"
            Write-Log "skipped (no MSIX)"
        } else {
            $signtool = Find-SignTool
            if (-not $signtool) { throw "signtool.exe not found. Install Windows SDK." }

            $signArgs = @("sign", "/fd", "SHA256", "/tr", "http://timestamp.digicert.com", "/td", "SHA256")
            if (-not [string]::IsNullOrWhiteSpace($CertThumbprint)) {
                $signArgs += @("/sha1", $CertThumbprint)
            } else {
                $signArgs += "/a"   # auto-select best cert from store
            }
            $signArgs += $msixOutput
            Run-OrThrow -Exe $signtool -Args $signArgs -WorkingDirectory $projectRoot
            Write-Ok "signed"
            Write-Log "signing OK"
        }
    } else {
        Write-Info "skipped (pass -Sign [-CertThumbprint <thumb>] to enable)"
        Write-Log "skipped"
    }

    # ---------------------------------------------------------------------------
    # STEP 10 — Checksum
    # ---------------------------------------------------------------------------

    Write-Step 10 $TOTAL_STEPS "SHA-256 checksum"
    Write-Log "[step 10] checksum"

    if ($NoChecksum -or -not (Test-Path $msixOutput)) {
        Write-Info "skipped"
        Write-Log "skipped"
    } else {
        $checksumFile = New-Sha256File -FilePath $msixOutput
        $hash = (Get-Content $checksumFile).Split("  ")[0]
        Write-Ok $hash
        Write-Info "written: $checksumFile"
        Write-Log "SHA256: $hash"
    }
}

# ---------------------------------------------------------------------------
# STEP 11 — Store upload
# ---------------------------------------------------------------------------

$storeUpload = $null
if (-not $SkipMsix) {
    Write-Step 11 $TOTAL_STEPS "Store upload packaging"
    Write-Log "[step 11] Store upload"

    if ($SkipUpload) {
        Write-Info "skipped (-SkipUpload)"
        Write-Log "skipped"
    } elseif (-not (Test-Path $msixOutput)) {
        Write-Warn "MSIX not found - Store upload skipped"
        Write-Log "skipped (no MSIX)"
    } else {
        $storeUpload = New-StoreUpload -ProjectRoot $projectRoot -ThisMsix $msixOutput -ThisArch $Arch
        Write-Log "Store upload OK - $storeUpload"
    }
}

# ---------------------------------------------------------------------------
# Build summary
# ---------------------------------------------------------------------------

$elapsed = [math]::Round((New-TimeSpan -Start $BuildStart -End (Get-Date)).TotalSeconds)
$mins    = [int]($elapsed / 60)
$secs    = $elapsed % 60

Write-Log ""
Write-Log "=== Build summary ==="
Write-Log "Elapsed : ${mins}m ${secs}s"
Write-Log "appDir  : $appDir"
if (Test-Path $msixOutput) { Write-Log "MSIX    : $msixOutput" }
if ($storeUpload) { Write-Log "Upload  : $storeUpload" }
Write-Log "Finished: $((Get-Date).ToString('o'))"

Flush-Log

Write-Host ""
Write-Host ("=" * 62) -ForegroundColor DarkGray
Write-Host "  Build complete" -ForegroundColor Green -NoNewline
Write-Host ("  [{0}m {1}s]" -f $mins, $secs) -ForegroundColor DarkGray
Write-Host ""
Write-Host ("  payload : {0}" -f $appDir)
if (Test-Path $msixOutput) {
    Write-Host ("  MSIX    : {0}" -f $msixOutput)
}
if ($storeUpload) {
    Write-Host ("  upload  : {0}" -f $storeUpload)
}
if ($script:LogPath) {
    Write-Host ("  log     : {0}" -f $script:LogPath) -ForegroundColor DarkGray
}
Write-Host ("=" * 62) -ForegroundColor DarkGray
Write-Host ""
