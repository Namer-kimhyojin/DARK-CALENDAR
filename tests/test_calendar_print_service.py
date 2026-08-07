# -*- coding: utf-8 -*-

from datetime import date, datetime

import pytest

from calendar_app.application.calendar_print_service import (
    CalendarPrintRequest,
    build_calendar_print_document,
    events_for_day,
)

CALENDARS = [
    {
        "id": "local::work",
        "name": "업무",
        "color": "#3366cc",
        "type": "local",
        "is_visible": 1,
    },
    {
        "id": "local::private",
        "name": "개인",
        "color": "#cc6633",
        "type": "local",
        "is_visible": 0,
    },
]


def _row(row_id, name, start, end=None, calendar_id="local::work", **extra):
    return {
        "id": row_id,
        "name": name,
        "type": "schedule",
        "deadline": start,
        "end_date": end or start,
        "target_date": str(start)[:10],
        "calendar_id": calendar_id,
        "priority": "normal",
        "status": "in_progress",
        **extra,
    }


def test_month_range_builds_partial_month_pages_in_order():
    request = CalendarPrintRequest(
        start_date=date(2026, 4, 15),
        end_date=date(2026, 6, 10),
        page_unit="month",
    )
    document = build_calendar_print_document(request, [], CALENDARS)

    assert [page.anchor_date for page in document.pages] == [
        date(2026, 4, 1),
        date(2026, 5, 1),
        date(2026, 6, 1),
    ]
    assert document.pages[0].period_start == date(2026, 4, 15)
    assert document.pages[-1].period_end == date(2026, 6, 10)


def test_month_grid_keeps_five_or_six_complete_weeks():
    april = build_calendar_print_document(
        CalendarPrintRequest(date(2026, 4, 1), date(2026, 4, 30)),
        [],
        CALENDARS,
    ).pages[0]
    august = build_calendar_print_document(
        CalendarPrintRequest(date(2026, 8, 1), date(2026, 8, 31)),
        [],
        CALENDARS,
    ).pages[0]

    assert len(april.grid_dates) == 35
    assert april.grid_dates[0] == date(2026, 3, 30)
    assert len(august.grid_dates) == 42
    assert august.grid_dates[-1] == date(2026, 9, 6)


def test_week_pages_use_inclusive_custom_range():
    request = CalendarPrintRequest(
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 20),
        page_unit="week",
        start_monday=True,
    )
    document = build_calendar_print_document(request, [], CALENDARS)

    assert len(document.pages) == 3
    assert document.pages[0].grid_dates[0] == date(2026, 4, 6)
    assert document.pages[0].period_start == date(2026, 4, 8)
    assert document.pages[-1].period_end == date(2026, 4, 20)


def test_event_normalization_filters_calendars_and_completed_rows():
    rows = [
        _row(1, "업무 일정", "2026-04-10 09:00:00"),
        _row(2, "개인 일정", "2026-04-10", calendar_id="local::private"),
        _row(3, "완료 일정", "2026-04-10", status="completed"),
    ]
    request = CalendarPrintRequest(
        date(2026, 4, 1),
        date(2026, 4, 30),
        selected_calendar_ids=("local::work",),
        include_completed=False,
    )
    document = build_calendar_print_document(request, rows, CALENDARS)

    assert [event.name for event in document.pages[0].events] == ["업무 일정"]


def test_google_mirror_rows_are_deduplicated_by_event_and_source():
    rows = [
        _row(
            10,
            "회의",
            "2026-04-10 09:00:00",
            calendar_id="gcal::team@example.com",
            gcal_event_id="event-1",
            gcal_source_calendar_id="team@example.com",
        ),
        _row(
            11,
            "회의",
            "2026-04-10 09:00:00",
            calendar_id="gcal::team@example.com",
            gcal_event_id="event-1",
            gcal_source_calendar_id="team@example.com",
        ),
    ]
    calendars = [
        {
            "id": "gcal::team@example.com",
            "name": "팀",
            "color": "#228855",
            "type": "gcal",
            "is_visible": 1,
        }
    ]
    document = build_calendar_print_document(
        CalendarPrintRequest(date(2026, 4, 1), date(2026, 4, 30)),
        rows,
        calendars,
    )

    assert len(document.pages[0].events) == 1


def test_multiday_event_occurs_on_every_in_scope_date():
    rows = [_row(20, "출장", "2026-04-10", "2026-04-12")]
    document = build_calendar_print_document(
        CalendarPrintRequest(date(2026, 4, 1), date(2026, 4, 30)),
        rows,
        CALENDARS,
        created_at=datetime(2026, 4, 1, 9, 0),
    )
    page = document.pages[0]

    assert [event.name for event in events_for_day(page, date(2026, 4, 11))] == ["출장"]
    assert events_for_day(page, date(2026, 4, 13)) == ()


def test_invalid_and_excessive_ranges_are_rejected():
    with pytest.raises(ValueError):
        CalendarPrintRequest(date(2026, 5, 1), date(2026, 4, 1)).validate()
    with pytest.raises(ValueError):
        CalendarPrintRequest(date(2020, 1, 1), date(2031, 1, 1)).validate()
    with pytest.raises(ValueError):
        CalendarPrintRequest(
            date(2026, 4, 1),
            date(2026, 4, 30),
            detail_page_mode="unsupported",
        ).validate()
