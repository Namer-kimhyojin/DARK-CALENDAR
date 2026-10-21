# -*- coding: utf-8 -*-
"""Sparse secondly expansion retains recurrence identity and wall-clock meaning."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
import pytest
import recurring_ical_events

from calendar_app.infrastructure.ics import ics_fetcher


def _calendar(rule, start="20261005T100000Z", extra="", exceptions=""):
    return icalendar.Calendar.from_ical(
        (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
            f"UID:fixture\r\nDTSTART{start if start.startswith(';') else ':' + start}\r\n"
            f"SUMMARY:Synthetic\r\nRRULE:{rule}\r\n{extra}END:VEVENT\r\n"
            f"{exceptions}END:VCALENDAR\r\n"
        ).encode("utf-8", errors="strict")
    )


def _expanded(calendar, start, end):
    return sorted(
        event.to_ical() for event in recurring_ical_events.of(calendar).between(start, end)
    )


@pytest.mark.parametrize(
    "start,rule,span_start",
    [
        (
            "20261005T100000Z",
            "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0;COUNT=3",
            datetime(2026, 10, 5, tzinfo=UTC),
        ),
        (
            "20261005T100001Z",
            "FREQ=SECONDLY;INTERVAL=1;BYHOUR=10;BYMINUTE=0;BYSECOND=0;COUNT=2",
            datetime(2026, 10, 5, tzinfo=UTC),
        ),
        (
            "20261005T100000Z",
            "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0;UNTIL=20261006T100000Z",
            datetime(2026, 10, 5, tzinfo=UTC),
        ),
        (
            "20261231T235959",
            "FREQ=SECONDLY;BYHOUR=0,23;BYMINUTE=0,59;BYSECOND=0,59;COUNT=12;WKST=SU",
            datetime(2026, 12, 31),
        ),
        (
            ";TZID=America/New_York:20260307T023000",
            "FREQ=SECONDLY;BYHOUR=2;BYMINUTE=30;BYSECOND=0;COUNT=3",
            datetime(2026, 3, 7, tzinfo=ZoneInfo("America/New_York")),
        ),
        (
            ";TZID=America/New_York:20261031T013000",
            "FREQ=SECONDLY;BYHOUR=1;BYMINUTE=30;BYSECOND=0;COUNT=3",
            datetime(2026, 10, 31, tzinfo=ZoneInfo("America/New_York")),
        ),
    ],
)
def test_daily_expansion_copy_matches_original_secondly_sequence(start, rule, span_start):
    original = _calendar(rule, start)
    original_bytes = original.to_ical()
    optimized = icalendar.Calendar()
    for event in original.walk("VEVENT"):
        optimized.add_component(ics_fetcher._recurrence_expansion_event(event))
    span_end = span_start + timedelta(days=4)
    expected = _expanded(original, span_start, span_end)
    assert expected
    assert _expanded(optimized, span_start, span_end) == expected
    assert original.to_ical() == original_bytes


def test_daily_expansion_preserves_exclusions_additions_and_moved_occurrence():
    original = _calendar(
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0;COUNT=4",
        extra="EXDATE:20261006T100000Z\r\nRDATE:20261006T150000Z\r\n",
        exceptions=(
            "BEGIN:VEVENT\r\nUID:fixture\r\nRECURRENCE-ID:20261007T100000Z\r\n"
            "DTSTART:20261007T113000Z\r\nDTEND:20261007T123000Z\r\n"
            "SUMMARY:Moved\r\nEND:VEVENT\r\n"
        ),
    )
    original_bytes = original.to_ical()
    optimized = icalendar.Calendar()
    for event in original.walk("VEVENT"):
        optimized.add_component(ics_fetcher._recurrence_expansion_event(event))
    start, end = datetime(2026, 10, 5, tzinfo=UTC), datetime(2026, 10, 9, tzinfo=UTC)
    expected = _expanded(original, start, end)
    assert len(expected) == 4
    assert _expanded(optimized, start, end) == expected
    assert original.to_ical() == original_bytes


def test_sparse_secondly_snapshot_completes_entire_window_with_default_budget(monkeypatch):
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    original = _calendar("FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0")
    rows = ics_fetcher._snapshot(original.to_ical(), icalendar, UTC, lambda: False)
    first = datetime(2026, 10, 5, 10, tzinfo=UTC)
    assert sorted(row[1] for row in rows.values()) == [
        (first + timedelta(days=index)).strftime("%Y-%m-%d %H:%M") for index in range(400)
    ]


@pytest.mark.parametrize(
    "rule",
    [
        "FREQ=SECONDLY;INTERVAL=2;BYHOUR=10;BYMINUTE=0;BYSECOND=0",
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0;BYSETPOS=1",
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0;BYDAY=MO",
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0;BYMONTH=10",
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0",
        "FREQ=SECONDLY;BYMINUTE=0;BYSECOND=0",
        "FREQ=SECONDLY;BYHOUR=10;BYSECOND=0",
        "FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=60",
        "FREQ=MINUTELY;BYHOUR=10;BYMINUTE=0;BYSECOND=0",
    ],
)
def test_frequency_sensitive_or_incomplete_rules_use_original_path(rule):
    event = _calendar(rule).walk("VEVENT")[0]
    assert ics_fetcher._recurrence_expansion_event(event) is event


def test_all_day_secondly_rule_uses_original_path():
    event = _calendar("FREQ=SECONDLY;BYHOUR=10;BYMINUTE=0;BYSECOND=0", ";VALUE=DATE:20261005").walk(
        "VEVENT"
    )[0]
    assert ics_fetcher._recurrence_expansion_event(event) is event
