# -*- coding: utf-8 -*-
"""Fail closed on native Windows SQLite runtimes without the WAL-reset fix.

No database is opened. Payloads are inspected through their actual SQLite C
exports, never through PE version metadata. Loading a payload DLL requires an
interpreter of the same architecture as both the DLL and DarkCalendar.exe.

Policy sources:
https://www.sqlite.org/wal.html#walreset
https://www.sqlite.org/changes.html (3.52.0 was withdrawn)
https://www.sqlite.org/c3ref/libversion.html
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import sysconfig

POLICY_SOURCES = (
    "https://www.sqlite.org/wal.html#walreset",
    "https://www.sqlite.org/changes.html",
    "https://www.sqlite.org/c3ref/libversion.html",
)
_MACHINES = {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_SOURCE_ID = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9a-f]{40,64}(?:alt1)?"
)


class SQLiteRuntimeError(RuntimeError):
    """Native runtime safety could not be established."""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


def validate_sqlite_version(value: str) -> tuple[int, int, int]:
    """Return a fixed release version, or raise for unknown/unsafe releases."""
    if not isinstance(value, str) or len(value) > 32 or not _VERSION.fullmatch(value):
        raise SQLiteRuntimeError(f"Unknown SQLite version: {value!r}")
    version = tuple(int(part) for part in value.split("."))
    if version[0] != 3:
        raise SQLiteRuntimeError(f"Unknown SQLite major version: {value}")
    if version == (3, 52, 0):
        raise SQLiteRuntimeError("SQLite 3.52.0 was withdrawn and is not allowed for release")
    fixed = (
        version >= (3, 51, 3)
        or (version[:2] == (3, 50) and version[2] >= 7)
        or (version[:2] == (3, 44) and version[2] >= 6)
    )
    if not fixed:
        raise SQLiteRuntimeError(
            f"SQLite {value} does not contain the required WAL-reset fix; "
            "use 3.51.3+, 3.50.7+ on the 3.50 branch, or 3.44.6+ on the 3.44 branch"
        )
    return version


def _pe_architecture(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
            if len(header) != 64 or header[:2] != b"MZ":
                raise SQLiteRuntimeError(f"Not a readable Windows PE image: {path}")
            offset = struct.unpack_from("<I", header, 0x3C)[0]
            stream.seek(offset)
            signature = stream.read(6)
        if len(signature) != 6 or signature[:4] != b"PE\0\0":
            raise SQLiteRuntimeError(f"Invalid Windows PE header: {path}")
        machine = struct.unpack_from("<H", signature, 4)[0]
        if machine not in _MACHINES:
            raise SQLiteRuntimeError(f"Unknown PE architecture 0x{machine:04x}: {path}")
        return _MACHINES[machine]
    except OSError as exc:
        raise SQLiteRuntimeError(f"Cannot read native image {path}: {exc}") from exc


def _host_architecture() -> str:
    platform = sysconfig.get_platform().lower()
    architectures = {"win-amd64": "x64", "win-arm64": "arm64", "win32": "x86"}
    if platform not in architectures:
        raise SQLiteRuntimeError(f"Native Windows SQLite verification needs Windows: {platform}")
    return architectures[platform]


def _module_path(handle: int) -> Path:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    size = kernel.GetModuleFileNameW(handle, buffer, len(buffer))
    if not size or size >= len(buffer):
        raise SQLiteRuntimeError("Cannot resolve the loaded native SQLite DLL path")
    return Path(buffer.value).resolve()


def _load_library(path: Path):
    # SQLite uses the C calling convention. An absolute path also prevents
    # accidental resolution of a same-named host DLL instead of the payload DLL.
    path = path.resolve()
    # LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS:
    # use payload-adjacent dependencies while excluding the current directory.
    library = ctypes.CDLL(str(path), winmode=0x00000100 | 0x00001000)
    if _module_path(library._handle) != path:
        raise SQLiteRuntimeError("The loaded SQLite DLL differs from the requested native image")
    return library


def _exported_text(library, name: str) -> str:
    try:
        function = getattr(library, name)
        function.argtypes = []
        function.restype = ctypes.c_char_p
        value = function()
        if not isinstance(value, bytes) or not value or len(value) > 256:
            raise SQLiteRuntimeError(f"Missing or invalid native SQLite export result: {name}")
        return value.decode("utf-8", errors="strict")
    except (AttributeError, OSError, UnicodeError, TypeError, ValueError) as exc:
        raise SQLiteRuntimeError(f"Cannot query native SQLite export {name}: {exc}") from exc


def _inspect_library(path: Path, expected_architecture: str) -> dict:
    path = path.resolve()
    architecture = _pe_architecture(path)
    if architecture != expected_architecture:
        raise SQLiteRuntimeError(
            f"SQLite DLL architecture {architecture} differs from application {expected_architecture}"
        )
    host = _host_architecture()
    if architecture != host:
        raise SQLiteRuntimeError(
            f"SQLite DLL architecture {architecture} differs from verification interpreter {host}"
        )
    try:
        library = _load_library(path)
    except (OSError, AttributeError, ValueError) as exc:
        raise SQLiteRuntimeError(
            f"Native SQLite load failed: {path}: {exc}; metadata fallback is not allowed"
        ) from exc
    version = _exported_text(library, "sqlite3_libversion")
    source_id = _exported_text(library, "sqlite3_sourceid")
    report = {
        "passed": True,
        "sqlite_library": str(path),
        "sqlite_library_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "architecture": architecture,
        "interpreter_architecture": host,
        "sqlite_version": version,
        "sqlite_source_id": source_id,
        "native_exports_queried": True,
        "metadata_fallback": False,
        "database_opened": False,
        "policy_sources": list(POLICY_SOURCES),
    }
    try:
        validate_sqlite_version(version)
        if not _SOURCE_ID.fullmatch(source_id):
            raise SQLiteRuntimeError(f"Unknown native SQLite source ID: {source_id!r}")
    except SQLiteRuntimeError as exc:
        raise SQLiteRuntimeError(str(exc), details={**report, "passed": False}) from exc
    return report


def verify_payload(payload: Path) -> dict:
    """Check the DLL from a frozen payload using its executable architecture."""
    payload = Path(payload).resolve()
    executable = payload / "DarkCalendar.exe"
    architecture = _pe_architecture(executable)
    report = _inspect_library(payload / "_internal/sqlite3.dll", architecture)
    return {**report, "mode": "payload", "executable": str(executable)}


def _runtime_library() -> tuple[Path, str]:
    if sys.platform != "win32":
        raise SQLiteRuntimeError("Host runtime verification currently requires Windows")
    try:
        import sqlite3
    except (ImportError, OSError) as exc:
        raise SQLiteRuntimeError(f"Cannot load the Python SQLite runtime: {exc}") from exc

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    handle = kernel.GetModuleHandleW("sqlite3.dll")
    if not handle:
        raise SQLiteRuntimeError("Cannot identify the SQLite DLL loaded by the Python runtime")
    return _module_path(handle), sqlite3.sqlite_version


def verify_runtime() -> dict:
    """Check the actual host SQLite DLL without creating even an in-memory DB."""
    path, python_version = _runtime_library()
    report = _inspect_library(path, _host_architecture())
    if report["sqlite_version"] != python_version:
        raise SQLiteRuntimeError(
            "SQLite C export version differs from the loaded Python sqlite3 runtime version",
            details={**report, "passed": False, "python_sqlite_version": python_version},
        )
    return {**report, "mode": "runtime", "python_sqlite_version": python_version}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--payload", type=Path, help="Frozen folder containing DarkCalendar.exe")
    mode.add_argument(
        "--runtime", action="store_true", help="Check this Python runtime's SQLite DLL"
    )
    parser.add_argument("--json", type=Path, help="Optional evidence file; its parent must exist")
    args = parser.parse_args(argv)
    try:
        report = verify_payload(args.payload) if args.payload is not None else verify_runtime()
    except (SQLiteRuntimeError, OSError) as exc:
        report = {
            **getattr(exc, "details", {}),
            "passed": False,
            "error": str(exc),
            "policy_sources": list(POLICY_SOURCES),
        }
    report["mode"] = "payload" if args.payload is not None else "runtime"
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered, end="")
    if args.json is not None:
        try:
            args.json.write_text(rendered, encoding="utf-8", errors="strict")
        except OSError as exc:
            print(f"Cannot write the specified evidence file: {exc}", file=sys.stderr)
            return 1
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
