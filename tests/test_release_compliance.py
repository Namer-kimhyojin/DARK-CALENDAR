# -*- coding: utf-8 -*-
import json
from pathlib import Path
import tempfile

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
