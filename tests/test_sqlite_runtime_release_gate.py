# -*- coding: utf-8 -*-
"""Release SQLite checks use native exports and fail closed without opening DBs."""

import json
from pathlib import Path
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts import verify_sqlite_runtime as gate

SOURCE_ID = "2026-03-13 10:38:09 " + "7" * 64


def _pe(path, machine=0x8664):
    image = bytearray(128)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 96)
    image[96:100] = b"PE\0\0"
    struct.pack_into("<H", image, 100, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)
    return path


def _library(version=b"3.51.3", source=SOURCE_ID.encode("utf-8", errors="strict")):
    return SimpleNamespace(
        sqlite3_libversion=Mock(return_value=version), sqlite3_sourceid=Mock(return_value=source)
    )


@pytest.fixture
def payload(tmp_path, monkeypatch):
    _pe(tmp_path / "DarkCalendar.exe")
    _pe(tmp_path / "_internal/sqlite3.dll")
    monkeypatch.setattr(gate, "_host_architecture", lambda: "x64")
    return tmp_path


@pytest.mark.parametrize(
    "version", ["3.44.6", "3.44.7", "3.50.7", "3.50.8", "3.51.3", "3.51.4", "3.52.1", "3.53.0"]
)
def test_fixed_releases_and_branch_bound_backports_are_accepted(version):
    assert gate.validate_sqlite_version(version) == tuple(map(int, version.split(".")))


@pytest.mark.parametrize(
    "version",
    [
        "3.7.0",
        "3.44.5",
        "3.45.0",
        "3.45.99",
        "3.49.100",
        "3.50.4",
        "3.50.6",
        "3.51.0",
        "3.51.2",
        "3.52.0",
    ],
)
def test_unsafe_or_withdrawn_release_is_rejected(version):
    with pytest.raises(gate.SQLiteRuntimeError):
        gate.validate_sqlite_version(version)


@pytest.mark.parametrize(
    "version",
    [
        None,
        b"3.51.3",
        "",
        "v3.51.3",
        "3.51",
        "3.51.3.0",
        "03.51.3",
        "3.51.3 ",
        "3.51.3-dev",
        "4.0.0",
    ],
)
def test_unknown_versions_fail_closed(version):
    with pytest.raises(gate.SQLiteRuntimeError, match="Unknown"):
        gate.validate_sqlite_version(version)


