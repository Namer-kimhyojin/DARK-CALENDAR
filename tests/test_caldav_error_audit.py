# -*- coding: utf-8 -*-
"""CalDAV recurrence validation preserves complete cache snapshots on failure."""

from datetime import UTC, datetime, timedelta
import sqlite3
from unittest.mock import Mock

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.caldav_sync import conversion
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.resource_cache import CalDAVResourceCache
from tests.test_caldav_sync import BASE, HREF, ICS, Response, Session, multi, xml_row

NOW = datetime(2026, 10, 5, tzinfo=UTC)
START, END = NOW - timedelta(days=120), NOW + timedelta(days=400)
COLLECTION = BASE + "calendar/"


def _recurring(rule):
    return ICS.replace("SUMMARY:Meeting", "RRULE:" + rule + "\r\nSUMMARY:Meeting")


@pytest.mark.parametrize(
    "rule",
    [
        "FREQ=HOURLY;INTERVAL=24;BYHOUR=1",
        "FREQ=HOURLY;BYHOUR=1",
        "FREQ=MINUTELY;BYHOUR=1;BYMINUTE=0",
        "FREQ=SECONDLY;BYHOUR=1;BYMINUTE=0;BYSECOND=0",
    ],
)
def test_sparse_filtered_series_retains_stable_read_only_occurrences(rule):
    first = conversion.records(HREF, "fixture-etag", _recurring(rule), START, END)
    assert 390 <= len(first) <= 403
    assert len({event["id"] for event in first}) == len(first)
    assert all(event["read_only"] for event in first)
    assert first == conversion.records(HREF, "fixture-etag", _recurring(rule), START, END)


@pytest.mark.parametrize(
    "rule",
    [
        "FREQ=DAILY;COUNT=0",
        "FREQ=DAILY;COUNT=-1",
        "FREQ=DAILY;INTERVAL=0",
        "FREQ=DAILY;INTERVAL=-1",
    ],
)
def test_nonpositive_count_or_interval_is_rejected(rule):
    with pytest.raises(CalendarSyncError, match="^invalid_recurrence$"):
        conversion.records(HREF, "fixture-etag", _recurring(rule), START, END)


def test_interval_aligned_filter_keeps_pre_expansion_event_limit(monkeypatch):
    expansion = Mock(side_effect=AssertionError("Dense series must not be expanded"))
    monkeypatch.setattr(conversion.recurring_ical_events, "of", expansion)
    minutes = ",".join(str(value) for value in range(60))
    with pytest.raises(CalendarSyncError, match="^too_many_events$"):
        conversion.records(
            HREF,
            "fixture-etag",
            _recurring(f"FREQ=HOURLY;INTERVAL=24;BYHOUR=1;BYMINUTE={minutes}"),
            START,
            END,
        )
    expansion.assert_not_called()


def _metadata():
    return Response(multi(xml_row(HREF, "<d:getetag>new</d:getetag>")))


def _content(data):
    return Response(
        multi(
            xml_row(
                HREF, "<d:getetag>new</d:getetag><c:calendar-data>" + data + "</c:calendar-data>"
            )
        )
    )


def test_invalid_rule_preserves_cache_and_same_etag_can_be_retried():
    conn = sqlite3.connect(":memory:")
    try:
        store = CalDAVResourceCache(conn, "synthetic-account")
        store.save(COLLECTION, {HREF: ("old", ICS)})
        failed = CalDAVClient(
            "icloud",
            "fixture",
            "synthetic",
            Session(_metadata(), _content(_recurring("FREQ=DAILY;COUNT=0"))),
            resource_cache=store,
        )
        with pytest.raises(CalendarSyncError, match="^invalid_recurrence$"):
            failed.events(COLLECTION, START.isoformat(), END.isoformat())
        assert store.load(COLLECTION) == {HREF: ("old", ICS)}
        assert not conn.in_transaction
        retry = CalDAVClient(
            "icloud",
            "fixture",
            "synthetic",
            Session(_metadata(), _content(_recurring("FREQ=DAILY;COUNT=3"))),
            resource_cache=store,
        )
        result = retry.events(COLLECTION, START.isoformat(), END.isoformat())
        assert len(result) == 3
        assert store.load(COLLECTION)[HREF][0] == "new"
    finally:
        conn.close()
