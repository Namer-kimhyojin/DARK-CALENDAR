# -*- coding: utf-8 -*-
"""Release metadata must stay inside cache directories and ZIP members."""

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest
from scripts import release_compliance

UNSAFE_FILENAMES = [
    "",
    ".",
    "..",
    "../escape.tar.gz",
    "..\\escape.tar.gz",
    "/escape.tar.gz",
    "\\escape.tar.gz",
    "C:\\escape.tar.gz",
    "C:escape.tar.gz",
    "\\\\server\\share\\escape.tar.gz",
    "nested/../escape.tar.gz",
    "nested\\../escape.tar.gz",
    "nested/archive.tar.gz",
    "nested\\archive.tar.gz",
    "archive.tar.gz:stream",
    "archive.tar.gz.",
    "archive.tar.gz ",
    "NUL.txt",
    "archive\x00.tar.gz",
    "archive\n.tar.gz",
    None,
    123,
]

PRIVATE_FILENAMES = [
    "credentials.json",
    "TOKEN.JSON",
    "Oauth.json",
    ".env",
    ".ENV.local",
    ".env.production",
    "client_secret.json",
    "client_secret_123.apps.googleusercontent.com.json",
    "caldav-personal.credential",
    "OUTLOOK-personal.cache",
    "outlook-personal.tmp",
    "caldav-personal.tmp",
    "token.json.abcd.tmp",
    "credentials.json.backup",
    "credentials.json.example.py",
    "oauth.json.random",
]


@pytest.mark.parametrize("filename", PRIVATE_FILENAMES)
def test_private_file_match_uses_case_insensitive_cross_platform_basename(filename):
    assert release_compliance._is_private_calendar_file(f"nested/{filename}")
    assert release_compliance._is_private_calendar_file(f"nested\\{filename}")


@pytest.mark.parametrize(
    "filename",
    [
        ".env.example",
        ".ENV.EXAMPLE",
        "token_store.py",
        "oauth.py",
        "client_secret_example.txt",
        "calendar.cache",
        "outlook_notes.md",
        "caldav.py",
    ],
)
def test_expected_public_source_names_remain_supported(filename):
    assert not release_compliance._is_private_calendar_file(filename)


@pytest.fixture
def release_fixture(tmp_path, monkeypatch):
    data = b"pinned upstream bytes"
    download = {
        "filename": "demo-1.0.tar.gz",
        "url": "https://example.invalid/source",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    config = {
        "sourceOverrides": {"demo": dict(download)},
        "additionalSources": [{**download, "filename": "extra.tar.gz"}],
        "commonLicenseTexts": [{**download, "filename": "MIT.txt"}],
        "licenseFallbacks": {"demo": {"filename": "MIT.txt"}},
    }
    (tmp_path / "runtime.lock").write_text("demo==1.0\n", encoding="utf-8", errors="strict")
    (tmp_path / "main.py").write_bytes(b"# application source\n")
    requests = []

    def open_download(request, **kwargs):
        requests.append(request.full_url)
        return io.BytesIO(data)

    monkeypatch.setattr(release_compliance, "urlopen", open_download)
    monkeypatch.setattr(release_compliance, "_tracked_files", lambda root: [Path("main.py")])
    monkeypatch.setattr(
        release_compliance, "verify_environment", lambda lock: [{"name": "demo", "version": "1.0"}]
    )
    monkeypatch.setattr(
        release_compliance.metadata,
        "distribution",
        lambda name: SimpleNamespace(files=[], metadata={}),
    )

    def run(command="source", version="1.0"):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8", errors="strict")
        if command == "licenses":
            return release_compliance.bundle_licenses(
                tmp_path / "runtime.lock", config_path, tmp_path / "payload", tmp_path / "cache"
            )
        return release_compliance.build_corresponding_source(
            tmp_path,
            version,
            tmp_path / "runtime.lock",
            config_path,
            tmp_path / "bundle.zip",
            tmp_path / "cache",
        )

    return SimpleNamespace(root=tmp_path, config=config, requests=requests, data=data, run=run)


def test_parent_filename_cannot_write_outside_source_cache(release_fixture):
    fixture = release_fixture
    fixture.config["sourceOverrides"]["demo"]["filename"] = "../escaped.tar.gz"
    with pytest.raises(ValueError, match="Unsafe compliance filename"):
        fixture.run()
    assert not (fixture.root / "cache/escaped.tar.gz").exists()


@pytest.mark.parametrize("filename", UNSAFE_FILENAMES)
@pytest.mark.parametrize("command", ["source", "licenses"])
@pytest.mark.parametrize(
    "section", ["sourceOverrides", "additionalSources", "commonLicenseTexts", "licenseFallbacks"]
)
def test_unsafe_config_filenames_fail_before_side_effects(
    release_fixture, filename, command, section
):
    fixture = release_fixture
    items = fixture.config[section]
    item = items["demo"] if isinstance(items, dict) else items[0]
    item["filename"] = filename

    with pytest.raises(ValueError, match="Unsafe compliance filename"):
        fixture.run(command)

    assert fixture.requests == []
    assert not (fixture.root / "cache").exists()
    assert not (fixture.root / "payload").exists()
    assert not (fixture.root / "bundle.zip").exists()


@pytest.mark.parametrize("filename", UNSAFE_FILENAMES)
def test_pypi_filenames_are_validated(release_fixture, monkeypatch, filename):
    fixture = release_fixture
    item = fixture.config["sourceOverrides"].pop("demo")
    monkeypatch.setattr(
        release_compliance, "_pypi_sdist", lambda name, version: {**item, "filename": filename}
    )

    with pytest.raises(ValueError, match="Unsafe compliance filename"):
        fixture.run()

    assert fixture.requests == []
    assert not (fixture.root / "cache").exists()


@pytest.mark.parametrize("directory", ["sources", "licenses"])
@pytest.mark.parametrize("partial", [False, True])
def test_cache_symlinks_cannot_escape(release_fixture, directory, partial):
    fixture = release_fixture
    outside = fixture.root / "outside.txt"
    outside.write_bytes(fixture.data)
    cache = fixture.root / "cache" / directory
    cache.mkdir(parents=True)
    filename = "demo-1.0.tar.gz" if directory == "sources" else "MIT.txt"
    target = cache / (filename + ".part" if partial else filename)
    try:
        target.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"File symlinks unavailable: {error}")

    with pytest.raises(ValueError, match="leaves cache directory"):
        fixture.run("source" if directory == "sources" else "licenses")

    assert outside.read_bytes() == fixture.data
    assert target.is_symlink()
    assert fixture.requests == []


