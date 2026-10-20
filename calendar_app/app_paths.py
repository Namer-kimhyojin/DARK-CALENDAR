# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

APP_VENDOR = "kimhyojin"
APP_NAME = "Dark Calendar"


@contextlib.contextmanager
def _database_error_context(target: Path, source: Path | None = None):
    """Retain the original exception while identifying its database profile."""
    try:
        yield
    except (OSError, sqlite3.Error) as error:
        error.database_path = str(target)
        if source is not None and not getattr(error, "database_source", None):
            error.database_source = str(source)
        raise


def _get_final_windows_path(path: Path) -> Path:
    """Resolve the file actually opened by this process without creating it."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    final_path = kernel32.GetFinalPathNameByHandleW
    final_path.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD)
    final_path.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    # FILE_READ_ATTRIBUTES, share read/write/delete, OPEN_EXISTING. The backup
    # semantics flag permits opening a parent directory with the same read-only API.
    handle = create_file(str(path), 0x80, 0x7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        length = final_path(handle, None, 0, 0)
        if not length:
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            buffer = ctypes.create_unicode_buffer(length + 1)
            written = final_path(handle, buffer, len(buffer), 0)
            if not written:
                raise ctypes.WinError(ctypes.get_last_error())
            if written < len(buffer):
                value = buffer.value
                if value.startswith("\\\\?\\UNC\\"):
                    value = "\\\\" + value[8:]
                elif value.startswith("\\\\?\\"):
                    value = value[4:]
                return Path(value)
            length = written
    finally:
        close_handle(handle)


def resolve_database_path(path: Path) -> Path:
    """Pin SQLite and its WAL/SHM to the existing database's physical profile."""
    path = Path(path)
    with _database_error_context(path):
        path = path.absolute()
        if sys.platform != "win32":
            return path.resolve()
        missing = []
        candidate = path
        while True:
            try:
                resolved = _get_final_windows_path(candidate)
                return resolved.joinpath(*reversed(missing))
            except FileNotFoundError:
                # A new database uses its existing physical parent. Permission and
                # other failures must not silently switch to another AppData profile.
                if candidate == candidate.parent:
                    raise
                missing.append(candidate.name)
                candidate = candidate.parent


def _path_exists(path: Path) -> bool:
    try:
        path.stat()
        return True
    except FileNotFoundError:
        return False


def _copy_database_snapshot(source: Path, target: Path) -> None:
    """Publish a consistent SQLite snapshot without overwriting another profile."""
    with _database_error_context(target, source):
        _copy_database_snapshot_with_context(source, target)


def _copy_database_snapshot_with_context(source: Path, target: Path) -> None:
    if _path_exists(target):
        return
    descriptor, name = tempfile.mkstemp(
        prefix=".calendar-migration-", suffix=".db", dir=target.parent
    )
    os.close(descriptor)
    staging = Path(name)
    deadline = time.monotonic() + 10

    def check_deadline(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise TimeoutError("Database migration could not obtain a consistent snapshot in time")

    try:
        with (
            contextlib.closing(
                sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)
            ) as src,
            contextlib.closing(sqlite3.connect(staging, timeout=10)) as dst,
        ):
            src.backup(dst, pages=256, progress=check_deadline)
            if dst.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise sqlite3.DatabaseError("Migrated database failed its integrity check")
            dst.execute("PRAGMA journal_mode = DELETE")
        # Unlike replace(), linking publishes the completed file atomically and
        # fails if another process created the destination during the snapshot.
        with contextlib.suppress(FileExistsError):
            os.link(staging, target)
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            with contextlib.suppress(OSError):
                Path(str(staging) + suffix).unlink(missing_ok=True)


def get_project_dir() -> Path:
    return Path(__file__).resolve().parent


def get_resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return get_project_dir()


