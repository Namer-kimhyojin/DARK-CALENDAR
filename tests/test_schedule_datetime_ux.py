# -*- coding: utf-8 -*-
"""Schedule date/time controls exercised against isolated persistence flows."""

import os
from pathlib import Path
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QDateTime, QEvent, QSettings, Qt, QTime
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton, QWidget

from calendar_app.application.task_dialog_usecases import persist_added_task
from calendar_app.infrastructure.db import calendar_repo, db_repository_unified, task_repo
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin, route_dialog
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from tests.support import TemporaryDatabaseTestCase


class _ScheduleHost(DialogActionsMixin, TaskActionsMixin, QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.added_tasks = []
        self.refresh_calls = []
        self.active_editing_task_ids = set()

    def handle_task_added(self, task):
        self.added_tasks.append(persist_added_task(task, db_repository_unified))

    def schedule_panel_refresh(self, **kwargs):
        self.refresh_calls.append(kwargs)

    def _refresh_all_panels(self):
        self.refresh_calls.append({"all": True})


class ScheduleDatetimeUxTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # The base helper isolates SQLite only. Redirect every QSettings scope as
        # well, before database/dialog code can read the user's preferences.
        self.settings_directory = tempfile.TemporaryDirectory()
        self.original_settings_format = QSettings.defaultFormat()
        self.original_settings_paths = {
            scope: str(
                Path(
                    QSettings(
                        QSettings.Format.IniFormat, scope, "ScheduleUxTests", "Isolation"
                    ).fileName()
                ).parent.parent
            )
            for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope)
        }
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for scope in self.original_settings_paths:
            QSettings.setPath(QSettings.Format.IniFormat, scope, self.settings_directory.name)
        super().setUp()
        self.dialogs = []
        self.settings = QSettings(
            str(Path(self.settings_directory.name) / "host.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("gcal_enabled", "false")
        self.host = _ScheduleHost(self.settings)
        self.info_patch = patch.object(QMessageBox, "information")
        self.info_patch.start()
        self.addCleanup(self.info_patch.stop)
        self.failure_patch = patch.object(QMessageBox, "critical")
        self.failure = self.failure_patch.start()
        self.addCleanup(self.failure_patch.stop)
        self.assertTrue(
            calendar_repo.upsert_calendar(
                "local::schedule-ux", "local", "Schedule UX", is_default=True
            )
        )

    def tearDown(self):
        # Let zero-delay initial layout callbacks finish before deleting their
        # child controls, just as the modal event loop does in the app.
        self.app.processEvents()
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.host.close()
        self.host.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.settings.sync()
        super().tearDown()
        QSettings.setDefaultFormat(self.original_settings_format)
        for scope, path in self.original_settings_paths.items():
            QSettings.setPath(QSettings.Format.IniFormat, scope, path)
        self.settings_directory.cleanup()

    def dialog(self, **kwargs):
        kwargs.setdefault("initial_date", QDate(2026, 10, 22))
        kwargs.setdefault("initial_time", QTime(14, 10))
        dialog = UnifiedTaskDialog(self.host, task_type="schedule", **kwargs)
        self.dialogs.append(dialog)
        return dialog

    def duration_button(self, dialog, minutes):
        matches = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("quickDurationMinutes") == minutes
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def existing(self, **overrides):
        data = {
            "name": "Existing schedule",
            "type": "schedule",
            "deadline": "2026-10-22 14:10:00",
            "end_date": "2026-10-22 15:25:00",
            "target_date": "2026-10-22",
            "calendar_id": "local::schedule-ux",
            "all_day": 0,
        }
        data.update(overrides)
        task_id = task_repo.create_unified_task(data)
        self.assertIsNotNone(task_id)
        return task_id

    def route_and_save(self, edit_controls, *, task_id=None, **kwargs):
        def use_real_dialog(dialog):
            self.dialogs.append(dialog)
            edit_controls(dialog)
            dialog._save_or_create()
            return dialog.result()

        with patch.object(UnifiedTaskDialog, "exec", use_real_dialog):
            if task_id is None:
                result = route_dialog(
                    self.host,
                    "task_dialog",
                    initial_date=QDate(2026, 10, 22),
                    initial_time=QTime(14, 10),
                    task_type="schedule",
                    **kwargs,
                )
            else:
                result = route_dialog(self.host, "modify_task_dialog", task_id)
        self.failure.assert_not_called()
        self.assertEqual(result, QDialog.DialogCode.Accepted)
        return task_id if task_id is not None else self.host.added_tasks[-1]["id"]

    def test_tab_moves_from_end_date_to_start_time_in_multiday_schedule(self):
        dialog = self.dialog()
        dialog.multiple_days_check.setChecked(True)
        dialog.show()
        dialog.activateWindow()
        self.app.processEvents()
        dialog.end_date.setFocus()
        dialog.end_date.setSelectedSection(dialog.end_date.Section.DaySection)
        QTest.keyClick(dialog.end_date, Qt.Key.Key_Tab)
        self.assertIs(self.app.focusWidget(), dialog.start_time)

    def test_same_day_date_tracks_start_even_without_automatic_duration(self):
        dialog = self.dialog()
        self.assertFalse(dialog.multiple_days_check.isChecked())
        self.assertTrue(dialog.end_date.isHidden())
        self.assertTrue(dialog.end_weekday_label.isHidden())
        dialog.auto_end_check.setChecked(False)
        dialog.start_date.setDate(QDate(2026, 10, 25))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 25))
        self.assertEqual(dialog.start_time.time(), QTime(14, 10))
        self.assertEqual(dialog.end_time.time(), QTime(15, 10))

    def test_multiple_days_can_expand_and_explicitly_return_to_one_day(self):
        dialog = self.dialog()
        dialog.multiple_days_check.setChecked(True)
        self.assertFalse(dialog.end_date.isHidden())
        dialog.end_date.setDate(QDate(2026, 10, 25))
        dialog.multiple_days_check.setChecked(False)
        self.assertEqual(dialog.end_date.date(), dialog.start_date.date())
        self.assertEqual(dialog.end_time.time(), QTime(15, 10))
        self.assertTrue(dialog.end_date.isHidden())

    def test_quick_durations_set_total_length_and_preserve_exact_minutes(self):
        dialog = self.dialog()
        for minutes in (15, 30, 60, 120):
            with self.subTest(minutes=minutes):
                button = self.duration_button(dialog, minutes)
                self.assertNotIn("+", button.text())
                button.click()
                self.assertEqual(dialog.start_time.time(), QTime(14, 10))
                self.assertEqual(dialog.end_time.time(), QTime(14, 10).addSecs(minutes * 60))
                self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 22))
                self.assertTrue(dialog.auto_end_check.isChecked())
                displayed_summary = dialog.duration_summary_label.text()
                dialog._update_duration_summary()
                self.assertEqual(displayed_summary, dialog.duration_summary_label.text())

    def test_direct_numeric_input_retains_non_half_hour_values(self):
        dialog = self.dialog()
        dialog.auto_end_check.setChecked(False)
        QTest.keyClicks(dialog.start_time, "1410")
        QTest.keyClicks(dialog.end_time, "1525")
        self.assertEqual(dialog.start_time.time(), QTime(14, 10))
        self.assertEqual(dialog.end_time.time(), QTime(15, 25))
        self.assertFalse(dialog.multiple_days_check.isChecked())

    def test_more_durations_preserves_three_and_six_hour_options(self):
        dialog = self.dialog()
        menus = [button.menu() for button in dialog.end_time_shortcuts.findChildren(QPushButton)]
        actions = [action for menu in menus if menu for action in menu.actions()]
        self.assertEqual([action.data() for action in actions], [180, 360])
        for action in actions:
            with self.subTest(minutes=action.data()):
                self.assertNotIn("+", action.text())
                action.trigger()
                self.assertEqual(dialog.end_time.time(), QTime(14, 10).addSecs(action.data() * 60))

    def test_loaded_short_interval_survives_direct_start_time_change(self):
        task_id = self.existing(end_date="2026-10-22 14:17:00")
        dialog = self.dialog(task_id=task_id)
        dialog.start_time.setTime(QTime(15, 10))
        self.assertEqual(dialog.end_time.time(), QTime(15, 17))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 22))

    def test_overnight_duration_expands_date_and_survives_start_changes(self):
        dialog = self.dialog(initial_time=QTime(23, 45))
        self.duration_button(dialog, 30).click()
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 23))
        self.assertEqual(dialog.end_time.time(), QTime(0, 15))
        self.assertTrue(dialog.multiple_days_check.isChecked())
        self.assertFalse(dialog.end_date.isHidden())
        dialog.start_date.setDate(QDate(2026, 10, 24))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 25))
        self.assertEqual(dialog.end_time.time(), QTime(0, 15))
        dialog.start_time.setTime(QTime(14, 10))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 24))
        self.assertEqual(dialog.end_time.time(), QTime(14, 40))
        self.assertFalse(dialog.multiple_days_check.isChecked())
        self.assertTrue(dialog.end_date.isHidden())

    def test_popup_selected_end_datetime_is_applied_atomically(self):
        dialog = self.dialog(initial_time=QTime(23, 45))
        dialog.end_time.dateTimeSelected.emit(QDateTime(QDate(2026, 10, 23), QTime(0, 30)))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 23))
        self.assertEqual(dialog.end_time.time(), QTime(0, 30))
        self.assertTrue(dialog.multiple_days_check.isChecked())
        dialog.start_time.setTime(QTime(23, 30))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 23))
        self.assertEqual(dialog.end_time.time(), QTime(0, 15))

    def test_all_day_toggle_preserves_timed_values_and_same_day_tracking(self):
        dialog = self.dialog(end_time=QTime(15, 25))
        dialog.all_day_check.setChecked(True)
        self.assertTrue(dialog.start_time.isHidden())
        self.assertTrue(dialog.end_time.isHidden())
        dialog.auto_end_check.setChecked(False)
        dialog.start_date.setDate(QDate(2026, 10, 25))
        self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 25))
        dialog.all_day_check.setChecked(False)
        self.assertEqual(dialog.start_time.time(), QTime(14, 10))
        self.assertEqual(dialog.end_time.time(), QTime(15, 25))
        self.assertFalse(dialog.start_time.isHidden())
        self.assertFalse(dialog.end_time.isHidden())

    def test_loaded_multiday_schedule_is_expanded_without_mutating_dates(self):
        for all_day in (0, 1):
            with self.subTest(all_day=all_day):
                task_id = self.existing(
                    deadline="2026-10-22 00:00:00" if all_day else "2026-10-22 14:10:00",
                    end_date="2026-10-25 23:59:59" if all_day else "2026-10-25 15:25:00",
                    all_day=all_day,
                )
                before = task_repo.get_unified_task(task_id)
                dialog = self.dialog(task_id=task_id)
                self.assertTrue(dialog.multiple_days_check.isChecked())
                self.assertFalse(dialog.end_date.isHidden())
                self.assertEqual(dialog.start_date.date(), QDate(2026, 10, 22))
                self.assertEqual(dialog.end_date.date(), QDate(2026, 10, 25))
                dialog.name_edit.setText("Title only changed")
                dialog._save_changes()
                after = task_repo.get_unified_task(task_id)
                for key in ("deadline", "end_date", "all_day", "calendar_id"):
                    self.assertEqual(after[key], before[key], key)

    def test_create_modify_move_copy_roundtrip_preserves_duration_and_calendar(self):
        def create_controls(dialog):
            dialog.name_edit.setText("Exact minute meeting")
            self.duration_button(dialog, 30).click()

        task_id = self.route_and_save(create_controls)
        created = task_repo.get_unified_task(task_id)
        self.assertEqual(created["deadline"], "2026-10-22 14:10:00")
        self.assertEqual(created["end_date"], "2026-10-22 14:40:00")
        self.assertEqual(created["calendar_id"], "local::schedule-ux")

        def modify_controls(dialog):
            self.assertFalse(dialog.multiple_days_check.isChecked())
            dialog.auto_end_check.setChecked(False)
            dialog.start_date.setDate(QDate(2026, 10, 23))
            dialog.start_time.setTime(QTime(16, 10))
            self.duration_button(dialog, 15).click()

        self.route_and_save(modify_controls, task_id=task_id)
        modified = task_repo.get_unified_task(task_id)
        self.assertEqual(modified["deadline"], "2026-10-23 16:10:00")
        self.assertEqual(modified["end_date"], "2026-10-23 16:25:00")

        self.host.handle_task_dropped([task_id], QDate(2026, 10, 24), QTime(23, 50), "move")
        moved = task_repo.get_unified_task(task_id)
        self.assertEqual(moved["id"], task_id)
        self.assertEqual(moved["deadline"], "2026-10-24 23:50:00")
        self.assertEqual(moved["end_date"], "2026-10-25 00:05:00")
        self.assertEqual(moved["calendar_id"], "local::schedule-ux")
        self.assertTrue(self.dialog(task_id=task_id).multiple_days_check.isChecked())

        self.host.handle_task_dropped([task_id], QDate(2026, 10, 26), QTime(9, 10), "copy")
        rows = (
            task_repo.get_connection().execute("SELECT * FROM unified_task ORDER BY id").fetchall()
        )
        self.assertEqual(len(rows), 2)
        copied = dict(next(row for row in rows if row["id"] != task_id))
        self.assertEqual(copied["deadline"], "2026-10-26 09:10:00")
        self.assertEqual(copied["end_date"], "2026-10-26 09:25:00")
        self.assertEqual(copied["calendar_id"], "local::schedule-ux")
        self.assertEqual(task_repo.get_unified_task(task_id)["deadline"], moved["deadline"])
        self.assertFalse(self.dialog(task_id=copied["id"]).multiple_days_check.isChecked())

    def test_all_day_create_move_copy_keeps_inclusive_period(self):
        def create_controls(dialog):
            dialog.name_edit.setText("Three day event")
            dialog.all_day_check.setChecked(True)
            dialog.multiple_days_check.setChecked(True)
            dialog.end_date.setDate(QDate(2026, 10, 24))

        task_id = self.route_and_save(create_controls)
        created = task_repo.get_unified_task(task_id)
        # Existing all-day payloads retain hidden clock values. Inclusive dates
        # and the all_day flag determine their visible span.
        self.assertEqual(created["deadline"], "2026-10-22 14:10:00")
        self.assertEqual(created["end_date"], "2026-10-24 15:10:00")
        self.host.handle_task_dropped([task_id], QDate(2026, 10, 26), None, "move")
        moved = task_repo.get_unified_task(task_id)
        self.assertEqual(moved["deadline"], "2026-10-26 14:10:00")
        self.assertEqual(moved["end_date"], "2026-10-28 15:10:00")
        self.host.handle_task_dropped([task_id], QDate(2026, 11, 2), None, "copy")
        copied = (
            task_repo.get_connection()
            .execute("SELECT * FROM unified_task WHERE id != ?", (task_id,))
            .fetchone()
        )
        self.assertEqual(copied["deadline"], "2026-11-02 14:10:00")
        self.assertEqual(copied["end_date"], "2026-11-04 15:10:00")
        self.assertEqual(copied["calendar_id"], "local::schedule-ux")
        self.assertEqual(copied["all_day"], 1)
