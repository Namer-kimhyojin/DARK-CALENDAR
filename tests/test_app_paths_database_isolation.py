# -*- coding: utf-8 -*-
"""Physical SQLite paths and first-run migration preserve existing profiles."""

from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def paths_module(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    resources = tmp_path / "resources"
    resources.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(resources), raising=False)
    source = Path(__file__).resolve().parents[1] / "calendar_app/app_paths.py"
    spec = importlib.util.spec_from_file_location("_isolated_app_paths", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_database(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE example(value TEXT)")
        conn.execute("INSERT INTO example VALUES(?)", (value,))
        conn.commit()


def test_existing_main_uses_physical_profile_for_actual_sqlite_sidecars(
    paths_module, tmp_path, monkeypatch
):
    logical = tmp_path / "logical" / "desk_calendar.db"
    physical = tmp_path / "package-cache" / "desk_calendar.db"
    create_database(logical, "desktop data")
    create_database(physical, "store data")
    desktop_bytes = logical.read_bytes()
    calls = []

    def resolve(path):
        calls.append(path)
        assert path == logical
        return physical

    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    monkeypatch.setattr(paths_module, "_get_final_windows_path", resolve)
    result = paths_module.resolve_database_path(logical)
    assert result == physical
    assert calls == [logical]
    with closing(sqlite3.connect(result)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO example VALUES('new store data')")
        conn.commit()
        assert Path(str(physical) + "-wal").exists()
        assert Path(str(physical) + "-shm").exists()
        assert not Path(str(logical) + "-wal").exists()
        assert not Path(str(logical) + "-shm").exists()
    assert logical.read_bytes() == desktop_bytes


def test_missing_main_is_pinned_to_existing_physical_parent(paths_module, tmp_path, monkeypatch):
    logical = tmp_path / "logical" / "desk_calendar.db"
    physical_parent = tmp_path / "package-cache"
    calls = []

    def resolve(path):
        calls.append(path)
        if path == logical:
            raise FileNotFoundError(str(path))
        assert path == logical.parent
        return physical_parent

    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    monkeypatch.setattr(paths_module, "_get_final_windows_path", resolve)
    assert paths_module.resolve_database_path(logical) == physical_parent / logical.name
    assert calls == [logical, logical.parent]


def test_missing_nested_parent_preserves_suffix_in_physical_profile(
    paths_module, tmp_path, monkeypatch
):
    logical = tmp_path / "logical" / "new" / "desk_calendar.db"
    physical_parent = tmp_path / "package-cache"

    def resolve(path):
        if path in (logical, logical.parent):
            raise FileNotFoundError(str(path))
        assert path == logical.parent.parent
        return physical_parent

    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    monkeypatch.setattr(paths_module, "_get_final_windows_path", resolve)
    assert paths_module.resolve_database_path(logical) == physical_parent / "new" / logical.name


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("device failure")])
def test_path_resolution_does_not_fallback_on_non_missing_errors(
    paths_module, tmp_path, monkeypatch, error
):
    calls = []

    def fail(path):
        calls.append(path)
        raise error

    logical = tmp_path / "logical" / "desk_calendar.db"
    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    monkeypatch.setattr(paths_module, "_get_final_windows_path", fail)
    with pytest.raises(type(error), match=str(error)) as failure:
        paths_module.resolve_database_path(logical)
    assert calls == [logical]
    assert failure.value is error
    assert error.database_path == str(logical)


class NativeFunction:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


@pytest.mark.parametrize(
    "native, expected",
    [
        (r"\\?\C:\Fixture\PackageCache\calendar.db", r"C:\Fixture\PackageCache\calendar.db"),
        (r"\\?\UNC\server\profile\calendar.db", r"\\server\profile\calendar.db"),
    ],
)
def test_windows_handle_probe_is_read_only_and_always_closes(
    paths_module, monkeypatch, native, expected
):
    opened, closed = [], []

    def create_file(*args):
        opened.append(args)
        return 123

    def get_final(handle, buffer, size, flags):
        assert handle == 123 and flags == 0
        if buffer is None:
            return len(native) + 1
        buffer.value = native
        return len(native)

    kernel = SimpleNamespace(
        CreateFileW=NativeFunction(create_file),
        GetFinalPathNameByHandleW=NativeFunction(get_final),
        CloseHandle=NativeFunction(lambda handle: closed.append(handle) or 1),
    )
    monkeypatch.setattr(
        paths_module.ctypes, "WinDLL", lambda *args, **kwargs: kernel, raising=False
    )
    assert str(paths_module._get_final_windows_path(Path("calendar.db"))) == expected
    assert opened[0][1:] == (0x80, 0x7, None, 3, 0x02000000, None)
    assert closed == [123]


def test_windows_final_name_failure_still_closes_handle(paths_module, monkeypatch):
    closed = []
    kernel = SimpleNamespace(
        CreateFileW=NativeFunction(lambda *args: 123),
        GetFinalPathNameByHandleW=NativeFunction(lambda *args: 0),
        CloseHandle=NativeFunction(lambda handle: closed.append(handle) or 1),
    )
    monkeypatch.setattr(
        paths_module.ctypes, "WinDLL", lambda *args, **kwargs: kernel, raising=False
    )
    monkeypatch.setattr(paths_module.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(
        paths_module.ctypes, "WinError", lambda code: PermissionError("denied"), raising=False
    )
    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    target = Path(paths_module.DB_PATH)
    with pytest.raises(PermissionError, match="denied") as failure:
        paths_module.resolve_database_path(target)
    assert closed == [123]
    assert failure.value.database_path == str(target)


def test_existing_database_never_receives_legacy_sidecars(paths_module, monkeypatch):
    target = Path(paths_module.DB_PATH)
    create_database(target, "current profile")
    original = target.read_bytes()
    legacy = paths_module.get_app_data_dir().parent / "Desk Calendar"
    legacy.mkdir()
    (legacy / "desk_calendar.db").write_bytes(b"old database")
    (legacy / "desk_calendar.db-wal").write_bytes(b"unrelated old WAL")
    (legacy / "desk_calendar.db-shm").write_bytes(b"unrelated old SHM")
    monkeypatch.setattr(
        paths_module, "_copy_database_snapshot", lambda *args: pytest.fail("Existing DB replaced")
    )

    paths_module.migrate_legacy_runtime_files(target)

    assert target.read_bytes() == original
    assert not Path(str(target) + "-wal").exists()
    assert not Path(str(target) + "-shm").exists()


def test_new_legacy_migration_includes_committed_wal_without_raw_sidecar_copy(paths_module):
    target = Path(paths_module.DB_PATH)
    legacy = paths_module.get_app_data_dir().parent / "Desk Calendar"
    legacy.mkdir()
    source = legacy / "desk_calendar.db"
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("CREATE TABLE example(value TEXT)")
        conn.execute("INSERT INTO example VALUES('committed in source WAL')")
        conn.commit()
        original_main = source.read_bytes()
        original_wal = Path(str(source) + "-wal").read_bytes()

        paths_module.migrate_legacy_runtime_files(target)

        assert source.read_bytes() == original_main
        assert Path(str(source) + "-wal").read_bytes() == original_wal
        with closing(sqlite3.connect(target)) as migrated:
            assert migrated.execute("SELECT value FROM example").fetchall() == [
                ("committed in source WAL",)
            ]
            assert migrated.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert not Path(str(target) + "-wal").exists()
    assert not Path(str(target) + "-shm").exists()
    assert not list(target.parent.glob(".calendar-migration-*"))


def test_corrupt_legacy_database_is_preserved_without_default_replacement(paths_module):
    target = Path(paths_module.DB_PATH)
    legacy = paths_module.get_app_data_dir().parent / "Desk Calendar"
    legacy.mkdir()
    source = legacy / "desk_calendar.db"
    source.write_bytes(b"corrupt legacy fixture")
    original = source.read_bytes()
    create_database(paths_module.get_resource_dir() / "desk_calendar_default.db", "empty default")

    with pytest.raises(sqlite3.DatabaseError) as failure:
        paths_module.migrate_legacy_runtime_files(target)

    assert source.read_bytes() == original
    assert failure.value.database_path == str(target)
    assert failure.value.database_source == str(source)
    assert failure.value.sqlite_errorcode == sqlite3.SQLITE_NOTADB
    assert not target.exists()
    assert not list(target.parent.glob(".calendar-migration-*"))


def test_legacy_permission_error_is_preserved_without_default_replacement(
    paths_module, monkeypatch
):
    target = Path(paths_module.DB_PATH)
    legacy = paths_module.get_app_data_dir().parent / "Desk Calendar"
    legacy.mkdir()
    source = legacy / "desk_calendar.db"
    create_database(source, "protected legacy data")
    original = source.read_bytes()
    create_database(paths_module.get_resource_dir() / "desk_calendar_default.db", "empty default")

    error = PermissionError("source access denied")

    def denied(*args, **kwargs):
        raise error

    monkeypatch.setattr(paths_module.sqlite3, "connect", denied)
    with pytest.raises(PermissionError, match="source access denied") as failure:
        paths_module.migrate_legacy_runtime_files(target)
    assert failure.value is error
    assert error.database_path == str(target)
    assert error.database_source == str(source)
    assert source.read_bytes() == original
    assert not target.exists()
    assert not list(target.parent.glob(".calendar-migration-*"))


def test_snapshot_publication_does_not_overwrite_a_concurrent_destination(
    paths_module, tmp_path, monkeypatch
):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    create_database(source, "legacy")
    real_link = paths_module.os.link

    def competing_link(staging, destination):
        create_database(destination, "concurrent profile")
        real_link(staging, destination)

    monkeypatch.setattr(paths_module.os, "link", competing_link)
    paths_module._copy_database_snapshot(source, target)

    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT value FROM example").fetchall() == [("concurrent profile",)]
    assert not list(target.parent.glob(".calendar-migration-*"))


def test_first_run_default_snapshot_does_not_reset_an_existing_database(paths_module):
    target = Path(paths_module.DB_PATH)
    default = paths_module.get_resource_dir() / "desk_calendar_default.db"
    create_database(default, "bundled default")
    paths_module.migrate_legacy_runtime_files(target)
    with closing(sqlite3.connect(target)) as conn:
        conn.execute("UPDATE example SET value='user data'")
        conn.commit()
    original = target.read_bytes()

    paths_module.migrate_legacy_runtime_files(target)

    assert target.read_bytes() == original
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT value FROM example").fetchall() == [("user data",)]


def test_app_data_directory_failure_identifies_its_database(paths_module, monkeypatch):
    app_dir = paths_module.get_app_data_dir()
    original_mkdir = Path.mkdir
    error = PermissionError("directory denied")

    def denied(path, *args, **kwargs):
        if path == app_dir:
            raise error
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(PermissionError, match="directory denied") as failure:
        paths_module.get_app_data_dir()

    assert failure.value is error
    assert error.database_path == str(app_dir / "desk_calendar.db")
    assert not hasattr(error, "database_source")


@pytest.mark.parametrize("stage", ["stat", "mkstemp"])
def test_snapshot_preparation_errors_keep_original_exception_and_both_paths(
    paths_module, tmp_path, monkeypatch, stage
):
    source, target = tmp_path / "source.db", tmp_path / "destination.db"
    source.write_bytes(b"preserved source")
    error = PermissionError("snapshot preparation denied")

    def denied(*args, **kwargs):
        raise error

    if stage == "stat":
        monkeypatch.setattr(paths_module, "_path_exists", denied)
    else:
        monkeypatch.setattr(paths_module.tempfile, "mkstemp", denied)

    with pytest.raises(PermissionError, match="snapshot preparation denied") as failure:
        paths_module._copy_database_snapshot(source, target)

    assert failure.value is error
    assert error.database_path == str(target)
    assert error.database_source == str(source)
    assert source.read_bytes() == b"preserved source"
    assert not target.exists()
    assert not list(tmp_path.glob(".calendar-migration-*"))


def test_backup_error_keeps_sqlite_identity_code_and_both_paths(
    paths_module, tmp_path, monkeypatch
):
    source, target = tmp_path / "source.db", tmp_path / "destination.db"
    create_database(source, "original")
    original = source.read_bytes()
    real_connect = sqlite3.connect
    error = sqlite3.DatabaseError("original backup failure")
    error.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    error.sqlite_errorname = "SQLITE_CORRUPT"

    class FailedBackup(sqlite3.Connection):
        def backup(self, *args, **kwargs):
            raise error

    def connect(database, *args, **kwargs):
        if database == source.as_uri() + "?mode=ro":
            kwargs["factory"] = FailedBackup
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(paths_module.sqlite3, "connect", connect)
    with pytest.raises(sqlite3.DatabaseError, match="original backup failure") as failure:
        paths_module._copy_database_snapshot(source, target)

    assert failure.value is error
    assert error.sqlite_errorcode == sqlite3.SQLITE_CORRUPT
    assert error.sqlite_errorname == "SQLITE_CORRUPT"
    assert error.database_path == str(target)
    assert error.database_source == str(source)
    assert source.read_bytes() == original
    assert not target.exists()
    assert not list(tmp_path.glob(".calendar-migration-*"))


def test_legacy_source_resolution_failure_reports_target_and_source(paths_module, monkeypatch):
    target = Path(paths_module.DB_PATH)
    legacy = paths_module.get_app_data_dir().parent / "Desk Calendar"
    legacy.mkdir()
    source = legacy / "desk_calendar.db"
    create_database(source, "legacy data")
    original = source.read_bytes()
    error = PermissionError("source resolution denied")

    def denied(path):
        assert path == source
        raise error

    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    monkeypatch.setattr(paths_module, "_get_final_windows_path", denied)
    with pytest.raises(PermissionError, match="source resolution denied") as failure:
        paths_module.migrate_legacy_runtime_files(target)

    assert failure.value is error
    assert error.database_path == str(target)
    assert error.database_source == str(source)
    assert source.read_bytes() == original
    assert not target.exists()
