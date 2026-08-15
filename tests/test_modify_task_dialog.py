# -*- coding: utf-8 -*-

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

    def test_google_delete_is_not_queued_when_local_calendar_move_fails_to_save(self):
        task_id = self._create_schedule_task()
        dialog = UnifiedModifyTaskDialog(task_id)
        self.addCleanup(dialog.close)
        dialog.task_data.update(
            {
                "calendar_id": "gcal::source",
                "gcal_event_id": "remote-event",
                "gcal_source_calendar_id": "source@example.com",
            }
        )

        with (
            patch.object(dialog, "_get_selected_calendar_id", return_value="local::private"),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "calendar_app.presentation.dialogs.task_dialog_unified."
                "task_repo.update_unified_task_with_gcal_delete",
                return_value=False,
            ) as atomic_move,
            patch.object(QMessageBox, "critical", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._save_changes()

        atomic_move.assert_called_once()

    def _create_weekly_series(self):
        series_id = "weekly-series"
        task_ids = []
        for order, target_date in enumerate(("2026-04-01", "2026-04-08", "2026-04-15"), start=1):
            task_ids.append(
                task_db.create_unified_task(
                    {
                        "name": "기존 반복 업무",
                        "type": "routine",
                        "priority": "normal",
                        "status": "pending",
                        "cycle_type": "weekly",
                        "target_date": target_date,
                        "deadline": f"{target_date} 09:00:00",
                        "series_id": series_id,
                        "series_order": order,
                        "series_total": 3,
                    }
                )
            )
        return task_ids

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

    def test_edit_this_and_following_renames_and_shortens_without_duplicates(self):
        task_ids = self._create_weekly_series()
        dialog = UnifiedModifyTaskDialog(task_ids[0])
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("변경된 반복 업무")
        dialog.routine_period_end_date.setDate(QDate(2026, 4, 8))

        with (
            patch.object(
                dialog,
                "_choose_repeat_routine_edit_scope",
                return_value="this_and_following",
            ),
            patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._save_changes()

        conn = task_db.get_connection()
        rows = conn.execute(
            "SELECT name, target_date, series_id, series_order, series_total "
            "FROM unified_task ORDER BY target_date, id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["name"] for row in rows}, {"변경된 반복 업무"})
        self.assertEqual([row["target_date"] for row in rows], ["2026-04-01", "2026-04-08"])
        self.assertEqual(len({row["series_id"] for row in rows}), 1)
        self.assertEqual([row["series_order"] for row in rows], [1, 2])
        self.assertEqual({row["series_total"] for row in rows}, {2})

    def test_edit_single_scope_changes_only_selected_occurrence(self):
        task_ids = self._create_weekly_series()
        dialog = UnifiedModifyTaskDialog(task_ids[1])
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("이번 일정만 변경")

        with (
            patch.object(dialog, "_choose_repeat_routine_edit_scope", return_value="single"),
            patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._save_changes()

        conn = task_db.get_connection()
        rows = conn.execute(
            "SELECT name, target_date, series_id, series_order, series_total "
            "FROM unified_task ORDER BY target_date, id"
        ).fetchall()
        self.assertEqual(
            [row["name"] for row in rows],
            [
                "기존 반복 업무",
                "이번 일정만 변경",
                "기존 반복 업무",
            ],
        )
        self.assertEqual({row["series_id"] for row in rows}, {"weekly-series"})
        self.assertEqual([row["series_order"] for row in rows], [1, 2, 3])
        self.assertEqual({row["series_total"] for row in rows}, {3})

    def test_edit_following_from_middle_splits_series_and_renumbers_both_sides(self):
        task_ids = self._create_weekly_series()
        dialog = UnifiedModifyTaskDialog(task_ids[1])
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("이후 반복 업무")
        dialog.routine_period_end_date.setDate(QDate(2026, 4, 15))

        with (
            patch.object(
                dialog,
                "_choose_repeat_routine_edit_scope",
                return_value="this_and_following",
            ),
            patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._save_changes()

        conn = task_db.get_connection()
        rows = conn.execute(
            "SELECT name, target_date, series_id, series_order, series_total "
            "FROM unified_task ORDER BY target_date, id"
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["name"], "기존 반복 업무")
        self.assertEqual(rows[0]["series_id"], "weekly-series")
        self.assertEqual((rows[0]["series_order"], rows[0]["series_total"]), (1, 1))
        self.assertEqual([row["name"] for row in rows[1:]], ["이후 반복 업무"] * 2)
        self.assertNotEqual(rows[1]["series_id"], "weekly-series")
        self.assertEqual(rows[1]["series_id"], rows[2]["series_id"])
        self.assertEqual([row["series_order"] for row in rows[1:]], [1, 2])
        self.assertEqual({row["series_total"] for row in rows[1:]}, {2})


if __name__ == "__main__":
    unittest.main()
