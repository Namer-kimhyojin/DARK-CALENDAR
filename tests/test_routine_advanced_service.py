import unittest

from calendar_app.application import routine_advanced_service
from calendar_app.infrastructure.db import task_repo
from tests.support import TemporaryDatabaseTestCase


class RoutineAdvancedServiceTests(TemporaryDatabaseTestCase):
    def _create_routine(
        self,
        *,
        name="Routine Lifecycle",
        cycle_type="daily",
        target_date="2026-03-24",
        recurrence=None,
        status="in_progress",
        location=None,
        assignee=None,
    ):
        return task_repo.create_unified_task(
            {
                "name": name,
                "type": "routine",
                "cycle_type": cycle_type,
                "target_date": target_date,
                "deadline": f"{target_date} 09:30:00",
                "recurrence": recurrence,
                "status": status,
                "location": location,
                "assignee": assignee,
            }
        )

    def test_auto_create_next_routine_is_idempotent_and_copies_checklist(self):
        task_id = self._create_routine(status="completed", target_date="2026-03-24")
        task_repo.add_checklist_item(task_id, "step-a", item_order=0, display_type="list")
        task_repo.add_checklist_item(task_id, "step-b", item_order=1, display_type="process")

        created_id = routine_advanced_service.auto_create_next_routine(task_id)
        repeated_id = routine_advanced_service.auto_create_next_routine(task_id)

        self.assertIsNotNone(created_id)
        self.assertEqual(repeated_id, created_id)

        created = task_repo.get_unified_task(created_id)
        self.assertEqual(created["target_date"], "2026-03-25")
        self.assertEqual(created["deadline"], "2026-03-25 09:30:00")
        self.assertEqual(created["status"], "in_progress")
        self.assertEqual(int(created.get("is_completed") or 0), 0)

        copied_items = task_repo.get_task_checklist_items(created_id)
        self.assertEqual([item["item_text"] for item in copied_items], ["step-a", "step-b"])
        self.assertEqual([item["display_type"] for item in copied_items], ["list", "process"])

        rows = [
            row
            for row in routine_advanced_service.search_routines(cycle_type="daily")
            if row.get("name") == "Routine Lifecycle"
        ]
        self.assertEqual(len(rows), 2)

    def test_ensure_overdue_routines_rollover_creates_current_instance_once(self):
        self._create_routine(
            name="Daily Carry",
            cycle_type="daily",
            target_date="2026-03-24",
            status="completed",
        )

        created = routine_advanced_service.ensure_overdue_routines_rollover("2026-03-28")
        created_again = routine_advanced_service.ensure_overdue_routines_rollover("2026-03-28")

        self.assertEqual(created, 1)
        self.assertEqual(created_again, 0)

        rows = [
            row
            for row in routine_advanced_service.search_routines(cycle_type="daily")
            if row.get("name") == "Daily Carry"
        ]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(row["target_date"] for row in rows), ["2026-03-24", "2026-03-28"])

    def test_ensure_overdue_routines_rollover_skips_when_open_instance_exists(self):
        self._create_routine(
            name="Open Carry",
            cycle_type="daily",
            target_date="2026-03-24",
            status="completed",
            location="desk",
        )
        self._create_routine(
            name="Open Carry",
            cycle_type="daily",
            target_date="2026-03-25",
            status="in_progress",
            location="desk",
        )

        created = routine_advanced_service.ensure_overdue_routines_rollover("2026-03-28")

        self.assertEqual(created, 0)
        rows = [
            row
            for row in routine_advanced_service.search_routines(cycle_type="daily")
            if row.get("name") == "Open Carry"
        ]
        self.assertEqual(len(rows), 2)

    def test_ensure_overdue_routines_rollover_uses_ad_hoc_identity_fields(self):
        self._create_routine(
            name="Shared Name",
            cycle_type="weekly",
            target_date="2026-03-16",
            status="completed",
            location="alpha",
        )
        self._create_routine(
            name="Shared Name",
            cycle_type="weekly",
            target_date="2026-03-16",
            status="completed",
            location="beta",
        )

        created = routine_advanced_service.ensure_overdue_routines_rollover("2026-03-28")

        self.assertEqual(created, 2)
        rows = [
            row
            for row in routine_advanced_service.search_routines(cycle_type="weekly")
            if row.get("name") == "Shared Name"
        ]
        self.assertEqual(
            sorted(row["target_date"] for row in rows),
            ["2026-03-16", "2026-03-16", "2026-03-30", "2026-03-30"],
        )


if __name__ == "__main__":
    unittest.main()
