# -*- coding: utf-8 -*-
"""Regression coverage for draft protection and monthly keyboard interaction."""

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import task_repo
from calendar_app.presentation.calendar.month_navigation import MonthGridNavigation
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from calendar_app.presentation.widgets.ui_components import ClickableCell
from tests.support import TemporaryDatabaseTestCase


class DraftProtectionTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self, **kwargs):
        dialog = UnifiedTaskDialog(task_type="schedule", initial_date=QDate(2026, 11, 14), **kwargs)
        self.addCleanup(dialog.done, 0)  # Teardown deliberately bypasses the user cancel action.
        dialog.show()
        self.app.processEvents()
        return dialog

    def test_escape_cancel_and_window_close_keep_or_discard_changed_draft(self):
        for action in ("escape", "cancel", "close"):
            with self.subTest(action=action):
                dialog = self.dialog()
                dialog.name_edit.setText("작성 중인 일정")

                def close(action=action, dialog=dialog):
                    if action == "escape":
                        QTest.keyClick(dialog, Qt.Key.Key_Escape)
                    elif action == "cancel":
                        dialog.cancel_btn.click()
                    else:
                        dialog.close()

                with patch.object(
                    dialog, "_confirm_discard_changes", return_value=False
                ) as confirm:
                    close()
                    confirm.assert_called_once()
                    self.assertTrue(dialog.isVisible())
                    self.assertEqual(dialog.name_edit.text(), "작성 중인 일정")
                with patch.object(dialog, "_confirm_discard_changes", return_value=True):
                    close()
                    self.assertFalse(dialog.isVisible())

    def test_real_confirmation_defaults_to_keep_and_escape_keeps_text(self):
        dialog = self.dialog()
        dialog.memo_toggle.click()
        dialog.memo_edit.setPlainText("메모만 입력한 경우")
        observed = []

        def dismiss_confirmation():
            box = self.app.activeModalWidget()
            observed.append(isinstance(box, QMessageBox))
            observed.append(
                box.buttonRole(box.defaultButton()) == QMessageBox.ButtonRole.RejectRole
            )
            QTest.keyClick(box, Qt.Key.Key_Escape)

        QTimer.singleShot(0, dismiss_confirmation)
        dialog.reject()
        self.assertEqual(observed, [True, True])
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.memo_edit.toPlainText(), "메모만 입력한 경우")

    def test_unchanged_prefill_and_disclosures_close_without_confirmation(self):
        dialog = self.dialog(prefill_dict={"name": "외부에서 복사", "memo": "기존 메모"})
        self.assertFalse(dialog.memo_panel.isHidden())
        dialog.details_toggle.click()
        dialog.memo_toggle.click()
        dialog.name_edit.setText("수정")
        dialog.name_edit.setText("외부에서 복사")
        with patch.object(dialog, "_confirm_discard_changes") as confirm:
            dialog.reject()
            confirm.assert_not_called()
        self.assertFalse(dialog.isVisible())

    def test_continuous_save_resets_baseline_and_next_edit_is_protected(self):
        dialog = self.dialog()
        dialog.name_edit.setText("연속 등록 첫 일정")
        dialog._create_task(continue_after_save=True)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(
            task_repo.get_unified_task(dialog._saved_task_id)["name"], "연속 등록 첫 일정"
        )
        self.assertEqual(dialog._draft_state(), dialog._draft_baseline)
        dialog.name_edit.setText("두 번째 일정")
        with patch.object(dialog, "_confirm_discard_changes", return_value=False) as confirm:
            dialog.reject()
            confirm.assert_called_once()
        self.assertTrue(dialog.isVisible())

    def test_successful_save_closes_without_discard_confirmation(self):
        dialog = self.dialog()
        dialog.name_edit.setText("저장 완료")
        with patch.object(dialog, "_confirm_discard_changes") as confirm:
            dialog._create_task()
            confirm.assert_not_called()
        self.assertFalse(dialog.isVisible())
        self.assertEqual(task_repo.get_unified_task(dialog._saved_task_id)["name"], "저장 완료")

    def test_modify_cancel_retains_lock_and_database_until_confirmed(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "원래 일정",
                "type": "schedule",
                "deadline": "2026-11-14 09:00:00",
                "end_date": "2026-11-14 10:00:00",
                "description": "원래 메모",
            }
        )
        host = QWidget()
        self.addCleanup(host.close)
        host.active_editing_task_ids = {task_id}
        dialog = self.dialog(parent=host, task_id=task_id)
        self.assertFalse(dialog.memo_panel.isHidden())
        dialog.start_date.setDate(QDate(2026, 11, 20))
        with patch.object(dialog, "_confirm_discard_changes", return_value=False):
            dialog.close()
        self.assertIn(task_id, host.active_editing_task_ids)
        self.assertEqual(task_repo.get_unified_task(task_id)["deadline"], "2026-11-14 09:00:00")
        with patch.object(dialog, "_confirm_discard_changes", return_value=True):
            dialog.close()
        self.assertNotIn(task_id, host.active_editing_task_ids)

    def test_compact_sheet_keeps_equal_footer_buttons_and_optional_memo(self):
        host = QMainWindow()
        self.addCleanup(host.close)
        host.resize(1240, 850)
        host.show()
        dialog = self.dialog(parent=host)
        self.app.processEvents()
        self.assertLessEqual(dialog.height(), 620)
        self.assertTrue(dialog.memo_panel.isHidden())
        self.assertTrue(dialog.editor_date_label.isHidden())
        self.assertEqual(dialog.cancel_btn.height(), dialog.save_btn.height())
        self.assertGreaterEqual(dialog.save_btn.height(), 44)
        dialog.memo_toggle.click()
        self.assertFalse(dialog.memo_panel.isHidden())


class MonthNavigationTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.host = QWidget()
        self.host.current_date = QDate(2026, 11, 14)
        self.host.cal_show_weekends = True
        self.host._calendar_keyboard_date = None
        self.host._calendar_cells_by_date = {}
        self.calls = []
        self.host.load_center_panel = lambda: self.calls.append(("render", self.host.current_date))
        layout = QVBoxLayout(self.host)
        self.scroll = QScrollArea()
        layout.addWidget(self.scroll)
        content = QWidget()
        days = QVBoxLayout(content)
        for day in range(9, 16):
            cell = ClickableCell(QDate(2026, 11, day))
            cell.clicked.connect(lambda date: self.calls.append(("select", date)))
            cell.doubleClicked.connect(lambda pack: self.calls.append(("create", pack)))
            days.addWidget(cell)
            self.host._calendar_cells_by_date[cell.target_date.toString("yyyy-MM-dd")] = cell
        self.scroll.setWidget(content)
        self.navigation = MonthGridNavigation(self.host, self.scroll)
        self.addCleanup(self.host.close)
        self.host.show()
        self.host.activateWindow()
        self.app.processEvents()
        self.navigation.restore_focus()
        self.app.processEvents()

    def test_one_tab_stop_arrows_selection_and_creation(self):
        cells = self.host._calendar_cells_by_date

        def tab_cells():
            return [c for c in cells.values() if c.focusPolicy() & Qt.FocusPolicy.TabFocus]

        self.assertEqual(len(tab_cells()), 1)
        QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_Left)
        self.assertEqual(self.app.focusWidget().target_date, QDate(2026, 11, 13))
        self.assertTrue(cells["2026-11-13"].property("keyboardFocused"))
        self.assertFalse(cells["2026-11-14"].property("keyboardFocused"))
        self.assertEqual(len(tab_cells()), 1)
        QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_Return)
        QTest.keyClick(
            self.app.focusWidget(), Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
        )
        self.assertEqual(
            self.calls,
            [
                ("select", QDate(2026, 11, 13)),
                ("create", (QDate(2026, 11, 13), None)),
            ],
        )

    def test_cross_visible_grid_boundary_remembers_focus_for_rerender(self):
        QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_Down)
        self.assertEqual(self.calls, [("render", QDate(2026, 11, 21))])
        self.assertEqual(self.host._calendar_keyboard_date, QDate(2026, 11, 21))

    def test_hidden_weekend_horizontal_navigation_skips_to_monday(self):
        self.host.cal_show_weekends = False
        cells = self.host._calendar_cells_by_date
        self.navigation.cells = {
            key: cell for key, cell in cells.items() if cell.target_date.dayOfWeek() < 6
        }
        self.navigation.dates = sorted(self.navigation.cells)
        self.navigation.active_key = "2026-11-13"
        cells["2026-11-13"].setFocus()
        self.app.processEvents()
        QTest.keyClick(cells["2026-11-13"], Qt.Key.Key_Right)
        self.assertEqual(self.host.current_date, QDate(2026, 11, 16))
