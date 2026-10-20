# -*- coding: utf-8 -*-
"""Integrity and containment contracts for the isolated native build runtime."""

import hashlib
import io
import json
from pathlib import Path
import site
import sys
from types import SimpleNamespace
import zipfile

import pytest
from scripts import prepare_sqlite_build_runtime as preparation


def _archive(members=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in (
            members or {"sqlite3.dll": b"native-dll", "sqlite3.def": b"exports"}
        ).items():
            archive.writestr(name, value)
    value = stream.getvalue()
    return value, {
        "archive_sha256": hashlib.sha256(value).hexdigest(),
        "archive_sha3_256": hashlib.sha3_256(value).hexdigest(),
        "dll_sha256": hashlib.sha256(b"native-dll").hexdigest(),
    }


@pytest.mark.parametrize("architecture", ["x64", "arm64"])
def test_committed_lock_uses_official_pinned_fixed_release(architecture):
    lock = preparation._read_json(preparation.LOCK)
    pin = preparation._pin(lock, architecture)
    assert lock["sqlite_version"] == "3.54.1"
    assert lock["python_version"] == "3.13.15"
    assert pin["url"].startswith("https://sqlite.org/2026/")


def test_corresponding_source_matches_the_pinned_native_release():
    lock = preparation._read_json(preparation.LOCK)
    config = preparation._read_json(preparation.ROOT / "release-compliance.json")
    sources = [source for source in config["additionalSources"] if source["name"] == "SQLite"]
    assert len(sources) == 1
    assert sources[0]["version"] == lock["sqlite_version"]
    assert sources[0]["url"] == lock["source_archive"]["url"]
    assert sources[0]["sha256"] == lock["source_archive"]["sha256"]


def test_extracts_only_pinned_dll_without_extracting_archive_paths():
    archive, pin = _archive()
    assert preparation._archive_dll(archive, pin) == b"native-dll"


@pytest.mark.parametrize("field", ["archive_sha256", "archive_sha3_256", "dll_sha256"])
def test_archive_or_dll_tampering_is_rejected(field):
    archive, pin = _archive()
    pin[field] = "0" * 64
    with pytest.raises(RuntimeError, match="mismatch"):
        preparation._archive_dll(archive, pin)


@pytest.mark.parametrize(
    "member", ["../sqlite3.dll", "/sqlite3.dll", "sub/sqlite3.dll", "extra.exe"]
)
def test_unexpected_or_traversing_archive_members_are_rejected(member):
    archive, pin = _archive(
        {"sqlite3.dll": b"native-dll", "sqlite3.def": b"exports", member: b"bad"}
    )
    with pytest.raises(RuntimeError, match="members"):
        preparation._archive_dll(archive, pin)


@pytest.mark.parametrize(
    "value", ["https://example.org/sqlite.zip", "http://sqlite.org/2026/sqlite.zip"]
)
def test_pin_cannot_redirect_to_unapproved_host_or_http(value):
    lock = preparation._read_json(preparation.LOCK)
    lock["architectures"]["x64"]["url"] = value
    with pytest.raises(RuntimeError, match="URL"):
        preparation._pin(lock, "x64")


def test_download_rejects_redirect_before_reading_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def geturl(self):
            return "https://other.invalid/replaced.zip"

        def read(self, *_):
            pytest.fail("Redirect response must not be consumed")

    monkeypatch.setattr(preparation, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="redirected"):
        preparation._download({"url": "https://sqlite.org/pinned.zip"})


def test_copy_inventory_omits_installed_packages_caches_and_test_data(tmp_path):
    included = [
        "python.exe",
        "python313.dll",
        "LICENSE.txt",
        "DLLs/_sqlite3.pyd",
        "DLLs/sqlite3.dll",
        "Lib/json/__init__.py",
    ]
    excluded = [
        "Lib/site-packages/private.txt",
        "Lib/__pycache__/cache.pyc",
        "Lib/test/test.py",
        "Doc/help.txt",
    ]
    for relative in included + excluded:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
    assert {
        path.relative_to(tmp_path).as_posix() for path in preparation._source_files(tmp_path)
    } == set(included)


def test_missing_native_runtime_fails_without_synthesizing_a_python(tmp_path):
    (tmp_path / "Lib").mkdir()
    (tmp_path / "DLLs").mkdir()
    with pytest.raises(RuntimeError, match="complete native"):
        preparation._source_files(tmp_path)


def test_package_link_initializes_nested_pth_without_source_bytecode_writes(tmp_path, monkeypatch):
    observed = []

    def addsitedir(path):
        observed.append((path, sys.dont_write_bytecode))
        # A nested initializer must not leave bytecode writes re-enabled.
        sys.dont_write_bytecode = False

    monkeypatch.setattr(site, "addsitedir", addsitedir)
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    exec(preparation._package_pth(tmp_path), {})
    assert observed == [(str(tmp_path), True)]
    assert sys.dont_write_bytecode is True


def test_build_module_probe_compiles_and_checks_actual_imports_and_pyinstaller_paths():
    compile(preparation._IMPORT_SMOKE, "native-module-import-smoke", "exec")
    for name in ("win32api", "win32gui", "win32process", "pywintypes", "pythoncom"):
        assert name in preparation._IMPORT_SMOKE
    assert "get_module_file_attribute(name)" in preparation._IMPORT_SMOKE


def _native_report():
    lock = preparation._read_json(preparation.LOCK)
    return {
        "architecture": "x64",
        "sqlite_version": lock["sqlite_version"],
        "sqlite_source_id": lock["sqlite_source_id"],
        "sqlite_library_sha256": lock["architectures"]["x64"]["dll_sha256"],
        "sqlite_library": "C:/private/build/sqlite3.dll",
    }


def test_payload_receipt_contains_provenance_and_excludes_private_build_paths(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(preparation.verifier, "verify_payload", lambda _: _native_report())
    result = preparation.record_payload(tmp_path, "x64")
    receipt = (tmp_path / "SQLITE_RUNTIME.json").read_text(encoding="utf-8", errors="strict")
    assert result["passed"] is True
    assert json.loads(receipt)["native_exports_queried"] is True
    assert "C:/private" not in receipt
    assert "archive_sha3_256" in receipt
    assert "https://sqlite.org/" in receipt


@pytest.mark.parametrize(
    "field,value",
    [
        ("sqlite_version", "3.50.4"),
        ("sqlite_source_id", "unknown"),
        ("architecture", "arm64"),
        ("sqlite_library_sha256", "0" * 64),
    ],
)
def test_payload_receipt_is_not_written_for_mismatched_native_dll(
    tmp_path, monkeypatch, field, value
):
    report = _native_report()
    report[field] = value
    monkeypatch.setattr(preparation.verifier, "verify_payload", lambda _: report)
    with pytest.raises(RuntimeError, match="differs"):
        preparation.record_payload(tmp_path, "x64")
    assert list(tmp_path.iterdir()) == []


def test_subprocess_scrubs_python_overrides_and_prevents_source_bytecode_writes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PYTHONHOME", "C:/wrong")
    monkeypatch.setenv("PYTHONPATH", "C:/wrong")

    def run(arguments, **kwargs):
        assert arguments[:2] == [str(tmp_path / "python.exe"), "-B"]
        assert "PYTHONHOME" not in kwargs["env"]
        assert "PYTHONPATH" not in kwargs["env"]
        assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "strict"
        return SimpleNamespace(returncode=0, stdout='{"passed":true}', stderr="")

    monkeypatch.setattr(preparation.subprocess, "run", run)
    assert preparation._run_json(tmp_path / "python.exe", ["probe.py"]) == {"passed": True}


def test_synthetic_wal_smoke_is_valid_python_and_never_uses_user_profile_paths():
    compile(preparation._SMOKE, "synthetic-wal-smoke", "exec")
    assert "TemporaryDirectory" in preparation._SMOKE
    assert "APPDATA" not in preparation._SMOKE
    assert "PRAGMA integrity_check" in preparation._SMOKE
