# -*- coding: utf-8 -*-
"""Incomplete HTTP responses and ambiguous ICS times must preserve cached snapshots."""

from datetime import UTC, datetime
from http.client import HTTPResponse, IncompleteRead
from io import BytesIO
import sqlite3
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.db import database_unified
from calendar_app.infrastructure.ics import ics_fetcher

KEY = "ics::boundary"
URL = "https://example.invalid/boundary.ics?token=synthetic-private-token"


def event(uid="one", start="DTSTART:20261005T100000Z", extra="", name="Original"):
    return f"BEGIN:VEVENT\r\nUID:{uid}\r\n{start}\r\nSUMMARY:{name}\r\n{extra}END:VEVENT\r\n"


def feed(*events):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n").encode(
        "utf-8",
        errors="strict",
    )


class Response(BytesIO):
    def __init__(self, data, *, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


@pytest.fixture
def boundary(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,is_active INTEGER,
          ics_url TEXT,ics_last_fetched TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,type TEXT,
          calendar_id TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,
          description TEXT,location TEXT,gcal_event_id TEXT,
          gcal_source_calendar_id TEXT,gcal_target_calendar_id TEXT,
          gcal_sync_mode TEXT,gcal_dirty INTEGER,status TEXT,created_at TEXT,updated_at TEXT);
        CREATE UNIQUE INDEX remote_identity ON unified_task(
          COALESCE(NULLIF(trim(gcal_source_calendar_id),''),
            NULLIF(trim(gcal_target_calendar_id),''),'primary'),gcal_event_id)
          WHERE gcal_event_id IS NOT NULL AND gcal_event_id != '';
    """)
    conn.execute("INSERT INTO calendar VALUES(?,'ics',1,?,NULL)", (KEY, URL))
    conn.commit()
    monkeypatch.setattr(database_unified.db_manager, "get_connection", lambda: conn)
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))

    def synchronize(data, response=None, **kwargs):
        stream = response or Response(data)
        monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", lambda *args, **kw: stream)
        return ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul", **kwargs)

    yield conn, synchronize
    conn.close()


def state(conn):
    return (
        conn.execute("SELECT * FROM unified_task ORDER BY id").fetchall(),
        conn.execute("SELECT * FROM calendar ORDER BY id").fetchall(),
    )


def cached(boundary):
    conn, synchronize = boundary
    assert synchronize(feed(event(), event("old"))) == (2, 0, None)
    return conn, synchronize, state(conn)


@pytest.mark.parametrize(
    "status,headers",
    [
        (206, {}),
        (200, {"Content-Range": "bytes 0-99/500"}),
    ],
)
def test_partial_http_snapshot_cannot_delete_absent_cached_events(boundary, status, headers):
    conn, synchronize, before = cached(boundary)
    data = feed(event(name="Changed"))
    response = Response(data, status=status, headers=headers)
    assert synchronize(data, response)[2] == "ics_fetch_failed"
    assert state(conn) == before
    assert response.closed


@pytest.mark.parametrize("size_delta", [-1, 1, 200])
def test_declared_length_mismatch_preserves_events_and_last_success(boundary, size_delta):
    conn, synchronize, before = cached(boundary)
    data = feed(event(name="Changed"))
    assert (
        synchronize(data, Response(data, headers={"Content-Length": str(len(data) + size_delta)}))[
            2
        ]
        == "network_unavailable"
    )
    assert state(conn) == before


def test_complete_declared_length_remains_a_valid_snapshot(boundary):
    conn, synchronize, _ = cached(boundary)
    data = feed(event(name="Changed"))
    assert synchronize(data, Response(data, headers={"Content-Length": str(len(data))})) == (
        1,
        1,
        None,
    )
    assert conn.execute("SELECT name FROM unified_task").fetchone() == ("Changed",)


@pytest.mark.parametrize(
    "extra,start",
    [
        ("", "DTSTART;TZID=Unknown/Synthetic:20261005T100000"),
        ("DTEND;TZID=Unknown/Synthetic:20261005T110000\r\n", "DTSTART:20261005T100000"),
        ("RDATE;TZID=Unknown/Synthetic:20261006T100000\r\n", "DTSTART:20261005T100000Z"),
        (
            "EXDATE;TZID=Unknown/Synthetic:20261006T100000\r\nRRULE:FREQ=DAILY;COUNT=3\r\n",
            "DTSTART:20261005T100000Z",
        ),
    ],
)
def test_unresolved_timezone_never_becomes_floating_wall_time(boundary, extra, start):
    conn, synchronize, before = cached(boundary)
    assert synchronize(feed(event(start=start, extra=extra)))[2] == "invalid_calendar_timezone"
    assert state(conn) == before


@pytest.mark.parametrize("extra", ["DTEND:20261005T100000Z\r\n", "DURATION:PT0S\r\n"])
def test_explicit_nonpositive_timed_span_preserves_snapshot(boundary, extra):
    conn, synchronize, before = cached(boundary)
    assert synchronize(feed(event(extra=extra)))[2] == "invalid_event_time"
    assert state(conn) == before


def test_point_in_time_events_without_end_keep_valid_recurring_occurrences(boundary):
    conn, synchronize = boundary
    assert synchronize(feed(event(extra="RRULE:FREQ=DAILY;COUNT=3\r\n"))) == (3, 0, None)
    assert conn.execute("SELECT deadline FROM unified_task ORDER BY deadline").fetchall() == [
        ("2026-10-05 19:00",),
        ("2026-10-06 19:00",),
        ("2026-10-07 19:00",),
    ]


def test_count_and_until_are_rejected_before_expansion(boundary, monkeypatch):
    import recurring_ical_events

    conn, synchronize, before = cached(boundary)
    expand = Mock(side_effect=AssertionError("Ambiguous rule must not be expanded"))
    monkeypatch.setattr(recurring_ical_events, "of", expand)
    assert (
        synchronize(feed(event(extra="RRULE:FREQ=DAILY;COUNT=3;UNTIL=20261010T100000Z\r\n")))[2]
        == "invalid_recurrence"
    )
    expand.assert_not_called()
    assert state(conn) == before


def test_excluded_only_occurrence_is_removed_even_without_rrule(boundary):
    conn, synchronize = boundary
    assert synchronize(feed(event())) == (1, 0, None)
    assert synchronize(feed(event(extra="EXDATE:20261005T100000Z\r\n"))) == (0, 1, None)
    assert not conn.execute("SELECT id FROM unified_task").fetchall()


@pytest.mark.parametrize(
    "rid",
    [
        "RECURRENCE-ID;VALUE=DATE:20261006",
        "RECURRENCE-ID:20261006T100000",
    ],
)
def test_exception_identity_type_matches_master_and_cannot_add_duplicate_occurrence(boundary, rid):
    conn, synchronize, before = cached(boundary)
    data = feed(
        event("series", extra="RRULE:FREQ=DAILY;COUNT=3\r\n"),
        event("series", start="DTSTART:20261006T120000Z", extra=rid + "\r\n"),
    )
    assert synchronize(data)[2] == "invalid_recurrence"
    assert state(conn) == before


def test_same_recurrence_identity_in_utc_and_named_zone_preserves_snapshot(boundary):
    conn, synchronize, before = cached(boundary)
    assert (
        synchronize(
            feed(
                event("series", extra="RRULE:FREQ=DAILY;COUNT=3\r\n"),
                event(
                    "series",
                    start="DTSTART:20261006T120000Z",
                    extra="RECURRENCE-ID:20261006T100000Z\r\n",
                ),
                event(
                    "series",
                    start="DTSTART:20261006T140000Z",
                    extra="RECURRENCE-ID;TZID=Asia/Seoul:20261006T190000\r\n",
                ),
            )
        )[2]
        == "duplicate_remote_event"
    )
    assert state(conn) == before


def test_named_timezone_dst_and_all_day_end_stay_correct(boundary):
    conn, synchronize = boundary
    assert synchronize(
        feed(
            event(
                "timed",
                start="DTSTART;TZID=America/New_York:20261031T100000",
                extra="DTEND;TZID=America/New_York:20261031T110000\r\nRRULE:FREQ=DAILY;COUNT=3\r\n",
            ),
            event(
                "all-day",
                start="DTSTART;VALUE=DATE:20261005",
                extra="DTEND;VALUE=DATE:20261008\r\n",
            ),
        )
    ) == (4, 0, None)
    assert conn.execute(
        "SELECT deadline,end_date,all_day FROM unified_task ORDER BY deadline"
    ).fetchall() == [
        ("2026-10-05", "2026-10-07", 1),
        ("2026-10-31 23:00", "2026-11-01 00:00", 0),
        ("2026-11-02 00:00", "2026-11-02 01:00", 0),
        ("2026-11-03 00:00", "2026-11-03 01:00", 0),
    ]


@pytest.mark.parametrize(
    "data", [b"", b"<html>Sign in</html>", b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"]
)
def test_empty_html_or_truncated_calendar_preserves_full_snapshot(boundary, data):
    conn, synchronize, before = cached(boundary)
    assert synchronize(data)[2] == "invalid_calendar_data"
    assert state(conn) == before


def test_stream_error_after_receiving_a_complete_prefix_preserves_snapshot(
    boundary, monkeypatch, caplog
):
    conn, _, before = cached(boundary)

    class Interrupted(Response):
        def read1(self, size):
            if self.tell():
                raise TimeoutError(URL)
            return super().read1(size)

    stream = Interrupted(feed(event(name="Changed")))
    monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", lambda *args, **kw: stream)
    assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul") == (0, 0, "network_unavailable")
    assert state(conn) == before
    assert stream.closed
    assert "synthetic-private-token" not in caplog.text


@pytest.mark.parametrize(
    "failure", [ConnectionResetError("synthetic"), IncompleteRead(b"synthetic")]
)
def test_network_stream_failures_are_actionable_and_keep_snapshot(boundary, monkeypatch, failure):
    conn, _, before = cached(boundary)

    class Broken(Response):
        def read1(self, size):
            raise failure

    stream = Broken(b"")
    monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", lambda *args, **kw: stream)
    assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul") == (0, 0, "network_unavailable")
    assert state(conn) == before
    assert stream.closed


def wire_response(wire):
    class Socket:
        def makefile(self, mode):
            return BytesIO(wire)

    response = HTTPResponse(Socket())
    response.begin()
    return response


def test_real_http_read1_silent_truncation_cannot_replace_snapshot(boundary):
    conn, synchronize, before = cached(boundary)
    data = feed(event(name="Changed"))
    wire = (
        f"HTTP/1.1 200 OK\r\nContent-Length: {len(data) + 50}\r\n\r\n".encode(
            "utf-8", errors="strict"
        )
        + data
    )
    response = wire_response(wire)
    assert synchronize(data, response)[2] == "network_unavailable"
    assert state(conn) == before


def test_chunked_http_transfer_remains_usable_without_declared_length(boundary):
    conn, synchronize, _ = cached(boundary)
    data = feed(event(name="Changed"))
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + f"{len(data):x}\r\n".encode("utf-8", errors="strict")
        + data
        + b"\r\n0\r\n\r\n"
    )
    assert synchronize(data, wire_response(wire)) == (1, 1, None)
    assert conn.execute("SELECT name FROM unified_task").fetchone() == ("Changed",)


def test_local_owned_identity_collision_cannot_commit_a_partial_snapshot(boundary):
    conn, synchronize, _ = cached(boundary)
    conn.execute("UPDATE unified_task SET gcal_sync_mode='local_owned' WHERE gcal_event_id='one'")
    conn.commit()
    before = state(conn)
    assert synchronize(feed(event(name="Changed")))[2] == "duplicate_remote_event"
    assert state(conn) == before


def test_database_connection_failure_returns_error_without_leaking_private_url(
    boundary, monkeypatch, caplog
):
    conn, synchronize, before = cached(boundary)
    monkeypatch.setattr(
        database_unified.db_manager,
        "get_connection",
        Mock(side_effect=sqlite3.OperationalError(URL)),
    )
    assert synchronize(feed(event(name="Changed")))[2] == "operation_failed"
    assert state(conn) == before
    assert "synthetic-private-token" not in caplog.text
