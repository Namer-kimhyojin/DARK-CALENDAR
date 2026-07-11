#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("x64", "arm64")]
    [string]$Arch = "x64",

    [switch]$SkipMsix,
    [switch]$ResetState,
    [switch]$PurgeLocalData,
    [switch]$DryRunReset,
    [switch]$AllowCrossArch,

    # Version override (skip interactive prompt when provided)
    [string]$Version        = "",
    [string]$ReleaseDate    = "",
    [ValidateSet("", "Stable", "Beta", "Dev")]
    [string]$Channel        = "",

    # Code signing (optional)
    [switch]$Sign,
    [string]$CertThumbprint = "",

    # Output control
    [switch]$NoBanner,
    [switch]$NoLog,
    [switch]$NoChecksum
)

$ErrorActionPreference = "Stop"
$BuildStart = Get-Date

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

# ---------------------------------------------------------------------------
# Version sync: write to all 3 locations
# ---------------------------------------------------------------------------

function Sync-AppVersion {
    param(
        [string]$MetadataPath,
        [string]$ManifestPath,
        [string]$VersionInfoPath,
        [string]$NewVersion,
        [string]$NewDate,
        [string]$NewChannel
    )

    # 1. app_metadata.py
    $content = Get-Content $MetadataPath -Raw -Encoding utf8
    $content = $content -replace '(APP_VERSION\s*=\s*)"[^"]+"', ('$1"' + $NewVersion + '"')
    $content = $content -replace '(APP_RELEASE_DATE\s*=\s*)"[^"]+"', ('$1"' + $NewDate + '"')
    $content = $content -replace '(APP_RELEASE_CHANNEL\s*=\s*)"[^"]+"', ('$1"' + $NewChannel + '"')
    [System.IO.File]::WriteAllText($MetadataPath, $content, [System.Text.Encoding]::UTF8)
    Write-Info "updated: app_metadata.py  ($NewVersion / $NewDate / $NewChannel)"

    # 2. AppxManifest.xml  (needs 4-part version: X.Y.Z.0)
    $msixVer = "$NewVersion.0"
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

    # 3. version_info.txt
    $parts = $NewVersion -split '\.'
    $ma = [int]$parts[0]; $mi = [int]$parts[1]; $pa = [int]$parts[2]
    $tuple = "($ma, $mi, $pa, 0)"
    $verStr = "$NewVersion.0"
    $vi = Get-Content $VersionInfoPath -Raw -Encoding utf8
    $vi = $vi -replace 'filevers\s*=\s*\([^)]+\)', "filevers=$tuple"
    $vi = $vi -replace 'prodvers\s*=\s*\([^)]+\)', "prodvers=$tuple"
    $vi = $vi -replace "(StringStruct\('FileVersion',\s*')[^']+(')", "`${1}$verStr`$2"
    $vi = $vi -replace "(StringStruct\('ProductVersion',\s*')[^']+(')", "`${1}$verStr`$2"
    [System.IO.File]::WriteAllText($VersionInfoPath, $vi, [System.Text.Encoding]::UTF8)
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

$projectRoot    = Split-Path -Parent $PSCommandPath
$venvPython     = Join-Path $projectRoot ".venv\Scripts\python.exe"
$resetScript    = Join-Path $projectRoot "scripts\reset_release_state.py"
$payloadScript  = Join-Path $projectRoot "build_store.py"
$specPath       = Join-Path $projectRoot "DarkCalendar.spec"
$manifestSource = Join-Path $projectRoot "AppxManifest.xml"
$assetsSource   = Join-Path $projectRoot "Assets"
$metadataFile   = Join-Path $projectRoot "calendar_app\app_metadata.py"
$versionInfoFile = Join-Path $projectRoot "version_info.txt"
$widgetSkinModule = Join-Path $projectRoot "calendar_app\presentation\widgets\widget_mode_skins.py"
$logsDir        = Join-Path $projectRoot "build_logs"

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

$appVersion = $resolvedVersion

$distRoot      = Join-Path $projectRoot "dist\$Arch"
$buildRoot     = Join-Path $projectRoot "build\$Arch"
$appDir        = Join-Path $distRoot "DarkCalendar"
$manifestDest  = Join-Path $appDir "AppxManifest.xml"
$assetsDest    = Join-Path $appDir "Assets"
$msixOutput    = Join-Path $distRoot "DarkCalendar-$appVersion-$Arch.msix"

$TOTAL_STEPS   = if ($SkipMsix) { 8 } elseif ($Sign) { 10 } else { 9 }

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
    @{ Path = $widgetSkinModule; Name = "widget_mode_skins.py" }
)) {
    if (-not (Test-Path $chk.Path)) {
        Write-Fail $chk.Name
        throw "$($chk.Name) not found: $($chk.Path)"
    }
    Write-Info "found: $($chk.Name)"
}

$hostArch = Get-HostArch
if (-not $AllowCrossArch -and $hostArch -and $hostArch -ne $Arch) {
    throw "Cross-arch blocked. Host='$hostArch' target='$Arch'. Use -AllowCrossArch to override."
}

Assert-DiskSpace -Path $projectRoot -MinimumGB 3
Test-PythonEnv -Python $venvPython

Write-Ok "preflight passed"
Write-Log "preflight OK"

# ---------------------------------------------------------------------------
# STEP 2 — Sync version to all files
# ---------------------------------------------------------------------------

Write-Step 2 $TOTAL_STEPS "Sync version info"
Write-Log "[step 2] version sync — $resolvedVersion / $resolvedDate / $resolvedChannel"

Sync-AppVersion `
    -MetadataPath    $metadataFile `
    -ManifestPath    $manifestSource `
    -VersionInfoPath $versionInfoFile `
    -NewVersion      $resolvedVersion `
    -NewDate         $resolvedDate `
    -NewChannel      $resolvedChannel

Write-Ok "v$resolvedVersion  [$resolvedChannel]  $resolvedDate"
Write-Log "version sync OK"

# ---------------------------------------------------------------------------
# STEP 3 — Reset state (optional)
# ---------------------------------------------------------------------------

Write-Step 3 $TOTAL_STEPS "Reset release state"
Write-Log "[step 2] reset state"

if ($ResetState) {
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
Copy-Item -Path $assetsSource -Destination $assetsDest -Recurse -Force
$assetCount = (Get-ChildItem -Recurse -File $assetsDest).Count
Write-Ok "copied ($assetCount asset files)"
Write-Log "assets+manifest OK — $assetCount files"

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

    if ($Sign) {
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
if ($script:LogPath) {
    Write-Host ("  log     : {0}" -f $script:LogPath) -ForegroundColor DarkGray
}
Write-Host ("=" * 62) -ForegroundColor DarkGray
Write-Host ""
