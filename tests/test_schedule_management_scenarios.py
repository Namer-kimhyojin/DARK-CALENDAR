import unittest

from calendar_app.application import task_delete_usecases
from calendar_app.infrastructure import task_drop_service
from calendar_app.infrastructure.db import search_repo, task_repo
from tests.support import TemporaryDatabaseTestCase


class _DummyApp:
    def __init__(self):
        self.refresh_calls = []
        self._drag_pending_refresh = True
        self._is_dragging = True

    def schedule_panel_refresh(self, **kwargs):
        self.refresh_calls.append(kwargs)


class ScheduleManagementScenarioTests(TemporaryDatabaseTestCase):
    def _create_schedule(self, **overrides):
        payload = {
            "name": "Schedule",
            "type": "schedule",
            "priority": "normal",
            "status": "pending",
            "deadline": "2026-04-01 09:00:00",
            "end_date": "2026-04-01 10:00:00",
            "target_date": "2026-04-01",
            "all_day": 0,
        }
        payload.update(overrides)
        return task_repo.create_unified_task(payload)

    def _create_routine(self, **overrides):
        payload = {
            "name": "Routine",
            "type": "routine",
            "priority": "normal",
            "status": "in_progress",
            "cycle_type": "weekly",
            "target_date": "2026-04-01",
            "deadline": "2026-04-01 08:00:00",
        }
        payload.update(overrides)
        return task_repo.create_unified_task(payload)

    def test_delete_all_tasks_by_date_removes_schedules_and_checklist_rows(self):
        same_day = self._create_schedule(
            name="same-day", deadline="2026-04-01 09:00:00", target_date="2026-04-01"
        )
        all_day_target_only = self._create_schedule(
            name="target-only",
            deadline=None,
            end_date=None,
            target_date="2026-04-01",
            all_day=1,
        )
        other_day = self._create_schedule(
            name="other-day", deadline="2026-04-02 09:00:00", target_date="2026-04-02"
        )
        routine_same_day = self._create_routine(name="routine-same-day")

        self.assertIsNotNone(task_repo.add_checklist_item(same_day, "step-a"))
        self.assertIsNotNone(task_repo.add_checklist_item(all_day_target_only, "step-b"))
        self.assertIsNotNone(task_repo.add_checklist_item(other_day, "step-c"))
        self.assertIsNotNone(task_repo.add_checklist_item(routine_same_day, "step-r"))

        deleted_count = task_repo.delete_all_tasks_by_date("2026-04-01")

        self.assertEqual(deleted_count, 2)
        self.assertIsNone(task_repo.get_unified_task(same_day))
        self.assertIsNone(task_repo.get_unified_task(all_day_target_only))
        self.assertIsNotNone(task_repo.get_unified_task(other_day))
        self.assertIsNotNone(task_repo.get_unified_task(routine_same_day))

        self.assertEqual(task_repo.get_task_checklist_items(same_day), [])
        self.assertEqual(task_repo.get_task_checklist_items(all_day_target_only), [])
        self.assertEqual(len(task_repo.get_task_checklist_items(other_day)), 1)
        self.assertEqual(len(task_repo.get_task_checklist_items(routine_same_day)), 1)

    def test_delete_tasks_on_date_with_google_queue_targets_deleted_schedules_only(self):
        schedule_id = self._create_schedule(
            name="schedule-gcal",
            deadline="2026-05-10 14:00:00",
            target_date="2026-05-10",
            gcal_event_id="evt-schedule",
            gcal_source_calendar_id="cal-team",
        )
        routine_id = self._create_routine(
            name="routine-gcal",
            target_date="2026-05-10",
            deadline="2026-05-10 07:00:00",
            gcal_event_id="evt-routine",
            gcal_source_calendar_id="cal-routine",
        )
        other_schedule_id = self._create_schedule(
            name="schedule-other-day",
            deadline="2026-05-11 10:00:00",
            target_date="2026-05-11",
            gcal_event_id="evt-other",
            gcal_source_calendar_id="cal-team",
        )

        queued_refs = []
        deleted_count = task_delete_usecases.delete_tasks_on_date_with_google_queue(
            search_repo,
            task_repo,
            "2026-05-10",
            queue_delete_fn=lambda event_id, local_task_id, gcal_calendar_id: queued_refs.append(
                (event_id, local_task_id, gcal_calendar_id)
            ),
        )

        self.assertEqual(deleted_count, 1)
        self.assertEqual(queued_refs, [("evt-schedule", schedule_id, "cal-team")])
        self.assertIsNone(task_repo.get_unified_task(schedule_id))
        self.assertIsNotNone(task_repo.get_unified_task(routine_id))
        self.assertIsNotNone(task_repo.get_unified_task(other_schedule_id))


class TaskDropDefensiveScenarioTests(TemporaryDatabaseTestCase):
    def _create_schedule(self):
        return task_repo.create_unified_task(
            {
                "name": "DropScenario",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-06-01 09:00:00",
                "end_date": "2026-06-01 10:00:00",
                "target_date": "2026-06-01",
            }
        )

    def test_handle_task_drop_ignores_unknown_action(self):
        task_id = self._create_schedule()
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id],
            "2026-07-01",
            "13:00:00",
            "archive",
        )

        self.assertEqual(changed, 0)
        self.assertEqual(copied_ids, [])
        task = task_repo.get_unified_task(task_id)
        self.assertEqual(task["target_date"], "2026-06-01")
        self.assertEqual(task["deadline"], "2026-06-01 09:00:00")
        self.assertFalse(app._is_dragging)
        self.assertFalse(app._drag_pending_refresh)
        self.assertEqual(app.refresh_calls, [{"left": True, "center": True, "right": False}])

    def test_handle_task_drop_skips_invalid_task_ids(self):
        task_id = self._create_schedule()
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id, "bad-id", None, task_id],
            "2026-07-02",
            "15:30:00",
            "move",
        )

        self.assertEqual(changed, 1)
        self.assertEqual(copied_ids, [])
        moved = task_repo.get_unified_task(task_id)
        self.assertEqual(moved["target_date"], "2026-07-02")
        self.assertEqual(moved["deadline"], "2026-07-02 15:30:00")


if __name__ == "__main__":
    unittest.main()
