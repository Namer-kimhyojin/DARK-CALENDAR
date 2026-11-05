# -*- coding: utf-8 -*-
"""Weekday placement persists and paints consistently across calendar layouts."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QLocale, QRectF, QSettings
from PyQt6.QtGui import QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QLabel, QWidget
import pytest

from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid
from calendar_app.presentation.main_window.calendar_view_actions import CalendarViewActionsMixin
from calendar_app.shared.calendar_display_settings import (
    WEEKDAY_DISPLAY_KEY,
    WEEKDAY_DISPLAY_MODES,
    read_weekday_display_mode,
    weekday_display_flags,
)
from tests.support import TemporaryDatabaseTestCase
from tests.test_week_planner_integration import CalendarRenderHost


@pytest.mark.parametrize(
    "values,expected",
    [
        ({}, "header"),
        ({"cal_show_weekday": False}, "header"),
        ({"cal_show_weekday": True}, "both"),
        ({"cal_show_weekday": "false"}, "header"),
        ({"cal_show_weekday": "true"}, "both"),
        ({"cal_show_day_name": True}, "both"),
        ({"cal_show_weekday": False, "cal_show_day_name": True}, "header"),
        ({WEEKDAY_DISPLAY_KEY: "date", "cal_show_weekday": False}, "date"),
        ({WEEKDAY_DISPLAY_KEY: "hidden", "cal_show_weekday": True}, "hidden"),
        ({WEEKDAY_DISPLAY_KEY: "invalid", "cal_show_weekday": True}, "both"),
    ],
)
def test_legacy_weekday_settings_are_read_without_migration_writes(tmp_path, values, expected):
    settings = QSettings(str(tmp_path / "weekday.ini"), QSettings.Format.IniFormat)
    for key, value in values.items():
        settings.setValue(key, value)
    before = {key: settings.value(key) for key in settings.allKeys()}
    assert read_weekday_display_mode(settings) == expected
    assert {key: settings.value(key) for key in settings.allKeys()} == before


class ActionHost(CalendarViewActionsMixin):
    def __init__(self, settings):
        self.settings = settings
        self.cal_weekday_display_mode = read_weekday_display_mode(settings)
        self.cal_show_weekday = weekday_display_flags(self.cal_weekday_display_mode)[1]
        self.current_date = QDate(2026, 11, 5)
        self.selected_task_ids = set()
        self.view_mode_state = "monthly"
        self.cal_show_weekends = True
        self.cal_start_monday = True
        self.cal_show_month = False
        self.load_center_panel = Mock()


def test_four_click_cycle_persists_and_refreshes_once_per_click(tmp_path):
    path = str(tmp_path / "weekday.ini")
    settings = QSettings(path, QSettings.Format.IniFormat)
    host = ActionHost(settings)
    initial_signature = host._build_center_render_signature()
    for expected in ("date", "both", "hidden", "header"):
        host.load_center_panel.reset_mock()
        host.cycle_weekday_display_mode()
        assert host.cal_weekday_display_mode == expected
        assert host.cal_show_weekday == (expected in {"date", "both"})
        settings.sync()
        reopened = QSettings(path, QSettings.Format.IniFormat)
        assert read_weekday_display_mode(reopened) == expected
        host.load_center_panel.assert_called_once_with()
        if expected == "hidden":
            assert host._build_center_render_signature() != initial_signature


def test_legacy_toggle_remains_compatible_with_new_explicit_mode(tmp_path):
    host = ActionHost(QSettings(str(tmp_path / "legacy.ini"), QSettings.Format.IniFormat))
    host.toggle_show_weekday(True)
    assert host.cal_weekday_display_mode == "both"
    host.toggle_show_weekday(False)
    assert host.cal_weekday_display_mode == "header"


def test_all_bundled_locales_have_weekday_modes_and_matching_action_placeholder():
    paths = list((Path(__file__).resolve().parents[1] / "locales").glob("*.json"))
    assert len(paths) == 19
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        values = data["calendar"]["weekday_display"]
        assert set(values) == {*WEEKDAY_DISPLAY_MODES, "action", "cycle_hint"}
        assert all(isinstance(value, str) and value.strip() for value in values.values())
        assert "{mode}" in values["action"]
        assert isinstance(data["common"]["search"], str) and data["common"]["search"].strip()
        if path.stem in {"ko", "en"}:
            assert data["common"]["search"] == ("검색" if path.stem == "ko" else "Search")


class WeekdayRenderHost(CalendarViewActionsMixin, CalendarRenderHost):
    def load_center_panel(self, force=True):
        self.refreshes.append({"center": True})


class RecordingPainter(QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.text = []

    def drawText(self, rect, flags, text):
        self.text.append((QRectF(rect), str(text), self.fontMetrics().height()))
        return super().drawText(rect, flags, text)


class CalendarWeekdayDisplayTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.original_font = QFont(self.app.font())
        font = QFont(self.original_font)
        font.setPointSize(11)
        self.app.setFont(font)
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "display.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("gcal_enabled", False)
        self.host = WeekdayRenderHost(self.settings)
        self.host.resize(1400, 900)
        self.host.cal_week_layout = "date"
        self.enterContext(patch("calendar_app.shared.theme_settings.QSettings", return_value=self.settings))
        self.enterContext(patch("calendar_app.shared.theme_snapshot.QSettings", return_value=self.settings))

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.setFont(self.original_font)
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    def render(self, view, mode, layout="date"):
        self.host.view_mode_state = view
        self.host.cal_week_layout = layout
        self.host.cal_weekday_display_mode = mode
        self.settings.setValue(WEEKDAY_DISPLAY_KEY, mode)
        with patch.object(month_renderer, "_get_subscription_events", return_value=[]):
            month_renderer.render_calendar(self.host)
        self.host.show()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_month_and_one_or_multiple_week_date_grids_follow_all_four_modes(self):
        for view in ("monthly", "weekly_1", "weekly_2"):
            for mode in WEEKDAY_DISPLAY_MODES:
                with self.subTest(view=view, mode=mode):
                    self.render(view, mode)
                    header = self.host.findChild(QWidget, "calendar_weekday_header")
                    self.assertEqual(header is not None, mode in {"header", "both"})
                    labels = self.host.findChildren(QLabel, "dayNumLabel")
                    self.assertTrue(labels)
                    self.assertTrue(all(label.text().strip() for label in labels))
                    self.assertTrue(all(("(" in label.text()) == (mode in {"date", "both"}) for label in labels))

    def test_real_options_action_cycles_label_mode_and_rebuilds_once(self):
        self.render("monthly", "header")
        action = next(
            action for action in self.host.findChildren(month_renderer.QAction)
            if action.objectName() == "calendar_weekday_display"
        )
        self.assertFalse(action.isCheckable())
        for expected in ("date", "both", "hidden", "header"):
            self.host.refreshes.clear()
            action.trigger()
            self.assertEqual(action.data(), expected)
            self.assertEqual(action.text(), month_renderer._weekday_display_action_text(expected))
            self.assertEqual(self.host.cal_weekday_display_mode, expected)
            self.assertEqual(self.host.refreshes, [{"center": True}])

    def test_compact_column_header_tracks_font_metrics(self):
        for points in (10, 11, 24):
            with self.subTest(points=points):
                font = QFont(self.original_font)
                font.setPointSize(points)
                self.app.setFont(font)
                self.render("monthly", "header")
                header = self.host.findChild(QWidget, "calendar_weekday_header")
                for label in header.findChildren(QLabel):
                    self.assertGreaterEqual(label.height(), label.fontMetrics().height())
                    self.assertLessEqual(header.height(), label.fontMetrics().height() + 8)

    def test_time_grid_paints_dates_in_every_mode_and_only_requested_weekdays(self):
        for mode in WEEKDAY_DISPLAY_MODES:
            with self.subTest(mode=mode):
                self.render("weekly_1", mode, "time")
                grid = self.host.findChild(WeekTimeGrid)
                self.assertEqual(grid._weekday_display_mode, mode)
                self.assertEqual(grid._selected_date, self.host.current_date)
                image = QImage(grid._header.width(), grid.HEADER_HEIGHT, QImage.Format.Format_ARGB32)
                painter = RecordingPainter(image)
                try:
                    grid._paint(painter, "header", QRectF(image.rect()))
                finally:
                    painter.end()
                date_texts = {QLocale().toString(date, "d") for date in grid._dates}
                self.assertTrue(date_texts.issubset({text for _rect, text, _height in painter.text}))
                self.assertEqual(len(painter.text), len(grid._dates) * {"header": 2, "date": 2, "both": 3, "hidden": 1}[mode])
                for rect, _text, text_height in painter.text:
                    self.assertGreaterEqual(rect.height(), text_height)
                    self.assertGreaterEqual(rect.top(), 0)
                    self.assertLessEqual(rect.bottom(), grid.HEADER_HEIGHT)
