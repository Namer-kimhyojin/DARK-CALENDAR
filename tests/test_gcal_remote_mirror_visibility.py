import unittest

from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from calendar_app.infrastructure.google_sync import repository as gcal_repo
from tests.support import TemporaryDatabaseTestCase


class RemoteMirrorVisibilityTests(TemporaryDatabaseTestCase):
    def test_overlap_query_includes_remote_mirror_even_if_type_is_routine(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Remote mirror event",
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": "2026-03-26 12:00:00",
                "end_date": "2026-03-26 13:00:00",
                "target_date": "2026-03-26",
                "calendar_id": "gcal::test@example.com",
                "gcal_event_id": "evt-1",
                "gcal_source_calendar_id": "test@example.com",
                "gcal_target_calendar_id": "test@example.com",
                "gcal_sync_mode": "remote_mirror",
            }
        )
        self.assertIsNotNone(task_id)

        conn = unified_repo.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE unified_task SET type='routine' WHERE id=?", (task_id,))
        conn.commit()

        rows = unified_repo.get_schedule_tasks_overlapping_range_with_progress(
            "2026-03-26", "2026-03-26"
        )
        row_ids = {row["id"] for row in rows}
        self.assertIn(task_id, row_ids)

    def test_find_unlinked_does_not_match_routine_rows(self):
        routine_id = unified_repo.create_unified_task(
            {
                "name": "Same Payload",
                "type": "routine",
                "priority": "normal",
                "status": "in_progress",
                "deadline": "2026-03-26 12:00:00",
                "end_date": "2026-03-26 13:00:00",
                "target_date": "2026-03-26",
                "all_day": 0,
            }
        )
        self.assertIsNotNone(routine_id)
        conn = unified_repo.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE unified_task SET gcal_sync_mode='unknown' WHERE id=?", (routine_id,))
        conn.commit()

        relink_id = gcal_repo.find_unlinked_unified_task_for_gcal_payload(
            "Same Payload",
            "2026-03-26 12:00:00",
            "2026-03-26 13:00:00",
            all_day=0,
            source_calendar_id=None,
        )
        self.assertIsNone(relink_id)

        schedule_id = unified_repo.create_unified_task(
            {
                "name": "Same Payload",
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": "2026-03-26 12:00:00",
                "end_date": "2026-03-26 13:00:00",
                "target_date": "2026-03-26",
                "all_day": 0,
            }
        )
        self.assertIsNotNone(schedule_id)
        conn = unified_repo.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE unified_task SET gcal_sync_mode='unknown' WHERE id=?", (schedule_id,))
        conn.commit()

        relink_id = gcal_repo.find_unlinked_unified_task_for_gcal_payload(
            "Same Payload",
            "2026-03-26 12:00:00",
            "2026-03-26 13:00:00",
            all_day=0,
            source_calendar_id=None,
        )
        self.assertEqual(relink_id, schedule_id)


if __name__ == "__main__":
    unittest.main()
