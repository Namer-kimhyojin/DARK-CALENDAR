# -*- coding: utf-8 -*-
"""A remote calendar may define timezones only for its own snapshot."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
import threading
from unittest.mock import Mock

import icalendar
from icalendar.timezone import tzp
import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync import ical_parser
from calendar_app.infrastructure.ics import ics_fetcher

TZID = "AirCalendar/SyntheticSecurityTimezone"


def calendar_data(offset="+0900", *, forward=False, extra="", include_zone=True, uid="one"):
    timezone = (
        (
            "BEGIN:VTIMEZONE\r\n"
            f"TZID:{TZID}\r\n"
            "BEGIN:STANDARD\r\nDTSTART:19700101T000000\r\n"
            f"TZOFFSETFROM:{offset}\r\nTZOFFSETTO:{offset}\r\n"
            "END:STANDARD\r\nEND:VTIMEZONE\r\n"
        )
        if include_zone
        else ""
    )
    event = (
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART;TZID={TZID}:20261020T120000\r\n{extra}END:VEVENT\r\n"
    )
    content = event + timezone if forward else timezone + event
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + content + "END:VCALENDAR\r\n").encode(
        "utf-8", errors="strict"
    )


@pytest.fixture
def global_cache(monkeypatch):
    cache = {}
    monkeypatch.setattr(tzp, "_TZP__tz_cache", cache)
    return cache


def utc_start(calendar):
    return calendar.walk("VEVENT")[0]["DTSTART"].dt.astimezone(UTC)


@pytest.mark.parametrize("offsets", [("+0900", "-0500"), ("-0500", "+0900")])
@pytest.mark.parametrize("forward", [False, True])
def test_each_calendar_owns_its_custom_timezone(global_cache, offsets, forward):
    expected_hour = {"+0900": 3, "-0500": 17}
    for offset in offsets:
        parsed = ical_parser.parse_calendar(calendar_data(offset, forward=forward))
        assert utc_start(parsed) == datetime(2026, 10, 20, expected_hour[offset], tzinfo=UTC)
    assert global_cache == {}


def test_existing_library_cache_cannot_supply_or_override_feed_timezone(global_cache):
    icalendar.Calendar.from_ical(calendar_data("+0900"))
    before = dict(global_cache)
    assert TZID in before
    parsed = ical_parser.parse_calendar(calendar_data("-0500"))
    assert utc_start(parsed).hour == 17
    unresolved = ical_parser.parse_calendar(calendar_data(include_zone=False))
    assert unresolved.walk("VEVENT")[0]["DTSTART"].dt.tzinfo is None
    assert global_cache == before


def test_shared_parser_never_calls_process_global_timezone_cache(monkeypatch, global_cache):
    cache = Mock(side_effect=AssertionError("Global timezone cache must not be used"))
    monkeypatch.setattr(tzp, "cache_timezone_component", cache)
    parsed = ical_parser.parse_calendar(calendar_data())
    assert utc_start(parsed).hour == 3
    cache.assert_not_called()


def test_rejected_ics_snapshot_cannot_influence_next_feed(global_cache):
    with pytest.raises(CalendarSyncError, match="invalid_calendar_data"):
        ics_fetcher._snapshot(calendar_data("+0900", uid=""), icalendar, UTC, lambda: False)
    rows = ics_fetcher._snapshot(calendar_data("-0500"), icalendar, UTC, lambda: False)
    assert rows["one"][1] == "2026-10-20 17:00"
    assert global_cache == {}


def test_timezone_definitions_are_isolated_during_simultaneous_parses(monkeypatch, global_cache):
    barrier = threading.Barrier(2)
    original = ical_parser._LocalTimezoneParser.handle_end_component

    def interleave(parser, value):
        original(parser, value)
        if value.upper() == "VTIMEZONE":
            barrier.wait(timeout=3)

    monkeypatch.setattr(ical_parser._LocalTimezoneParser, "handle_end_component", interleave)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda offset: utc_start(ical_parser.parse_calendar(calendar_data(offset))).hour,
                ["+0900", "-0500"],
            )
        )
    assert results == [3, 17]
    assert global_cache == {}


def test_custom_timezone_recurrence_and_exdates_keep_their_offsets(monkeypatch, global_cache):
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 20, tzinfo=UTC))
    rows = ics_fetcher._snapshot(
        calendar_data(
            "-0500",
            forward=True,
            extra=(
                "RRULE:FREQ=DAILY;COUNT=3\r\n"
                f"EXDATE;TZID={TZID}:20261021T120000\r\n"
                f"RDATE;TZID={TZID}:20261025T120000\r\n"
            ),
        ),
        icalendar,
        UTC,
        lambda: False,
    )
    assert sorted(row[1] for row in rows.values()) == [
        "2026-10-20 17:00",
        "2026-10-22 17:00",
        "2026-10-25 17:00",
    ]
    assert global_cache == {}


def test_known_timezone_and_all_day_dates_keep_existing_semantics(global_cache):
    raw = (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        b"BEGIN:VEVENT\r\nUID:timed\r\nDTSTART;TZID=Asia/Seoul:20261020T120000\r\nEND:VEVENT\r\n"
        b"BEGIN:VEVENT\r\nUID:all-day\r\nDTSTART;VALUE=DATE:20261020\r\nEND:VEVENT\r\n"
        b"END:VCALENDAR\r\n"
    )
    timed, all_day = ical_parser.parse_calendar(raw).walk("VEVENT")
    assert timed["DTSTART"].dt.astimezone(UTC) == datetime(2026, 10, 20, 3, tzinfo=UTC)
    assert type(all_day["DTSTART"].dt) is date
    assert all_day["DTSTART"].dt == date(2026, 10, 20)
    assert global_cache == {}


def test_remote_text_is_never_treated_as_a_local_filename(monkeypatch):
    probe = Mock(side_effect=AssertionError("Calendar content must not access local files"))
    monkeypatch.setattr(Path, "is_file", probe)
    monkeypatch.setattr(Path, "read_bytes", probe)
    with pytest.raises(ValueError):
        ical_parser.parse_calendar("C:/synthetic-private-calendar.ics")
    probe.assert_not_called()


def test_unreviewed_parser_version_fails_closed(monkeypatch):
    monkeypatch.setattr(icalendar, "__version__", "8.0.0")
    with pytest.raises(ImportError, match="Unsupported iCalendar parser API"):
        ical_parser.parse_calendar(calendar_data())
