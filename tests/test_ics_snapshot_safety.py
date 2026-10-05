# -*- coding: utf-8 -*-
"""An ICS feed must be a complete, validated, atomic subscription snapshot."""

from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
import sqlite3
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.db import database_unified
from calendar_app.infrastructure.ics import ics_fetcher

URL = "https://example.invalid/calendar.ics"
KEY = "ics::fixture"


def feed(*events):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n").encode(
        "utf-8", errors="strict"
    )


def event(uid, name="Original", extra="", start="20261005T100000Z"):
    return (
        "BEGIN:VEVENT\r\n"
        + (f"UID:{uid}\r\n" if uid else "")
        + f"DTSTART:{start}\r\nSUMMARY:{name}\r\n{extra}END:VEVENT\r\n"
    )


@pytest.fixture
def snapshot(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,is_active INTEGER,ics_url TEXT,ics_last_fetched TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT CHECK(name != 'FAIL'),type TEXT,
          calendar_id TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,description TEXT,location TEXT,
          gcal_event_id TEXT,gcal_source_calendar_id TEXT,gcal_target_calendar_id TEXT,
          gcal_sync_mode TEXT,gcal_dirty INTEGER,status TEXT,created_at TEXT,updated_at TEXT);
        CREATE UNIQUE INDEX remote_identity ON unified_task(
          COALESCE(NULLIF(trim(gcal_source_calendar_id),''),NULLIF(trim(gcal_target_calendar_id),''),'primary'),
          gcal_event_id) WHERE gcal_event_id IS NOT NULL AND gcal_event_id != '';
    """)
    conn.execute("INSERT INTO calendar VALUES(?,'ics',1,?,NULL)", (KEY, URL))
    conn.commit()
    monkeypatch.setattr(database_unified.db_manager, "get_connection", lambda: conn)

    def sync(data, **kwargs):
        monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", lambda *a, **k: BytesIO(data))
        return ics_fetcher.fetch_and_sync(KEY, URL, local_zone="Asia/Seoul", **kwargs)

    yield conn, sync
    conn.close()


def rows(conn):
    return conn.execute(
        "SELECT gcal_event_id,name FROM unified_task ORDER BY gcal_event_id"
    ).fetchall()


def test_failed_row_rolls_back_updates_and_deletions(snapshot):
    conn, sync = snapshot
    assert sync(feed(event("one"), event("old")))[2] is None
    before = rows(conn)
    fetched = conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()[0]
    assert sync(feed(event("one", "Changed"), event("two", "FAIL")))[2] is not None
    assert rows(conn) == before
    assert conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()[0] == fetched
    assert not conn.in_transaction


def test_valid_empty_calendar_removes_only_its_mirrors(snapshot):
    conn, sync = snapshot
    sync(feed(event("one")))
    conn.execute(
        "INSERT INTO unified_task(name,calendar_id,type) VALUES('Local','local::one','schedule')"
    )
    conn.commit()
    assert sync(feed()) == (0, 1, None)
    assert rows(conn) == [(None, "Local")]


@pytest.mark.parametrize(
    "data",
    [
        feed(event("one", "Changed"), event("", "No UID")),
        feed(event("one", "Changed"), event("two", start="invalid")),
        feed(event("one", "Changed"), event("one", "Duplicate")),
        feed(event("one", "Changed"))[:-15],
        feed(event("one", "Changed"), event("two", extra="DTEND:20261004T100000Z\r\n")),
    ],
)
def test_incomplete_or_ambiguous_feed_preserves_snapshot(snapshot, data):
    conn, sync = snapshot
    sync(feed(event("one"), event("old")))
    before = rows(conn)
    assert sync(data)[2] is not None
    assert rows(conn) == before


def test_inactive_or_changed_subscription_does_not_apply_stale_fetch(snapshot):
    conn, sync = snapshot
    sync(feed(event("one")))
    conn.execute("UPDATE calendar SET is_active=0")
    conn.commit()
    assert sync(feed(event("one", "Changed")))[2] is not None
    assert rows(conn) == [("one", "Original")]


def test_concurrent_cancellation_before_commit_rolls_back(snapshot):
    conn, sync = snapshot
    sync(feed(event("one")))
    conn.execute(
        "CREATE TRIGGER cancellation AFTER UPDATE ON unified_task BEGIN SELECT interrupted(); END"
    )
    cancelled = [False]
    conn.create_function("interrupted", 0, lambda: cancelled.__setitem__(0, True))
    assert sync(feed(event("one", "Changed")), cancelled=lambda: cancelled[0])[2] == "cancelled"
    assert rows(conn) == [("one", "Original")]


def test_feed_size_is_bounded(snapshot, monkeypatch):
    conn, sync = snapshot
    monkeypatch.setattr(ics_fetcher, "MAX_FEED_BYTES", 64, raising=False)
    assert sync(feed(event("one")))[2] == "response_too_large"
    assert rows(conn) == []


def test_recurring_exceptions_have_separate_stable_identities(snapshot, monkeypatch):
    conn, sync = snapshot
    monkeypatch.setattr(
        ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC), raising=False
    )
    data = feed(
        event("series", extra="RRULE:FREQ=DAILY;COUNT=3\r\n"),
        event(
            "series", "Moved", extra="RECURRENCE-ID:20261006T100000Z\r\n", start="20261006T120000Z"
        ),
    )
    assert sync(data)[2] is None
    first = rows(conn)
    assert len(first) == 3
    assert [name for _, name in first].count("Moved") == 1
    assert sync(data)[2] is None
    assert rows(conn) == first


def test_ics_worker_forwards_cancellation_callback(monkeypatch):
    from calendar_app.presentation.main_window.calendar_sync_coordinator import IcsSyncWorker

    calls = Mock(return_value=(0, 0, None))
    monkeypatch.setattr(ics_fetcher, "fetch_and_sync", calls)
    monkeypatch.setattr(database_unified.db_manager, "close_connection", Mock())
    worker = IcsSyncWorker([{"id": KEY, "ics_url": URL}], None, "Asia/Seoul")
    worker.run()
    assert callable(calls.call_args.kwargs.get("cancelled"))


def test_duration_and_excluded_recurring_day_are_preserved(snapshot, monkeypatch):
    conn, sync = snapshot
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    assert (
        sync(
            feed(
                event(
                    "series",
                    extra="RRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20261006T100000Z\r\nDURATION:PT2H\r\n",
                )
            )
        )[2]
        is None
    )
    times = conn.execute("SELECT deadline,end_date FROM unified_task ORDER BY deadline").fetchall()
    assert times == [
        ("2026-10-05 19:00", "2026-10-05 21:00"),
        ("2026-10-07 19:00", "2026-10-07 21:00"),
    ]


def test_dense_recurrence_is_rejected_before_applying(snapshot):
    conn, sync = snapshot
    assert sync(feed(event("series", extra="RRULE:FREQ=SECONDLY\r\n")))[2] == "too_many_events"
    assert rows(conn) == []


def test_cancelled_event_removes_its_existing_mirror(snapshot):
    conn, sync = snapshot
    sync(feed(event("one")))
    assert sync(feed("BEGIN:VEVENT\r\nUID:one\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\n")) == (
        0,
        1,
        None,
    )


def test_changed_subscription_url_does_not_apply_old_feed(snapshot):
    conn, sync = snapshot
    sync(feed(event("one")))
    conn.execute("UPDATE calendar SET ics_url='https://example.invalid/new.ics'")
    conn.commit()
    assert sync(feed(event("one", "Changed")))[2] == "calendar_access_lost"
    assert rows(conn) == [("one", "Original")]


def test_failed_snapshot_preserves_uncommitted_unrelated_work(snapshot):
    conn, sync = snapshot
    conn.execute(
        "INSERT INTO unified_task(name,type,calendar_id) VALUES('Pending local','schedule','local::one')"
    )
    assert sync(feed(event("one"), event("two", "FAIL")))[2] == "operation_failed"
    assert rows(conn) == [(None, "Pending local")]
    assert conn.in_transaction
    conn.rollback()
    assert rows(conn) == []


def test_real_database_schema_accepts_atomic_ics_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(database_unified, "DB_PATH", str(tmp_path / "calendar.db"))
    database_unified.initialize_unified_database()
    conn = database_unified.db_manager.get_connection()
    try:
        conn.execute(
            "INSERT INTO calendar(id,type,name,color,is_active,access_role,ics_url) VALUES(?,'ics','Fixture','#123456',1,'reader',?)",
            (KEY, URL),
        )
        conn.commit()
        monkeypatch.setattr(
            ics_fetcher.urllib.request, "urlopen", lambda *a, **k: BytesIO(feed(event("one")))
        )
        assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul") == (1, 0, None)
        monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", lambda *a, **k: BytesIO(feed()))
        assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul") == (0, 1, None)
    finally:
        database_unified.db_manager.close_connection()
