# -*- coding: utf-8 -*-
"""Deadline editor regressions with isolated SQLite and Qt preferences."""

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QEvent, QSettings, Qt, QTime
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton


class DirectiveDatetimeUxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_settings_format = QSettings.defaultFormat()
        self.original_settings_paths = {
            scope: str(
                Path(
                    QSettings(
                        QSettings.Format.IniFormat, scope, "DirectiveUxTests", "Isolation"
                    ).fileName()
                ).parent.parent
            )
            for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope)
        }
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for scope in self.original_settings_paths:
            QSettings.setPath(QSettings.Format.IniFormat, scope, self.directory.name)
        # Import UI modules only after isolating preferences: i18n initializes a
        # global manager and may save its detected language during first import.
        from calendar_app.infrastructure.i18n import t
        from calendar_app.presentation.dialogs.directive_dialog import DirectiveDialog
        from calendar_app.presentation.dialogs.time_picker_widget import (
            DatePickerWidget,
            TimePickerWidget,
        )

        self.translate = t
        self.dialog_class = DirectiveDialog
        self.date_picker_class = DatePickerWidget
        self.time_picker_class = TimePickerWidget
        self.db_path = str(Path(self.directory.name) / "directives.db")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE task_directive (id INTEGER PRIMARY KEY, content TEXT, "
                "receiver_name TEXT, deadline TEXT, status TEXT, memo TEXT, priority TEXT)"
            )
        conn.close()
        self.db_patch = patch(
            "calendar_app.presentation.dialogs.directive_dialog.DB_PATH", self.db_path
        )
        self.db_patch.start()
        self.connections = []
        original_connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            self.connections.append(connection)
            return connection

        self.connection_patch = patch.object(sqlite3, "connect", tracked_connect)
        self.connection_patch.start()
        self.error_patch = patch.object(QMessageBox, "critical")
        self.error = self.error_patch.start()
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.error_patch.stop()
        self.db_patch.stop()
        self.connection_patch.stop()
        for connection in self.connections:
            connection.close()
        QSettings.setDefaultFormat(self.original_settings_format)
        for scope, path in self.original_settings_paths.items():
            QSettings.setPath(QSettings.Format.IniFormat, scope, path)
        self.directory.cleanup()

    def dialog(self, **kwargs):
        kwargs.setdefault("initial_date", QDate(2026, 10, 22))
        dialog = self.dialog_class(**kwargs)
        self.dialogs.append(dialog)
        self.error.assert_not_called()
        return dialog

    def rows(self):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT id, content, receiver_name, deadline, status, memo, priority "
                "FROM task_directive ORDER BY id"
            ).fetchall()

    def existing(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO task_directive "
                "(content, receiver_name, deadline, status, memo, priority) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("Review", "Team", "2026-10-25 14:10", "in_progress", "Details", "high"),
            )
            return cursor.lastrowid

    def choose_time(self, dialog, label):
        dialog.show()
        self.app.processEvents()
        dialog.deadline_time.show_time_dropdown()
        self.app.processEvents()
        choices = dialog.deadline_time._dropdown_list
        matches = choices.findItems(label, Qt.MatchFlag.MatchExactly)
        self.assertEqual(len(matches), 1)
        choices.scrollToItem(matches[0])
        self.app.processEvents()
        QTest.mouseClick(
            choices.viewport(),
            Qt.MouseButton.LeftButton,
            pos=choices.visualItemRect(matches[0]).center(),
        )
        self.assertFalse(dialog.deadline_time._dropdown_popup.isVisible())

    def test_single_deadline_keeps_shared_editor_metrics_and_initial_date(self):
        dialog = self.dialog()
        self.assertEqual(len(dialog.findChildren(self.date_picker_class)), 1)
        self.assertEqual(len(dialog.findChildren(self.time_picker_class)), 1)
        self.assertEqual(dialog.deadline_date.date(), QDate(2026, 10, 22))
        self.assertEqual(dialog.deadline_time.time(), QTime(12, 0))
        self.assertTrue(dialog.deadline_time._dropdown_enabled)
        self.assertEqual(dialog.deadline_date.minimumHeight(), dialog.deadline_time.minimumHeight())
        self.assertTrue(dialog.deadline_date.accessibleName())
        self.assertTrue(dialog.deadline_time.accessibleName())

    def test_create_saves_dropdown_time_without_changing_deadline_date(self):
        dialog = self.dialog()
        dialog.content_edit.setText("Submit report")
        dialog.receiver_edit.setText("Team")
        dialog.memo_edit.setPlainText("Attachment")
        dialog.set_priority("high")
        self.choose_time(dialog, "18:30")
        dialog.save_data()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(
            self.rows()[0][1:],
            ("Submit report", "Team", "2026-10-22 18:30", "in_progress", "Attachment", "high"),
        )
        self.error.assert_not_called()

    def test_edit_loads_and_preserves_non_half_hour_deadline(self):
        task_id = self.existing()
        before = self.rows()
        dialog = self.dialog(task_id=task_id)
        self.assertEqual(dialog.deadline_date.date(), QDate(2026, 10, 25))
        self.assertEqual(dialog.deadline_time.time(), QTime(14, 10))
        self.assertIn("14:10", [label for label, _ in dialog.deadline_time._time_choices()])
        dialog.save_data()
        self.assertEqual(self.rows(), before)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.error.assert_not_called()

    def test_edit_accepts_numeric_date_and_exact_time_without_changing_identity(self):
        task_id = self.existing()
        dialog = self.dialog(task_id=task_id)
        QTest.keyClicks(dialog.deadline_date, "20261028")
        QTest.keyClicks(dialog.deadline_time, "0925")
        dialog.save_data()
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], task_id)
        self.assertEqual(rows[0][3], "2026-10-28 09:25")
        self.assertEqual(rows[0][1:3], ("Review", "Team"))
        self.assertEqual(rows[0][4:], ("in_progress", "Details", "high"))
        self.error.assert_not_called()

    def test_existing_date_and_time_shortcuts_remain_available(self):
        dialog = self.dialog()
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        for key, days in (
            ("quick_today", 0),
            ("quick_tomorrow", 1),
            ("quick_plus_3d", 3),
            ("quick_plus_1w", 7),
        ):
            buttons[self.translate(f"dialog.directive.{key}")].click()
            self.assertEqual(dialog.deadline_date.date(), QDate.currentDate().addDays(days))
        for hour in (9, 12, 15, 18):
            buttons[f"{hour:02}:00"].click()
            self.assertEqual(dialog.deadline_time.time(), QTime(hour, 0))

    def test_required_content_validation_still_prevents_empty_save(self):
        dialog = self.dialog()
        dialog.content_edit.setText("  ")
        dialog.save_data()
        self.assertEqual(self.rows(), [])
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog._content_err.isHidden())
        self.error.assert_not_called()
