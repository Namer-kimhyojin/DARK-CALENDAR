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
    detail_page_mode: str = "all",
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


def test_quiet_month_includes_a_details_sheet_by_default(tmp_path):
    output = tmp_path / "quiet-calendar.pdf"
    report = _render_pdf(output, 2, grayscale=True)

    assert output.exists()
    assert report.sheet_count == 2
    assert report.detail_sheet_count == 1
    assert report.missing_event_keys == ()
    assert len(report.drawn_event_keys) == 2


def test_quiet_month_can_limit_details_to_overflow_only(tmp_path):
    output = tmp_path / "compact-calendar.pdf"
    report = _render_pdf(output, 2, detail_page_mode="overflow")

    assert output.exists()
    assert report.sheet_count == 1
    assert report.detail_sheet_count == 0
    assert report.missing_event_keys == ()
