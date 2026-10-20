# -*- coding: utf-8 -*-
"""Release metadata synchronization must not invalidate dependency lock hashes."""

import hashlib
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_dependency_lock_header_is_independent_of_application_version():
    header = (
        (ROOT / "requirements-runtime.lock")
        .read_text(encoding="utf-8", errors="strict")
        .splitlines()[0]
    )
    assert "Air Calendar release runtime lock" in header
    assert not re.search(r"\d+\.\d+\.\d+", header)


def test_real_version_sync_preserves_legacy_dependency_lock_bytes(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("The release version synchronization contract requires PowerShell")
    files = (
        "calendar_app/app_metadata.py",
        "pyproject.toml",
        "AppxManifest.xml",
        "version_info.txt",
        "docs/site-config.json",
        "docs/app.js",
        "docs/index.html",
        "README.md",
        "SOURCE_OFFER.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/microsoft-store-gpl-release.md",
        "rules/store_release_process.md",
    )
    for relative in files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    # Reproduce the exact old versioned comment that invalidated the prepared
    # cache, even when a future caller supplies a legacy dependency lock.
    original = (ROOT / "requirements-runtime.lock").read_bytes()
    original = re.sub(
        rb"^#[^\r\n]*", b"# Air Calendar 4.3.3 release runtime lock (Windows x64/arm64)", original
    )
    dependency_lock = tmp_path / "requirements-runtime.lock"
    dependency_lock.write_bytes(original)
    runner = tmp_path / "invoke-version-sync.ps1"
    runner.write_text(
        """param([string]$PipelinePath, [string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($PipelinePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Invalid release pipeline PowerShell' }
$function = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Sync-AppVersion'}, $true)
if ($null -eq $function) { throw 'Sync-AppVersion function missing' }
function Write-Info { param([string]$Message) }
function Write-Warn { param([string]$Message) }
. ([scriptblock]::Create($function.Extent.Text))
Sync-AppVersion -ProjectRoot $FixtureRoot `
  -MetadataPath (Join-Path $FixtureRoot 'calendar_app/app_metadata.py') `
  -PyprojectPath (Join-Path $FixtureRoot 'pyproject.toml') `
  -ManifestPath (Join-Path $FixtureRoot 'AppxManifest.xml') `
  -VersionInfoPath (Join-Path $FixtureRoot 'version_info.txt') `
  -NewVersion '4.6.2' -NewPackageVersion '4.6.2.0' -NewDate '2026-10-20' -NewChannel 'Stable'
""",
        encoding="utf-8",
        errors="strict",
    )
    before = hashlib.sha256(dependency_lock.read_bytes()).hexdigest()
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(runner),
            str(ROOT / "scripts/build_pipeline.ps1"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert dependency_lock.read_bytes() == original
    assert hashlib.sha256(dependency_lock.read_bytes()).hexdigest() == before
    assert 'APP_VERSION = "4.6.2"' in (tmp_path / "calendar_app/app_metadata.py").read_text(
        encoding="utf-8", errors="strict"
    )
