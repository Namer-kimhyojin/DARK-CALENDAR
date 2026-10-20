# -*- coding: utf-8 -*-
"""Failed SQLite setup must release new connections without touching personal data."""

import importlib.util
import logging
import logging.handlers
from pathlib import Path
import sqlite3
import sys
from types import ModuleType

import pytest


@pytest.fixture
def database_module(tmp_path, monkeypatch):
    # Import the actual module against temporary paths, avoiding app_paths'
    # runtime migration and personal log handlers even during test collection.
    paths = ModuleType("calendar_app.app_paths")
    paths.DB_PATH = str(tmp_path / "database.sqlite")
    paths.LOG_PATH = str(tmp_path / "database.log")
    source = (
        Path(__file__).resolve().parents[1] / "calendar_app/infrastructure/db/database_unified.py"
    )
    spec = importlib.util.spec_from_file_location("_db_connection_initialization_test", source)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as isolated_import:
        isolated_import.setitem(sys.modules, "calendar_app.app_paths", paths)
        isolated_import.setattr(logging, "basicConfig", lambda **kwargs: None)
        isolated_import.setattr(
            logging.handlers, "RotatingFileHandler", lambda *args, **kwargs: logging.NullHandler()
        )
        spec.loader.exec_module(module)
    yield module
    module.db_manager.close_all_connections()


class TrackedConnection(sqlite3.Connection):
    fail_sql = None
    fail_close = False
    close_calls = 0

    def execute(self, sql, parameters=()):
        if sql == self.fail_sql:
            raise sqlite3.DatabaseError("database disk image is malformed")
        return super().execute(sql, parameters)

    def close(self):
        self.close_calls += 1
        super().close()
        if self.fail_close:
            raise sqlite3.OperationalError("secondary close failure")


@pytest.fixture
def tracked_connections(database_module, monkeypatch):
    real_connect = sqlite3.connect
    connections = []

    def install(*, fail_sql=None, fail_close=False, first_only=False):
        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs, factory=TrackedConnection)
            conn.fail_sql = fail_sql if not first_only or not connections else None
            conn.fail_close = fail_close
            connections.append(conn)
            return conn

        monkeypatch.setattr(database_module.sqlite3, "connect", connect)
        return connections

    yield install
    for conn in connections:
        sqlite3.Connection.close(conn)


@pytest.mark.parametrize(
    "fail_sql",
    [
        "PRAGMA busy_timeout = 10000",
        "PRAGMA foreign_keys = ON",
        "PRAGMA journal_mode = WAL",
        "PRAGMA synchronous = NORMAL",
    ],
)
@pytest.mark.parametrize("fail_close", [False, True])
def test_failed_setup_closes_connection_and_preserves_original_error(
    database_module, tracked_connections, caplog, fail_sql, fail_close
):
    connections = tracked_connections(fail_sql=fail_sql, fail_close=fail_close)
    manager = database_module.db_manager

    with caplog.at_level(logging.ERROR, logger="Database"):
        assert manager.get_connection() is None

    assert len(connections) == 1
    assert connections[0].close_calls == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].cursor()
    assert manager._connections == {}
    assert "Failed to connect to database: database disk image is malformed" in caplog.text
    assert "secondary close failure" not in caplog.text
    manager.close_all_connections()
    assert connections[0].close_calls == 1


def test_healthy_connection_is_configured_reused_and_persists_data(
    database_module, tracked_connections
):
    connections = tracked_connections()
    manager = database_module.db_manager
    first = manager.get_connection()
    assert first is not None
    first.execute("CREATE TABLE example(value TEXT)")
    first.execute("INSERT INTO example VALUES('retained')")
    first.commit()
    first.close()

    second = manager.get_connection()
    assert second._conn is first._conn
    assert len(connections) == 1
    assert connections[0].close_calls == 0
    assert second.execute("SELECT value FROM example").fetchone()["value"] == "retained"
    for pragma, expected in (
        ("busy_timeout", 10000),
        ("foreign_keys", 1),
        ("journal_mode", "wal"),
        ("synchronous", 1),
    ):
        assert second.execute(f"PRAGMA {pragma}").fetchone()[0] == expected

    manager.close_all_connections()
    assert connections[0].close_calls == 1
    third = manager.get_connection()
    assert len(connections) == 2
    assert third.execute("SELECT value FROM example").fetchone()["value"] == "retained"


def test_failed_setup_can_retry_with_a_fresh_connection(database_module, tracked_connections):
    connections = tracked_connections(fail_sql="PRAGMA journal_mode = WAL", first_only=True)
    manager = database_module.db_manager
    assert manager.get_connection() is None
    assert manager._connections == {}
    assert connections[0].close_calls == 1

    connection = manager.get_connection()
    assert connection is not None
    assert len(connections) == 2
    assert connection._conn is connections[1]
    connection.execute("CREATE TABLE retry_succeeded(id INTEGER)")
    connection.commit()


def test_connect_failure_preserves_error_without_caching(database_module, monkeypatch, caplog):
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(database_module.sqlite3, "connect", unavailable)
    with caplog.at_level(logging.ERROR, logger="Database"):
        assert database_module.db_manager.get_connection() is None
    assert database_module.db_manager._connections == {}
    assert "Failed to connect to database: unable to open database file" in caplog.text


@pytest.mark.parametrize("fail_close", [False, True])
def test_startup_opt_in_propagates_sqlite_failure_after_cleanup(
    database_module, tracked_connections, fail_close
):
    connections = tracked_connections(fail_sql="PRAGMA journal_mode = WAL", fail_close=fail_close)
    with pytest.raises(sqlite3.DatabaseError, match="database disk image is malformed"):
        database_module.initialize_unified_database(raise_on_error=True)
    assert connections[0].close_calls == 1
    assert database_module.db_manager._connections == {}


@pytest.mark.parametrize("raise_on_error", [False, True])
def test_corrupt_database_is_preserved_without_silent_reset(database_module, raise_on_error):
    original = b"A damaged original database which must remain available for recovery"
    path = Path(database_module.DB_PATH)
    path.write_bytes(original)
    if raise_on_error:
        with pytest.raises(sqlite3.DatabaseError) as failure:
            database_module.initialize_unified_database(raise_on_error=True)
        assert failure.value.sqlite_errorcode in (sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_CORRUPT)
    else:
        assert database_module.initialize_unified_database() is False
    assert path.read_bytes() == original
    assert database_module.db_manager._connections == {}
