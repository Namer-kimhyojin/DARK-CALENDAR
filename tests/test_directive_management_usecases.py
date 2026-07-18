import unittest

from calendar_app.application import directive_management_usecases
from calendar_app.infrastructure.db import database_unified, directive_repo
from tests.support import TemporaryDatabaseTestCase


class DirectiveManagementUsecasesTests(TemporaryDatabaseTestCase):
    def setUp(self):
        super().setUp()
        directive_repo.ensure_priority_column()

    def _insert_directive(
        self,
        *,
        content,
        receiver_name="Team",
        deadline="2026-03-18 12:00:00",
        status="in_progress",
        priority="normal",
    ):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO task_directive (content, receiver_name, deadline, status, priority, memo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (content, receiver_name, deadline, status, priority, f"memo:{content}"),
        )
        conn.commit()
        return cur.lastrowid

    def test_bulk_update_status_and_priority(self):
        first_id = self._insert_directive(content="Alpha", status="pending", priority="low")
        second_id = self._insert_directive(content="Beta", status="pending", priority="low")

        updated_status = directive_management_usecases.bulk_update_status(
            directive_repo,
            [first_id, second_id],
            "completed",
        )
        updated_priority = directive_management_usecases.bulk_update_priority(
            directive_repo,
            [first_id, second_id],
            "urgent",
        )

        self.assertEqual(updated_status, 2)
        self.assertEqual(updated_priority, 2)

        rows = directive_repo.get_directives_by_date("2026-03-18")
        row_map = {row["id"]: row for row in rows}
        self.assertEqual(row_map[first_id]["status"], "completed")
        self.assertEqual(row_map[second_id]["priority"], "urgent")

    def test_move_to_trash_and_restore_round_trip_preserves_content(self):
        directive_id = self._insert_directive(
            content="Trash me",
            receiver_name="Chris",
            deadline="2026-03-18 18:00:00",
            status="in_progress",
            priority="high",
        )

        moved = directive_management_usecases.move_selected_to_trash(
            directive_repo,
            [directive_id],
            reason="regression_test",
        )

        self.assertEqual(moved, 1)
        self.assertEqual(directive_repo.get_directives_by_date("2026-03-18"), [])

        trash_rows = directive_management_usecases.list_trashed(directive_repo)
        self.assertEqual(len(trash_rows), 1)
        self.assertEqual(trash_rows[0]["content"], "Trash me")

        restored_ids = directive_management_usecases.restore_selected_from_trash(
            directive_repo,
            [trash_rows[0]["id"]],
        )

        self.assertEqual(len(restored_ids), 1)
        restored = directive_repo.get_directives_by_date("2026-03-18")
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["content"], "Trash me")
        self.assertEqual(restored[0]["receiver_name"], "Chris")
        self.assertEqual(restored[0]["priority"], "high")


if __name__ == "__main__":
    unittest.main()
