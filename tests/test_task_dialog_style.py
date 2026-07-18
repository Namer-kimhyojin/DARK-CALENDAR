# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QTime
from PyQt6.QtWidgets import QApplication, QBoxLayout, QPushButton, QScrollArea

from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class TaskDialogStyleTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_editor_token_skin_is_applied_to_unified_task_dialog(self):
        dialog = UnifiedTaskDialog(task_type="schedule")
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.objectName(), "TaskEditorDialog")
        self.assertEqual(dialog.tabs.objectName(), "TaskEditorTabs")
        self.assertEqual(dialog.name_edit.objectName(), "TaskTitleEdit")
        self.assertEqual(dialog.calendar_combo.objectName(), "TaskCalendarCombo")
        self.assertTrue(
            all(isinstance(dialog.tabs.widget(i), QScrollArea) for i in range(dialog.tabs.count()))
        )

        stylesheet = dialog.styleSheet()
        self.assertIn("QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs::pane", stylesheet)
        self.assertIn("QPushButton#primary_btn", stylesheet)
        self.assertIn('QPushButton#ghost_btn[accentVariant="true"]', stylesheet)
        self.assertIn("QLineEdit#TaskTitleEdit", stylesheet)
        self.assertIn("QDialog#TaskEditorDialog QStackedWidget", stylesheet)
        self.assertNotIn("background: #eef1f4;", stylesheet)

        create_buttons = [
            btn for btn in dialog.findChildren(QPushButton) if btn.objectName() == "primary_btn"
        ]
        self.assertGreaterEqual(len(create_buttons), 1)

    def test_modify_dialog_uses_same_editor_token_skin(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Modify palette target",
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": "2026-03-26 12:00:00",
                "end_date": "2026-03-26 13:00:00",
                "target_date": "2026-03-26",
            }
        )
        self.assertIsNotNone(task_id)

        dialog = UnifiedTaskDialog(task_type="schedule", task_id=task_id)
        self.addCleanup(dialog.close)

        stylesheet = dialog.styleSheet()
        self.assertIn("QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs::pane", stylesheet)
        self.assertIn("QPushButton#primary_btn", stylesheet)
        self.assertNotIn("background: #eef1f4;", stylesheet)
        self.assertIn("QDialog#TaskEditorDialog QStackedWidget", stylesheet)

    def test_timed_schedule_defaults_to_one_hour_and_shows_time_fields(self):
        dialog = UnifiedTaskDialog(
            task_type="schedule",
            initial_date=QDate(2026, 7, 11),
            initial_time=QTime(14, 30),
        )
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        self.assertFalse(dialog.all_day_check.isChecked())
        self.assertEqual(dialog.start_time.time(), QTime(14, 30))
        self.assertEqual(dialog.end_time.time(), QTime(15, 30))
        self.assertFalse(dialog.start_time.isHidden())
        self.assertFalse(dialog.end_time.isHidden())

    def test_period_inputs_reflow_for_schedule_and_routine(self):
        for task_type in ("schedule", "routine"):
            with self.subTest(task_type=task_type):
                dialog = UnifiedTaskDialog(task_type=task_type)
                self.addCleanup(dialog.close)

                dialog._update_period_layout_for_width(680)
                self.assertEqual(
                    dialog._period_range_layout.direction(),
                    QBoxLayout.Direction.TopToBottom,
                )

                dialog._update_period_layout_for_width(780)
                self.assertEqual(
                    dialog._period_range_layout.direction(),
                    QBoxLayout.Direction.LeftToRight,
                )

    def test_schedule_period_controls_have_accessible_labels(self):
        dialog = UnifiedTaskDialog(task_type="schedule")
        self.addCleanup(dialog.close)

        self.assertTrue(dialog.start_date.accessibleName())
        self.assertTrue(dialog.start_time.accessibleName())
        self.assertTrue(dialog.end_date.accessibleName())
        self.assertTrue(dialog.end_time.accessibleName())
        self.assertIs(dialog.start_label_widget.buddy(), dialog.start_date)
        self.assertIs(dialog.end_label_widget.buddy(), dialog.end_date)

    def test_routine_create_and_modify_use_same_initial_size(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Routine sizing target",
                "type": "routine",
                "priority": "normal",
                "status": "pending",
                "cycle_type": "single",
                "deadline": "2026-07-11 12:00:00",
                "target_date": "2026-07-11",
            }
        )
        create_dialog = UnifiedTaskDialog(task_type="routine")
        modify_dialog = UnifiedTaskDialog(task_type="routine", task_id=task_id)
        self.addCleanup(create_dialog.close)
        self.addCleanup(modify_dialog.close)

        self.assertEqual(create_dialog.size(), modify_dialog.size())
        self.assertGreaterEqual(create_dialog.width(), 720)
        self.assertGreaterEqual(create_dialog.height(), 560)

    def test_schedule_color_swatch_fits_detail_view_in_create_and_modify(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Color swatch sizing target",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-07-11 09:00:00",
                "end_date": "2026-07-11 10:00:00",
                "target_date": "2026-07-11",
            }
        )
        for dialog in (
            UnifiedTaskDialog(task_type="schedule"),
            UnifiedTaskDialog(task_type="schedule", task_id=task_id),
        ):
            self.addCleanup(dialog.close)
            dialog.tabs.setCurrentIndex(1)
            dialog.show()
            self._app.processEvents()

            visible = dialog.color_swatch.visibleRegion().boundingRect()
            self.assertLessEqual(dialog.color_swatch.minimumSizeHint().width(), 400)
            self.assertEqual(visible.width(), dialog.color_swatch.width())

    def test_routine_action_and_alarm_buttons_fit_translated_labels(self):
        dialog = UnifiedTaskDialog(task_type="routine")
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        buttons = [
            dialog.manage_checklist_btn,
            dialog.cancel_btn,
            dialog.save_continue_btn,
            dialog.save_btn,
            dialog.set_default_alarm_btn,
        ]
        for button in buttons:
            with self.subTest(label=button.text()):
                required = button.fontMetrics().horizontalAdvance(button.text())
                self.assertGreaterEqual(button.width(), required)


if __name__ == "__main__":
    unittest.main()