@pytest.mark.parametrize("directory", ["sources", "licenses"])
@pytest.mark.parametrize("partial", [False, True])
def test_resolved_cache_paths_are_checked_before_reuse_or_download(
    release_fixture, monkeypatch, directory, partial
):
    fixture = release_fixture
    cache = fixture.root / "cache" / directory
    cache.mkdir(parents=True)
    filename = "demo-1.0.tar.gz" if directory == "sources" else "MIT.txt"
    destination = cache / filename
    destination.write_bytes(fixture.data)
    target = cache / (filename + ".part" if partial else filename)
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == target:
            return fixture.root / "outside.txt"
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="leaves cache directory"):
        fixture.run("source" if directory == "sources" else "licenses")
    assert destination.read_bytes() == fixture.data
    assert fixture.requests == []


def test_download_still_rejects_hash_mismatch(release_fixture, monkeypatch):
    fixture = release_fixture
    monkeypatch.setattr(
        release_compliance, "urlopen", lambda *args, **kwargs: io.BytesIO(b"wrong bytes")
    )
    with pytest.raises(RuntimeError, match="Downloaded hash mismatch"):
        fixture.run()
    assert not (fixture.root / "cache/sources/demo-1.0.tar.gz").exists()
    assert not (fixture.root / "cache/sources/demo-1.0.tar.gz.part").exists()


def test_safe_release_bundle_and_license_fallback_remain_supported(release_fixture):
    fixture = release_fixture
    bundle = fixture.run()
    with zipfile.ZipFile(bundle) as archive:
        expected = {
            "DarkCalendar-1.0/application-source/main.py",
            "DarkCalendar-1.0/SOURCE_BUNDLE_MANIFEST.json",
            "DarkCalendar-1.0/upstream-sources/demo-1.0.tar.gz",
            "DarkCalendar-1.0/upstream-sources/extra.tar.gz",
            "DarkCalendar-1.0/common-license-texts/MIT.txt",
        }
        assert set(archive.namelist()) == expected
        assert all(
            part not in ("", ".", "..") for name in archive.namelist() for part in name.split("/")
        )
        assert archive.read("DarkCalendar-1.0/upstream-sources/demo-1.0.tar.gz") == fixture.data
    manifest_path = fixture.run("licenses")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="strict"))
    assert manifest["packages"][0]["licenseFiles"][0]["file"] == "MIT.txt"
    assert (
        fixture.root / "payload/THIRD_PARTY_LICENSES/demo-1.0/MIT.txt"
    ).read_bytes() == fixture.data
    assert (
        len(fixture.requests) == 3
    )  # License fallback and repeat builds reuse verified cache files.


@pytest.mark.parametrize(
    "member",
    [
        "../escape.py",
        "/absolute.py",
        "DarkCalendar-1.0/upstream-sources/../escape.py",
        "DarkCalendar-1.0//escape.py",
        "DarkCalendar-1.0/./escape.py",
        "DarkCalendar-1.0/..\\escape.py",
        "C:/escape.py",
    ],
)
def test_payload_verification_rejects_unsafe_zip_members(release_fixture, member):
    fixture = release_fixture
    bundle = fixture.run()
    fixture.run("licenses")
    payload = fixture.root / "payload"
    for name in ("LICENSE", "README.md", "SOURCE_OFFER.md", "THIRD_PARTY_NOTICES.md"):
        (payload / name).write_bytes(b"notice")
    args = (payload, fixture.root / "runtime.lock", fixture.root / "config.json", bundle)
    release_compliance.verify_payload(*args)
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr(member, b"unsafe entry")
    with pytest.raises(ValueError, match="Unsafe compliance filename"):
        release_compliance.verify_payload(*args)


