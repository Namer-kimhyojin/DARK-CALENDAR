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


if __name__ == "__main__":
    unittest.main()
