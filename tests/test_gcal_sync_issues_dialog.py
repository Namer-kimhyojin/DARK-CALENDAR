# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.infrastructure.db import task_repo
from calendar_app.presentation.dialogs.gcal_sync_issues_dialog import GCalSyncIssuesDialog
from tests.support import TemporaryDatabaseTestCase


class GCalSyncIssuesDialogTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def _create_conflict(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Conflict Task",
                "type": "schedule",
                "deadline": "2026-04-01 09:00:00",
                "end_date": "2026-04-01 10:00:00",
                "gcal_sync_error": "remote_newer_than_local",
                "gcal_dirty": 1,
            }
        )
        self.assertIsNotNone(task_id)
        ok = task_repo.queue_gcal_sync_conflict(
            task_id,
            "evt-conflict-1",
            gcal_calendar_id="team-calendar",
            local_snapshot={"name": "Local Version"},
            remote_snapshot={"summary": "Remote Version"},
        )
        self.assertTrue(ok)
        rows = task_repo.list_gcal_sync_conflicts()
        self.assertEqual(len(rows), 1)
        return task_id, rows[0]["id"]

    def _select_conflict_row(self, dialog):
        for row_index in range(dialog.table.rowCount()):
            item = dialog.table.item(row_index, 0)
            if item is None:
                continue
            meta = item.data(Qt.ItemDataRole.UserRole)
            if meta and meta.get("type") == "conflict":
                dialog.table.setCurrentCell(row_index, 0)
                return meta
        self.fail("Conflict row not found")

    def _select_delete_queue_row(self, dialog):
        for row_index in range(dialog.table.rowCount()):
            item = dialog.table.item(row_index, 0)
            if item is None:
                continue
            meta = item.data(Qt.ItemDataRole.UserRole)
            if meta and meta.get("type") == "delete_queue":
                dialog.table.setCurrentCell(row_index, 0)
                return meta
        self.fail("Delete queue row not found")

    def test_load_rows_includes_conflict_queue(self):
        task_id, conflict_id = self._create_conflict()
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)

        conflict_meta = self._select_conflict_row(dialog)
        self.assertEqual(conflict_meta["id"], conflict_id)
        self.assertEqual(conflict_meta["local_task_id"], task_id)

    def test_retry_selected_marks_conflict_resolved(self):
        self._create_conflict()
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)
        self._select_conflict_row(dialog)

        dialog.retry_selected()

        unresolved = task_repo.list_gcal_sync_conflicts()
        self.assertEqual(unresolved, [])

    def test_clear_selected_error_marks_conflict_cleared(self):
        self._create_conflict()
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)
        self._select_conflict_row(dialog)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dialog.clear_selected_error()

        unresolved = task_repo.list_gcal_sync_conflicts()
        self.assertEqual(unresolved, [])
        rows = task_repo.list_gcal_sync_conflicts(only_unresolved=False, limit=10)
        self.assertEqual(rows[0]["resolution"], "cleared")

    def test_force_ignore_selected_marks_conflict_ignored(self):
        self._create_conflict()
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)
        self._select_conflict_row(dialog)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            dialog.force_ignore_selected()

        unresolved = task_repo.list_gcal_sync_conflicts()
        self.assertEqual(unresolved, [])
        rows = task_repo.list_gcal_sync_conflicts(only_unresolved=False, limit=10)
        self.assertEqual(rows[0]["resolution"], "ignored")

    def test_dialog_uses_token_style_bundle(self):
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)

        self.assertIn("QTableWidget {", dialog.table.styleSheet())
        self.assertIn("QFrame#GuidanceBox", dialog.guidance_box.styleSheet())
        self.assertIn("QFrame#DiffPanel", dialog._diff_panel.styleSheet())
        self.assertIn("color:", dialog.retry_btn.styleSheet())
        self.assertIn("color:", dialog.force_ignore_btn.styleSheet())

    def test_empty_state_disables_selection_actions(self):
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertIs(dialog.table_stack.currentWidget(), dialog.empty_state)
        self.assertFalse(dialog.guidance_box.isVisible())
        self.assertFalse(dialog.retry_btn.isEnabled())
        self.assertFalse(dialog.clear_btn.isEnabled())
        self.assertFalse(dialog.force_ignore_btn.isEnabled())
        self.assertFalse(dialog.clear_healed_btn.isEnabled())
        self.assertTrue(dialog.refresh_btn.isEnabled())

    def test_conflict_selection_enables_applicable_actions(self):
        self._create_conflict()
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)

        self._select_conflict_row(dialog)

        self.assertTrue(dialog.retry_btn.isEnabled())
        self.assertTrue(dialog.clear_btn.isEnabled())
        self.assertTrue(dialog.force_ignore_btn.isEnabled())
        self.assertTrue(dialog.keep_local_btn.isEnabled())
        self.assertTrue(dialog.use_remote_btn.isEnabled())
        self.assertFalse(dialog.delete_remote_btn.isEnabled())

    def test_exhausted_delete_queue_row_is_retained_and_labeled(self):
        queued = task_repo.queue_gcal_delete(
            "evt-delete-failed",
            gcal_calendar_id="primary",
        )
        self.assertTrue(queued)
        queue_row = next(
            row
            for row in task_repo.get_gcal_delete_queue()
            if row.get("gcal_event_id") == "evt-delete-failed"
        )
        queue_id = queue_row["id"]
        for _ in range(5):
            task_repo.mark_gcal_delete_failed(queue_id, "delete_failed")

        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)
        meta = self._select_delete_queue_row(dialog)

        self.assertTrue(meta["retry_exhausted"])
        self.assertEqual(meta["status"], "재시도 한도 초과")
        self.assertIn("(5/5)", meta["error"])

        dialog.retry_selected()
        queue_row = next(
            row for row in task_repo.get_gcal_delete_queue() if row.get("id") == queue_id
        )
        self.assertEqual(int(queue_row.get("retry_count") or 0), 0)
        self.assertIsNone(queue_row.get("last_error"))


if __name__ == "__main__":
    unittest.main()
