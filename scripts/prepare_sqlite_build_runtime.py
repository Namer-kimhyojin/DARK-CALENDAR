# -*- coding: utf-8 -*-
"""Prepare a private Python build runtime with a pinned official SQLite DLL.

The selected development Python, its environment and installed Store packages
are never modified. Only Python's standard runtime is copied; locked packages
are read from the selected environment through a .pth file. No personal DB is
opened. The only database exercise uses a temporary synthetic WAL database.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

if __package__:
    from scripts import verify_sqlite_runtime as verifier
else:
    import verify_sqlite_runtime as verifier

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name("sqlite-runtime-lock.json")
RECEIPT = "build-runtime-receipt.json"
_EXCLUDED = {"site-packages", "__pycache__", "test", "tests", "idlelib", "turtledemo"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="strict"))


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", errors="strict")


def _pin(lock: dict, architecture: str) -> dict:
    if lock.get("schema_version") != 1:
        raise RuntimeError("Unsupported SQLite runtime lock schema")
    verifier.validate_sqlite_version(lock["sqlite_version"])
    pin = lock["architectures"][architecture]
    expected_url = f"https://sqlite.org/2026/sqlite-dll-win-{architecture}-3540100.zip"
    if pin["url"] != expected_url:
        raise RuntimeError("SQLite download URL differs from the approved official archive")
    for field in ("archive_sha256", "archive_sha3_256", "dll_sha256"):
        value = pin[field]
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise RuntimeError(f"Invalid pinned {field}")
    return pin


def _archive_dll(data: bytes, pin: dict) -> bytes:
    if hashlib.sha256(data).hexdigest() != pin["archive_sha256"]:
        raise RuntimeError("SQLite archive SHA-256 mismatch")
    if hashlib.sha3_256(data).hexdigest() != pin["archive_sha3_256"]:
        raise RuntimeError("SQLite archive official SHA3-256 mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sorted(archive.namelist()) != ["sqlite3.def", "sqlite3.dll"]:
            raise RuntimeError("Unexpected SQLite archive members")
        entry = archive.getinfo("sqlite3.dll")
        if entry.file_size > 20 * 1024 * 1024:
            raise RuntimeError("SQLite DLL exceeds the expected size bound")
        dll = archive.read(entry)
    if hashlib.sha256(dll).hexdigest() != pin["dll_sha256"]:
        raise RuntimeError("SQLite DLL SHA-256 mismatch")
    return dll


def _download(pin: dict) -> bytes:
    request = Request(pin["url"], headers={"User-Agent": "AirCalendar-BuildRuntime/1.0"})
    with urlopen(request, timeout=45) as response:
        if response.geturl() != pin["url"]:
            raise RuntimeError("SQLite archive download redirected from its pinned URL")
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise RuntimeError("SQLite archive exceeds the expected size bound")
    return _archive_dll(data, pin)


def _source_files(base: Path) -> list[Path]:
    files = [
        path
        for path in base.iterdir()
        if path.is_file()
        and (path.suffix.lower() in {".exe", ".dll"} or path.name == "LICENSE.txt")
    ]
    for directory in ("Lib", "DLLs"):
        for folder, directories, names in os.walk(base / directory):
            directories[:] = sorted(name for name in directories if name not in _EXCLUDED)
            files.extend(Path(folder) / name for name in names if not name.endswith(".pyc"))
    if not all((base / name).is_file() for name in ("python.exe", "DLLs/_sqlite3.pyd")):
        raise RuntimeError("Selected Python has no complete native standard runtime")
    return sorted(files)


def _package_pth(packages: Path) -> str:
    # A bare path only appends site-packages; it does not process pywin32.pth.
    # Execute the selected environment's normal .pth initialization while
    # preventing imports from writing bytecode back into that environment.
    return (
        "import site, sys; sys.dont_write_bytecode = True; "
        f"site.addsitedir({str(packages)!r}); sys.dont_write_bytecode = True\n"
    )


def _inputs(lock: dict) -> tuple[dict, list[Path], Path]:
    if sys.platform != "win32":
        raise RuntimeError("Private release runtimes require native Windows Python")
    actual_version = ".".join(str(value) for value in sys.version_info[:3])
    if actual_version != lock["python_version"]:
        raise RuntimeError(f"Release runtime requires Python {lock['python_version']}")
    base = Path(sys.base_prefix).resolve()
    packages = Path(sys.prefix, "Lib", "site-packages").resolve()
    if not packages.is_dir():
        raise RuntimeError("Selected environment has no locked site-packages directory")
    files = _source_files(base)
    inputs = {
        "python_version": actual_version,
        "source_python": str(Path(sys.executable).resolve()),
        "source_packages": str(packages),
        "lock_sha256": _sha256(LOCK),
        "preparer_sha256": _sha256(Path(__file__).resolve()),
        "verifier_sha256": _sha256(ROOT / "scripts/verify_sqlite_runtime.py"),
        "build_lock_sha256": _sha256(ROOT / "requirements-build.lock"),
        "runtime_lock_sha256": _sha256(ROOT / "requirements-runtime.lock"),
        "source_package_pth_sha256": {
            path.name: _sha256(path) for path in sorted(packages.glob("*.pth"))
        },
        "standard_runtime_sha256": {
            path.relative_to(base).as_posix(): _sha256(path) for path in files
        },
    }
    return inputs, files, packages


def _run_json(python: Path, arguments: list[str]) -> dict:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [str(python), "-B", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Private runtime validation failed: {result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


_SMOKE = """
import json, sqlite3, tempfile
from contextlib import closing
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
with tempfile.TemporaryDirectory(prefix='air-calendar-sqlite-smoke-') as folder:
    path = str(Path(folder) / 'synthetic.db')
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        connection.execute('CREATE TABLE smoke (value INTEGER PRIMARY KEY)')
        assert connection.execute("SELECT json_extract(json_object('value', 1), '$.value')").fetchone()[0] == 1
    def write(offset):
        with closing(sqlite3.connect(path, timeout=15)) as connection:
            connection.executemany('INSERT INTO smoke VALUES (?)', [(offset+i,) for i in range(25)])
            connection.commit()
            connection.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchall()
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write, (0, 25, 50, 75)))
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM smoke').fetchone()[0] == 100
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    print(json.dumps({'passed': True, 'sqlite_version': sqlite3.sqlite_version, 'wal_rows': 100}))
"""


_IMPORT_SMOKE = """
import importlib, json, sys
from pathlib import Path
from PyInstaller.utils.hooks import get_module_file_attribute
assert sys.dont_write_bytecode, 'Source packages must remain read-only'
names = ('win32api', 'win32gui', 'win32process', 'pywintypes', 'pythoncom',
         'win32com', 'PyInstaller', 'PyQt6.QtCore', 'qtawesome',
         'winrt.windows.applicationmodel')
