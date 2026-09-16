# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QRect, QSize
from PyQt6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from calendar_app.presentation import drag_drop_manager
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.widgets.ui_components import (
    DraggableTaskButton,
    _detail_overlay_position,
    get_detail_overlay,
)
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

    def test_widget_calendar_cache_includes_deduplicated_subscription_rows(self):
        local = [{"id": 1, "name": "Local"}]
        subscription = [{"id": 2, "name": "Subscription", "read_only": True}]

        rows = month_renderer._widget_calendar_cache_rows(local, subscription)

        self.assertEqual([1, 2], [row["id"] for row in rows])
        rows[0]["name"] = "Changed"
        self.assertEqual("Local", local[0]["name"])


class DraggableTaskButtonRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_constructor_builds_title_widgets(self):
        btn = DraggableTaskButton(100, "Render Regression")
        self.assertEqual(btn.title_label.text(), "Render Regression")
        self.assertGreater(btn.title_bar.minimumHeight(), 0)

    def test_bottom_row_detail_card_opens_above_anchor(self):
        available = QRect(0, 0, 1920, 1040)
        bottom_row = QRect(100, 990, 190, 24)
        card_size = QSize(320, 224)

        point = _detail_overlay_position(bottom_row, card_size, available)

        self.assertLessEqual(point.y() + card_size.height(), bottom_row.top())
        self.assertGreaterEqual(point.y(), available.top() + 8)

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

    def test_narrow_calendar_item_opens_readable_non_overlapping_detail_card(self):
        task = {
            "id": 77,
            "name": "[회의] 포미아-아카데미 운영 점검",
            "priority": "low",
            "status": "completed",
            "deadline": "2026-09-22 14:00:00",
            "end_date": "2026-09-22 15:00:00",
            "all_day": False,
            "location": "회의실",
            "assignee": "김담당",
            "description": "진행 상태를 확인합니다.",
            "calendar_id": "local::work",
        }
        host = QWidget()
        host.resize(210, 260)
        layout = QVBoxLayout(host)
        button = DraggableTaskButton(77, "📌 [회의] 포미아-아카...")
        button.setFixedWidth(190)
        layout.addWidget(button)
        host.show()

        with (
            patch(
                "calendar_app.presentation.widgets.ui_components.task_repo.get_unified_task",
                return_value=task,
            ),
            patch(
                "calendar_app.presentation.widgets.ui_components.checklist_repo.get_task_checklist_items",
                return_value=[],
            ),
            patch(
                "calendar_app.presentation.widgets.ui_components.calendar_repo.get_calendar",
                return_value={"id": "local::work", "name": "업무 캘린더"},
            ),
        ):
            button.toggle_expand()
            self._app.processEvents()
            overlay = get_detail_overlay()
            self.assertGreaterEqual(overlay.width(), 320)

            action_buttons = button.actions_widget.findChildren(QPushButton)
            self.assertEqual(2, len(action_buttons))
            self.assertLessEqual(
                action_buttons[0].geometry().right(),
                action_buttons[1].geometry().left(),
            )

            overlay._do_collapse()
            self._app.processEvents()
            button.toggle_expand()
            self._app.processEvents()
            self.assertEqual(2, len(button.actions_widget.findChildren(QPushButton)))
            overlay._do_collapse()

        host.close()


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
