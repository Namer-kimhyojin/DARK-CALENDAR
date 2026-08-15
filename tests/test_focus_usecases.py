# -*- coding: utf-8 -*-

from datetime import datetime
import unittest

from calendar_app.application import focus_usecases
from calendar_app.infrastructure.db import database_unified, db_repository
from tests.support import TemporaryDatabaseTestCase


class _FakeFocusRepo:
    def __init__(
        self, *, tasks_by_date=None, incomplete_tasks=None, directive_rows=None, urgent_task=None
    ):
        self.tasks_by_date = tasks_by_date or {}
        self.incomplete_tasks = list(incomplete_tasks or [])
        self.directive_rows = list(directive_rows or [])
        self.urgent_task = urgent_task or (None, None)
        self.worklog_rows = []
        self.worklog_calls = []
        self.worklog_stats = {
            "today_sessions": 0,
            "today_secs": 0,
            "monthly_sessions": 0,
            "monthly_secs": 0,
        }
        self.worklog_stats_calls = []

    def get_tasks_by_date(self, date_str):
        return list(self.tasks_by_date.get(date_str, []))

    def get_incomplete_tasks(self):
        return list(self.incomplete_tasks)

    def get_recent_directives(self, limit=200):
        return list(self.directive_rows[:limit])

    def get_most_urgent_pending_task(self, today_str):
        return self.urgent_task

    def get_worklog_entries(self, limit=100):
        self.worklog_calls.append(limit)
        return list(self.worklog_rows[:limit])

    def get_worklog_stats(self, reference_date):
        self.worklog_stats_calls.append(reference_date)
        return dict(self.worklog_stats)


class FocusUsecasesTests(unittest.TestCase):
    def test_normalize_focus_log_entry_accepts_extended_tuple_and_mapping(self):
        tuple_entry = focus_usecases.normalize_focus_log_entry(
            (7, 11, "문서 검토", 125, "2026-08-15 09:30:00", "schedule")
        )
        mapping_entry = focus_usecases.normalize_focus_log_entry(
            {
                "id": 8,
                "task_id": 12,
                "task_name": "회의",
                "elapsed_secs": -3,
                "logged_at": "2026-08-14 13:00:00",
            }
        )

        self.assertEqual(tuple_entry.task_type, "schedule")
        self.assertEqual(tuple_entry.elapsed_secs, 125)
        self.assertEqual(mapping_entry.task_name, "회의")
        self.assertEqual(mapping_entry.elapsed_secs, 0)

    def test_history_snapshot_uses_one_read_for_rows_and_both_stats(self):
        repo = _FakeFocusRepo()
        repo.worklog_rows = [
            (1, 10, "오늘 1", 120, "2026-08-15 09:00:00"),
            (2, 11, "오늘 2", 180, "2026-08-15 10:00:00", "task"),
            (3, 12, "이번 달", 300, "2026-08-01 11:00:00"),
            (4, 13, "지난 달", 600, "2026-07-31 11:00:00"),
            (5, 14, "깨진 날짜", 900, "not-a-date"),
        ]
        repo.worklog_stats = {
            "today_sessions": 2,
            "today_secs": 300,
            "monthly_sessions": 3,
            "monthly_secs": 600,
        }

        snapshot = focus_usecases.get_focus_history_snapshot(
            repo,
            limit=2,
            stats_limit=5000,
            now=datetime(2026, 8, 15, 12, 0, 0),
        )

        self.assertEqual(repo.worklog_calls, [2])
        self.assertEqual(repo.worklog_stats_calls, ["2026-08-15"])
        self.assertEqual([entry.id for entry in snapshot.entries], [1, 2])
        self.assertEqual(snapshot.stats.today_sessions, 2)
        self.assertEqual(snapshot.stats.today_secs, 300)
        self.assertEqual(snapshot.stats.monthly_sessions, 3)
        self.assertEqual(snapshot.stats.monthly_secs, 600)

    def test_history_snapshot_surfaces_repository_errors(self):
        class BrokenRepo:
            def get_worklog_entries(self, limit=100):
                raise RuntimeError("history unavailable")

            def get_worklog_stats(self, reference_date):
                return None

        snapshot = focus_usecases.get_focus_history_snapshot(
            BrokenRepo(), now=datetime(2026, 8, 15, 12, 0, 0)
        )

        self.assertEqual(snapshot.entries, ())
        self.assertEqual(snapshot.stats, focus_usecases.FocusStatsSnapshot())
        self.assertIn("history unavailable", snapshot.load_error)

    def test_all_filter_excludes_past_and_far_future_items(self):
        repo = _FakeFocusRepo(
            incomplete_tasks=[
                {
                    "id": 1,
                    "name": "Past schedule",
                    "priority": "normal",
                    "deadline": "2026-04-01 09:00:00",
                    "type": "schedule",
                    "is_completed": False,
                },
                {
                    "id": 2,
                    "name": "Ongoing schedule",
                    "priority": "normal",
                    "deadline": "2026-04-01 09:00:00",
                    "end_date": "2026-04-02 18:00:00",
                    "type": "schedule",
                    "is_completed": False,
                },
                {
                    "id": 3,
                    "name": "Soon task",
                    "priority": "normal",
                    "deadline": "2026-04-03 09:00:00",
                    "type": "schedule",
                    "is_completed": False,
                },
                {
                    "id": 4,
                    "name": "Far schedule",
                    "priority": "normal",
                    "deadline": "2027-04-04 09:00:00",
                    "type": "schedule",
                    "is_completed": False,
                },
                {
                    "id": 5,
                    "name": "Undated task",
                    "priority": "high",
                    "deadline": "",
                    "type": "task",
                    "is_completed": False,
                },
            ],
            directive_rows=[
                (101, "Past directive", "pending", "", "2026-04-01 10:00:00", "", None),
                (102, "Soon directive", "pending", "", "2026-04-04 10:00:00", "", None),
                (103, "Far directive", "pending", "", "2027-04-04 10:00:00", "", None),
            ],
        )

        tasks = focus_usecases.get_filtered_focus_tasks(repo, "all", "2026-04-02")

        self.assertEqual(
            [task.get("name") for task in tasks],
            ["Ongoing schedule", "Soon task", "Undated task", "Soon directive"],
        )

    def test_today_and_directives_filter_removes_past_and_too_far_directives(self):
        repo = _FakeFocusRepo(
            tasks_by_date={
                "2026-04-02": [
                    {
                        "id": 1,
                        "name": "Today task",
                        "priority": "normal",
                        "deadline": "2026-04-02 09:00:00",
                        "type": "schedule",
                        "is_completed": False,
                    },
                    {
                        "id": 2,
                        "name": "Completed task",
                        "priority": "normal",
                        "deadline": "2026-04-02 13:00:00",
                        "type": "schedule",
                        "is_completed": True,
                    },
                ]
            },
            directive_rows=[
                (101, "Past directive", "pending", "", "2026-04-01 10:00:00", "", None),
                (102, "Soon directive", "pending", "", "2026-04-05 10:00:00", "", None),
                (103, "Far directive", "pending", "", "2027-04-04 10:00:00", "", None),
            ],
        )

        tasks = focus_usecases.get_filtered_focus_tasks(repo, "today_and_directives", "2026-04-02")

        self.assertEqual(
            [task.get("name") for task in tasks],
            ["Today task", "Soon directive"],
        )

    def test_auto_select_fallback_skips_out_of_window_tasks(self):
        repo = _FakeFocusRepo(urgent_task=(None, None))

        task_id, task_name = focus_usecases.select_auto_focus_task(
            repo,
            "2026-04-02",
            fallback_tasks=[
                {
                    "id": 1,
                    "name": "Past schedule",
                    "deadline": "2026-04-01 09:00:00",
                    "type": "schedule",
                },
                {
                    "id": 2,
                    "name": "Far schedule",
                    "deadline": "2027-04-04 09:00:00",
                    "type": "schedule",
                },
                {
                    "id": 3,
                    "name": "Valid schedule",
                    "deadline": "2026-04-03 09:00:00",
                    "type": "schedule",
                },
            ],
        )

        self.assertEqual(task_id, 3)
        self.assertEqual(task_name, "Valid schedule")


