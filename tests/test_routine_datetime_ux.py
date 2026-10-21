# -*- coding: utf-8 -*-
"""Routine create/modify clock choices with isolated SQLite and settings."""

import os
from pathlib import Path
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QDateTime, QEvent, QLocale, QSettings, Qt, QTime
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton

from calendar_app.infrastructure.db import task_repo
from calendar_app.presentation.dialogs.routine_modify_dialog import RoutineModifyDialog
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class RoutineDatetimeUxTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings_directory = tempfile.TemporaryDirectory()
        self.previous_format = QSettings.defaultFormat()
        self.previous_paths = {
            scope: str(
                Path(
                    QSettings(
                        QSettings.Format.IniFormat, scope, "RoutineUxTests", "Isolation"
                    ).fileName()
                ).parent.parent
            )
            for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope)
        }
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for scope in self.previous_paths:
            QSettings.setPath(QSettings.Format.IniFormat, scope, self.settings_directory.name)
        super().setUp()
        self.dialogs = []
        for method in ("information", "warning", "critical"):
            message_patch = patch.object(QMessageBox, method)
            message_patch.start()
            self.addCleanup(message_patch.stop)

    def tearDown(self):
        self.app.processEvents()
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        super().tearDown()
        QSettings.setDefaultFormat(self.previous_format)
        for scope, path in self.previous_paths.items():
            QSettings.setPath(QSettings.Format.IniFormat, scope, path)
        self.settings_directory.cleanup()

    def create_dialog(self):
        dialog = UnifiedTaskDialog(
            task_type="routine", initial_date=QDate(2026, 10, 22), initial_time=QTime(9, 10)
        )
        self.dialogs.append(dialog)
        return dialog

    def existing_dialog(self, **overrides):
        data = {
            "name": "Routine clock test",
            "type": "routine",
            "deadline": "2026-10-22 09:10:00",
            "target_date": "2026-10-22",
            "cycle_type": "single",
            "recurrence": "mode=single",
            "description": "Keep memo",
            "tags": "keep-tag",
        }
        data.update(overrides)
        task_id = task_repo.create_unified_task(data)
        self.assertIsNotNone(task_id)
        dialog = RoutineModifyDialog(task_id)
        self.dialogs.append(dialog)
        return dialog, task_id

    def choose_time(self, dialog, value):
        dialog.show()
        self.app.processEvents()
        picker = dialog.start_time
        self.assertTrue(picker._dropdown_enabled)
        QTest.keyClick(picker, Qt.Key.Key_F4)
        self.app.processEvents()
        items = picker._dropdown_list
        target = next(
            index
            for index in range(items.count())
            if items.item(index).data(Qt.ItemDataRole.UserRole).time() == value
        )
        items.setCurrentRow(target)
        QTest.keyClick(items, Qt.Key.Key_Return)
        self.assertEqual(picker.time(), value)

    def quick_button(self, dialog, action):
        return next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("quickAction") == action
        )

    def test_create_routine_saves_dropdown_and_exact_numeric_time(self):
        dialog = self.create_dialog()
        dialog.name_edit.setText("Create routine clock")
        self.choose_time(dialog, QTime(16, 30))
        QTest.keyClicks(dialog.start_time, "1645")
        dialog.start_date.setDate(QDate(2026, 10, 23))
        dialog.save_data()
        task = task_repo.get_unified_task(dialog._saved_task_id)
        self.assertEqual(task["deadline"], "2026-10-23 16:45:00")
        self.assertEqual(task["target_date"], "2026-10-23")
        self.assertEqual(task["cycle_type"], "single")
        self.assertEqual(task["recurrence"], "mode=single")

    def test_modify_routine_saves_date_time_without_losing_other_fields(self):
        dialog, task_id = self.existing_dialog()
        self.choose_time(dialog, QTime(15, 30))
        dialog.start_date.setDate(QDate(2026, 10, 24))
        dialog._save_changes()
        task = task_repo.get_unified_task(task_id)
        self.assertEqual(task["deadline"], "2026-10-24 15:30:00")
        self.assertEqual(task["target_date"], "2026-10-24")
        self.assertEqual(task["description"], "Keep memo")
        self.assertEqual(task["tags"], "keep-tag")
        self.assertEqual(task["recurrence"], "mode=single")

    def test_unified_routine_quick_date_keeps_weekday_badge_current(self):
        dialog = self.create_dialog()
        self.quick_button(dialog, "tomorrow").click()
        expected = QDate.currentDate().addDays(1)
        self.assertEqual(dialog.start_date.date(), expected)
        self.assertEqual(dialog.start_weekday_label.text(), QLocale().toString(expected, "ddd"))

    def test_modify_today_tomorrow_keep_time_and_now_uses_current_minute(self):
        dialog, _ = self.existing_dialog()
        dialog.start_time.setTime(QTime(14, 10))
        self.quick_button(dialog, "today").click()
        self.assertEqual(dialog.start_date.date(), QDate.currentDate())
        self.assertEqual(dialog.start_time.time(), QTime(14, 10))
        self.quick_button(dialog, "tomorrow").click()
        self.assertEqual(dialog.start_date.date(), QDate.currentDate().addDays(1))
        self.assertEqual(dialog.start_time.time(), QTime(14, 10))
        before = QDateTime.currentDateTime()
        self.quick_button(dialog, "now").click()
        after = QDateTime.currentDateTime()
        selected = QDateTime(dialog.start_date.date(), dialog.start_time.time())
        self.assertLessEqual(before.addSecs(-60), selected)
        self.assertLessEqual(selected, after)

    def test_modify_repeat_rule_and_series_metadata_survive_date_change(self):
        dialog, task_id = self.existing_dialog(
            cycle_type="weekly",
            recurrence="mode=weekly;weekday=3",
            series_id="routine-clock-series",
            series_order=2,
            series_total=4,
        )
        self.assertTrue(dialog.repeat_task_radio.isChecked())
        self.assertTrue(dialog._routine_time_group.isHidden())
        self.assertEqual(dialog._build_recurrence_rule(), "mode=weekly;weekday=3")
        dialog.start_date.setDate(QDate(2026, 10, 29))
        dialog._save_changes()
        task = task_repo.get_unified_task(task_id)
        self.assertEqual(task["deadline"], "2026-10-29 09:10:00")
        self.assertEqual(task["cycle_type"], "weekly")
        self.assertEqual(task["recurrence"], "mode=weekly;weekday=3")
        self.assertEqual(task["series_id"], "routine-clock-series")
        self.assertEqual(task["series_order"], 2)
        self.assertEqual(task["series_total"], 4)

    def test_create_repeat_series_keeps_dates_and_chosen_clock(self):
        dialog = self.create_dialog()
        dialog.name_edit.setText("Weekly clock choice")
        self.choose_time(dialog, QTime(15, 30))
        dialog.repeat_task_radio.setChecked(True)
        dialog.repeat_cycle_combo.setCurrentIndex(dialog.repeat_cycle_combo.findData("weekly"))
        dialog.routine_period_end_date.setDate(QDate(2026, 11, 5))
        self.assertTrue(dialog._routine_time_group.isHidden())
        dialog.save_data()
        rows = (
            task_repo.get_connection()
            .execute(
                "SELECT deadline, target_date, cycle_type, series_id, series_total "
                "FROM unified_task WHERE name=? ORDER BY target_date",
                ("Weekly clock choice",),
            )
            .fetchall()
        )
        self.assertEqual(
            [row["target_date"] for row in rows],
            ["2026-10-22", "2026-10-29", "2026-11-05"],
        )
        self.assertTrue(all(row["deadline"].endswith("15:30:00") for row in rows))
        self.assertEqual({row["cycle_type"] for row in rows}, {"weekly"})
        self.assertEqual(len({row["series_id"] for row in rows}), 1)
        self.assertEqual({row["series_total"] for row in rows}, {3})
