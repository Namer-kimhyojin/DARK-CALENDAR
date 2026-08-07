# -*- coding: utf-8 -*-

import os
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QSettings
from PyQt6.QtPrintSupport import QPrintPreviewWidget
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.dialogs.calendar_print_dialog import CalendarPrintDialog

APP = QApplication.instance() or QApplication([])


class _Host(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.current_date = QDate(2026, 4, 15)
        self.view_mode_state = "monthly"
        self.cal_show_weekends = True
        self.cal_start_monday = True


CALENDARS = [
    {
        "id": "local::work",
        "name": "업무",
        "color": "#3366cc",
        "type": "local",
        "is_visible": 1,
    },
    {
        "id": "local::hidden",
        "name": "숨김",
        "color": "#cc6633",
        "type": "local",
        "is_visible": 0,
    },
]


def test_current_month_request_uses_one_month_and_visible_calendars():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = QSettings(f"{tmpdir}/print-test.ini", QSettings.Format.IniFormat)
        host = _Host(settings)
        with patch(
            "calendar_app.presentation.dialogs.calendar_print_dialog.list_calendars",
            return_value=CALENDARS,
        ):
            dialog = CalendarPrintDialog(host)
        request = dialog._build_request()

        assert request.start_date.isoformat() == "2026-04-01"
        assert request.end_date.isoformat() == "2026-04-30"
        assert request.page_unit == "month"
        assert request.selected_calendar_ids == ("local::work",)
        assert request.detail_page_mode == "all"
        assert dialog.output_preset_combo.currentData() == "readable"
        assert dialog.margin_spin.value() == 12
        assert "전체 페이지" in dialog.preview_btn.text()
        assert dialog.content_scroll.widgetResizable()
        assert dialog.content_scroll.accessibleName()

        dialog.show()
        QApplication.processEvents()
        assert dialog.height() <= 720

        dialog.close()
        host.close()


def test_custom_week_range_is_inclusive():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = QSettings(f"{tmpdir}/print-test.ini", QSettings.Format.IniFormat)
        host = _Host(settings)
        with patch(
            "calendar_app.presentation.dialogs.calendar_print_dialog.list_calendars",
            return_value=CALENDARS,
        ):
            dialog = CalendarPrintDialog(host)
        dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("range"))
        dialog.start_date_edit.setDate(QDate(2026, 4, 8))
        dialog.end_date_edit.setDate(QDate(2026, 4, 20))
        dialog.page_unit_combo.setCurrentIndex(dialog.page_unit_combo.findData("week"))

        request = dialog._build_request()

        assert request.start_date.isoformat() == "2026-04-08"
        assert request.end_date.isoformat() == "2026-04-20"
        assert request.page_unit == "week"

        dialog.close()
        host.close()


def test_legacy_output_choices_are_preserved_as_custom():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = QSettings(f"{tmpdir}/print-test.ini", QSettings.Format.IniFormat)
        settings.setValue("print_margin_mm", 8)
        settings.setValue("print_grayscale", True)
        host = _Host(settings)
        with patch(
            "calendar_app.presentation.dialogs.calendar_print_dialog.list_calendars",
            return_value=CALENDARS,
        ):
            dialog = CalendarPrintDialog(host)

        assert dialog.output_preset_combo.currentData() == "custom"
        assert dialog.margin_spin.value() == 8
        assert dialog.grayscale_check.isChecked()

        dialog.close()
        host.close()


def test_output_presets_keep_quality_choices_visible_and_customizable():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = QSettings(f"{tmpdir}/print-test.ini", QSettings.Format.IniFormat)
        host = _Host(settings)
        with patch(
            "calendar_app.presentation.dialogs.calendar_print_dialog.list_calendars",
            return_value=CALENDARS,
        ):
            dialog = CalendarPrintDialog(host)

        dialog.output_preset_combo.setCurrentIndex(dialog.output_preset_combo.findData("compact"))
        QApplication.processEvents()

        assert dialog.margin_spin.value() == 7
        assert dialog.detail_mode_combo.currentData() == "overflow"
        assert not dialog.grayscale_check.isChecked()

        dialog.margin_spin.setValue(9)
        QApplication.processEvents()

        assert dialog.output_preset_combo.currentData() == "custom"
        assert "9mm" in dialog.output_summary_label.text()

        dialog.output_preset_combo.setCurrentIndex(dialog.output_preset_combo.findData("grayscale"))
        QApplication.processEvents()

        assert dialog.grayscale_check.isChecked()
        assert dialog.detail_mode_combo.currentData() == "all"
        assert dialog.margin_spin.value() == 10

        dialog.close()
        host.close()


def test_preview_defaults_to_all_pages_so_detail_sheets_are_visible():
    class _PreviewWidget:
        def __init__(self):
            self.view_mode = None
            self.was_fitted = False

        def setViewMode(self, view_mode):
            self.view_mode = view_mode

        def fitInView(self):
            self.was_fitted = True

    class _PreviewDialog:
        def __init__(self):
            self.widget = _PreviewWidget()

        def findChild(self, _widget_type):
            return self.widget

    preview = _PreviewDialog()
    preview_widget = CalendarPrintDialog._configure_preview_view(preview)

    assert preview_widget is preview.widget
    assert preview_widget.view_mode == QPrintPreviewWidget.ViewMode.AllPagesView
    assert preview_widget.was_fitted
