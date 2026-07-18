import unittest

from calendar_app.application import eod_usecases


class _FakeReportRepo:
    def __init__(self, events_by_date):
        self.events_by_date = events_by_date

    def get_calendar_events(self, date_str):
        return list(self.events_by_date.get(date_str, []))


class _FakeDirectiveRepo:
    def __init__(self, rows_by_date=None, recent_rows=None):
        self.rows_by_date = rows_by_date or {}
        self.recent_rows = recent_rows or []

    def get_directives_by_date(self, date_str):
        return list(self.rows_by_date.get(date_str, []))

    def get_recent_directives(self, limit=200):
        return list(self.recent_rows[:limit])


class _FallbackDirectiveRepo:
    def __init__(self, recent_rows):
        self.recent_rows = recent_rows

    def get_recent_directives(self, limit=200):
        return list(self.recent_rows[:limit])


class EodUsecasesTests(unittest.TestCase):
    def test_get_eod_summary_returns_date_scoped_directives_and_combined_counts(self):
        report_repo = _FakeReportRepo(
            {
                "2026-04-10": [
                    (1, "Focus block", "high", "2026-04-10 09:00:00", None, "#112233", None),
                ]
            }
        )
        directive_repo = _FakeDirectiveRepo(
            rows_by_date={
                "2026-04-10": [
                    {
                        "id": 11,
                        "content": "Send recap",
                        "status": "pending",
                        "receiver_name": "Team",
                        "deadline": "2026-04-10 18:00:00",
                        "memo": "daily wrap",
                        "bg_color": "#445566",
                        "priority": "urgent",
                    }
                ]
            }
        )

        summary = eod_usecases.get_eod_summary(report_repo, directive_repo, "2026-04-10")

        self.assertEqual(len(summary["events"]), 1)
        self.assertEqual(len(summary["directives"]), 1)
        self.assertEqual(summary["directives"][0][1], "Send recap")
        self.assertEqual(summary["summary"]["total"], 2)
        self.assertEqual(summary["summary"]["directive"], 1)
        self.assertEqual(summary["summary"]["high_priority"], 2)

    def test_get_eod_summary_filters_recent_directives_when_date_api_missing(self):
        report_repo = _FakeReportRepo({"2026-04-10": []})
        directive_repo = _FallbackDirectiveRepo(
            [
                (11, "Old", "pending", "Team", "2026-04-09 18:00:00", "", None),
                (12, "Today", "completed", "Team", "2026-04-10 18:00:00", "", None),
            ]
        )

        summary = eod_usecases.get_eod_summary(report_repo, directive_repo, "2026-04-10")

        self.assertEqual([row[1] for row in summary["directives"]], ["Today"])
        self.assertEqual(summary["summary"]["directive"], 1)


if __name__ == "__main__":
    unittest.main()