def test_payload_queries_only_c_version_exports_and_does_not_modify_files(payload, monkeypatch):
    library = _library()
    loader = Mock(return_value=library)
    monkeypatch.setattr(gate, "_load_library", loader)
    before = {
        path.relative_to(payload): path.read_bytes()
        for path in payload.rglob("*")
        if path.is_file()
    }
    report = gate.verify_payload(payload)
    after = {
        path.relative_to(payload): path.read_bytes()
        for path in payload.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert report["passed"] and not report["database_opened"] and not report["metadata_fallback"]
    assert report["sqlite_version"] == "3.51.3" and report["sqlite_source_id"] == SOURCE_ID
    loader.assert_called_once_with((payload / "_internal/sqlite3.dll").resolve())
    library.sqlite3_libversion.assert_called_once_with()
    library.sqlite3_sourceid.assert_called_once_with()


def test_payload_unsafe_c_version_cannot_pass_using_metadata(payload, monkeypatch):
    with (payload / "_internal/sqlite3.dll").open("ab") as stream:
        stream.write(b"FileVersion=3.51.3")
    monkeypatch.setattr(gate, "_load_library", Mock(return_value=_library(b"3.50.4")))
    with pytest.raises(gate.SQLiteRuntimeError, match="3.50.4.*WAL-reset") as error:
        gate.verify_payload(payload)
    assert error.value.details["sqlite_version"] == "3.50.4"
    assert error.value.details["sqlite_source_id"] == SOURCE_ID
    assert error.value.details["native_exports_queried"]
    assert not error.value.details["passed"]


def test_blocked_native_load_does_not_fall_back_to_safe_pe_metadata(payload, monkeypatch):
    monkeypatch.setattr(gate, "_load_library", Mock(side_effect=OSError("DLL loading blocked")))
    with pytest.raises(gate.SQLiteRuntimeError, match="metadata fallback is not allowed"):
        gate.verify_payload(payload)


def test_loader_uses_absolute_path_and_rejects_another_loaded_dll(payload, monkeypatch):
    path = (payload / "_internal/sqlite3.dll").resolve()
    library = SimpleNamespace(_handle=123)
    load = Mock(return_value=library)
    monkeypatch.setattr(gate.ctypes, "CDLL", load)
    monkeypatch.setattr(gate, "_module_path", lambda handle: path)
    assert gate._load_library(path) is library
    load.assert_called_once_with(str(path), winmode=0x00000100 | 0x00001000)
    monkeypatch.setattr(gate, "_module_path", lambda handle: payload / "different.dll")
    with pytest.raises(gate.SQLiteRuntimeError, match="differs from the requested"):
        gate._load_library(path)


@pytest.mark.parametrize(
    "application,dll,host",
    [(0xAA64, 0x8664, "x64"), (0x8664, 0xAA64, "arm64"), (0x8664, 0x8664, "arm64")],
)
def test_architecture_mismatch_fails_before_loading(payload, monkeypatch, application, dll, host):
    _pe(payload / "DarkCalendar.exe", application)
    _pe(payload / "_internal/sqlite3.dll", dll)
    loader = Mock()
    monkeypatch.setattr(gate, "_load_library", loader)
    monkeypatch.setattr(gate, "_host_architecture", lambda: host)
    with pytest.raises(gate.SQLiteRuntimeError, match="architecture"):
        gate.verify_payload(payload)
    loader.assert_not_called()


@pytest.mark.parametrize("machine,expected", [(0x014C, "x86"), (0x8664, "x64"), (0xAA64, "arm64")])
def test_supported_pe_architectures_are_read_from_machine_header(tmp_path, machine, expected):
    assert gate._pe_architecture(_pe(tmp_path / "image.dll", machine)) == expected


def test_unknown_pe_architecture_fails_closed(payload, monkeypatch):
    _pe(payload / "_internal/sqlite3.dll", 0x9999)
    loader = Mock()
    monkeypatch.setattr(gate, "_load_library", loader)
    with pytest.raises(gate.SQLiteRuntimeError, match="Unknown PE architecture"):
        gate.verify_payload(payload)
    loader.assert_not_called()


@pytest.mark.parametrize("contents", [b"", b"not a PE", b"MZ" + bytes(62)])
def test_bad_pe_headers_are_rejected(tmp_path, contents):
    path = tmp_path / "invalid.dll"
    path.write_bytes(contents)
    with pytest.raises(gate.SQLiteRuntimeError, match="PE"):
        gate._pe_architecture(path)


@pytest.mark.parametrize(
    "version,source",
    [
        (None, SOURCE_ID.encode("utf-8", errors="strict")),
        (b"3.51.3", None),
        (b"3.51.3", b""),
        (b"3.51.3", b"unknown"),
        (b"3.51.3", b"\xff"),
    ],
)
def test_unknown_or_unreadable_exports_cannot_pass(payload, monkeypatch, version, source):
    monkeypatch.setattr(gate, "_load_library", Mock(return_value=_library(version, source)))
    with pytest.raises(gate.SQLiteRuntimeError):
        gate.verify_payload(payload)


def test_missing_native_export_cannot_pass(payload, monkeypatch):
    monkeypatch.setattr(gate, "_load_library", Mock(return_value=SimpleNamespace()))
    with pytest.raises(gate.SQLiteRuntimeError, match="native SQLite export"):
        gate.verify_payload(payload)


def test_runtime_compares_python_runtime_with_queried_dll(payload, monkeypatch):
    path = payload / "_internal/sqlite3.dll"
    monkeypatch.setattr(gate, "_runtime_library", lambda: (path, "3.51.3"))
    monkeypatch.setattr(gate, "_load_library", Mock(return_value=_library()))
    assert gate.verify_runtime()["python_sqlite_version"] == "3.51.3"
    monkeypatch.setattr(gate, "_runtime_library", lambda: (path, "3.53.0"))
    with pytest.raises(gate.SQLiteRuntimeError, match="differs"):
        gate.verify_runtime()


def test_runtime_library_resolution_failure_is_not_replaced_with_metadata(monkeypatch):
    monkeypatch.setattr(
        gate, "_runtime_library", Mock(side_effect=gate.SQLiteRuntimeError("Cannot identify DLL"))
    )
    with pytest.raises(gate.SQLiteRuntimeError, match="Cannot identify DLL"):
        gate.verify_runtime()


def test_cli_writes_only_explicit_evidence_and_fails_on_unsafe_runtime(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        gate, "verify_runtime", Mock(side_effect=gate.SQLiteRuntimeError("SQLite 3.50.4 unsafe"))
    )
    evidence = tmp_path / "native-sqlite.json"
    assert gate.main(["--runtime", "--json", str(evidence)]) == 1
    assert set(tmp_path.iterdir()) == {evidence}
    assert json.loads(evidence.read_text(encoding="utf-8", errors="strict"))["passed"] is False
    assert "3.50.4 unsafe" in capsys.readouterr().out


def test_cli_success_needs_native_success_and_does_not_create_implicit_evidence(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        gate, "verify_payload", Mock(return_value={"passed": True, "sqlite_version": "3.51.3"})
    )
    assert gate.main(["--payload", str(tmp_path)]) == 0
    assert not list(tmp_path.iterdir())
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_cli_cannot_silently_drop_requested_evidence(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "verify_runtime", Mock(return_value={"passed": True}))
    assert gate.main(["--runtime", "--json", str(tmp_path / "missing/report.json")]) == 1
    assert not list(tmp_path.iterdir())
    assert "Cannot write" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments", [[], ["--runtime", "--payload", "dist"], ["--runtime", "--allow-unsafe"]]
)
def test_cli_requires_one_mode_and_exposes_no_unsafe_override(arguments):
    with pytest.raises(SystemExit) as error:
        gate.main(arguments)
    assert error.value.code == 2
