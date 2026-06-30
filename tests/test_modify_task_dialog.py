import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.infrastructure.db import checklist_template_repo as checklist_repo
from calendar_app.infrastructure.db import task_repo as task_db
from calendar_app.presentation.dialogs.modify_task_dialog_unified import UnifiedModifyTaskDialog
from tests.support import TemporaryDatabaseTestCase


class ModifyTaskDialogTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def _create_schedule_task(self):
        return task_db.create_unified_task(
            {
                "name": "테스트 일정",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-03-04 09:00:00",
                "end_date": "2026-03-04 10:00:00",
                "target_date": "2026-03-04",
            }
        )

    def _create_routine_task(self):
        return task_db.create_unified_task(
            {
                "name": "테스트 업무",
                "type": "routine",
                "priority": "normal",
                "status": "pending",
                "cycle_type": "single",
                "deadline": "2026-03-04 12:00:00",
                "target_date": "2026-03-04",
            }
        )

    def test_template_combo_lists_all_templates_without_section_headers(self):
        # 체크리스트는 일반업무(routine) 전용 — 일정(schedule)에는 템플릿 콤보가 없다.
        task_id = self._create_routine_task()
        schedule_template = checklist_repo.create_checklist_template(
            "출장 정산 및 보고", category="schedule", checklist_type="list"
        )
        common_template = checklist_repo.create_checklist_template(
            "월간 결산 업무", category="common", checklist_type="process"
        )
        checklist_repo.create_checklist_item(schedule_template, "영수증 정리", item_order=0)
        checklist_repo.create_checklist_item(common_template, "자료 수집", item_order=0)

        dialog = UnifiedModifyTaskDialog(task_id)
        self.addCleanup(dialog.close)

        combo_texts = [
            dialog.checklist_template_combo.itemText(i)
            for i in range(dialog.checklist_template_combo.count())
        ]

        self.assertEqual(combo_texts[0], "-- 템플릿 선택 --")
        self.assertTrue(any("출장 정산 및 보고" in text for text in combo_texts[1:]))
        self.assertTrue(any("월간 결산 업무" in text for text in combo_texts[1:]))
        self.assertFalse(any("일정 템플릿" in text for text in combo_texts))
        self.assertFalse(any("공통 템플릿" in text for text in combo_texts))

    def test_save_changes_updates_task_fields(self):
        task_id = self._create_schedule_task()
        dialog = UnifiedModifyTaskDialog(task_id)
        self.addCleanup(dialog.close)

        dialog.name_edit.setText("수정된 일정")
        dialog.memo_edit.setPlainText("상세 메모")
        dialog.location_edit.setText("회의실 A")
        dialog.assignee_edit.setText("홍길동")

        with (
            patch(
                "calendar_app.presentation.dialogs.modify_task_dialog_unified.queue_task_sync_to_google",
                return_value=None,
            ),
            patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._save_changes()

        task = task_db.get_unified_task(task_id)
        self.assertEqual(task["name"], "수정된 일정")
        self.assertEqual(task["description"], "상세 메모")
        self.assertEqual(task["location"], "회의실 A")
        self.assertEqual(task["assignee"], "홍길동")

    def test_modify_routine_repeat_mode_exposes_end_date_and_creates_series(self):
        task_id = self._create_routine_task()
        dialog = UnifiedModifyTaskDialog(task_id)
        self.addCleanup(dialog.close)

        self.assertIsNotNone(dialog.routine_period_end_date)

        dialog.name_edit.setText("반복 전환 업무")
        dialog.repeat_task_radio.setChecked(True)
        idx = dialog.repeat_cycle_combo.findData("weekly")
        if idx >= 0:
            dialog.repeat_cycle_combo.setCurrentIndex(idx)
        dialog.start_date.setDate(QDate(2026, 3, 4))
        dialog.routine_period_end_date.setDate(QDate(2026, 3, 18))

        with (
            patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok),
            patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._save_changes()

        conn = task_db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT name, cycle_type, series_id, series_order, series_total, target_date
            FROM unified_task
            WHERE name=?
            ORDER BY target_date ASC
            """,
            ("반복 전환 업무",),
        )
        rows = cur.fetchall()

        self.assertEqual(
            [row["target_date"] for row in rows], ["2026-03-04", "2026-03-11", "2026-03-18"]
        )
        self.assertEqual({row["cycle_type"] for row in rows}, {"weekly"})
        self.assertEqual(len({row["series_id"] for row in rows}), 1)
        self.assertEqual([int(row["series_order"]) for row in rows], [1, 2, 3])
        self.assertEqual({int(row["series_total"]) for row in rows}, {3})


if __name__ == "__main__":
    unittest.main()
