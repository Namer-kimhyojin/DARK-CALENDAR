import unittest

from calendar_app.application import routine_advanced_service
from calendar_app.infrastructure.db import db_repository
from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from tests.support import TemporaryDatabaseTestCase


class DbRepositoryHookTests(TemporaryDatabaseTestCase):
    def tearDown(self):
        db_repository.register_checklist_routine_rollover_hook(None)
        super().tearDown()

    def _create_routine(self):
        return unified_repo.create_unified_task(
            {
                "name": "HookRoutine",
                "type": "routine",
                "cycle_type": "daily",
                "target_date": "2026-03-10",
                "deadline": "2026-03-10 09:00:00",
                "status": "in_progress",
            }
        )

    def test_process_checklist_completion_calls_registered_rollover_hook(self):
        task_id = self._create_routine()
        link_id = unified_repo.add_checklist_item(
            task_id, "step-1", item_order=0, display_type="process"
        )
        self.assertIsNotNone(link_id)

        called = []
        db_repository.register_checklist_routine_rollover_hook(
            lambda owner_id: called.append(owner_id)
        )
        db_repository.toggle_checklist_item(link_id)

        self.assertEqual(called, [task_id])
        task = unified_repo.get_unified_task(task_id)
        self.assertEqual(int(task.get("is_completed") or 0), 1)

    def test_list_checklist_toggle_does_not_call_rollover_hook(self):
        task_id = self._create_routine()
        link_id = unified_repo.add_checklist_item(
            task_id, "step-1", item_order=0, display_type="list"
        )
        self.assertIsNotNone(link_id)

        called = []
        db_repository.register_checklist_routine_rollover_hook(
            lambda owner_id: called.append(owner_id)
        )
        db_repository.toggle_checklist_item(link_id)

        self.assertEqual(called, [])

    def test_process_checklist_completion_can_persist_next_routine_instance(self):
        task_id = self._create_routine()
        link_id = unified_repo.add_checklist_item(
            task_id, "step-1", item_order=0, display_type="process"
        )
        self.assertIsNotNone(link_id)

        db_repository.register_checklist_routine_rollover_hook(
            routine_advanced_service.auto_create_next_routine
        )
        db_repository.toggle_checklist_item(link_id)

        rows = routine_advanced_service.search_routines(cycle_type="daily")
        targets = sorted(row.get("target_date") for row in rows if row.get("name") == "HookRoutine")
        self.assertEqual(targets, ["2026-03-10", "2026-03-11"])
        created = next(row for row in rows if row.get("target_date") == "2026-03-11")
        self.assertEqual(created.get("status"), "in_progress")
        self.assertEqual(int(created.get("is_completed") or 0), 0)


if __name__ == "__main__":
    unittest.main()
