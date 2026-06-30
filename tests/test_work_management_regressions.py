import unittest

from calendar_app.application import routine_advanced_service
from calendar_app.infrastructure.db import task_repo
from tests.support import TemporaryDatabaseTestCase


class WorkManagementRegressionTests(TemporaryDatabaseTestCase):
    def _create_routine(self, *, status="in_progress", target_date="2026-03-23"):
        return task_repo.create_unified_task(
            {
                "name": "Routine Regression",
                "type": "routine",
                "cycle_type": "weekly",
                "target_date": target_date,
                "deadline": f"{target_date} 09:00:00",
                "status": status,
            }
        )

    def test_calculate_next_period_exists_and_returns_date(self):
        next_date = routine_advanced_service.calculate_next_period(
            "2026-03-23",
            "monthly",
            "mode=day_of_month;slot=1;day=23",
        )
        self.assertEqual(next_date, "2026-04-23")

    def test_status_update_keeps_routine_completion_fields_in_sync(self):
        task_id = self._create_routine(status="in_progress")

        updated = task_repo.update_unified_task(task_id, {"status": "completed"})
        self.assertTrue(updated)
        row = task_repo.get_unified_task(task_id)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(int(row.get("is_completed") or 0), 1)
        self.assertTrue(bool((row.get("completed_at") or "").strip()))

        updated = task_repo.update_unified_task(task_id, {"status": "in_progress"})
        self.assertTrue(updated)
        row = task_repo.get_unified_task(task_id)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(int(row.get("is_completed") or 0), 0)
        self.assertFalse(bool((row.get("completed_at") or "").strip()))

    def test_routine_trash_and_restore_preserves_cycle_target_and_completion(self):
        task_id = self._create_routine(status="completed", target_date="2026-04-01")
        row = task_repo.get_unified_task(task_id)
        self.assertEqual(int(row.get("is_completed") or 0), 1)

        moved = task_repo.move_task_to_trash(task_id, reason="manual_trash_routine")
        self.assertTrue(moved)

        trashed = task_repo.list_task_trash(task_type="routine")
        self.assertEqual(len(trashed), 1)
        self.assertEqual(trashed[0]["cycle_type"], "weekly")
        self.assertEqual(trashed[0]["target_date"], "2026-04-01")
        self.assertEqual(int(trashed[0].get("is_completed") or 0), 1)

        restored_id = task_repo.restore_task_from_trash(trashed[0]["id"])
        self.assertIsNotNone(restored_id)
        restored = task_repo.get_unified_task(restored_id)
        self.assertEqual(restored["status"], "completed")
        self.assertEqual(int(restored.get("is_completed") or 0), 1)
        self.assertEqual(restored.get("cycle_type"), "weekly")
        self.assertEqual(restored.get("target_date"), "2026-04-01")


if __name__ == "__main__":
    unittest.main()