def get_app_data_dir() -> Path:
    base_dir = os.environ.get("LOCALAPPDATA")
    if base_dir:
        app_dir = Path(base_dir) / APP_VENDOR / APP_NAME
    else:
        app_dir = Path.home() / "AppData" / "Local" / APP_VENDOR / APP_NAME
    with _database_error_context(app_dir / "desk_calendar.db"):
        app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_resource_path(*parts: str) -> str:
    # First, check the root project directory (fallback_path)
    # This allows a root app_icon.ico to take precedence over an internal one.
    # Note: get_project_dir() returns calendar_app here, we want the actual root.

    # We define the actual root as the parent of get_project_dir()
    # since get_project_dir() returns the package folder (calendar_app)
    actual_root = get_project_dir().parent
    root_path = actual_root.joinpath(*parts)
    if root_path.exists():
        return str(root_path)

    # Check Assets folder in root
    assets_path = actual_root.joinpath("Assets", *parts)
    if assets_path.exists():
        return str(assets_path)

    resource_path = get_resource_dir().joinpath(*parts)
    if resource_path.exists():
        return str(resource_path)

    # Check Assets folder in calendar_app
    pkg_assets = get_project_dir().joinpath("Assets", *parts)
    if pkg_assets.exists():
        return str(pkg_assets)

    fallback_path = get_project_dir().joinpath(*parts)
    if fallback_path.exists():
        return str(fallback_path)

    return str(resource_path)


def migrate_legacy_runtime_files(database_path: Path | None = None) -> None:
    app_data_dir = get_app_data_dir()
    main_db_path = database_path or resolve_database_path(app_data_dir / "desk_calendar.db")
    runtime_files = (
        "desk_calendar.log",
        "credentials.json",
        "token.json",
    )

    legacy_dirs: list[Path] = []

    # Developer convenience for source runs only.
    # For frozen builds, never migrate from bundled directories.
    if not getattr(sys, "frozen", False):
        legacy_dirs.append(get_project_dir())

    # Migrate from historical app folders (old product names).
    base_dir = os.environ.get("LOCALAPPDATA")
    if base_dir:
        base_path = Path(base_dir) / APP_VENDOR
    else:
        base_path = Path.home() / "AppData" / "Local" / APP_VENDOR
    for legacy_name in ("Desk Calendar",):
        candidate = base_path / legacy_name
        with _database_error_context(main_db_path, candidate / "desk_calendar.db"):
            if _path_exists(candidate):
                legacy_dirs.append(candidate)

    app_data_resolved = app_data_dir.resolve()
    for source_dir in legacy_dirs:
        try:
            if source_dir.resolve() == app_data_resolved:
                continue
        except OSError:
            continue

        legacy_db_path = source_dir / "desk_calendar.db"
        with _database_error_context(main_db_path, legacy_db_path):
            if not _path_exists(main_db_path) and _path_exists(legacy_db_path):
                _copy_database_snapshot(resolve_database_path(legacy_db_path), main_db_path)

        for filename in runtime_files:
            legacy_path = source_dir / filename
            target_path = app_data_dir / filename
            if legacy_path.exists() and not target_path.exists():
                with contextlib.suppress(OSError):
                    shutil.copy2(legacy_path, target_path)

        legacy_locales_dir = source_dir / "locales_user"
        if legacy_locales_dir.is_dir():
            target_locales_dir = app_data_dir / "locales_user"
            try:
                target_locales_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            for legacy_file in legacy_locales_dir.glob("*.json"):
                target_file = target_locales_dir / legacy_file.name
                if not target_file.exists():
                    with contextlib.suppress(OSError):
                        shutil.copy2(legacy_file, target_file)

    # Bundle default DB logic
    default_db_src = get_resource_dir() / "desk_calendar_default.db"
    with _database_error_context(main_db_path, default_db_src):
        if _path_exists(default_db_src) and not _path_exists(main_db_path):
            _copy_database_snapshot(default_db_src, main_db_path)


_APP_DATA_DIR = get_app_data_dir()
DB_PATH = str(resolve_database_path(_APP_DATA_DIR / "desk_calendar.db"))
migrate_legacy_runtime_files(Path(DB_PATH))

APP_DATA_DIR = str(_APP_DATA_DIR)
LOG_PATH = str(_APP_DATA_DIR / "desk_calendar.log")
CREDENTIALS_PATH = str(_APP_DATA_DIR / "credentials.json")
TOKEN_PATH = str(_APP_DATA_DIR / "token.json")
APP_ICON_PATH = get_resource_path("app_icon.ico")
APP_ICON_TOAST_PATH = get_resource_path("app_icon.png")
DEFAULT_PRESETS_PATH = get_resource_path("default_presets.json")
