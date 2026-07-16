# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

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
        local_cal_id = "local::copy-target"
        calendar_repo.upsert_calendar(
            local_cal_id,
            "local",
            "Copy target",
            color=DEFAULT_CALENDAR_COLOR,
            is_default=True,
            is_active=True,
            is_visible=True,
        )
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
                "gcal_source_calendar_id": "readonly-copy@example.com",
                "gcal_source_summary": "Read only calendar",
                "gcal_target_calendar_id": "readonly-copy@example.com",
                "gcal_sync_mode": "remote_mirror",
                "series_id": "remote-series",
                "series_order": 2,
                "series_total": 4,
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

        copied = task_repo.get_unified_task(copied_ids[0])
        default_calendar = calendar_repo.get_default_calendar()
        self.assertIsNotNone(default_calendar)
        self.assertEqual(copied["calendar_id"], default_calendar["id"])
        self.assertIsNone(copied["gcal_event_id"])
        self.assertIsNone(copied["gcal_source_calendar_id"])
        self.assertIsNone(copied["gcal_source_summary"])
        self.assertIsNone(copied["gcal_target_calendar_id"])
        self.assertEqual(copied["gcal_sync_mode"], "local_owned")
        self.assertEqual(copied["gcal_dirty"], 1)
        self.assertIsNone(copied["series_id"])
        self.assertIsNone(copied["series_order"])
        self.assertIsNone(copied["series_total"])

    def test_finalize_task_drag_flushes_refresh_deferred_by_cancel(self):
        app = _DummyApp()

        task_drop_service.finalize_task_drag(app)

        self.assertFalse(app._is_dragging)
        self.assertFalse(app._drag_pending_refresh)
        self.assertEqual(app.refresh_calls, [{"left": True, "center": True, "right": False}])

    def test_batch_move_rolls_back_when_one_update_fails(self):
        first_id = self._create_schedule_task()
        second_id = self._create_schedule_task()
        app = _DummyApp()
        original_update = task_repo.update_unified_task
        call_count = 0

        def fail_second_update(task_id, updates, mark_gcal_dirty=None, commit=True):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return False
            return original_update(
                task_id,
                updates,
                mark_gcal_dirty=mark_gcal_dirty,
                commit=commit,
            )

        with patch.object(task_repo, "update_unified_task", side_effect=fail_second_update):
            changed, copied_ids = task_drop_service.handle_task_drop(
                app,
                [first_id, second_id],
                "2026-04-03",
                "12:00:00",
                "move",
            )

        self.assertEqual(changed, 0)
        self.assertEqual(copied_ids, [])
        self.assertEqual(app._last_drop_failed_ids, [first_id, second_id])
        self.assertEqual(task_repo.get_unified_task(first_id)["target_date"], "2026-03-05")
        self.assertEqual(task_repo.get_unified_task(second_id)["target_date"], "2026-03-05")

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