class FocusRepositoryStatsTests(TemporaryDatabaseTestCase):
    def test_worklog_stats_are_uncapped_and_ignore_other_months(self):
        conn = database_unified.db_manager.get_connection()
        conn.executemany(
            "INSERT INTO worklog (task_id, task_type, elapsed_secs, logged_at) "
            "VALUES (?, 'schedule', ?, ?)",
            [
                (1, 120, "2026-08-15 09:00:00"),
                (2, 180, "2026-08-15 10:00:00"),
                (3, 300, "2026-08-01 11:00:00"),
                (4, 600, "2026-07-31 11:00:00"),
                (5, -5, "2026-08-02 11:00:00"),
            ],
        )
        conn.commit()

        stats = db_repository.get_worklog_stats("2026-08-15")

        self.assertEqual(stats["today_sessions"], 2)
        self.assertEqual(stats["today_secs"], 300)
        self.assertEqual(stats["monthly_sessions"], 4)
        self.assertEqual(stats["monthly_secs"], 600)

    def test_worklog_stats_query_uses_logged_at_index(self):
        conn = database_unified.db_manager.get_connection()
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list('worklog')").fetchall()}
        self.assertIn("idx_worklog_logged_at", indexes)

        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM worklog "
            "WHERE logged_at >= ? AND logged_at < ?",
            ("2026-08-01 00:00:00", "2026-09-01 00:00:00"),
        ).fetchall()
        detail = " ".join(str(row["detail"]) for row in plan).upper()
        self.assertIn("IDX_WORKLOG_LOGGED_AT", detail)
        self.assertNotIn("SCAN WORKLOG", detail)


if __name__ == "__main__":
    unittest.main()
