# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QRect, QSize, Qt
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

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

    def test_toolbar_month_title_uses_localized_template(self):
        with patch.object(
            month_renderer,
            "t",
            side_effect=lambda key, default=None: (
                "{year}년 {month_name}" if key == "calendar.month_title" else default
            ),
        ):
            title = month_renderer._format_toolbar_date(QDate(2026, 9, 17), True)

        self.assertEqual(title, "2026년 9월")

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

    def test_monthly_time_uses_start_and_skips_all_day_rows(self):
        row = {"deadline": "2026-03-26T09:30:00+09:00", "end_date": "2026-03-26 10:30:00"}
        self.assertEqual(month_renderer._month_start_time(row), "09:30")
        self.assertEqual(month_renderer._month_start_time({**row, "all_day": True}), "")
        self.assertEqual(month_renderer._month_start_time({"deadline": "2026-03-26"}), "")

    def test_widget_calendar_cache_includes_deduplicated_subscription_rows(self):
        local = [{"id": 1, "name": "Local"}]
        subscription = [{"id": 2, "name": "Subscription", "read_only": True}]

        rows = month_renderer._widget_calendar_cache_rows(local, subscription)

        self.assertEqual([1, 2], [row["id"] for row in rows])
        rows[0]["name"] = "Changed"
        self.assertEqual("Local", local[0]["name"])

    def test_month_weekday_separator_paints_continuously_in_each_theme(self):
        for name, background, divider in (
            ("dark", "#121827", "rgba(255,255,255,0.16)"),
            ("light", "#f3f1fa", "rgba(0,0,0,0.16)"),
            ("custom_glass", "rgba(18,42,46,150)", "rgba(208,232,236,0.25)"),
        ):
            for columns in (5, 7):
                with self.subTest(theme=name, columns=columns):
                    tokens = month_renderer._resolve_calendar_tokens(
                        {"bg_main": background, "divider": divider}
                    )
                    host = QFrame()
                    self.addCleanup(host.close)
                    host.setObjectName("calendar_surface")
                    host.setStyleSheet(month_renderer._calendar_surface_style(tokens=tokens))
                    layout = QVBoxLayout(host)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(0)
                    start = QDate(2026, 10, 26)
                    header = month_renderer._build_month_weekday_header(
                        [start.addDays(index) for index in range(columns)], tokens
                    )
                    layout.addWidget(header)
                    body = QWidget()
                    body.setFixedHeight(40)
                    layout.addWidget(body)
                    host.resize(700, header.sizeHint().height() + 40)
                    host.show()
                    self._app.processEvents()
                    self.assertTrue(header.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
                    self.assertEqual(len(header.findChildren(QLabel)), columns)
                    image = header.grab().toImage()
                    bottom = image.height() - 1
                    samples = [image.pixelColor(x, bottom) for x in range(2, image.width() - 2)]
                    self.assertTrue(all(color == samples[0] for color in samples))
                    self.assertNotEqual(samples[0], image.pixelColor(image.width() // 2, bottom - 2))
                    host.close()


class DraggableTaskButtonRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_constructor_builds_title_widgets(self):
        btn = DraggableTaskButton(100, "Render Regression")
        self.assertEqual(btn.title_label.text(), "Render Regression")
        self.assertGreater(btn.title_bar.minimumHeight(), 0)
        detail_style = btn.detail_container.styleSheet()
        self.assertIn("QFrame#taskDetailCard {", detail_style)
        self.assertNotRegex(detail_style, r"^\s*background-color:")

    def test_timed_chip_keeps_title_when_resized(self):
        for prefix in ("09:30", "09:30 ⚡"):
            with self.subTest(prefix=prefix):
                button = DraggableTaskButton(101, "Review")
                button.set_title_time_hint(prefix)
                label = button.title_label
                full_text = f"{prefix} Review"
                label.resize(label.fontMetrics().horizontalAdvance(full_text) + 5, 24)
                self.assertEqual(label._display_text(), full_text)
                label.resize(label.fontMetrics().horizontalAdvance("Review") + 5, 24)
                self.assertEqual(label._display_text(), "Review")
                self.assertEqual(button.raw_text, "Review")

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

    def test_hover_and_detail_singletons_are_recreated_after_deletion(self):
        """Window teardown deletes the shared popups; later events must not raise."""
        from PyQt6 import sip
        from PyQt6.QtCore import QEvent

        from calendar_app.presentation.widgets import ui_components

        popup = ui_components.get_hover_info_popup()
        overlay = get_detail_overlay()
        sip.delete(popup)
        sip.delete(overlay)

        fresh_popup = ui_components.get_hover_info_popup()
        fresh_overlay = get_detail_overlay()
        self.assertFalse(sip.isdeleted(fresh_popup))
        self.assertFalse(sip.isdeleted(fresh_overlay))
        self.assertIsNot(fresh_popup, popup)
        self.assertIsNot(fresh_overlay, overlay)

        # Deleted again: the app-wide filter and the cancel helper must stay quiet.
        sip.delete(ui_components.get_hover_info_popup())
        sip.delete(get_detail_overlay())
        ui_components.hide_hover_info()
        watched = QWidget()
        event_filter = ui_components.HoverInfoEventFilter()
        try:
            for kind in (QEvent.Type.MouseMove, QEvent.Type.Leave, QEvent.Type.Enter):
                self.assertFalse(
                    event_filter.eventFilter(watched, QEvent(kind)),
                    kind,
                )
        finally:
            watched.deleteLater()
            event_filter.deleteLater()

    def test_detail_card_closes_when_its_calendar_item_is_rebuilt(self):
        """A refresh may delete the item while its floating detail card is open."""
        from PyQt6 import sip

        task = {"id": 78, "name": "Refresh", "status": "pending", "deadline": "2026-09-22"}
        host = QWidget()
        layout = QVBoxLayout(host)
        button = DraggableTaskButton(78, "Refresh")
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
        ):
            button.toggle_expand()
            self._app.processEvents()
        overlay = get_detail_overlay()
        self.assertTrue(overlay.isVisible())
        action_buttons = button.actions_widget.findChildren(QPushButton)
        self.assertEqual(2, len(action_buttons))

        sip.delete(button)
        self._app.processEvents()

        self.assertFalse(overlay.isVisible())
        self.assertIsNone(overlay._owner)
        self.assertEqual(0, overlay.layout().count())
        # Stale action rows must not reach the deleted item's signals.
        for action in action_buttons:
            if not sip.isdeleted(action):
                action.click()
        self._app.processEvents()
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
