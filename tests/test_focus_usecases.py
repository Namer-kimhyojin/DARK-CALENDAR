import unittest

from calendar_app.application import focus_usecases


class _FakeFocusRepo:
    def __init__(
        self, *, tasks_by_date=None, incomplete_tasks=None, directive_rows=None, urgent_task=None
    ):
        self.tasks_by_date = tasks_by_date or {}
        self.incomplete_tasks = list(incomplete_tasks or [])
        self.directive_rows = list(directive_rows or [])
        self.urgent_task = urgent_task or (None, None)

    def get_tasks_by_date(self, date_str):
        return list(self.tasks_by_date.get(date_str, []))

    def get_incomplete_tasks(self):
        return list(self.incomplete_tasks)

    def get_recent_directives(self, limit=200):
        return list(self.directive_rows[:limit])

    def get_most_urgent_pending_task(self, today_str):
        return self.urgent_task


class FocusUsecasesTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
