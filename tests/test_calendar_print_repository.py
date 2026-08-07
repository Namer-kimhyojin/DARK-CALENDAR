# -*- coding: utf-8 -*-

from calendar_app.infrastructure.db import calendar_repo, db_repository_unified
from calendar_app.infrastructure.db.calendar_print_repository import (
    load_calendar_print_source,
)
from tests.support import TemporaryDatabaseTestCase


class CalendarPrintRepositoryTests(TemporaryDatabaseTestCase):
    def setUp(self):
        super().setUp()
        calendar_repo.upsert_calendar(
            "local::visible",
            "local",
            "표시 캘린더",
            color="#3366cc",
            is_visible=True,
        )
        calendar_repo.upsert_calendar(
            "local::hidden",
            "local",
            "숨긴 캘린더",
            color="#cc6633",
            is_visible=False,
        )

    def _create(self, name, calendar_id, start, end=None):
        return db_repository_unified.create_unified_task(
            {
                "name": name,
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": start,
                "end_date": end or start,
                "target_date": start[:10],
                "calendar_id": calendar_id,
            }
        )

    def test_explicit_selection_can_print_a_hidden_calendar(self):
        visible_id = self._create("표시 일정", "local::visible", "2026-04-10 09:00:00")
        hidden_id = self._create("숨긴 일정", "local::hidden", "2026-04-10 10:00:00")

        source = load_calendar_print_source(
            "2026-04-01",
            "2026-04-30",
            ("local::hidden",),
        )
        ids = {row["id"] for row in source["rows"]}

        self.assertIn(hidden_id, ids)
        self.assertNotIn(visible_id, ids)

    def test_overlap_query_includes_events_starting_before_range(self):
        event_id = self._create(
            "연속 일정",
            "local::visible",
            "2026-03-29 09:00:00",
            "2026-04-03 18:00:00",
        )

        source = load_calendar_print_source(
            "2026-04-01",
            "2026-04-30",
            ("local::visible",),
        )

        self.assertIn(event_id, {row["id"] for row in source["rows"]})


if __name__ == "__main__":
    import unittest

    unittest.main()
