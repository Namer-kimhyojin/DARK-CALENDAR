# -*- coding: utf-8 -*-
"""Render real side-panel widgets for target-date-only and timed schedules."""

from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore, sip
from PyQt6.QtCore import QDate, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QPushButton,
    QToolButton,
    QWidget,
)

from calendar_app.infrastructure.db import task_repo
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.presentation.panels import side_panel_renderer
from calendar_app.shared import theme_settings, theme_snapshot
from tests.support import TemporaryDatabaseTestCase


class SidePanelHost(TaskActionsMixin, QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.left_panel_mode = "today"
        self.left_group_by_date = True
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self.expanded_tids = set()
        self._panel_task_frames = {}
        self._panel_directive_frames = {}
        self.modified_ids = []
        self.added_dates = []
        self.refresh_requests = []
        self.current_date = QDate.currentDate()
        self.view_mode_state = "monthly"
        self.left_dock = QDockWidget(self)
        self.left_frame = QWidget(self.left_dock)
        self.left_dock.setWidget(self.left_frame)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)
        self.resize(600, 440)

    @staticmethod
    def reset_frame(frame):
        layout = frame.layout()
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            sip.delete(layout)

    def open_task_dialog(self, initial_date=None):
        self.added_dates.append(initial_date)

    def schedule_panel_refresh(self, **kwargs):
        self.refresh_requests.append(kwargs)

    def sync_panel_menu_state(self):
        pass

    @staticmethod
    def open_work_management_dialog(*_args, **_kwargs):
        return None

    def open_modify_task_dialog(self, task_id):
        self.modified_ids.append(task_id)


class SidePanelAllDayStartupTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "side-panel.ini"), QSettings.Format.IniFormat
        )
        self.settings.setFallbacksEnabled(False)
        self.assertTrue(Path(self.settings.fileName()).is_relative_to(Path(self._tmpdir.name)))
        self.settings.setValue("text_theme", "dark")
        self.settings.setValue("last_opacity", 255)
        self.settings.setValue("last_opacity_unit", "byte")
        self._settings_patches = ExitStack()
        self.addCleanup(self._settings_patches.close)
        # Dynamic imports and previously imported theme constructors share this explicit INI.
        for module in (QtCore, theme_settings, theme_snapshot):
            self._settings_patches.enter_context(
                patch.object(module, "QSettings", return_value=self.settings)
            )
        self.host = SidePanelHost(self.settings)
        self.addCleanup(self.host.close)
        side_panel_renderer.invalidate_panel_calendar_cache()

    def _render(self):
        side_panel_renderer.load_left_panel(self.host)
        self.host.show()
        self.qt_app.processEvents()
        self.assertFalse(self.host.grab().isNull())

    def _task_button(self, task_id):
        container, _color = self.host._panel_task_frames[task_id]
        return container.findChild(QPushButton)

    def _assert_date_group(self, date):
        label = (
            f"{date.month()}.{date.day()} ({side_panel_renderer._localized_weekday_short(date)})"
        )
        self.assertIn(label, [widget.text() for widget in self.host.findChildren(QLabel)])

    def test_target_date_only_all_day_renders_and_opens(self):
        date = QDate.currentDate()
        task_id = task_repo.create_unified_task(
            {
                "name": "All-day startup regression",
                "type": "schedule",
                "all_day": 1,
                "target_date": date.toString("yyyy-MM-dd"),
            }
        )
        self.assertIsNone(task_repo.get_unified_task(task_id)["deadline"])

        self._render()

        button = self._task_button(task_id)
        self.assertIn("All-day startup regression", button.text())
        self._assert_date_group(date)
        QTest.mouseDClick(button, Qt.MouseButton.LeftButton)
        self.assertEqual([task_id], self.host.modified_ids)

    def test_week_group_uses_target_date_of_all_day_schedule(self):
        self.host.left_panel_mode = "week"
        today = QDate.currentDate()
        target_date = today.addDays(2 - today.dayOfWeek())
        task_id = task_repo.create_unified_task(
            {
                "name": "All-day week group",
                "type": "schedule",
                "all_day": 1,
                "target_date": target_date.toString("yyyy-MM-dd"),
            }
        )

        self._render()

        self.assertIn("All-day week group", self._task_button(task_id).text())
        self._assert_date_group(target_date)

    def test_month_overflow_opens_selected_date_without_changing_view(self):
        today = self.host.current_date
        target = today.addDays(5)
        today_id = task_repo.create_unified_task(
            {"name": "Today only", "type": "schedule", "target_date": today.toString("yyyy-MM-dd")}
        )
        multi_id = task_repo.create_unified_task(
            {
                "name": "Spans selected date",
                "type": "schedule",
                "all_day": 1,
                "deadline": target.addDays(-1).toString("yyyy-MM-dd"),
                "end_date": target.addDays(1).toString("yyyy-MM-dd"),
            }
        )
        self.host.left_dock.hide()
        self.host.show_month_day_agenda(target)
        self._render()

        self.assertEqual(self.host.current_date, today)
        self.assertEqual(self.host.view_mode_state, "monthly")
        self.assertEqual(self.settings.value("left_panel_mode"), "selected")
        self.assertEqual(self.host._last_clicked_date, target)
        self.assertTrue(self.host.left_dock.isVisible())
        self.assertNotIn(today_id, self.host._panel_task_frames)
        self.assertIn("Spans selected date", self._task_button(multi_id).text())
        add_button = next(
            button
            for button in self.host.left_dock.titleBarWidget().findChildren(QPushButton)
            if button.text() == "+"
        )
        add_button.click()
        self.assertEqual(self.host.added_dates, [target])

    def test_timed_schedule_keeps_datetime_and_hover_range(self):
        date = QDate.currentDate()
        date_text = date.toString("yyyy-MM-dd")
        task_id = task_repo.create_unified_task(
            {
                "name": "Timed startup regression",
                "type": "schedule",
                "all_day": 0,
                "deadline": f"{date_text} 09:00:00",
                "end_date": f"{date_text} 10:30:00",
            }
        )

        self._render()

        row = task_repo.get_unified_task(task_id)
        self.assertEqual(f"{date_text} 09:00:00", row["deadline"])
        self.assertEqual(f"{date_text} 10:30:00", row["end_date"])
        self._assert_date_group(date)
        self.assertIn("09:00 - 10:30", self._task_button(task_id).property("_hover_info_html"))

    def test_selected_agenda_shrinks_and_keeps_modes_and_actions_reachable(self):
        self.host.left_panel_mode = "selected"
        task_repo.create_unified_task(
            {
                "name": "Long schedule title " * 8,
                "type": "schedule",
                "all_day": 1,
                "target_date": self.host.current_date.toString("yyyy-MM-dd"),
            }
        )
        self._render()

        toolbar = self.host.left_dock.titleBarWidget()
        self.assertLessEqual(toolbar.minimumSizeHint().width(), 250)
        self.assertGreaterEqual(self.host.left_dock.minimumSizeHint().width(), 200)
        self.assertLessEqual(self.host.left_dock.minimumSizeHint().width(), 250)
        switch = toolbar.findChild(QToolButton, "schedulePanelMode")
        self.assertIsNotNone(switch)
        # It reads as the panel title: no toolbar padding pushing it right, the
        # title color and weight, and its menu cue right after the words.
        self.assertIs(toolbar.layout().itemAt(0).widget(), switch)
        self.assertTrue(switch.text().endswith(" ▾"))
        self.assertEqual(switch.accessibleName(), switch.text().strip().removesuffix(" ▾"))
        self.assertIn("padding: 2px 6px 2px 0px", switch.styleSheet())
        self.assertIn("::menu-indicator { image: none;", switch.styleSheet())
        self.assertIn("font-weight: bold", switch.styleSheet())
        actions = {action.data(): action for action in switch.menu().actions()}
        self.assertEqual(set(actions), {"today", "week", "selected"})
        self.assertTrue(actions["selected"].isChecked())
        for mode in ("today", "week", "selected"):
            actions[mode].trigger()
            self.assertEqual(self.host.left_panel_mode, mode)
            self.assertEqual(self.settings.value("left_panel_mode"), mode)

        buttons = toolbar.findChildren(QPushButton)
        next(button for button in buttons if button.text() == "+").click()
        self.assertEqual(self.host.added_dates, [self.host.current_date])
        self.host.open_work_management_dialog = Mock()
        next(button for button in buttons if button.text() == "⋯").click()
        self.host.open_work_management_dialog.assert_called_once_with(start_tab="schedule")
