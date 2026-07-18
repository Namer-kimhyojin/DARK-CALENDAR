import unittest

from calendar_app.application import review_usecases


class _FakeRepo:
    def __init__(self, rows_by_date):
        self.rows_by_date = rows_by_date

    def get_all_tasks_by_date(self, date_str):
        return list(self.rows_by_date.get(date_str, []))


class _FakeDirectiveRepo:
    def __init__(self, rows_by_date):
        self.rows_by_date = rows_by_date

    def get_directives_by_date(self, date_str):
        return list(self.rows_by_date.get(date_str, []))


class ReviewUsecasesTests(unittest.TestCase):
    def test_build_daily_review_counts_states(self):
        repo = _FakeRepo(
            {
                "2026-04-10": [
                    {
                        "id": 1,
                        "type": "schedule",
                        "status": "completed",
                        "priority": "high",
                        "deadline": "2026-04-10 09:00:00",
                    },
                    {
                        "id": 2,
                        "type": "routine",
                        "status": "in_progress",
                        "priority": "normal",
                        "deadline": "2026-04-10 11:00:00",
                    },
                    {
                        "id": 3,
                        "type": "schedule",
                        "status": "pending",
                        "priority": "urgent",
                        "deadline": "2026-04-09 12:00:00",
                    },
                ]
            }
        )

        daily = review_usecases.build_daily_review(repo, "2026-04-10")

        self.assertEqual(daily["total"], 3)
        self.assertEqual(daily["completed"], 1)
        self.assertEqual(daily["in_progress"], 1)
        self.assertEqual(daily["pending"], 1)
        self.assertEqual(daily["overdue"], 1)
        self.assertEqual(daily["high_priority"], 2)
        self.assertEqual(daily["schedule"], 2)
        self.assertEqual(daily["routine"], 1)
        self.assertEqual(daily["completion_rate"], 33.3)

    def test_build_weekly_review_aggregates_unique_tasks(self):
        repo = _FakeRepo(
            {
                "2026-04-13": [
                    {
                        "id": 10,
                        "type": "schedule",
                        "status": "pending",
                        "deadline": "2026-04-13 09:00:00",
                    },
                    {
                        "id": 11,
                        "type": "routine",
                        "status": "completed",
                        "deadline": "2026-04-13 10:00:00",
                    },
                ],
                "2026-04-14": [
                    {
                        "id": 10,
                        "type": "schedule",
                        "status": "pending",
                        "deadline": "2026-04-13 09:00:00",
                    },
                    {
                        "id": 12,
                        "type": "schedule",
                        "status": "deferred",
                        "deadline": "2026-04-14 12:00:00",
                    },
                ],
            }
        )

        weekly = review_usecases.build_weekly_review(repo, "2026-04-13", days=2)

        self.assertEqual(weekly["period_start"], "2026-04-13")
        self.assertEqual(weekly["period_end"], "2026-04-14")
        self.assertEqual(len(weekly["days"]), 2)
        self.assertEqual(weekly["summary"]["total"], 3)  # id=10 deduplicated across days
        self.assertEqual(weekly["summary"]["completed"], 1)
        self.assertEqual(weekly["summary"]["deferred"], 1)

    def test_build_daily_review_includes_directives_when_available(self):
        repo = _FakeRepo(
            {
                "2026-04-10": [
                    {
                        "id": 1,
                        "type": "schedule",
                        "status": "completed",
                        "priority": "normal",
                        "deadline": "2026-04-10 09:00:00",
                    },
                ]
            }
        )
        directive_repo = _FakeDirectiveRepo(
            {
                "2026-04-10": [
                    {
                        "id": 101,
                        "content": "Review note",
                        "status": "pending",
                        "priority": "urgent",
                        "deadline": "2026-04-10 18:00:00",
                    },
                    {
                        "id": 102,
                        "content": "Late item",
                        "status": "in_progress",
                        "priority": "low",
                        "deadline": "2026-04-09 12:00:00",
                    },
                ]
            }
        )

        daily = review_usecases.build_daily_review(
            repo, "2026-04-10", directive_repo=directive_repo
        )

        self.assertEqual(daily["total"], 3)
        self.assertEqual(daily["completed"], 1)
        self.assertEqual(daily["pending"], 1)
        self.assertEqual(daily["in_progress"], 1)
        self.assertEqual(daily["directive"], 2)
        self.assertEqual(daily["high_priority"], 1)
        self.assertEqual(daily["overdue"], 1)


if __name__ == "__main__":
    unittest.main()
