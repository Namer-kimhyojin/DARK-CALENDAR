# -*- coding: utf-8 -*-
"""Weekly navigation and live opacity with isolated DB and explicit INI settings."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QPoint, QSettings, Qt, QTime
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QPushButton

from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid
from calendar_app.presentation.main_window.theme_actions import ThemeActionsMixin
from tests.support import TemporaryDatabaseTestCase
from tests.test_week_planner_integration import CalendarRenderHost


class OpacityCalendarRenderHost(CalendarRenderHost, ThemeActionsMixin):
    pass


class WeekPlannerConvenienceTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "settings.ini"), QSettings.Format.IniFormat
        )
        self.settings.setFallbacksEnabled(False)
        for key, value in {
            "gcal_enabled": False,
            "text_theme": "dark",
            "panel_base_color": "#202735",
            "last_opacity": 255,
            "last_opacity_unit": "byte",
        }.items():
            self.settings.setValue(key, value)
        self.host = OpacityCalendarRenderHost(self.settings)
        for target in (
            "calendar_app.shared.theme_settings.QSettings",
            "calendar_app.shared.theme_snapshot.QSettings",
        ):
            self.enterContext(patch(target, return_value=self.settings))
        month_renderer.invalidate_calendar_meta_cache()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.qt_app.processEvents()
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    def render(self):
        with patch.object(month_renderer, "_get_subscription_events", return_value=[]):
            month_renderer.render_calendar(self.host)
        self.host.show()
        self.qt_app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        return self.host.center_frame.findChild(WeekTimeGrid)

    def test_saved_midnight_is_preserved(self):
        self.settings.setValue("cal_week_scroll_minutes", 0)
        grid = self.render()
        self.assertEqual(grid._scroll.verticalScrollBar().value(), 0)
        self.assertEqual(self.settings.value("cal_week_scroll_minutes", type=int), 0)

    def test_work_start_jump_is_saved_and_survives_rerender(self):
        self.render()
        button = self.host.calendar_toolbar_widget.findChild(QPushButton, "week_jump_work_start")
        button.click()
        self.qt_app.processEvents()
        self.assertEqual(self.settings.value("cal_week_scroll_minutes", type=int), 540)
        grid = self.render()
        self.assertEqual(grid._scroll.verticalScrollBar().value(), 648)

    def test_current_time_jump_keeps_viewed_week_and_date(self):
        grid = self.render()
        before = QDate(self.host.current_date)
        button = self.host.calendar_toolbar_widget.findChild(QPushButton, "week_jump_now")
        with patch.object(month_renderer, "QTime") as clock:
            clock.currentTime.return_value = QTime(14, 30)
            button.click()
        self.qt_app.processEvents()
        self.assertEqual(self.host.current_date, before)
        self.assertEqual(self.settings.value("cal_week_scroll_minutes", type=int), 810)
        self.assertEqual(grid._scroll.verticalScrollBar().value(), 972)

    def test_selected_day_updates_without_replacing_grid(self):
        grid = self.render()
        self.assertEqual(grid._selected_date, self.host.current_date)
        QTest.mouseClick(
            grid._header,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(round(grid.GUTTER + grid._column_width() / 2), 25),
        )
        self.assertEqual(grid._selected_date, QDate(2026, 10, 5))
        self.assertEqual(self.host.current_date, QDate(2026, 10, 5))
        self.assertIs(self.host.center_frame.findChild(WeekTimeGrid), grid)
        self.assertEqual(self.host.refreshes[-1], {"left": True})
        date_button = self.host.calendar_toolbar_widget.findChild(
            QPushButton, "calendar_date_selector"
        )
        self.assertEqual(
            date_button.text(), month_renderer._format_toolbar_date(self.host.current_date, False)
        )
        self.assertEqual(date_button.accessibleName(), date_button.text())
        today_button = self.host.calendar_toolbar_widget.findChild(QPushButton, "calendar_today")
        self.assertEqual(today_button.isEnabled(), self.host.current_date != QDate.currentDate())

    def test_live_opacity_preserves_drag_and_scroll_without_db_rerender(self):
        grid = self.render()
        grid.scroll_to_time(480)
        self.qt_app.processEvents()
        start = QPoint(round(grid.GUTTER + grid._column_width() / 2), 650)
        QTest.mousePress(grid._timeline, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(grid._timeline, start + QPoint(0, 36))
        gesture, preview = grid._gesture, grid._preview
        scroll = grid._scroll.verticalScrollBar().value()
        created = QSignalSpy(grid.create_requested)
        with patch.object(month_renderer, "render_calendar") as rerender:
            self.host.set_opacity(85)
        self.assertFalse(rerender.called)
        self.assertIs(grid._gesture, gesture)
        self.assertEqual(grid._preview, preview)
        self.assertEqual(grid._scroll.verticalScrollBar().value(), scroll)
        self.assertEqual(grid._surface().alpha(), 0)
        self.assertIn("55)", grid.parentWidget().styleSheet())
        QTest.keyClick(grid, Qt.Key.Key_Escape)
        self.assertEqual(len(created), 0)

    def test_time_actions_do_not_appear_in_date_or_month_view(self):
        for mode, layout in (("weekly_1", "date"), ("monthly", "time")):
            with self.subTest(mode=mode):
                self.host.view_mode_state = mode
                self.host.cal_week_layout = layout
                self.render()
                self.assertIsNone(
                    self.host.calendar_toolbar_widget.findChild(QPushButton, "week_jump_now")
                )

    def test_narrow_jump_controls_remain_inside_toolbar(self):
        self.host.resize(760, 700)
        self.render()
        toolbar = self.host.calendar_toolbar_widget
        self.assertEqual(self.host.width(), 760)
        self.assertLessEqual(toolbar.width(), 760)
        self.assertIsNone(toolbar.findChild(QPushButton, "week_planner_help"))
        scroll = toolbar.findChild(month_renderer._CalToolbarScroll)
        self.assertIsNotNone(scroll)
        centers = []
        for name in (
            "calendar_today",
            "calendar_previous",
            "calendar_date_selector",
            "calendar_next",
            "week_jump_now",
            "week_jump_work_start",
            "calendar_add",
            "calendar_sync",
            "calendar_options",
            "week_layout_toggle",
            "calendar_view",
        ):
            button = toolbar.findChild(QPushButton, name)
            self.assertTrue(button.isVisible())
            centers.append(button.mapTo(scroll.widget(), button.rect().center()).y())
            scroll.ensureWidgetVisible(button, 0, 0)
            self.qt_app.processEvents()
            origin = button.mapTo(scroll.viewport(), QPoint())
            self.assertGreaterEqual(origin.x(), 0)
            self.assertLessEqual(origin.x() + button.width(), scroll.viewport().width())
        self.assertLessEqual(max(centers) - min(centers), 2)
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
