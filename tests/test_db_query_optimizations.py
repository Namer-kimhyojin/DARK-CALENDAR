import unittest
from unittest.mock import patch

from calendar_app.infrastructure.db import db_repository
from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from tests.support import TemporaryDatabaseTestCase


class DbQueryOptimizationTests(TemporaryDatabaseTestCase):
    def test_get_tasks_by_type_with_progress_uses_bulk_checklist_aggregation(self):
        first_id = unified_repo.create_unified_task(
            {
                "name": "Routine A",
                "type": "routine",
                "target_date": "2026-03-27",
                "deadline": "2026-03-27 09:00:00",
                "status": "pending",
            }
        )
        second_id = unified_repo.create_unified_task(
            {
                "name": "Routine B",
                "type": "routine",
                "target_date": "2026-03-28",
                "deadline": "2026-03-28 09:00:00",
                "status": "pending",
            }
        )
        self.assertIsNotNone(first_id)
        self.assertIsNotNone(second_id)

        unified_repo.add_checklist_item(first_id, "Step 1", 0)
        unified_repo.add_checklist_item(first_id, "Step 2", 1)
        link_id = unified_repo.add_checklist_item(second_id, "Step 1", 0)
        unified_repo.toggle_checklist_item(link_id)

        with patch.object(
            unified_repo,
            "get_task_checklist_progress",
            side_effect=AssertionError("per-row progress query should not run"),
        ):
            rows = unified_repo.get_tasks_by_type_with_progress("routine")

        by_id = {row["id"]: row for row in rows}
        self.assertEqual(2, by_id[first_id]["checklist_total"])
        self.assertEqual(0, by_id[first_id]["checklist_completed"])
        self.assertEqual(1, by_id[second_id]["checklist_total"])
        self.assertEqual(1, by_id[second_id]["checklist_completed"])
        self.assertEqual({"total": 1, "completed": 1}, by_id[second_id]["progress"])

    def test_schedule_overlap_with_progress_uses_bulk_checklist_aggregation(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Schedule A",
                "type": "schedule",
                "deadline": "2026-03-27 09:00:00",
                "end_date": "2026-03-27 10:00:00",
                "target_date": "2026-03-27",
                "status": "pending",
            }
        )
        self.assertIsNotNone(task_id)
        unified_repo.add_checklist_item(task_id, "Step 1", 0)

        with patch.object(
            unified_repo,
            "get_task_checklist_progress",
            side_effect=AssertionError("per-row progress query should not run"),
        ):
            rows = unified_repo.get_schedule_tasks_overlapping_range_with_progress(
                "2026-03-27", "2026-03-27"
            )

        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["checklist_total"])
        self.assertEqual(0, rows[0]["checklist_completed"])

    def test_bulk_checklist_owner_helpers_ignore_duplicate_owner_ids(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Checklist bulk",
                "type": "routine",
                "target_date": "2026-03-29",
                "deadline": "2026-03-29 09:00:00",
                "status": "pending",
            }
        )
        self.assertIsNotNone(task_id)
        first_link_id = unified_repo.add_checklist_item(task_id, "Step 1", 0)
        unified_repo.add_checklist_item(task_id, "Step 2", 1)
        unified_repo.toggle_checklist_item(first_link_id)

        items_by_owner = unified_repo.get_task_checklist_items_for_owners([task_id, task_id, None])
        progress_by_owner = unified_repo.get_checklist_progress_for_owners([task_id, task_id, None])

        self.assertEqual([task_id], list(items_by_owner.keys()))
        self.assertEqual(
            ["Step 1", "Step 2"], [item["item_text"] for item in items_by_owner[task_id]]
        )
        self.assertEqual({"total": 2, "completed": 1}, progress_by_owner[task_id])

    def test_toggle_checklist_item_reports_missing_link(self):
        self.assertFalse(unified_repo.toggle_checklist_item(999999))

    def test_database_initialization_creates_query_indexes(self):
        conn = unified_repo.get_connection()
        cur = conn.cursor()

        cur.execute("PRAGMA index_list('unified_task')")
        unified_indexes = {row["name"] for row in cur.fetchall()}
        cur.execute("PRAGMA index_list('task_directive')")
        directive_indexes = {row["name"] for row in cur.fetchall()}
        cur.execute("PRAGMA index_list('task_checklist_link')")
        checklist_indexes = {row["name"] for row in cur.fetchall()}

        self.assertIn("idx_unified_task_schedule_overlap", unified_indexes)
        self.assertIn("idx_unified_task_type_target_date", unified_indexes)
        self.assertIn("idx_task_directive_deadline_order", directive_indexes)
        self.assertIn("idx_task_directive_status_deadline", directive_indexes)
        self.assertIn("idx_checklist_link_owner_completed", checklist_indexes)

    def test_get_recent_directives_supports_legacy_schema_with_cached_columns(self):
        conn = unified_repo.get_connection()
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS task_directive")
        cur.execute(
            """
            CREATE TABLE task_directive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                details TEXT,
                requester TEXT,
                deadline TEXT,
                status TEXT DEFAULT 'in_progress'
            )
            """
        )
        cur.execute(
            """
            INSERT INTO task_directive (content, details, requester, deadline, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Legacy row", "Detail memo", "Bob", "2026-03-18 11:00", "in_progress"),
        )
        conn.commit()

        rows = db_repository.get_recent_directives(limit=10)

        self.assertEqual(1, len(rows))
        did, content, status, receiver, deadline, memo, bg_color = rows[0]
        self.assertEqual("Legacy row", content)
        self.assertEqual("Bob", receiver)
        self.assertEqual("Detail memo", memo)
        self.assertIsNone(bg_color)


if __name__ == "__main__":
    unittest.main()
