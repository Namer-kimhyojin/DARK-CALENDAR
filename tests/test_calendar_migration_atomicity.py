# -*- coding: utf-8 -*-
"""Legacy calendar migration must be retryable without committing caller data."""

import sqlite3

import pytest

from calendar_app.infrastructure.db import calendar_repo


@pytest.fixture(params=["", None], ids=["implicit_transactions", "autocommit"])
def migration_db(request, monkeypatch):
    conn = sqlite3.connect(":memory:", isolation_level=request.param)
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY, type TEXT, name TEXT, color TEXT,
          is_default INTEGER, is_active INTEGER, is_visible INTEGER, gcal_calendar_id TEXT,
          sort_order INTEGER, access_role TEXT);
        CREATE TABLE gcal_subscription(calendar_id TEXT PRIMARY KEY, summary TEXT,
          is_primary INTEGER, is_active INTEGER, access_role TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY, name TEXT, calendar_id TEXT,
          gcal_source_calendar_id TEXT);
        CREATE TABLE unrelated(id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO gcal_subscription VALUES('first@example.invalid','First',1,1,'owner');
        INSERT INTO gcal_subscription VALUES('second@example.invalid','Second',0,1,'reader');
        INSERT INTO unified_task VALUES(1,'Remote',NULL,'second@example.invalid');
        INSERT INTO unified_task VALUES(2,'Local',NULL,NULL);
        INSERT INTO unified_task VALUES(3,'Assigned','local::custom',NULL);
    """)
    monkeypatch.setattr(calendar_repo.db_manager, "get_connection", lambda: conn)
    yield conn
    conn.close()


def block_insert(conn):
    conn.executescript("""
        CREATE TRIGGER fail_second BEFORE INSERT ON calendar
        WHEN NEW.gcal_calendar_id = 'second@example.invalid'
        BEGIN SELECT RAISE(ABORT, 'simulated migration failure'); END;
    """)


def test_success_preserves_legacy_rows_explicit_assignments_and_alias(migration_db):
    conn = migration_db
    assert calendar_repo.migrate_from_gcal_subscription()
    assert not conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM gcal_subscription").fetchone()[0] == 2
    assert conn.execute("SELECT calendar_id FROM unified_task ORDER BY id").fetchall() == [
        ("gcal::second@example.invalid",),
        ("gcal::first@example.invalid",),
        ("local::custom",),
    ]
    assert conn.execute("SELECT COUNT(*) FROM calendar WHERE id='gcal::primary'").fetchone()[0] == 0
    assert (
        conn.execute(
            "SELECT access_role FROM calendar WHERE id='gcal::second@example.invalid'"
        ).fetchone()[0]
        == "reader"
    )


def test_failed_insert_leaves_no_partial_migration_and_can_retry_after_next_write(migration_db):
    conn = migration_db
    block_insert(conn)
    assert not calendar_repo.migrate_from_gcal_subscription()
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 0
    assert not conn.in_transaction
    assert conn.execute("SELECT calendar_id FROM unified_task WHERE id=1").fetchone()[0] is None
    conn.execute("INSERT INTO unrelated VALUES(1, 'Keep')")
    conn.commit()
    conn.execute("DROP TRIGGER fail_second")
    assert calendar_repo.migrate_from_gcal_subscription()
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM gcal_subscription").fetchone()[0] == 2


def test_task_assignment_failure_rolls_back_calendar_and_prior_task_updates(migration_db):
    conn = migration_db
    conn.executescript("""
        CREATE TRIGGER fail_local BEFORE UPDATE OF calendar_id ON unified_task
        WHEN NEW.id = 2 BEGIN SELECT RAISE(ABORT, 'simulated task failure'); END;
    """)
    assert not calendar_repo.migrate_from_gcal_subscription()
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 0
    assert conn.execute("SELECT calendar_id FROM unified_task ORDER BY id").fetchall() == [
        (None,),
        (None,),
        ("local::custom",),
    ]
    assert not conn.in_transaction


def test_failure_keeps_unrelated_pending_transaction(migration_db):
    conn = migration_db
    block_insert(conn)
    conn.execute("BEGIN")
    conn.execute("INSERT INTO unrelated VALUES(1, 'Pending')")
    assert not calendar_repo.migrate_from_gcal_subscription()
    assert conn.in_transaction
    assert conn.execute("SELECT name FROM unrelated").fetchall() == [("Pending",)]
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 0
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM unrelated").fetchone()[0] == 0


def test_success_keeps_caller_in_charge_of_outer_commit(migration_db):
    conn = migration_db
    conn.execute("BEGIN")
    conn.execute("INSERT INTO unrelated VALUES(1, 'Pending')")
    assert calendar_repo.migrate_from_gcal_subscription()
    assert conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 2
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM unrelated").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 0
    assert conn.execute("SELECT calendar_id FROM unified_task WHERE id=1").fetchone()[0] is None


def test_existing_calendar_is_not_overwritten_or_committed(migration_db):
    conn = migration_db
    conn.execute("BEGIN")
    conn.execute("INSERT INTO calendar(id,type,name) VALUES('local::mine','local','Mine')")
    assert calendar_repo.migrate_from_gcal_subscription()
    assert conn.in_transaction
    assert conn.execute("SELECT id FROM calendar").fetchall() == [("local::mine",)]
    assert conn.execute("SELECT calendar_id FROM unified_task WHERE id=1").fetchone()[0] is None
    conn.rollback()


def test_schema_read_failure_returns_failure_without_an_open_transaction(migration_db):
    conn = migration_db
    conn.execute("DROP TABLE calendar")
    assert not calendar_repo.migrate_from_gcal_subscription()
    assert not conn.in_transaction


def test_settings_failure_returns_failure_without_writes(migration_db):
    class BrokenSettings:
        def value(self, *args):
            raise ValueError("simulated corrupt preference")

    conn = migration_db
    assert not calendar_repo.migrate_from_gcal_subscription(BrokenSettings())
    assert not conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM calendar").fetchone()[0] == 0


def test_empty_subscription_creates_local_default(migration_db):
    conn = migration_db
    conn.execute("DELETE FROM gcal_subscription")
    conn.execute("UPDATE unified_task SET gcal_source_calendar_id=NULL")
    conn.commit()
    assert calendar_repo.migrate_from_gcal_subscription()
    assert conn.execute("SELECT id,type,is_default FROM calendar").fetchall() == [
        ("local::기본", "local", 1)
    ]
    assert conn.execute("SELECT calendar_id FROM unified_task ORDER BY id").fetchall() == [
        ("local::기본",),
        ("local::기본",),
        ("local::custom",),
    ]


def test_unavailable_database_returns_failure(monkeypatch):
    monkeypatch.setattr(calendar_repo.db_manager, "get_connection", lambda: None)
    assert not calendar_repo.migrate_from_gcal_subscription()