@pytest.mark.parametrize("version", ["../escape", "1.0/../../escape", "1.0\\escape"])
def test_unsafe_bundle_prefix_is_rejected(release_fixture, version):
    with pytest.raises(ValueError, match="Unsafe compliance filename"):
        release_fixture.run(version=version)
    assert release_fixture.requests == []
    assert not (release_fixture.root / "bundle.zip").exists()


@pytest.mark.parametrize(
    "relative", ["../escape.py", "/absolute.py", "nested/../escape.py", "C:/escape.py"]
)
def test_unexpected_application_archive_member_fails(release_fixture, monkeypatch, relative):
    monkeypatch.setattr(release_compliance, "_tracked_files", lambda root: [Path(relative)])
    with pytest.raises(ValueError, match="Unsafe compliance filename"):
        release_fixture.run()
    assert release_fixture.requests == []
    assert not (release_fixture.root / "bundle.zip").exists()


@pytest.mark.parametrize("filename", PRIVATE_FILENAMES)
def test_private_source_inventory_fails_before_download_or_output_replace(
    release_fixture, monkeypatch, filename
):
    fixture = release_fixture
    relative = Path("nested") / filename
    # No credential file is created or opened: the inventory alone must stop packaging.
    inventory = Mock(return_value=[Path("main.py"), relative])
    monkeypatch.setattr(release_compliance, "_tracked_files", inventory)
    output = fixture.root / "bundle.zip"
    output.write_bytes(b"previous synthetic bundle")
    with pytest.raises(ValueError, match="Private calendar file"):
        fixture.run()
    inventory.assert_called_once_with(fixture.root)
    assert fixture.requests == []
    assert not (fixture.root / "cache").exists()
    assert output.read_bytes() == b"previous synthetic bundle"


def test_source_inventory_is_collected_only_once(release_fixture, monkeypatch):
    inventory = Mock(side_effect=[[Path("main.py")], [Path("token.json")]])
    monkeypatch.setattr(release_compliance, "_tracked_files", inventory)
    release_fixture.run()
    inventory.assert_called_once_with(release_fixture.root)


@pytest.mark.parametrize("escape", [False, True])
def test_resolved_source_targets_cannot_bypass_preflight(release_fixture, monkeypatch, escape):
    fixture = release_fixture
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == fixture.root / "main.py":
            return fixture.root.parent / "outside.py" if escape else fixture.root / "token.json"
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="leaves project directory|Private calendar file"):
        fixture.run()
    assert fixture.requests == []
    assert not (fixture.root / "bundle.zip").exists()


@pytest.mark.parametrize("filename", PRIVATE_FILENAMES)
@pytest.mark.parametrize("surface", ["payload", "source_bundle"])
def test_payload_gate_rejects_private_files_without_reading_contents(
    release_fixture, filename, surface
):
    fixture = release_fixture
    bundle = fixture.run()
    fixture.run("licenses")
    payload = fixture.root / "payload"
    for name in ("LICENSE", "README.md", "SOURCE_OFFER.md", "THIRD_PARTY_NOTICES.md"):
        (payload / name).write_bytes(b"notice")
    if surface == "payload":
        nested = payload / "_internal"
        nested.mkdir()
        (nested / filename).write_bytes(b"synthetic placeholder")
    else:
        with zipfile.ZipFile(bundle, "a") as archive:
            archive.writestr(
                f"DarkCalendar-1.0/application-source/nested/{filename}", b"placeholder"
            )
    with pytest.raises(
        (RuntimeError, ValueError), match="Unapproved runtime|Private calendar file"
    ):
        release_compliance.verify_payload(
            payload, fixture.root / "runtime.lock", fixture.root / "config.json", bundle
        )


@pytest.mark.parametrize("section", ["sourceOverrides", "additionalSources", "commonLicenseTexts"])
def test_private_metadata_filename_is_rejected_before_download(release_fixture, section):
    fixture = release_fixture
    items = fixture.config[section]
    item = items["demo"] if isinstance(items, dict) else items[0]
    item["filename"] = "token.json"
    with pytest.raises(ValueError, match="Private calendar file"):
        fixture.run()
    assert fixture.requests == []
    assert not (fixture.root / "bundle.zip").exists()


def test_environment_example_is_allowed_in_source_and_payload(release_fixture, monkeypatch):
    fixture = release_fixture
    (fixture.root / ".env.example").write_bytes(b"# template without credentials")
    monkeypatch.setattr(
        release_compliance, "_tracked_files", lambda _root: [Path("main.py"), Path(".env.example")]
    )
    bundle = fixture.run()
    fixture.run("licenses")
    payload = fixture.root / "payload"
    for name in (
        "LICENSE",
        "README.md",
        "SOURCE_OFFER.md",
        "THIRD_PARTY_NOTICES.md",
        ".env.example",
    ):
        (payload / name).write_bytes(b"public placeholder")
    release_compliance.verify_payload(
        payload, fixture.root / "runtime.lock", fixture.root / "config.json", bundle
    )
