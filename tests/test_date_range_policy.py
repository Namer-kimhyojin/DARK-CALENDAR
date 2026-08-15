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
