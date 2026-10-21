# -*- coding: utf-8 -*-
import os
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.infrastructure.db import db_repository_unified, task_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.gcal_sync_issues_dialog import GCalSyncIssuesDialog
from calendar_app.presentation.dialogs.sync_feedback import sync_error_message
from tests.support import TemporaryDatabaseTestCase


class GCalSyncIssuesDialogTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_legacy_unknown_error_never_displays_payload_or_renders_its_markup(self):
        marker = "synthetic-private-calendar-payload"
        task_id = task_repo.create_unified_task(
            {
                "name": "Task",
                "type": "schedule",
                "deadline": "2026-10-20 09:00:00",
                "gcal_sync_error": f"<img src='file:///synthetic-test-image'>{marker}",
                "gcal_dirty": 1,
            }
        )
        self.assertIsNotNone(task_id)
        dialog = GCalSyncIssuesDialog()
        try:
            dialog.table.setCurrentCell(0, 0)
            dialog._on_selection_changed()
            visible = " ".join(
                dialog.table.item(row, column).text()
                for row in range(dialog.table.rowCount())
                for column in range(dialog.table.columnCount())
                if dialog.table.item(row, column) is not None
            )
            self.assertNotIn(marker, visible)
            self.assertNotIn(marker, dialog.guidance_text.toPlainText())
            self.assertNotIn("<img", dialog.guidance_text.toHtml())
            self.assertIn(
                sync_error_message("operation_failed"), dialog.guidance_text.toPlainText()
            )
        finally:
            dialog.close()

    def _create_conflict(self):
        task_id = task_repo.create_unified_task(
            {
                "name": "Remote Version",
                "type": "schedule",
                "deadline": "2026-04-01 11:00:00",
                "end_date": "2026-04-01 12:00:00",
                "description": "Remote note",
                "location": "Remote room",
                "calendar_id": "gcal::team-calendar",
                "gcal_event_id": "evt-conflict-1",
                "gcal_source_calendar_id": "team-calendar",
                "gcal_target_calendar_id": "team-calendar",
                "gcal_remote_updated_at": "2026-04-01T02:00:00Z",
                "gcal_sync_error": "remote_newer_than_local",
                "gcal_dirty": 0,
            }
        )
        self.assertIsNotNone(task_id)
        ok = task_repo.queue_gcal_sync_conflict(
            task_id,
            "evt-conflict-1",
            gcal_calendar_id="team-calendar",
            local_snapshot={
                "name": "Local Version",
                "deadline": "2026-04-01 09:00:00",
                "end_date": "2026-04-01 10:00:00",
                "description": "Local note",
                "location": "Local room",
                "all_day": 0,
                "bg_color": "#123456",
                "gcal_remote_updated_at": "2026-03-31T01:00:00Z",
            },
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

    def _keep_local_dialog(self):
        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)
        dialog.app = SimpleNamespace(
            show_toast=Mock(), wake_gcal_sync=Mock(), _refresh_all_panels=Mock()
        )
        self._select_conflict_row(dialog)
        return dialog

    def test_keep_local_restores_saved_content_and_keeps_current_server_revision(self):
        task_id, conflict_id = self._create_conflict()
        dialog = self._keep_local_dialog()

        dialog.resolve_keep_local()

        task = task_repo.get_unified_task(task_id)
        for field, expected in {
            "name": "Local Version",
            "deadline": "2026-04-01 09:00:00",
            "end_date": "2026-04-01 10:00:00",
            "description": "Local note",
            "location": "Local room",
            "all_day": 0,
            "bg_color": "#123456",
            "gcal_event_id": "evt-conflict-1",
            "gcal_source_calendar_id": "team-calendar",
            "gcal_target_calendar_id": "team-calendar",
            "gcal_remote_updated_at": "2026-04-01T02:00:00Z",
            "gcal_dirty": 1,
            "gcal_sync_error": None,
        }.items():
            self.assertEqual(task[field], expected, field)
        self.assertEqual(task_repo.list_gcal_sync_conflicts(), [])
        conflict = task_repo.list_gcal_sync_conflicts(only_unresolved=False)[0]
        self.assertEqual(conflict["id"], conflict_id)
        self.assertEqual(conflict["resolution"], "keep_local")
        dialog.app.show_toast.assert_called_once()
        dialog.app.wake_gcal_sync.assert_called_once()
        dialog.app._refresh_all_panels.assert_called_once()

    def test_keep_local_failed_conflict_commit_rolls_back_restore_and_reports_failure(self):
        task_id, conflict_id = self._create_conflict()
        before = task_repo.get_unified_task(task_id)
        conn = task_repo.get_connection()
        conn.execute(
            "CREATE TRIGGER reject_conflict_resolution BEFORE UPDATE ON gcal_sync_conflict_queue "
            "WHEN NEW.is_resolved=1 BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        conn.commit()
        dialog = self._keep_local_dialog()

        with patch.object(QMessageBox, "warning") as warning:
            dialog.resolve_keep_local()

        self.assertEqual(task_repo.get_unified_task(task_id), before)
        self.assertEqual(task_repo.list_gcal_sync_conflicts()[0]["id"], conflict_id)
        self.assertFalse(conn.in_transaction)
        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[2], sync_error_message("database_failed"))
        dialog.app.show_toast.assert_not_called()
        dialog.app.wake_gcal_sync.assert_not_called()
        dialog.app._refresh_all_panels.assert_not_called()

    def test_keep_local_refuses_relinked_task_and_keeps_conflict_unresolved(self):
        task_id, conflict_id = self._create_conflict()
        conn = task_repo.get_connection()
        conn.execute(
            "UPDATE unified_task SET gcal_event_id='replacement-event' WHERE id=?", (task_id,)
        )
        conn.commit()
        before = task_repo.get_unified_task(task_id)
        dialog = self._keep_local_dialog()

        with patch.object(QMessageBox, "warning") as warning:
            dialog.resolve_keep_local()

        self.assertEqual(task_repo.get_unified_task(task_id), before)
        self.assertEqual(task_repo.list_gcal_sync_conflicts()[0]["id"], conflict_id)
        warning.assert_called_once()
        dialog.app.show_toast.assert_not_called()
        dialog.app.wake_gcal_sync.assert_not_called()
        self.assertFalse(conn.in_transaction)

    def test_keep_local_holds_writer_lock_before_checking_task_identity(self):
        task_id, conflict_id = self._create_conflict()
        conn = task_repo.get_connection()
        database_path = conn.execute("PRAGMA database_list").fetchone()[2]
        competing = sqlite3.connect(database_path, timeout=0)
        original_read = db_repository_unified.get_unified_task
        observed = []

        def inspect_locked_identity(identifier):
            self.assertTrue(conn.in_transaction)
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                competing.execute(
                    "UPDATE unified_task SET gcal_event_id='competing-relink' WHERE id=?",
                    (identifier,),
                )
            competing.rollback()
            observed.append(identifier)
            return original_read(identifier)

        try:
            with patch.object(db_repository_unified, "get_unified_task", inspect_locked_identity):
                self.assertTrue(
                    task_repo.mark_gcal_sync_conflict_resolved(conflict_id, "keep_local")
                )
        finally:
            competing.close()
        self.assertEqual(observed, [task_id])
        self.assertEqual(task_repo.get_unified_task(task_id)["gcal_event_id"], "evt-conflict-1")

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
        self.assertEqual(
            meta["status"],
            t("gcal.issues_retry_exhausted", "재시도 한도 초과"),
        )
        self.assertIn("(5/5)", meta["error"])

        dialog.retry_selected()
        queue_row = next(
            row for row in task_repo.get_gcal_delete_queue() if row.get("id") == queue_id
        )
        self.assertEqual(int(queue_row.get("retry_count") or 0), 0)
        self.assertIsNone(queue_row.get("last_error"))

    def test_pending_moves_have_friendly_retry_labels(self):
        cases = (
            ("network:calendar_move_failed", "gcal_focus.move_failed_label", "캘린더 이동 실패"),
            (
                "calendar_move_unconfirmed:calendar_move_destination_unconfirmed",
                "gcal_focus.move_unconfirmed_label",
                "이동 확인 필요",
            ),
            (
                "calendar_move_local_state:calendar_move_local_state_not_saved",
                "gcal_focus.move_local_state_label",
                "이동 연결 저장 필요",
            ),
        )
        for raw, key, fallback in cases:
            with self.subTest(error=raw):
                self.assertEqual(
                    GCalSyncIssuesDialog._map_error_to_friendly(None, raw),
                    (t(key, fallback), t("gcal.treatments.pending_retry", "재시도 대기")),
                )

    def test_pending_move_guidance_does_not_claim_recovery_or_change_destination(self):
        cases = (
            ("network:calendar_move_failed", "calendar_move"),
            (
                "calendar_move_unconfirmed:calendar_move_destination_unconfirmed",
                "calendar_move_unconfirmed",
            ),
            (
                "calendar_move_local_state:calendar_move_local_state_not_saved",
                "calendar_move_local_state",
            ),
        )
        expected = {}
        for raw, code in cases:
            task_id = task_repo.create_unified_task(
                {
                    "name": code,
                    "type": "schedule",
                    "deadline": "2026-10-07 09:00:00",
                    "calendar_id": "gcal::team",
                    "gcal_event_id": "event-" + code,
                    "gcal_source_calendar_id": "family",
                    "gcal_target_calendar_id": "team",
                    "gcal_sync_error": raw,
                    "gcal_dirty": 1,
                }
            )
            self.assertIsNotNone(task_id)
            expected[task_id] = code

        dialog = GCalSyncIssuesDialog(None)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.table.rowCount(), len(expected))
        for row in range(dialog.table.rowCount()):
            meta = dialog.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            with self.subTest(error=meta["raw_error"]):
                self.assertEqual(meta["type"], "task")
                self.assertEqual(meta["status"], t("gcal.issues_retry_scheduled", "재시도 예정"))
                dialog.table.setCurrentCell(row, 0)
                self.assertEqual(
                    dialog.guidance_text.toPlainText(), sync_error_message(expected[meta["id"]])
                )
                self.assertTrue(dialog.retry_btn.isEnabled())
                task = task_repo.get_unified_task(meta["id"])
                self.assertEqual(task["calendar_id"], "gcal::team")
                self.assertEqual(task["gcal_source_calendar_id"], "family")
                self.assertEqual(task["gcal_target_calendar_id"], "team")
                self.assertEqual(task["gcal_dirty"], 1)


if __name__ == "__main__":
    unittest.main()
