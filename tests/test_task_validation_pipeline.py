import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.infrastructure.db import database_unified, task_repo
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class TaskValidationPipelineTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_create_normalizes_invalid_datetime_range_to_open_end(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Invalid range",
                "type": "schedule",
                "deadline": "2026-04-01 10:00:00",
                "end_date": "2026-04-01 09:00:00",
            }
        )
        self.assertIsNotNone(task_id)
        row = task_repo.get_unified_task(task_id)
        self.assertIsNone(row.get("end_date"))

    def test_create_normalizes_datetime_without_seconds(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Normalize time",
                "type": "schedule",
                "status": "pending",
                "deadline": "2026-04-02 09:00",
                "end_date": "2026-04-02 10:30",
            }
        )
        self.assertIsNotNone(task_id)
        row = task_repo.get_unified_task(task_id)
        self.assertEqual(row["deadline"], "2026-04-02 09:00:00")
        self.assertEqual(row["end_date"], "2026-04-02 10:30:00")

    def test_status_transition_policy_blocks_completed_to_pending(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Transition block",
                "type": "routine",
                "status": "completed",
                "cycle_type": "weekly",
                "target_date": "2026-04-03",
                "deadline": "2026-04-03 09:00:00",
            }
        )
        self.assertIsNotNone(task_id)

        updated = task_repo.update_unified_task(task_id, {"status": "pending"})
        self.assertFalse(updated)
        row = task_repo.get_unified_task(task_id)
        self.assertEqual(row["status"], "completed")

    def test_repeat_routine_creation_sets_series_metadata(self):
        dialog = UnifiedTaskDialog(initial_date=QDate(2026, 4, 1), task_type="routine")
        self.addCleanup(dialog.close)

        dialog.name_edit.setText("Series Routine")
        dialog.repeat_task_radio.setChecked(True)
        idx = dialog.repeat_cycle_combo.findData("weekly")
        if idx >= 0:
            dialog.repeat_cycle_combo.setCurrentIndex(idx)
        dialog.start_date.setDate(QDate(2026, 4, 1))
        if dialog.routine_period_end_date is not None:
            dialog.routine_period_end_date.setDate(QDate(2026, 4, 15))

        with (
            patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok),
            patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok),
            patch.object(QMessageBox, "critical", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._create_task()

        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT series_id, series_order, series_total, target_date
            FROM unified_task
            WHERE name=?
            ORDER BY target_date ASC
            """,
            ("Series Routine",),
        )
        rows = cur.fetchall()
        self.assertEqual(len(rows), 3)
        series_ids = {row["series_id"] for row in rows}
        self.assertEqual(len(series_ids), 1)
        self.assertTrue(next(iter(series_ids)))
        self.assertEqual([int(row["series_order"]) for row in rows], [1, 2, 3])
        self.assertEqual({int(row["series_total"]) for row in rows}, {3})


class GovernanceProcessTests(TemporaryDatabaseTestCase):
    def test_conflict_queue_deduplicates_and_resolves(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Conflict seed",
                "type": "schedule",
                "deadline": "2026-04-06 09:00:00",
                "end_date": "2026-04-06 10:00:00",
            }
        )
        self.assertIsNotNone(task_id)

        ok = task_repo.queue_gcal_sync_conflict(
            task_id,
            "evt-1",
            gcal_calendar_id="team-cal",
            local_snapshot={"version": 1},
            remote_snapshot={"version": 2},
        )
        self.assertTrue(ok)
        ok = task_repo.queue_gcal_sync_conflict(
            task_id,
            "evt-1",
            gcal_calendar_id="team-cal",
            local_snapshot={"version": 3},
            remote_snapshot={"version": 4},
        )
        self.assertTrue(ok)

        unresolved = task_repo.list_gcal_sync_conflicts()
        self.assertEqual(len(unresolved), 1)
        self.assertIn('"version": 3', unresolved[0]["local_snapshot_json"])
        self.assertEqual(task_repo.count_gcal_sync_conflicts(), 1)

        resolved = task_repo.mark_gcal_sync_conflict_resolved(
            unresolved[0]["id"], resolution="manual_review"
        )
        self.assertTrue(resolved)
        unresolved_after = task_repo.list_gcal_sync_conflicts()
        self.assertEqual(unresolved_after, [])
        self.assertEqual(task_repo.count_gcal_sync_conflicts(), 0)

    def test_purge_task_trash_older_than_days(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Trash candidate",
                "type": "schedule",
                "deadline": "2026-04-07 09:00:00",
                "end_date": "2026-04-07 10:00:00",
            }
        )
        self.assertTrue(task_repo.move_task_to_trash(task_id, reason="manual_trash"))

        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE gcal_deleted_task_archive SET archived_at=datetime('now', 'localtime', '-40 days')"
        )
        conn.commit()

        deleted_count = task_repo.purge_task_trash_older_than(30)
        self.assertEqual(deleted_count, 1)
        self.assertEqual(task_repo.list_task_trash(), [])


if __name__ == "__main__":
    unittest.main()
