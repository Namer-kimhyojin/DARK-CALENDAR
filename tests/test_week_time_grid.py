# -*- coding: utf-8 -*-
"""Exercise actual Qt pointer gestures and geometry in the weekly planner."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QEvent, QPoint, Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid


class WeekTimeGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.grid = WeekTimeGrid()
        self.addCleanup(self.grid.close)
        self.grid.resize(1000, 700)
        self.start = QDate(2026, 10, 5)
        self.grid.set_week(self.start, [])
        self.grid.show()
        self.app.processEvents()
        self.grid.scroll_to_time(8 * 60)
        self.app.processEvents()

    def task(self, identity=1, start="2026-10-05 09:00:00", end="2026-10-05 10:00:00", **kwargs):
        return {
            "id": identity,
            "name": f"일정 {identity}",
            "deadline": start,
            "end_date": end,
            "all_day": 0,
            **kwargs,
        }

    def load(self, tasks, **kwargs):
        self.grid.set_week(self.start, tasks, **kwargs)
        self.app.processEvents()

    def point(self, day, minute):
        x = self.grid.GUTTER + (day + 0.5) * self.grid._column_width()
        return QPoint(round(x), round(minute * self.grid.HOUR_HEIGHT / 60))

    def drag(self, canvas, start, end):
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas, end, 10)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        self.app.processEvents()

    def test_date_only_and_explicit_all_day_keep_midnight_timed(self):
        tasks = [
            self.task(1, "2026-10-05", "2026-10-06"),
            self.task(2, "2026-10-05 00:00:00", "2026-10-05 00:30:00"),
            self.task(3, "2026-10-05 00:00:00", "2026-10-05 00:00:00", all_day=1),
        ]
        self.load(tasks)
        self.assertEqual([segment.task["id"] for segment in self.grid._segments], [2])
        self.assertEqual(
            [(segment.task["id"], segment.day) for segment in self.grid._all_day],
            [(1, 0), (1, 1), (3, 0)],
        )
        self.assertEqual(tasks[0]["deadline"], "2026-10-05")

    def test_target_date_only_task_can_be_scheduled_from_all_day_lane(self):
        task = {
            "id": 1,
            "name": "보고서 제출",
            "target_date": "2026-10-05",
            "deadline": None,
            "end_date": None,
            "all_day": 1,
        }
        self.load([task])
        self.assertEqual(len(self.grid._all_day_rects), 1)
        changed = QSignalSpy(self.grid.reschedule_requested)
        source = self.grid._all_day_rects[0][1].center().toPoint()
        target_global = self.grid._timeline.mapToGlobal(self.point(1, 600))
        target_local = self.grid._all_day_canvas.mapFromGlobal(target_global)
        self.drag(self.grid._all_day_canvas, source, target_local)
        self.assertEqual(list(changed), [[task, "2026-10-06", 600, 15]])

    def test_missing_end_gets_default_fifteen_minutes(self):
        self.load([self.task(end="")])
        segment = self.grid._segments[0]
        self.assertEqual((segment.start, segment.end, segment.duration), (540, 555, 15))

    def test_overlap_groups_share_lanes_without_covering_each_other(self):
        tasks = [
            self.task(),
            self.task(2, "2026-10-05 09:30:00", "2026-10-05 10:30:00"),
            self.task(3, "2026-10-05 10:00:00", "2026-10-05 11:00:00"),
            self.task(4, "2026-10-05 11:00:00", "2026-10-05 12:00:00"),
        ]
        self.load(tasks)
        rects = {task["id"]: rect for task, _date, rect in self.grid.event_rects()}
        self.assertLessEqual(rects[1].right(), rects[2].left())
        self.assertEqual(rects[1].left(), rects[3].left())
        self.assertGreater(rects[4].width(), rects[1].width() * 1.8)

    def test_blank_click_creates_snapped_fifteen_minute_task(self):
        created, interactions = (
            QSignalSpy(self.grid.create_requested),
            QSignalSpy(self.grid.interaction_changed),
        )
        QTest.mouseClick(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(1, 9 * 60 + 8),
        )
        self.assertEqual(list(created), [["2026-10-06", 555, 15]])
        self.assertEqual(list(interactions), [[True], [False]])

    def test_drag_blank_range_supports_forward_and_backward_duration(self):
        created = QSignalSpy(self.grid.create_requested)
        self.drag(self.grid._timeline, self.point(2, 600), self.point(2, 675))
        self.drag(self.grid._timeline, self.point(3, 675), self.point(3, 600))
        self.assertEqual(list(created), [["2026-10-07", 600, 75], ["2026-10-08", 600, 75]])

    def test_drag_event_changes_day_and_start_preserving_duration(self):
        task = self.task()
        self.load([task])
        changed = QSignalSpy(self.grid.reschedule_requested)
        self.drag(self.grid._timeline, self.point(0, 560), self.point(1, 620))
        self.assertEqual(list(changed), [[task, "2026-10-06", 600, 60]])
        self.assertEqual(task["deadline"], "2026-10-05 09:00:00")

    def test_move_short_existing_event_preserves_five_minute_duration(self):
        task = self.task(end="2026-10-05 09:05:00")
        self.load([task])
        changed = QSignalSpy(self.grid.reschedule_requested)
        self.drag(self.grid._timeline, self.point(0, 542), self.point(1, 602))
        self.assertEqual(list(changed), [[task, "2026-10-06", 600, 5]])

    def test_bottom_resize_updates_whole_duration(self):
        task = self.task()
        self.load([task])
        changed = QSignalSpy(self.grid.reschedule_requested)
        rect = self.grid.event_rects()[0][2]
        start = QPoint(round(rect.center().x()), round(rect.bottom() - 2))
        self.drag(self.grid._timeline, start, self.point(0, 645))
        self.assertEqual(list(changed), [[task, "2026-10-05", 540, 105]])

    def test_cross_midnight_splits_without_a_phantom_midnight_end_segment(self):
        self.load([self.task(start="2026-10-05 23:00:00", end="2026-10-07 00:00:00")])
        segments = self.grid._segments
        self.assertEqual(
            [(item.day, item.start, item.end) for item in segments], [(0, 1380, 1440), (1, 0, 1440)]
        )
        self.assertEqual([item.duration for item in segments], [1500, 1500])
        self.assertEqual([item.final for item in segments], [False, True])

    def test_move_continuation_subtracts_original_offset(self):
        task = self.task(start="2026-10-05 23:00:00", end="2026-10-06 01:00:00")
        self.load([task])
        self.grid.scroll_to_time(0)
        changed = QSignalSpy(self.grid.reschedule_requested)
        self.drag(self.grid._timeline, self.point(1, 15), self.point(2, 75))
        self.assertEqual(list(changed), [[task, "2026-10-07", 0, 120]])

    def test_resize_continuation_preserves_previous_day_time(self):
        task = self.task(start="2026-10-05 23:00:00", end="2026-10-06 01:00:00")
        self.load([task])
        self.grid.scroll_to_time(0)
        changed = QSignalSpy(self.grid.reschedule_requested)
        final_rect = self.grid.event_rects()[1][2]
        start = QPoint(round(final_rect.center().x()), round(final_rect.bottom() - 2))
        self.drag(self.grid._timeline, start, self.point(1, 120))
        self.assertEqual(list(changed), [[task, "2026-10-05", 1380, 180]])

    def test_all_day_drag_into_timeline_assigns_default_duration(self):
        task = self.task(start="2026-10-05", end="2026-10-05", all_day=1)
        self.load([task])
        changed = QSignalSpy(self.grid.reschedule_requested)
        source = self.grid._all_day_rects[0][1].center().toPoint()
        target_global = self.grid._timeline.mapToGlobal(self.point(1, 600))
        target_local = self.grid._all_day_canvas.mapFromGlobal(target_global)
        self.drag(self.grid._all_day_canvas, source, target_local)
        self.assertEqual(list(changed), [[task, "2026-10-06", 600, 15]])

    def test_read_only_calendar_opens_but_cannot_be_moved_or_resized(self):
        task = self.task(read_only=True)
        self.load([task])
        changed, opened = (
            QSignalSpy(self.grid.reschedule_requested),
            QSignalSpy(self.grid.edit_requested),
        )
        self.drag(self.grid._timeline, self.point(0, 560), self.point(1, 620))
        self.assertEqual(len(changed), 0)
        QTest.mouseClick(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 560),
        )
        self.assertEqual(list(opened), [[task]])

    def test_custom_dates_keep_friday_monday_separated_when_weekends_hidden(self):
        dates = [QDate(2026, 10, 8), QDate(2026, 10, 9), QDate(2026, 10, 12)]
        task = self.task(start="2026-10-09 09:00:00", end="2026-10-09 10:00:00")
        self.load([task], dates=dates)
        changed = QSignalSpy(self.grid.reschedule_requested)
        self.drag(self.grid._timeline, self.point(1, 560), self.point(2, 560))
        self.assertEqual(list(changed), [[task, "2026-10-12", 540, 60]])

    def test_escape_cancels_preview_and_releases_interaction_guard(self):
        created, interactions = (
            QSignalSpy(self.grid.create_requested),
            QSignalSpy(self.grid.interaction_changed),
        )
        QTest.mousePress(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 600),
        )
        QTest.mouseMove(self.grid._timeline, self.point(0, 660))
        QTest.keyClick(self.grid, Qt.Key.Key_Escape)
        QTest.mouseRelease(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 660),
        )
        self.assertEqual(len(created), 0)
        self.assertEqual(list(interactions), [[True], [False]])
        self.assertIsNone(self.grid._preview)

    def test_hide_cancels_active_gesture(self):
        interactions = QSignalSpy(self.grid.interaction_changed)
        QTest.mousePress(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 600),
        )
        self.grid.hide()
        self.assertEqual(list(interactions), [[True], [False]])

    def test_window_deactivation_cancels_active_gesture(self):
        interactions = QSignalSpy(self.grid.interaction_changed)
        QTest.mousePress(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 600),
        )
        QApplication.sendEvent(self.grid, QEvent(QEvent.Type.WindowDeactivate))
        self.assertEqual(list(interactions), [[True], [False]])
        self.assertIsNone(self.grid._gesture)

    def test_dragging_near_viewport_edge_autoscrolls_and_cancels_timer(self):
        QTest.mousePress(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 600),
        )
        viewport = self.grid._scroll.viewport()
        edge_global = viewport.mapToGlobal(
            QPoint(round(self.grid.GUTTER + self.grid._column_width() / 2), viewport.height() - 5)
        )
        edge_local = self.grid._timeline.mapFromGlobal(edge_global)
        QTest.mouseMove(self.grid._timeline, edge_local)
        before = self.grid._scroll.verticalScrollBar().value()
        self.grid._autoscroll_tick()
        self.assertGreater(self.grid._scroll.verticalScrollBar().value(), before)
        QTest.keyClick(self.grid, Qt.Key.Key_Escape)
        self.assertFalse(self.grid._autoscroll_timer.isActive())

    def test_repeating_event_opens_without_emitting_a_move(self):
        task = self.task(recurrence="weekly")
        self.load([task])
        changed, opened = (
            QSignalSpy(self.grid.reschedule_requested),
            QSignalSpy(self.grid.edit_requested),
        )
        self.drag(self.grid._timeline, self.point(0, 560), self.point(1, 620))
        QTest.mouseClick(
            self.grid._timeline,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.point(0, 560),
        )
        self.assertEqual(len(changed), 0)
        self.assertEqual(list(opened), [[task]])

    def test_continuation_move_snaps_original_non_grid_start(self):
        task = self.task(start="2026-10-05 23:05:30", end="2026-10-06 01:00:00")
        self.load([task])
        self.grid.scroll_to_time(0)
        changed = QSignalSpy(self.grid.reschedule_requested)
        self.drag(self.grid._timeline, self.point(1, 15), self.point(2, 75))
        self.assertEqual(list(changed), [[task, "2026-10-07", 0, 115]])

    def test_keyboard_selection_enter_opens_and_scrolls_event(self):
        task = self.task()
        self.load([task])
        opened = QSignalSpy(self.grid.edit_requested)
        QTest.keyClick(self.grid, Qt.Key.Key_Down)
        QTest.keyClick(self.grid, Qt.Key.Key_Return)
        self.assertEqual(list(opened), [[task]])

    def test_first_keyboard_selection_starts_at_the_correct_end_after_escape(self):
        tasks = [
            self.task(1),
            self.task(2, start="2026-10-05 11:00:00", end="2026-10-05 12:00:00"),
            self.task(3, start="2026-10-06 09:00:00", end="2026-10-06 10:00:00"),
        ]
        self.load(tasks)
        for key, expected in (
            (Qt.Key.Key_Up, tasks[-1]),
            (Qt.Key.Key_Left, tasks[-1]),
            (Qt.Key.Key_Down, tasks[0]),
            (Qt.Key.Key_Right, tasks[0]),
        ):
            with self.subTest(key=key):
                QTest.keyClick(self.grid, Qt.Key.Key_Escape)
                QTest.keyClick(self.grid, key)
                self.assertIs(self.grid._selected, expected)

    def test_keyboard_selection_wraps_both_ends_without_skipping_an_event(self):
        tasks = [
            self.task(1),
            self.task(2, start="2026-10-05 11:00:00", end="2026-10-05 12:00:00"),
            self.task(3, start="2026-10-06 09:00:00", end="2026-10-06 10:00:00"),
        ]
        self.load(tasks)
        for key, expected in (
            (Qt.Key.Key_Down, tasks[0]),
            (Qt.Key.Key_Up, tasks[-1]),
            (Qt.Key.Key_Down, tasks[0]),
            (Qt.Key.Key_Right, tasks[1]),
            (Qt.Key.Key_Right, tasks[2]),
            (Qt.Key.Key_Right, tasks[0]),
        ):
            QTest.keyClick(self.grid, key)
            self.assertIs(self.grid._selected, expected)

    def test_scroll_restore_before_show_and_user_scroll_signal(self):
        grid = WeekTimeGrid()
        self.addCleanup(grid.close)
        grid.resize(1000, 700)
        grid.scroll_to_time(540)
        grid.show()
        self.app.processEvents()
        self.assertEqual(grid._scroll.verticalScrollBar().value(), 648)
        scrolled = QSignalSpy(grid.scroll_position_changed)
        grid._scroll.verticalScrollBar().setValue(720)
        self.assertEqual(list(scrolled), [[600]])

    def test_keyboard_selection_keeps_a_fitting_timed_event_fully_visible(self):
        tasks = [
            self.task(1, start="2026-10-05 01:00:00", end="2026-10-05 03:00:00"),
            self.task(2, start="2026-10-05 19:00:00", end="2026-10-05 21:00:00"),
        ]
        self.load(tasks)
        for key in (Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Up):
            QTest.keyClick(self.grid, key)
            rect = next(
                rect for item, rect in self.grid._timed_rects if item.task is self.grid._selected
            )
            top = self.grid._scroll.verticalScrollBar().value()
            self.assertGreaterEqual(rect.top(), top)
            self.assertLessEqual(rect.bottom(), top + self.grid._scroll.viewport().height())

    def test_semantic_rgba_tokens_and_long_titles_render(self):
        task = self.task(name="매우 긴 일정 " * 30, bg_color="rgba(90, 140, 200, 0.8)")
        self.load(
            [task],
            tokens={
                "content_bg": "rgba(245, 247, 250, 0.95)",
                "text_primary": "rgba(25, 30, 40, 255)",
                "border": "rgba(80, 90, 100, 0.2)",
            },
        )
        self.assertFalse(self.grid.grab().isNull())
        self.assertEqual(self.grid._color("text_primary").red(), 25)

    def test_hover_shows_literal_title_and_owning_calendar_name(self):
        self.load([self.task(name="<공휴일 & 일정>", _calendar_name="<R&D> 캘린더")])
        QTest.mouseMove(self.grid._timeline, self.point(0, 570))
        self.app.processEvents()
        document = QTextDocument()
        document.setHtml(self.grid._timeline.toolTip())
        text = document.toPlainText()
        self.assertIn("<공휴일 & 일정>", text)
        self.assertIn("<R&D> 캘린더", text)
        self.assertIn("2026-10-05", text)


if __name__ == "__main__":
    unittest.main()
