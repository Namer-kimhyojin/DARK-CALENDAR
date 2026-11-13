# -*- coding: utf-8 -*-

from datetime import date
import unittest

from calendar_app.domain.date_range import (
    InclusiveDateRange,
    inclusive_day_count,
    inclusive_end_from_exclusive,
)
from calendar_app.presentation.calendar.month_renderer import _subscription_period_text


class InclusiveDateRangeTests(unittest.TestCase):
    def test_single_and_multi_day_spans_are_inclusive(self):
        self.assertEqual(inclusive_day_count(date(2026, 8, 15), date(2026, 8, 15)), 1)
        self.assertEqual(inclusive_day_count(date(2026, 8, 15), date(2026, 8, 16)), 2)

    def test_span_crosses_month_boundary_without_special_case(self):
        period = InclusiveDateRange(date(2026, 8, 31), date(2026, 9, 2))

        self.assertEqual(period.day_count, 3)

    def test_external_exclusive_end_converts_to_last_visible_day(self):
        start = date(2026, 8, 15)

        self.assertEqual(inclusive_end_from_exclusive(start, date(2026, 8, 17)), date(2026, 8, 16))
        self.assertEqual(inclusive_end_from_exclusive(start, start), start)

    def test_start_and_span_preserves_requested_visible_day_count(self):
        period = InclusiveDateRange.from_start_and_span(date(2026, 8, 31), 3)

        self.assertEqual(period.end, date(2026, 9, 2))
        self.assertEqual(period.day_count, 3)

    def test_invalid_direct_range_is_rejected_and_safe_count_clamps(self):
        with self.assertRaises(ValueError):
            InclusiveDateRange(date(2026, 8, 16), date(2026, 8, 15))
        self.assertEqual(inclusive_day_count(date(2026, 8, 16), date(2026, 8, 15)), 1)

    def test_subscription_all_day_period_displays_inclusive_end(self):
        period = _subscription_period_text(
            {
                "all_day": 1,
                "deadline": "2026-08-15 00:00:00",
                "end_date": "2026-08-16 00:00:00",
                "_start_raw": "2026-08-15",
                "_end_raw": "2026-08-17",
            }
        )

        self.assertIn("2026.08.15", period)
        self.assertIn("2026.08.16", period)
        self.assertNotIn("2026.08.17", period)


if __name__ == "__main__":
    unittest.main()


class TimedSpanDayPlacementTests(unittest.TestCase):
    def test_midnight_end_is_exclusive_and_month_view_agrees(self):
        from datetime import datetime as _dt
        from types import SimpleNamespace

        from calendar_app.domain.date_range import timed_span_last_day
        from calendar_app.presentation.calendar.month_renderer import (
            _normalize_subscription_event,
            _task_date_range,
        )

        self.assertEqual(
            timed_span_last_day("2026-11-13 23:00:00", "2026-11-14 00:00:00"), date(2026, 11, 13)
        )
        self.assertEqual(
            timed_span_last_day("2026-11-13 23:00:00", "2026-11-14 00:30:00"), date(2026, 11, 14)
        )
        self.assertIsNone(timed_span_last_day("2026-11-13", "2026-11-14"))

        start, end = _task_date_range(
            {"deadline": "2026-11-13 23:00:00", "end_date": "2026-11-14 00:00:00", "all_day": 0}
        )
        self.assertEqual(start, end)
        start, end = _task_date_range(
            {"deadline": "2026-11-13 00:00:00", "end_date": "2026-11-15 00:00:00", "all_day": 1}
        )
        self.assertEqual(start.daysTo(end), 2)

        event = SimpleNamespace(
            id="e1",
            summary="NY",
            start_time="2026-11-13T18:00:00-05:00",
            end_time="2026-11-13T19:00:00-05:00",
        )
        row = _normalize_subscription_event({"calendar_id": "c"}, event, 0)
        expected = _dt.fromisoformat("2026-11-13T18:00:00-05:00").astimezone().replace(tzinfo=None)
        self.assertEqual(row["deadline"], expected.strftime("%Y-%m-%d %H:%M:%S"))
