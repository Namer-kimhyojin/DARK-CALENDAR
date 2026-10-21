# -*- coding: utf-8 -*-
"""Exercise the real release asset copier without running the build pipeline."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHELLS = [shell for name in ("powershell", "pwsh") if (shell := shutil.which(name))]


@pytest.fixture(
    params=SHELLS or [None], ids=lambda shell: Path(shell).stem if shell else "no-shell"
)
def invoke_assets(request, tmp_path):
    if request.param is None:
        pytest.skip("Manifest asset security tests require PowerShell on Windows")
    if sys.platform != "win32":
        pytest.skip("The release pipeline uses Windows path semantics")
    runner = tmp_path / "invoke-assets.ps1"
    runner.write_text(
        r"""param([string]$PipelinePath, [string]$RequestPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($PipelinePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Invalid release pipeline PowerShell' }
$names = @('Copy-ManifestAssets', 'Get-ManifestAssetCopies', 'Assert-ManifestAssetTreePath')
foreach ($definition in $ast.FindAll({param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names
}, $true)) {
    . ([scriptblock]::Create($definition.Extent.Text))
}
$request = Get-Content -LiteralPath $RequestPath -Raw -Encoding utf8 | ConvertFrom-Json
try {
    if ($request.Validate) {
        $copies = @(Get-ManifestAssetCopies -ManifestPath $request.Manifest `
            -SourceRoot $request.Source -DestinationRoot $request.Destination -RequireDestination)
        $count = $copies.Count
    } else {
        $count = Copy-ManifestAssets -ManifestPath $request.Manifest `
            -SourceRoot $request.Source -DestinationRoot $request.Destination
    }
    @{ Rejected = $false; Count = $count } | ConvertTo-Json -Compress
} catch {
    @{ Rejected = $true; Error = $_.Exception.Message } | ConvertTo-Json -Compress
}
""",
        encoding="utf-8",
        errors="strict",
    )

    def invoke(manifest, source, destination, *, validate=False):
        request_path = tmp_path / "request.json"
        request_path.write_text(
            json.dumps(
                {
                    "Manifest": str(manifest),
                    "Source": str(source),
                    "Destination": str(destination),
                    "Validate": validate,
                }
            ),
            encoding="utf-8",
            errors="strict",
        )
        result = subprocess.run(
            [
                request.param,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(runner),
                str(ROOT / "scripts/build_pipeline.ps1"),
                str(request_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    return invoke


def manifest_fixture(tmp_path, references):
    source = tmp_path / "source" / "Assets"
    source.mkdir(parents=True)
    (source / "payload.png").write_bytes(b"repository-controlled bytes")
    destination = tmp_path / "stage"
    destination.mkdir()
    entries = []
    for kind, path in references:
        if kind == "element":
            entries.append(f"<Logo>{escape(path)}</Logo>")
        else:
            entries.append(f"<VisualElements Square44x44Logo={quoteattr(path)} />")
    manifest = tmp_path / "AppxManifest.xml"
    manifest.write_text(
        "<Package>" + "".join(entries) + "</Package>", encoding="utf-8", errors="strict"
    )
    return manifest, source, destination


@pytest.mark.parametrize("kind", ["attribute", "element"])
def test_parent_traversal_cannot_overwrite_outside_staging(invoke_assets, tmp_path, kind):
    manifest, source, destination = manifest_fixture(
        tmp_path, [(kind, r"Assets\..\..\payload.png")]
    )
    sentinel = tmp_path / "payload.png"
    sentinel.write_bytes(b"preserve outside file")
    result = invoke_assets(manifest, source, destination)
    assert sentinel.read_bytes() == b"preserve outside file"
    assert result["Rejected"], result
    assert list(destination.rglob("*")) == []


@pytest.mark.parametrize(
    "path",
    [
        r"Assets\..\payload.png",
        r"Assets\..\stage-sibling\payload.png",
        "Assets/../../payload.png",
        r"Assets\../payload.png",
        r"Assets/..\payload.png",
        r"\Assets\payload.png",
        r"C:\Assets\payload.png",
        r"C:Assets\payload.png",
        r"\\server\share\Assets\payload.png",
        r"\\?\C:\Assets\payload.png",
        r"Assets\C:\payload.png",
        r"Assets\payload.png:stream",
        r"Assets\*payload.png",
        "Assets\\\\payload.png",
        r"Assets\.\payload.png",
        "Assets\\",
        "",
        "payload.png",
        "Assets",
        r"Assets\.. \payload.png",
        "Assets\\payload.png.",
        "Assets\\payload.png ",
        "Assets\\sub\\..\\payload.png",
        r"Assets\NUL.png",
        r"Assets\sub\COM1",
        r"Assets\payload?.png",
    ],
)
def test_invalid_paths_fail_before_any_asset_is_copied(invoke_assets, tmp_path, path):
    manifest, source, destination = manifest_fixture(
        tmp_path, [("element", r"Assets\payload.png"), ("attribute", path)]
    )
    result = invoke_assets(manifest, source, destination)
    assert result["Rejected"], result
    assert list(destination.rglob("*")) == []


def test_nested_assets_and_duplicate_references_copy_exact_files(invoke_assets, tmp_path):
    manifest, source, destination = manifest_fixture(
        tmp_path,
        [
            ("element", r"Assets\payload.png"),
            ("attribute", r"assets\PAYLOAD.png"),
            ("attribute", r"Assets\nested\payload.png"),
        ],
    )
    (source / "nested").mkdir()
    (source / "nested" / "payload.png").write_bytes(b"nested image")
    (source / "unreferenced.png").write_bytes(b"do not copy")
    result = invoke_assets(manifest, source, destination)
    assert result == {"Rejected": False, "Count": 2}
    assert (destination / "Assets" / "payload.png").read_bytes() == b"repository-controlled bytes"
    assert (destination / "Assets" / "nested" / "payload.png").read_bytes() == b"nested image"
    assert len(list(destination.rglob("*.png"))) == 2
    assert invoke_assets(manifest, source, destination, validate=True) == result


def test_missing_source_fails_before_any_copy(invoke_assets, tmp_path):
    manifest, source, destination = manifest_fixture(
        tmp_path,
        [
            ("element", r"Assets\payload.png"),
            ("attribute", r"Assets\missing.png"),
        ],
    )
    result = invoke_assets(manifest, source, destination)
    assert result["Rejected"], result
    assert list(destination.rglob("*")) == []


def test_empty_manifest_is_rejected(invoke_assets, tmp_path):
    manifest, source, destination = manifest_fixture(tmp_path, [])
    assert invoke_assets(manifest, source, destination)["Rejected"]


@pytest.mark.parametrize("path", ["", "Assets\\payload.png ", r"C:\Assets\payload.png"])
def test_invalid_element_text_is_rejected(invoke_assets, tmp_path, path):
    manifest, source, destination = manifest_fixture(tmp_path, [("element", path)])
    assert invoke_assets(manifest, source, destination)["Rejected"]
    assert list(destination.rglob("*")) == []


def test_repository_manifest_copies_and_revalidates(invoke_assets, tmp_path):
    destination = tmp_path / "stage"
    destination.mkdir()
    result = invoke_assets(ROOT / "AppxManifest.xml", ROOT / "Assets", destination)
    assert result == {"Rejected": False, "Count": 6}
    assert (
        invoke_assets(ROOT / "AppxManifest.xml", ROOT / "Assets", destination, validate=True)
        == result
    )
    (destination / "Assets" / "StoreLogo.png").unlink()
    missing = invoke_assets(ROOT / "AppxManifest.xml", ROOT / "Assets", destination, validate=True)
    assert missing["Rejected"] and "missing" in missing["Error"].lower(), missing


def test_changed_staged_manifest_is_rejected(invoke_assets, tmp_path):
    manifest, source, destination = manifest_fixture(tmp_path, [("element", r"Assets\payload.png")])
    assert not invoke_assets(manifest, source, destination)["Rejected"]
    manifest.write_text(
        r"<Package><Logo>Assets\..\..\payload.png</Logo></Package>",
        encoding="utf-8",
        errors="strict",
    )
    assert invoke_assets(manifest, source, destination, validate=True)["Rejected"]
    assert not (tmp_path / "payload.png").exists()


@pytest.mark.parametrize("side", ["source", "destination"])
def test_junction_cannot_redirect_asset_copy(invoke_assets, tmp_path, side):
    manifest, source, destination = manifest_fixture(
        tmp_path, [("element", r"Assets\nested\payload.png")]
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "payload.png"
    sentinel.write_bytes(b"preserve junction target")
    (source / "nested").mkdir()
    (source / "nested" / "payload.png").write_bytes(b"source nested image")
    if side == "source":
        (source / "nested" / "payload.png").unlink()
        (source / "nested").rmdir()
        link = source / "nested"
    else:
        (destination / "Assets").mkdir()
        link = destination / "Assets" / "nested"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    try:
        result = invoke_assets(manifest, source, destination)
        assert result["Rejected"], result
        assert "reparse" in result["Error"].lower(), result
        assert sentinel.read_bytes() == b"preserve junction target"
    finally:
        link.rmdir()


def test_pipeline_revalidates_staged_manifest_before_packaging():
    script = (ROOT / "scripts/build_pipeline.ps1").read_text(encoding="utf-8", errors="strict")
    pack = script.index('$packArgs = @("pack"')
    gate = script.rindex("Get-ManifestAssetCopies", 0, pack)
    assert "-ManifestPath $manifestDest" in script[gate:pack]
    assert "-RequireDestination" in script[gate:pack]
