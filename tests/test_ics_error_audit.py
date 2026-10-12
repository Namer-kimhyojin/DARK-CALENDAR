# -*- coding: utf-8 -*-
"""Concrete ICS error regressions use synthetic feeds and an isolated database."""

from datetime import UTC, datetime
from io import BytesIO
import sqlite3
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.db import database_unified
from calendar_app.infrastructure.ics import ics_fetcher

KEY = "ics::error-audit"
URL = "https://example.invalid/audit.ics?key=synthetic-private-key"


def _feed(rule=None, name="Fixture"):
    recurrence = f"RRULE:{rule}\r\n" if rule else ""
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
        "UID:fixture\r\nDTSTART:20261005T100000Z\r\n"
        f"SUMMARY:{name}\r\n{recurrence}END:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode("utf-8", errors="strict")


@pytest.fixture
def isolated_subscription(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,is_active INTEGER,
          ics_url TEXT,ics_last_fetched TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,type TEXT,
          calendar_id TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,
          description TEXT,location TEXT,gcal_event_id TEXT,
          gcal_source_calendar_id TEXT,gcal_target_calendar_id TEXT,
          gcal_sync_mode TEXT,gcal_dirty INTEGER,status TEXT,
          created_at TEXT,updated_at TEXT);
        CREATE UNIQUE INDEX remote_identity ON unified_task(
          COALESCE(NULLIF(trim(gcal_source_calendar_id),''),
            NULLIF(trim(gcal_target_calendar_id),''),'primary'),gcal_event_id)
          WHERE gcal_event_id IS NOT NULL AND gcal_event_id != '';
    """)
    conn.execute("INSERT INTO calendar VALUES(?,'ics',1,?,NULL)", (KEY, URL))
    conn.commit()
    monkeypatch.setattr(database_unified.db_manager, "get_connection", lambda: conn)
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))

    def synchronize(data):
        monkeypatch.setattr(
            ics_fetcher.urllib.request, "urlopen", lambda *args, **kwargs: BytesIO(data)
        )
        return ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul")

    yield conn, synchronize
    conn.close()


@pytest.mark.parametrize(
    "rule",
    [
        "FREQ=HOURLY;BYHOUR=10",
        "FREQ=MINUTELY;BYHOUR=10;BYMINUTE=0",
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0",
    ],
)
def test_filtered_frequent_recurrence_does_not_report_too_many_events(isolated_subscription, rule):
    conn, synchronize = isolated_subscription
    assert synchronize(_feed(rule))[2] is None
    count = conn.execute("SELECT COUNT(*) FROM unified_task").fetchone()[0]
    assert 390 <= count <= 403


@pytest.mark.parametrize("count", [0, -1])
def test_nonpositive_recurrence_count_is_rejected_without_replacing_cached_events(
    isolated_subscription, count
):
    conn, synchronize = isolated_subscription
    assert synchronize(_feed())[2] is None
    before = conn.execute("SELECT id,name FROM unified_task").fetchall()
    fetched = conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()[0]
    assert synchronize(_feed(f"FREQ=DAILY;COUNT={count}", "Malformed"))[2] == "invalid_recurrence"
    assert conn.execute("SELECT id,name FROM unified_task").fetchall() == before
    assert conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()[0] == fetched


def test_aligned_filter_and_interval_reject_dense_expansion_before_library(
    isolated_subscription, monkeypatch
):
    import recurring_ical_events

    conn, synchronize = isolated_subscription
    assert synchronize(_feed())[2] is None
    before = conn.execute("SELECT id,name FROM unified_task").fetchall()
    expansion = Mock(side_effect=AssertionError("Dense series must not be expanded"))
    monkeypatch.setattr(recurring_ical_events, "of", expansion)
    minutes = ",".join(str(value) for value in range(60))
    rule = f"FREQ=HOURLY;INTERVAL=24;BYHOUR=10;BYMINUTE={minutes}"
    assert synchronize(_feed(rule))[2] == "too_many_events"
    expansion.assert_not_called()
    assert conn.execute("SELECT id,name FROM unified_task").fetchall() == before


@pytest.mark.parametrize("stage", ["open", "read"])
def test_socket_timeout_is_network_failure_and_preserves_snapshot(
    isolated_subscription, monkeypatch, caplog, stage
):
    conn, synchronize = isolated_subscription
    assert synchronize(_feed())[2] is None
    before = conn.execute("SELECT id,name FROM unified_task").fetchall()
    fetched = conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()[0]
    failure = TimeoutError("timed out " + URL)
    if stage == "open":
        monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", Mock(side_effect=failure))
    else:

        class TimedOutResponse(BytesIO):
            def read1(self, _size):
                raise failure

        monkeypatch.setattr(
            ics_fetcher.urllib.request, "urlopen", lambda *args, **kwargs: TimedOutResponse()
        )
    assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul") == (0, 0, "network_unavailable")
    assert conn.execute("SELECT id,name FROM unified_task").fetchall() == before
    assert conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()[0] == fetched
    assert "synthetic-private-key" not in caplog.text
