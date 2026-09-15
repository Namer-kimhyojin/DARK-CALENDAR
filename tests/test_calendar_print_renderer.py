# -*- coding: utf-8 -*-

from datetime import date, datetime
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QApplication

from calendar_app.application.calendar_print_service import (
    CalendarPrintRequest,
    build_calendar_print_document,
)
from calendar_app.presentation.printing.calendar_print_renderer import (
    CalendarPrintRenderOptions,
    _build_sheet_plan,
    _build_week_layouts,
    _event_cell_text,
    _multiday_segment_text,
    configure_printer,
    render_calendar_document,
)

APP = QApplication.instance() or QApplication([])


def _calendar_rows():
    return [
        {
            "id": "local::work",
            "name": "업무",
            "color": "#3366cc",
            "type": "local",
            "is_visible": 1,
        }
    ]


def _event_rows(count: int):
    return [
        {
            "id": index + 1,
            "name": f"긴 한글 일정 제목 {index + 1}",
            "type": "schedule",
            "deadline": f"2026-04-10 {9 + index % 8:02d}:00:00",
            "end_date": "2026-04-10 18:00:00",
            "target_date": "2026-04-10",
            "calendar_id": "local::work",
            "priority": "high" if index == 0 else "normal",
            "status": "in_progress",
            "location": "대회의실",
        }
        for index in range(count)
    ]


def _render_pdf(
    path,
    event_count: int,
    *,
    grayscale: bool = False,
    detail_page_mode: str = "overflow",
):
    request = CalendarPrintRequest(
        date(2026, 4, 1),
        date(2026, 4, 30),
        include_location=True,
        grayscale=grayscale,
        detail_page_mode=detail_page_mode,
    )
    document = build_calendar_print_document(
        request,
        _event_rows(event_count),
        _calendar_rows(),
        created_at=datetime(2026, 4, 1, 9, 0),
    )
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    configure_printer(
        printer,
        CalendarPrintRenderOptions(document_title="Calendar print test"),
        grayscale=grayscale,
    )
    return render_calendar_document(printer, document)


def test_vector_pdf_is_created_without_missing_events(tmp_path):
    output = tmp_path / "calendar.pdf"
    report = _render_pdf(output, 12)

    assert output.read_bytes().startswith(b"%PDF")
    assert output.stat().st_size > 3_000
    assert report.calendar_sheet_count == 1
    assert report.detail_sheet_count >= 1
    assert report.overflow_event_count > 0
    assert report.missing_event_keys == ()
    assert len(report.drawn_event_keys) == 12


def test_quiet_month_uses_single_overview_sheet_by_default(tmp_path):
    output = tmp_path / "quiet-calendar.pdf"
    report = _render_pdf(output, 2, grayscale=True)

    assert output.exists()
    assert report.sheet_count == 1
    assert report.detail_sheet_count == 0
    assert report.missing_event_keys == ()
    assert len(report.drawn_event_keys) == 2


def test_quiet_month_can_limit_details_to_overflow_only(tmp_path):
    output = tmp_path / "compact-calendar.pdf"
    report = _render_pdf(output, 2, detail_page_mode="overflow")

    assert output.exists()
    assert report.sheet_count == 1
    assert report.detail_sheet_count == 0
    assert report.missing_event_keys == ()


def test_multiday_event_is_planned_as_one_weekly_ribbon_instead_of_daily_labels():
    rows = [
        {
            "id": 99,
            "name": "연속 교육",
            "type": "schedule",
            "deadline": "2026-04-07",
            "end_date": "2026-04-11",
            "target_date": "2026-04-07",
            "calendar_id": "local::work",
            "priority": "low",
            "status": "in_progress",
            "all_day": 1,
        }
    ]
    page = build_calendar_print_document(
        CalendarPrintRequest(date(2026, 4, 1), date(2026, 4, 30)),
        rows,
        _calendar_rows(),
    ).pages[0]

    layouts, overflow = _build_week_layouts(page, 760.0, 500.0)
    segments = [segment for layout in layouts for segment in layout.segments]

    assert len(segments) == 1
    assert segments[0].end_col - segments[0].start_col == 4
    assert overflow == set()
    assert "All day" not in _event_cell_text(page.events[0], date(2026, 4, 7))
    assert "[L]" not in _event_cell_text(page.events[0], date(2026, 4, 7))


def test_multiday_continuation_uses_a_printer_safe_marker():
    rows = [
        {
            "id": 100,
            "name": "두 주 일정",
            "type": "schedule",
            "deadline": "2026-04-07",
            "end_date": "2026-04-14",
            "target_date": "2026-04-07",
            "calendar_id": "local::work",
            "priority": "normal",
            "status": "in_progress",
            "all_day": 1,
        }
    ]
    page = build_calendar_print_document(
        CalendarPrintRequest(date(2026, 4, 1), date(2026, 4, 30)),
        rows,
        _calendar_rows(),
    ).pages[0]
    layouts, _ = _build_week_layouts(page, 760.0, 500.0)
    segments = [segment for layout in layouts for segment in layout.segments]

    assert len(segments) == 2
    assert _multiday_segment_text(segments[1]).startswith("... ")


def test_overflow_detail_sheet_contains_only_events_missing_from_calendar_grid():
    request = CalendarPrintRequest(
        date(2026, 4, 1),
        date(2026, 4, 30),
        detail_page_mode="overflow",
    )
    document = build_calendar_print_document(
        request,
        _event_rows(12),
        _calendar_rows(),
        created_at=datetime(2026, 4, 1, 9, 0),
    )
    sheets, _ = _build_sheet_plan(document, 760.0, 500.0)
    detail_keys = {
        event.event_key
        for sheet in sheets
        if sheet.kind == "details"
        for event in sheet.detail_events
    }

    assert detail_keys
    assert detail_keys < {event.event_key for event in document.pages[0].events}
