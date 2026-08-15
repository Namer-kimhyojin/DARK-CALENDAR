# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QApplication, QListWidgetItem, QMessageBox

from calendar_app.infrastructure.db import database_unified, db_repository_unified, task_repo
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

    def test_repeat_routine_rolls_back_entire_series_when_checklist_copy_fails(self):
        dialog = UnifiedTaskDialog(initial_date=QDate(2026, 4, 1), task_type="routine")
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("Atomic Series")
        dialog.repeat_task_radio.setChecked(True)
        dialog.repeat_cycle_combo.setCurrentIndex(dialog.repeat_cycle_combo.findData("weekly"))
        dialog.routine_period_end_date.setDate(QDate(2026, 4, 15))
        item = QListWidgetItem("")
        item.setData(Qt.ItemDataRole.UserRole, "required step")
        item.setData(Qt.ItemDataRole.UserRole + 1, False)
        dialog.checklist_widget.addItem(item)

        real_add = db_repository_unified.add_checklist_item
        call_count = 0

        def fail_on_second_task(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return None
            return real_add(*args, **kwargs)

        with (
            patch(
                "calendar_app.presentation.dialogs.task_dialog_unified."
                "checklist_repo.add_checklist_item",
                side_effect=fail_on_second_task,
            ),
            patch.object(QMessageBox, "critical", return_value=QMessageBox.StandardButton.Ok),
        ):
            dialog._create_task()

        conn = database_unified.db_manager.get_connection()
        task_count = conn.execute(
            "SELECT COUNT(*) FROM unified_task WHERE name='Atomic Series'"
        ).fetchone()[0]
        checklist_count = conn.execute("SELECT COUNT(*) FROM task_checklist_link").fetchone()[0]
        self.assertEqual(task_count, 0)
        self.assertEqual(checklist_count, 0)

    def test_repeat_routine_metadata_counts_only_dates_actually_added(self):
        existing_id = task_repo.create_unified_task(
            {
                "name": "Duplicate-aware Series",
                "type": "routine",
                "cycle_type": "weekly",
                "target_date": "2026-04-08",
                "deadline": "2026-04-08 09:00:00",
            }
        )
        self.assertIsNotNone(existing_id)
        dialog = UnifiedTaskDialog(initial_date=QDate(2026, 4, 1), task_type="routine")
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("Duplicate-aware Series")
        dialog.repeat_task_radio.setChecked(True)
        dialog.repeat_cycle_combo.setCurrentIndex(dialog.repeat_cycle_combo.findData("weekly"))
        dialog.routine_period_end_date.setDate(QDate(2026, 4, 15))

        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            dialog._create_task()

        conn = database_unified.db_manager.get_connection()
        rows = conn.execute(
            "SELECT target_date, series_order, series_total FROM unified_task "
            "WHERE name=? AND series_id IS NOT NULL ORDER BY target_date",
            ("Duplicate-aware Series",),
        ).fetchall()
        self.assertEqual([row["target_date"] for row in rows], ["2026-04-01", "2026-04-15"])
        self.assertEqual([row["series_order"] for row in rows], [1, 2])
        self.assertEqual({row["series_total"] for row in rows}, {2})


class GovernanceProcessTests(TemporaryDatabaseTestCase):
    def _create_google_schedule(self, name="Google task"):
        return task_repo.create_unified_task(
            {
                "name": name,
                "type": "schedule",
                "deadline": "2026-04-07 09:00:00",
                "end_date": "2026-04-07 10:00:00",
                "gcal_event_id": f"evt-{name}",
                "gcal_source_calendar_id": "team-cal",
            }
        )

    def test_atomic_google_task_delete_persists_outbox_before_local_removal(self):
        task_id = self._create_google_schedule("atomic-delete")

        self.assertTrue(task_repo.delete_unified_task_with_gcal_outbox(task_id))

        self.assertIsNone(task_repo.get_unified_task(task_id))
        self.assertTrue(task_repo.is_gcal_delete_queued("evt-atomic-delete", "team-cal"))

    def test_atomic_google_task_delete_rolls_back_when_outbox_fails(self):
        task_id = self._create_google_schedule("rollback-delete")

        with patch.object(db_repository_unified, "queue_gcal_delete", return_value=False):
            deleted = task_repo.delete_unified_task_with_gcal_outbox(task_id)

        self.assertFalse(deleted)
        self.assertIsNotNone(task_repo.get_unified_task(task_id))

    def test_move_off_google_rolls_back_when_outbox_fails(self):
        task_id = self._create_google_schedule("rollback-move")

        with patch.object(db_repository_unified, "queue_gcal_delete", return_value=False):
            moved = task_repo.update_unified_task_with_gcal_delete(
                task_id,
                {
                    "calendar_id": "local::default",
                    "gcal_event_id": None,
                    "gcal_source_calendar_id": None,
                    "gcal_dirty": 0,
                },
                "evt-rollback-move",
                "team-cal",
            )

        self.assertFalse(moved)
        row = task_repo.get_unified_task(task_id)
        self.assertEqual(row["gcal_event_id"], "evt-rollback-move")
        self.assertEqual(row["gcal_source_calendar_id"], "team-cal")

    def test_trash_purge_keeps_archive_when_outbox_fails(self):
        task_id = self._create_google_schedule("rollback-purge")
        self.assertTrue(task_repo.move_task_to_trash(task_id, reason="manual_trash"))
        archive_id = task_repo.list_task_trash()[0]["id"]

        with patch.object(db_repository_unified, "queue_gcal_delete", return_value=False):
            purged = task_repo.purge_task_trash_with_gcal_outbox(archive_id)

        self.assertIsNone(purged)
        self.assertEqual(len(task_repo.list_task_trash()), 1)

    def test_automatic_old_trash_purge_keeps_archive_when_outbox_fails(self):
        task_id = self._create_google_schedule("rollback-old-purge")
        self.assertTrue(task_repo.move_task_to_trash(task_id, reason="manual_trash"))
        conn = database_unified.db_manager.get_connection()
        conn.execute(
            "UPDATE gcal_deleted_task_archive "
            "SET archived_at=datetime('now', 'localtime', '-40 days')"
        )
        conn.commit()

        with patch.object(db_repository_unified, "queue_gcal_delete", return_value=False):
            deleted_count = task_repo.purge_task_trash_older_than(30)

        self.assertEqual(deleted_count, 0)
        self.assertEqual(len(task_repo.list_task_trash()), 1)

    def test_google_delete_queue_is_unique_per_event_and_calendar(self):
        self.assertTrue(task_repo.queue_gcal_delete("evt-dedupe", " team-cal ", 10))
        self.assertTrue(task_repo.queue_gcal_delete("evt-dedupe", "team-cal", 11))

        rows = [
            row for row in task_repo.get_gcal_delete_queue() if row["gcal_event_id"] == "evt-dedupe"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["local_task_id"], 11)

        conn = database_unified.db_manager.get_connection()
        indexes = {
            row["name"]: int(row["unique"])
            for row in conn.execute("PRAGMA index_list('gcal_delete_queue')").fetchall()
        }
        self.assertEqual(indexes["idx_gcal_delete_queue_event_calendar_unique"], 1)

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