files = {}
for name in names:
    module = importlib.import_module(name)
    discovered = get_module_file_attribute(name)
    assert discovered and Path(discovered).is_file(), name
    files[name] = {'imported_file': module.__file__, 'pyinstaller_file': discovered}
assert sys.dont_write_bytecode
print(json.dumps({'passed': True, 'source_bytecode_writes_disabled': True,
                  'module_files': files}))
"""


def _validate_runtime(directory: Path, lock: dict, pin: dict, inputs: dict) -> dict:
    receipt = _read_json(directory / RECEIPT)
    if receipt.get("inputs") != inputs:
        raise RuntimeError("Private runtime inputs changed; select a new runtime directory")
    expected = {**inputs["standard_runtime_sha256"], "DLLs/sqlite3.dll": pin["dll_sha256"]}
    for relative, expected_hash in expected.items():
        if _sha256(directory / relative) != expected_hash:
            raise RuntimeError(f"Private runtime file changed: {relative}")
    pth = directory / "Lib/site-packages/air_calendar_build_packages.pth"
    if pth.read_text(encoding="utf-8", errors="strict") != _package_pth(
        Path(inputs["source_packages"])
    ):
        raise RuntimeError("Private runtime package link changed")
    python = directory / "python.exe"
    report = _run_json(python, [str(ROOT / "scripts/verify_sqlite_runtime.py"), "--runtime"])
    if (
        report["sqlite_version"] != lock["sqlite_version"]
        or report["sqlite_source_id"] != lock["sqlite_source_id"]
    ):
        raise RuntimeError("Private runtime C exports differ from the pinned SQLite release")
    if report["sqlite_library_sha256"] != pin["dll_sha256"]:
        raise RuntimeError("Python loaded a SQLite DLL outside the pinned private runtime")
    return report


def prepare(directory: Path, architecture: str, *, check_only: bool = False) -> dict:
    lock = _read_json(LOCK)
    pin = _pin(lock, architecture)
    if verifier._host_architecture() != architecture:
        raise RuntimeError("Cross-architecture private runtime preparation is not supported")
    cache_root = directory.resolve()
    inputs, files, packages = _inputs(lock)
    if cache_root.is_relative_to(Path(sys.base_prefix).resolve()) or cache_root.is_relative_to(
        Path(sys.prefix).resolve()
    ):
        raise RuntimeError("Private runtime must be outside the source Python and environment")
    input_id = hashlib.sha256(
        json.dumps(inputs, sort_keys=True).encode("utf-8", errors="strict")
    ).hexdigest()[:24]
    directory = cache_root / input_id
    reused = directory.exists()
    if not reused:
        if check_only:
            raise RuntimeError("Private runtime missing; run prepare_sqlite_build_runtime.py first")
        dll = _download(pin)
        directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="sqlite-runtime-staging-", dir=directory.parent
        ) as staging_name:
            staging = Path(staging_name)
            for source in files:
                target = staging / source.relative_to(sys.base_prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            (staging / "DLLs/sqlite3.dll").write_bytes(dll)
            site = staging / "Lib/site-packages"
            site.mkdir(parents=True, exist_ok=True)
            (site / "air_calendar_build_packages.pth").write_text(
                _package_pth(packages), encoding="utf-8", errors="strict"
            )
            _write_json(
                staging / RECEIPT, {"inputs": inputs, "sqlite": lock, "architecture": architecture}
            )
            _validate_runtime(staging, lock, pin, inputs)
            _run_json(staging / "python.exe", ["-c", _IMPORT_SMOKE])
            _run_json(staging / "python.exe", ["-c", _SMOKE])
            # Publish without replacing any existing environment. A racing
            # preparation can only be reused after the same complete checks.
            try:
                staging.rename(directory)
            except FileExistsError:
                reused = True
            else:
                # TemporaryDirectory must not clean the renamed destination.
                staging.mkdir()
    report = _validate_runtime(directory, lock, pin, inputs)
    imports = _run_json(directory / "python.exe", ["-c", _IMPORT_SMOKE])
    smoke = _run_json(directory / "python.exe", ["-c", _SMOKE])
    return {
        "passed": True,
        "reused": reused,
        "python_executable": str(directory / "python.exe"),
        "receipt_sha256": _sha256(directory / RECEIPT),
        "runtime": report,
        "native_module_imports": imports,
        "synthetic_wal_smoke": smoke,
        "source_environment_modified": False,
        "personal_database_opened": False,
    }


def record_payload(payload: Path, architecture: str) -> dict:
    lock = _read_json(LOCK)
    pin = _pin(lock, architecture)
    report = verifier.verify_payload(payload)
    if (
        report["architecture"] != architecture
        or report["sqlite_version"] != lock["sqlite_version"]
        or report["sqlite_source_id"] != lock["sqlite_source_id"]
        or report["sqlite_library_sha256"] != pin["dll_sha256"]
    ):
        raise RuntimeError("Frozen SQLite DLL differs from the pinned official release")
    # Deliberately exclude local build paths and installed package paths.
    evidence = {
        "sqlite_version": lock["sqlite_version"],
        "sqlite_source_id": lock["sqlite_source_id"],
        "architecture": architecture,
        "native_exports_queried": True,
        "dll_sha256": report["sqlite_library_sha256"],
        "official_archive": pin,
        "source_archive": lock["source_archive"],
        "license": lock["license"],
        "release_notes": lock["release_notes"],
        "c_api_compatibility": lock["c_api_compatibility"],
    }
    _write_json(payload / "SQLITE_RUNTIME.json", evidence)
    return {"passed": True, **evidence}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=("x64", "arm64"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--directory", type=Path)
    mode.add_argument("--payload", type=Path)
    parser.add_argument(
        "--check", action="store_true", help="Check an existing runtime without writing files"
    )
    args = parser.parse_args(argv)
    if args.check and args.payload is not None:
        parser.error("--check applies only to --directory")
    try:
        report = (
            record_payload(args.payload, args.arch)
            if args.payload is not None
            else prepare(args.directory, args.arch, check_only=args.check)
        )
    except (OSError, RuntimeError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
