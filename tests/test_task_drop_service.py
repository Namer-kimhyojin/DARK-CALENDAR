import unittest

from calendar_app.infrastructure import task_drop_service
from calendar_app.infrastructure.db import calendar_repo, task_repo
from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR
from tests.support import TemporaryDatabaseTestCase


class _DummyApp:
    def __init__(self):
        self.refresh_calls = []
        self._drag_pending_refresh = True
        self._is_dragging = True

    def schedule_panel_refresh(self, **kwargs):
        self.refresh_calls.append(kwargs)


class TaskDropServiceTests(TemporaryDatabaseTestCase):
    def _create_schedule_task(self):
        return task_repo.create_unified_task(
            {
                "name": "DropTest",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-03-05 09:00:00",
                "end_date": "2026-03-05 10:00:00",
                "target_date": "2026-03-05",
            }
        )

    def test_move_updates_datetime_and_requests_refresh(self):
        task_id = self._create_schedule_task()
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id],
            "2026-04-01",
            "14:30:00",
            "move",
        )

        self.assertEqual(changed, 1)
        self.assertEqual(copied_ids, [])

        moved = task_repo.get_unified_task(task_id)
        self.assertEqual(moved["target_date"], "2026-04-01")
        self.assertEqual(moved["deadline"], "2026-04-01 14:30:00")
        self.assertEqual(moved["end_date"], "2026-04-01 15:30:00")

        self.assertFalse(app._is_dragging)
        self.assertFalse(app._drag_pending_refresh)
        self.assertEqual(app.refresh_calls, [{"left": True, "center": True, "right": False}])

    def test_copy_creates_new_task_with_moved_datetime(self):
        task_id = self._create_schedule_task()
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id],
            "2026-04-02",
            "11:00:00",
            "copy",
        )

        self.assertEqual(changed, 1)
        self.assertEqual(len(copied_ids), 1)
        self.assertNotEqual(copied_ids[0], task_id)

        original = task_repo.get_unified_task(task_id)
        copied = task_repo.get_unified_task(copied_ids[0])
        self.assertEqual(original["target_date"], "2026-03-05")
        self.assertEqual(copied["target_date"], "2026-04-02")
        self.assertEqual(copied["deadline"], "2026-04-02 11:00:00")
        self.assertEqual(copied["end_date"], "2026-04-02 12:00:00")
        self.assertEqual(copied["status"], "in_progress")

        self.assertEqual(app.refresh_calls, [{"left": True, "center": True, "right": False}])

    def test_move_skips_task_in_read_only_calendar(self):
        readonly_cal_id = "gcal::readonly-calendar@example.com"
        calendar_repo.upsert_calendar(
            readonly_cal_id,
            "gcal",
            "Read only calendar",
            color=DEFAULT_CALENDAR_COLOR,
            is_default=False,
            is_active=False,
            is_visible=True,
            gcal_calendar_id="readonly-calendar@example.com",
        )
        task_id = task_repo.create_unified_task(
            {
                "name": "ReadOnly",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-03-05 09:00:00",
                "end_date": "2026-03-05 10:00:00",
                "target_date": "2026-03-05",
                "calendar_id": readonly_cal_id,
            }
        )
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id],
            "2026-04-01",
            "14:30:00",
            "move",
        )

        self.assertEqual(changed, 0)
        self.assertEqual(copied_ids, [])
        self.assertEqual(getattr(app, "_last_drop_blocked_readonly_ids", []), [task_id])

        task = task_repo.get_unified_task(task_id)
        self.assertEqual(task["target_date"], "2026-03-05")
        self.assertEqual(task["deadline"], "2026-03-05 09:00:00")

    def test_copy_allows_task_in_read_only_calendar(self):
        readonly_cal_id = "gcal::readonly-copy@example.com"
        calendar_repo.upsert_calendar(
            readonly_cal_id,
            "gcal",
            "Read only calendar",
            color=DEFAULT_CALENDAR_COLOR,
            is_default=False,
            is_active=False,
            is_visible=True,
            gcal_calendar_id="readonly-copy@example.com",
        )
        task_id = task_repo.create_unified_task(
            {
                "name": "ReadOnlyCopy",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-03-05 09:00:00",
                "end_date": "2026-03-05 10:00:00",
                "target_date": "2026-03-05",
                "calendar_id": readonly_cal_id,
            }
        )
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id],
            "2026-04-02",
            "11:00:00",
            "copy",
        )

        self.assertEqual(changed, 1)
        self.assertEqual(len(copied_ids), 1)
        self.assertEqual(getattr(app, "_last_drop_blocked_readonly_ids", []), [])

    def test_calendar_read_only_helper(self):
        writable_id = "local::writable"
        readonly_gcal_id = "gcal::readonly-helper@example.com"
        readonly_ics_id = "ics::abcd1234"

        calendar_repo.upsert_calendar(
            writable_id, "local", "Writable", is_active=True, is_visible=True
        )
        calendar_repo.upsert_calendar(
            readonly_gcal_id,
            "gcal",
            "Read only gcal",
            is_active=False,
            is_visible=True,
            gcal_calendar_id="readonly-helper@example.com",
        )
        calendar_repo.upsert_calendar(
            readonly_ics_id,
            "ics",
            "Read only ics",
            is_active=True,
            is_visible=True,
            ics_url="https://example.com/test.ics",
        )

        self.assertFalse(calendar_repo.is_calendar_read_only(writable_id))
        self.assertTrue(calendar_repo.is_calendar_read_only(readonly_gcal_id))
        self.assertTrue(calendar_repo.is_calendar_read_only(readonly_ics_id))

    def test_move_skips_task_when_source_calendar_is_read_only(self):
        source_gcal_id = "source-readonly@example.com"
        readonly_cal_id = f"gcal::{source_gcal_id}"
        calendar_repo.upsert_calendar(
            readonly_cal_id,
            "gcal",
            "Read only source",
            is_active=False,
            is_visible=True,
            gcal_calendar_id=source_gcal_id,
        )
        task_id = task_repo.create_unified_task(
            {
                "name": "SourceReadOnly",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-03-05 09:00:00",
                "end_date": "2026-03-05 10:00:00",
                "target_date": "2026-03-05",
                "calendar_id": None,
                "gcal_source_calendar_id": source_gcal_id,
            }
        )
        app = _DummyApp()

        changed, copied_ids = task_drop_service.handle_task_drop(
            app,
            [task_id],
            "2026-04-01",
            "14:30:00",
            "move",
        )

        self.assertEqual(changed, 0)
        self.assertEqual(copied_ids, [])
        self.assertEqual(getattr(app, "_last_drop_blocked_readonly_ids", []), [task_id])


if __name__ == "__main__":
    unittest.main()
