# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QTime
from PyQt6.QtWidgets import QApplication, QBoxLayout, QPushButton, QScrollArea

from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from calendar_app.infrastructure.i18n import t
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

    def test_all_day_schedule_keeps_date_shortcuts_and_hides_time_actions(self):
        dialog = UnifiedTaskDialog(task_type="schedule", initial_date=QDate(2026, 7, 11))
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()
        date_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("quickAction") in {"today", "tomorrow"}
        ]

        self.assertTrue(dialog.all_day_check.isChecked())
        self.assertTrue(all(not button.isHidden() for button in date_buttons))
        self.assertTrue(dialog.start_time_shortcuts.isHidden())
        self.assertTrue(dialog.end_time_shortcuts.isHidden())

    def test_subscription_prefill_explicitly_restores_all_day_mode(self):
        dialog = UnifiedTaskDialog(
            task_type="schedule",
            initial_date=QDate(2026, 8, 15),
            initial_time=QTime(9, 0),
            end_date=QDate(2026, 8, 16),
            prefill_dict={"name": "Conference", "all_day": True},
        )
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        self.assertTrue(dialog.all_day_check.isChecked())
        self.assertTrue(dialog.start_time.isHidden())
        self.assertTrue(dialog.end_time.isHidden())
        self.assertEqual(dialog.end_date.date(), QDate(2026, 8, 16))

    def test_period_inputs_reflow_for_schedule_and_routine(self):
        for task_type in ("schedule", "routine"):
            with self.subTest(task_type=task_type):
                dialog = UnifiedTaskDialog(task_type=task_type)
                self.addCleanup(dialog.close)

                dialog._update_period_layout_for_width(640)
                self.assertEqual(
                    dialog._period_range_layout.direction(),
                    QBoxLayout.Direction.TopToBottom,
                )

                dialog._update_period_layout_for_width(680)
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
        self.assertEqual(dialog.start_date.displayFormat(), "yyyy-MM-dd")
        self.assertEqual(dialog.end_date.displayFormat(), "yyyy-MM-dd")
        self.assertTrue(dialog.start_weekday_label.text())
        self.assertTrue(dialog.end_weekday_label.text())

    def test_schedule_quick_actions_update_start_and_keep_duration(self):
        dialog = UnifiedTaskDialog(
            task_type="schedule",
            initial_date=QDate(2026, 7, 11),
            initial_time=QTime(14, 30),
        )
        self.addCleanup(dialog.close)
        tomorrow_btn = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("quickAction") == "tomorrow"
        )

        tomorrow_btn.click()

        self.assertEqual(dialog.start_date.date(), QDate.currentDate().addDays(1))
        self.assertEqual(dialog.start_time.time(), QTime(14, 30))
        self.assertEqual(dialog.end_time.time(), QTime(15, 30))

    def test_two_day_all_day_schedule_counts_dates_and_keeps_span(self):
        start = QDate(2026, 8, 13)
        dialog = UnifiedTaskDialog(
            task_type="schedule",
            initial_date=start,
            end_date=start.addDays(1),
        )
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        self.assertTrue(dialog.all_day_check.isChecked())
        self.assertEqual(dialog._all_day_span_days, 2)
        self.assertEqual(
            dialog.duration_summary_label.text(),
            t(
                "dialog.task.all_day_duration_summary",
                "📅 {start} → {end} · 총 {count}일 · 종일",
                start="8/13",
                end="8/14",
                count=2,
            ),
        )
        self.assertEqual(
            dialog.auto_end_check.text(),
            t("dialog.task.keep_period", "기간 유지"),
        )

        dialog.start_date.setDate(start.addDays(2))
        self._app.processEvents()

        self.assertEqual(dialog.end_date.date(), start.addDays(3))
        self.assertEqual(dialog._all_day_span_days, 2)

    def test_invalid_all_day_period_is_blocked_with_inline_feedback(self):
        start = QDate(2026, 8, 13)
        dialog = UnifiedTaskDialog(
            task_type="schedule",
            initial_date=start,
            end_date=start.addDays(1),
        )
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("Invalid period")
        dialog.end_date.setDate(start.addDays(-1))

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.task_repo.create_unified_task"
        ) as create_task:
            dialog._create_task()

        create_task.assert_not_called()
        self.assertFalse(dialog.status_feedback_label.isHidden())
        self.assertEqual(
            dialog.status_feedback_label.text(),
            t(
                "dialog.task.date_end_before_start",
                "종료일은 시작일보다 빠를 수 없습니다. 종료일을 다시 선택해 주세요.",
            ),
        )

    def test_schedule_quick_actions_have_clear_groups_icons_and_semantics(self):
        dialog = UnifiedTaskDialog(
            task_type="schedule",
            initial_date=QDate(2026, 7, 11),
            initial_time=QTime(14, 30),
        )
        self.addCleanup(dialog.close)
        quick_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("quickActionButton")
        ]

        self.assertGreaterEqual(len(quick_buttons), 6)
        self.assertTrue(all(not button.icon().isNull() for button in quick_buttons))
        self.assertTrue(all(button.accessibleName() for button in quick_buttons))
        self.assertTrue(all(button.accessibleDescription() for button in quick_buttons))
        self.assertTrue(
            all(button.toolTip() == button.accessibleDescription() for button in quick_buttons)
        )
        self.assertTrue(
            any(button.property("quickDurationMinutes") == 60 for button in quick_buttons)
        )
        self.assertFalse(dialog.start_time_shortcuts.isHidden())
        self.assertFalse(dialog.end_time_shortcuts.isHidden())

    def test_missing_name_uses_inline_feedback_instead_of_modal_warning(self):
        dialog = UnifiedTaskDialog(task_type="schedule")
        self.addCleanup(dialog.close)
        dialog.tabs.setCurrentIndex(1)

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.QMessageBox.warning"
        ) as warning:
            dialog._create_task()

        warning.assert_not_called()
        self.assertEqual(0, dialog.tabs.currentIndex())
        self.assertFalse(dialog.status_feedback_label.isHidden())
        self.assertTrue(dialog.status_feedback_label.text())
        self.assertTrue(dialog.status_feedback_label.accessibleDescription())

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
        self.assertGreaterEqual(create_dialog.width(), 640)
        self.assertLessEqual(create_dialog.width(), 700)
        self.assertGreaterEqual(create_dialog.height(), 500)
        self.assertLessEqual(create_dialog.height(), 660)

    def test_schedule_dialog_stays_compact_and_scrollable(self):
        dialog = UnifiedTaskDialog(task_type="schedule")
        self.addCleanup(dialog.close)

        self.assertLessEqual(dialog.width(), 700)
        self.assertLessEqual(dialog.height(), 620)
        self.assertLessEqual(dialog.maximumWidth(), 700)
        self.assertLessEqual(dialog.maximumHeight(), 660)
        self.assertTrue(
            all(isinstance(dialog.tabs.widget(i), QScrollArea) for i in range(dialog.tabs.count()))
        )

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
