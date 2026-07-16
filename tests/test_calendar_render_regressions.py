# -*- coding: utf-8 -*-

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication

from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from calendar_app.presentation import drag_drop_manager
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.widgets.ui_components import DraggableTaskButton
from tests.support import TemporaryDatabaseTestCase


class MonthRendererDateParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_coerce_qdate_accepts_iso_datetime_with_timezone(self):
        qd = month_renderer._coerce_qdate("2026-03-26T09:30:00+09:00")
        self.assertIsNotNone(qd)
        self.assertTrue(qd.isValid())
        self.assertEqual(qd.toString("yyyy-MM-dd"), "2026-03-26")

    def test_task_date_range_falls_back_to_target_date(self):
        task = {
            "deadline": "",
            "end_date": "",
            "target_date": "2026-03-26",
        }
        start_date, end_date = month_renderer._task_date_range(task)
        self.assertIsNotNone(start_date)
        self.assertEqual(start_date.toString("yyyy-MM-dd"), "2026-03-26")
        self.assertEqual(end_date.toString("yyyy-MM-dd"), "2026-03-26")


class DraggableTaskButtonRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_constructor_builds_title_widgets(self):
        btn = DraggableTaskButton(100, "Render Regression")
        self.assertEqual(btn.title_label.text(), "Render Regression")
        self.assertGreater(btn.title_bar.minimumHeight(), 0)

    def test_drag_pixmap_renders_single_and_stacked_cards(self):
        single = drag_drop_manager.build_task_drag_pixmap(
            [100], {100: {"name": "Render Regression"}}
        )
        stacked = drag_drop_manager.build_task_drag_pixmap(
            [100, 101, 102],
            {
                100: {"name": "First"},
                101: {"name": "Second"},
                102: {"name": "Third"},
            },
        )

        self.assertEqual(single.size(), stacked.size())
        self.assertGreaterEqual(single.width(), 240)
        self.assertGreaterEqual(single.height(), 80)
        self.assertGreater(single.toImage().pixelColor(24, 24).alpha(), 0)
        self.assertGreater(stacked.toImage().pixelColor(30, 6).alpha(), 0)


class MonthRendererMonthRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_month_view_uses_minimal_full_week_span(self):
        dates = month_renderer._build_month_dates(
            QDate(2026, 4, 2),
            show_weekends=True,
            start_monday=True,
        )
        self.assertEqual(35, len(dates))
        self.assertEqual("2026-03-30", dates[0].toString("yyyy-MM-dd"))
        self.assertEqual("2026-05-03", dates[-1].toString("yyyy-MM-dd"))

    def test_month_view_keeps_six_weeks_only_when_needed(self):
        dates = month_renderer._build_month_dates(
            QDate(2026, 8, 1),
            show_weekends=True,
            start_monday=True,
        )
        self.assertEqual(42, len(dates))
        self.assertEqual("2026-07-27", dates[0].toString("yyyy-MM-dd"))
        self.assertEqual("2026-09-06", dates[-1].toString("yyyy-MM-dd"))

    def test_month_view_respects_hidden_weekends(self):
        dates = month_renderer._build_month_dates(
            QDate(2026, 4, 2),
            show_weekends=False,
            start_monday=True,
        )
        self.assertEqual(25, len(dates))
        self.assertEqual("2026-03-30", dates[0].toString("yyyy-MM-dd"))
        self.assertEqual("2026-05-01", dates[-1].toString("yyyy-MM-dd"))


class ScheduleOverlapFallbackTests(TemporaryDatabaseTestCase):
    def test_overlap_query_includes_target_date_when_deadline_missing(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Fallback schedule",
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": "2026-03-26 09:00:00",
                "end_date": "2026-03-26 10:00:00",
                "target_date": "2026-03-26",
            }
        )
        self.assertIsNotNone(task_id)

        conn = unified_repo.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE unified_task SET deadline=NULL, end_date=NULL WHERE id=?", (task_id,))
        conn.commit()

        rows = unified_repo.get_schedule_tasks_overlapping_range_with_progress(
            "2026-03-26", "2026-03-26"
        )
        returned_ids = {row["id"] for row in rows}
        self.assertIn(task_id, returned_ids)


if __name__ == "__main__":
    unittest.main()
