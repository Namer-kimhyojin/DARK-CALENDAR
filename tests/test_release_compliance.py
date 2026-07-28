# -*- coding: utf-8 -*-
import json
from pathlib import Path
import tempfile
import tomllib

import pytest
from scripts import release_compliance

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_lock_uses_only_exact_unique_pins():
    pins = release_compliance.read_lock(ROOT / "requirements-runtime.lock")
    normalized = [name.lower().replace("_", "-") for name, _version in pins]

    assert len(pins) >= 30
    assert len(normalized) == len(set(normalized))
    assert ("QtAwesome", "1.4.2") in pins
    assert ("PyQt6", "6.10.2") in pins


def test_runtime_lock_rejects_version_ranges():
    with tempfile.TemporaryDirectory() as temp_dir:
        lock = Path(temp_dir) / "bad.lock"
        lock.write_text("QtAwesome>=1.4.2\n", encoding="utf-8", errors="strict")

        with pytest.raises(ValueError, match="exact == pins"):
            release_compliance.read_lock(lock)


def test_payload_verifier_rejects_removed_qt_and_ffmpeg_modules():
    with tempfile.TemporaryDirectory() as temp_dir:
        payload = Path(temp_dir)
        for name in ("LICENSE", "README.md", "SOURCE_OFFER.md", "THIRD_PARTY_NOTICES.md"):
            (payload / name).write_text("notice\n", encoding="utf-8", errors="strict")
        (payload / "THIRD_PARTY_LICENSES").mkdir()
        pins = release_compliance.read_lock(ROOT / "requirements-runtime.lock")
        (payload / "THIRD_PARTY_MANIFEST.json").write_text(
            json.dumps(
                {"packages": [{"name": name, "version": version} for name, version in pins]}
            ),
            encoding="utf-8",
            errors="strict",
        )
        (payload / "avcodec-61.dll").write_bytes(b"not allowed")

        with pytest.raises(RuntimeError, match="Unapproved Qt/FFmpeg"):
            release_compliance.verify_payload(
                payload,
                ROOT / "requirements-runtime.lock",
                ROOT / "release-compliance.json",
                None,
            )


def test_compliance_config_pins_every_download_with_sha256():
    config = json.loads(
        (ROOT / "release-compliance.json").read_text(encoding="utf-8", errors="strict")
    )
    downloads = list(config["additionalSources"]) + list(config["commonLicenseTexts"])
    downloads += [item for item in config["sourceOverrides"].values() if "filename" in item]

    assert downloads
    for item in downloads:
        assert item["url"].startswith("https://")
        assert len(item["sha256"]) == 64


def test_release_version_surfaces_are_in_sync():
    from calendar_app.app_metadata import APP_RELEASE_DATE, APP_VERSION

    package_version = f"{APP_VERSION}.0"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8", errors="strict"))
    site_config = json.loads(
        (ROOT / "docs" / "site-config.json").read_text(encoding="utf-8", errors="strict")
    )

    assert project["project"]["version"] == APP_VERSION
    assert f'Version="{package_version}"' in (ROOT / "AppxManifest.xml").read_text(
        encoding="utf-8", errors="strict"
    )
    assert f"FileVersion', '{package_version}'" in (ROOT / "version_info.txt").read_text(
        encoding="utf-8", errors="strict"
    )
    assert site_config["appVersion"] == APP_VERSION

    expected_release_url = (
        f"https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v{APP_VERSION}"
    )
    expected_source_asset = (
        "https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/download/"
        f"v{APP_VERSION}/DarkCalendar-{APP_VERSION}-corresponding-source.zip"
    )
    assert site_config["releaseSourceUrl"] == expected_release_url
    assert expected_release_url in (ROOT / "README.md").read_text(encoding="utf-8", errors="strict")
    assert expected_source_asset in (ROOT / "SOURCE_OFFER.md").read_text(
        encoding="utf-8", errors="strict"
    )

    checklist = ROOT / "docs" / f"release-{APP_VERSION}-checklist.md"
    notes = ROOT / "docs" / f"release-{APP_VERSION}-notes.md"
    assert checklist.is_file()
    assert notes.is_file()
    checklist_text = checklist.read_text(encoding="utf-8", errors="strict")
    assert f"**Date:** {APP_RELEASE_DATE}" in checklist_text


def test_github_release_workflow_uses_unified_release_entrypoint():
    workflow = (ROOT / ".github" / "workflows" / "build-release.yml").read_text(
        encoding="utf-8", errors="strict"
    )

    assert "build-release.bat" in workflow
    assert "requirements-build.lock" in workflow
    assert "corresponding-source.zip" in workflow
    assert "gh release" in workflow
    assert "build.ps1" not in workflow
    assert "make-store-upload.ps1" not in workflow
