# -*- coding: utf-8 -*-
"""Hourly calendar integration checks with isolated SQLite and INI settings."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QDockWidget, QLineEdit, QMainWindow, QWidget

from calendar_app.infrastructure.db import calendar_repo, task_repo
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin
from tests.support import TemporaryDatabaseTestCase


class CalendarRenderHost(QMainWindow):
    """Exercise the real calendar renderer without bootstrap or sync workers."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.current_date = QDate(2026, 10, 7)
        self.view_mode_state = "weekly_1"
        self.cal_week_layout = settings.value("cal_week_layout", "time")
        self.cal_show_weekends = True
        self.cal_start_monday = True
        self.cal_show_month = False
        self.cal_show_weekday = True
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self.active_editing_task_ids = set()
        self._active_calendar_range_drag_cell = None
        self._is_calendar_range_dragging = False
        self._is_dragging = False
        self._drag_pending_refresh = False
        self._latest_calendar_range_data = None
        self._gcal_subscription_events_cache = {}
        self._last_clicked_date = None
        self.gcal_sync = None
        self.refreshes = []
        self.dialog_calls = []
        self.modified_ids = []
        self.toasts = []
        self.wake_calls = 0
        self.search_edit = QLineEdit(self)
        self.center_dock = QDockWidget(self)
        self.center_frame = QWidget(self.center_dock)
        self.center_dock.setWidget(self.center_frame)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.center_dock)
        self.resize(1320, 900)

    @staticmethod
    def reset_frame(frame):
        layout = frame.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        sip.delete(layout)

    @staticmethod
    def _noop(*_args, **_kwargs):
        return None

    jump_to_today = _noop
    prev_day = _noop
    next_day = _noop
    change_view_mode = _noop
    toggle_weekends = _noop
    toggle_show_month = _noop
    toggle_show_weekday = _noop
    toggle_start_day = _noop
    open_calendar_print_dialog = _noop
    open_calendar_management = _noop
    sync_calendars = _noop
    handle_task_status_changed = _noop
    handle_task_priority_changed = _noop
    handle_task_deleted = _noop
    handle_task_clicked = _noop
    handle_color_auto_assign_requested = _noop
    handle_color_change_requested = _noop
    handle_color_clear_requested = _noop
    handle_checklist_requested = _noop
    handle_alarm_clear_requested = _noop
    handle_task_rename_requested = _noop
    handle_task_resized = _noop
    handle_cell_click = _noop
    handle_cell_shift_click = _noop
    handle_cell_drag_range = _noop
    handle_task_dropped = _noop
    update_task_selection_status = _noop

    @staticmethod
    def _calendar_toolbar_visible_setting():
        return True

    def schedule_panel_refresh(self, **kwargs):
        self.refreshes.append(kwargs)

    def open_task_dialog(self, *args, **kwargs):
        self.dialog_calls.append((args, kwargs))

    def open_modify_task_dialog(self, task_id, **_kwargs):
        self.modified_ids.append(task_id)

    def show_toast(self, *args):
        self.toasts.append(args)

    def wake_calendar_sync(self):
        self.wake_calls += 1


def seed_preview_tasks():
    """Insert deterministic examples into the caller's isolated test database."""
    calendar_repo.upsert_calendar("local::planner-preview", "local", "업무", "#5294f7")
    calendar_repo.upsert_calendar("local::private-preview", "local", "개인", "#a88fe9")
    calendar_repo.upsert_calendar(
        "ics::preview", "ics", "구독 캘린더", "#d29a58", access_role="reader"
    )
    entries = [
        (
            "팀 주간회의",
            "2026-10-05 09:00:00",
            "2026-10-05 10:00:00",
            False,
            "local::planner-preview",
        ),
        (
            "기획안 작성",
            "2026-10-05 10:30:00",
            "2026-10-05 12:00:00",
            False,
            "local::planner-preview",
        ),
        (
            "자료 검토",
            "2026-10-06 13:00:00",
            "2026-10-06 14:30:00",
            False,
            "local::planner-preview",
        ),
        (
            "협력사 미팅",
            "2026-10-06 13:30:00",
            "2026-10-06 15:00:00",
            False,
            "local::private-preview",
        ),
        (
            "프로젝트 집중 작업",
            "2026-10-07 09:30:00",
            "2026-10-07 11:30:00",
            False,
            "local::planner-preview",
        ),
        ("읽기 전용 일정", "2026-10-08 11:00:00", "2026-10-08 12:00:00", False, "ics::preview"),
        (
            "다음 주 계획",
            "2026-10-09 15:00:00",
            "2026-10-09 16:00:00",
            False,
            "local::planner-preview",
        ),
        ("보고서 제출", "2026-10-07", "2026-10-07", True, "local::planner-preview"),
        ("현장 출장", "2026-10-08 00:00:00", "2026-10-09 23:59:00", True, "local::private-preview"),
    ]
    result = []
    for title, start, end, all_day, calendar_id in entries:
        task_id = task_repo.create_unified_task(
            {
                "name": title,
                "type": "schedule",
                "deadline": start,
                "end_date": end,
                "target_date": start[:10],
                "all_day": int(all_day),
                "calendar_id": calendar_id,
            }
        )
        if not task_id:
            raise RuntimeError("Failed to seed isolated planner example")
        result.append(task_repo.get_unified_task(task_id))
    return result


class WeekPlannerIntegrationTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "settings.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("gcal_enabled", False)
        self.settings.setValue("theme_color", "#5294f7")
        self.settings.setValue("text_theme", "light")
        self.settings.setValue("panel_base_color", "#202735")
        self.settings.setValue("last_opacity", 255)
        self.settings.setValue("last_opacity_unit", "byte")
        self.host = CalendarRenderHost(self.settings)
        month_renderer.invalidate_calendar_meta_cache()
        self.theme_patch = patch(
            "calendar_app.shared.theme_settings.QSettings", return_value=self.settings
        )
        self.theme_patch.start()
        self.snapshot_patch = patch(
            "calendar_app.shared.theme_snapshot.QSettings", return_value=self.settings
        )
        self.snapshot_patch.start()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.qt_app.processEvents()
        self.theme_patch.stop()
        self.snapshot_patch.stop()
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    @staticmethod
    def _controller():
        from calendar_app.presentation.calendar import week_planner_controller

        return week_planner_controller

    def _render(self, subscription_rows=()):
        with patch.object(
            month_renderer, "_get_subscription_events", return_value=list(subscription_rows)
        ):
            month_renderer.render_calendar(self.host)
        self.host.show()
        self.qt_app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _task(self, **extra):
        calendar_repo.upsert_calendar("local::test", "local", "Test", "#5294f7")
        payload = {
            "name": "Editable",
            "type": "schedule",
            "deadline": "2026-10-07 09:00:00",
            "end_date": "2026-10-07 10:00:00",
            "target_date": "2026-10-07",
            "all_day": 0,
            "calendar_id": "local::test",
        }
        payload.update(extra)
        task_id = task_repo.create_unified_task(payload)
        self.assertTrue(task_id)
        return task_repo.get_unified_task(task_id)

    def test_create_prefills_exact_midnight_and_cross_midnight_end(self):
        controller = self._controller()
        controller.create_week_schedule(self.host, "2026-10-07", 0, 15)
        kwargs = self.host.dialog_calls[-1][1]
        self.assertEqual(kwargs["initial_time"].toString("HH:mm"), "00:00")
        self.assertEqual(kwargs["end_time"].toString("HH:mm"), "00:15")
        controller.create_week_schedule(self.host, "2026-10-07", 1425, 60)
        kwargs = self.host.dialog_calls[-1][1]
        self.assertEqual(kwargs["initial_date"], QDate(2026, 10, 7))
        self.assertEqual(kwargs["end_date"], QDate(2026, 10, 8))
        self.assertEqual(kwargs["end_time"].toString("HH:mm"), "00:45")

    def test_successful_reschedule_preserves_calendar_and_dispatches_common_sync(self):
        controller = self._controller()
        task = self._task()
        with patch.object(controller.gcal_push_queue, "enqueue") as enqueue:
            saved = controller.reschedule_week_schedule(self.host, task, "2026-10-08", 600, 90)
        self.assertTrue(saved)
        persisted = task_repo.get_unified_task(task["id"])
        self.assertEqual(persisted["deadline"][:16], "2026-10-08 10:00")
        self.assertEqual(persisted["end_date"][:16], "2026-10-08 11:30")
        self.assertEqual(persisted["calendar_id"], "local::test")
        self.assertEqual(self.host.wake_calls, 1)
        self.assertTrue(self.host.refreshes)
        enqueue.assert_not_called()

    def test_enabled_google_push_receives_fresh_saved_row(self):
        controller = self._controller()
        task = self._task()
        self.settings.setValue("gcal_enabled", True)
        with patch.object(controller.gcal_push_queue, "enqueue") as enqueue:
            self.assertTrue(
                controller.reschedule_week_schedule(self.host, task, "2026-10-07", 720, 45)
            )
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(enqueue.call_args.args[1]["deadline"][:16], "2026-10-07 12:00")

    def test_readonly_calendar_blocks_stale_editable_payload(self):
        controller = self._controller()
        task = self._task()
        stale = dict(task)
        calendar_repo.upsert_calendar("ics::test", "ics", "Read only", "#bb9955")
        task_repo.update_unified_task(task["id"], {"calendar_id": "ics::test"})
        with patch.object(controller.gcal_push_queue, "enqueue") as enqueue:
            self.assertFalse(
                controller.reschedule_week_schedule(self.host, stale, "2026-10-08", 600, 30)
            )
        persisted = task_repo.get_unified_task(task["id"])
        self.assertEqual(persisted["deadline"], task["deadline"])
        self.assertEqual(self.host.wake_calls, 0)
        enqueue.assert_not_called()
        self.assertTrue(self.host.toasts)

    def test_recurring_google_instance_does_not_silently_retime(self):
        controller = self._controller()
        task = self._task()
        task_repo.update_unified_task(task["id"], {"gcal_recurring_series_id": "series-id"})
        task = task_repo.get_unified_task(task["id"])
        with patch.object(controller.gcal_push_queue, "enqueue") as enqueue:
            self.assertFalse(
                controller.reschedule_week_schedule(self.host, task, "2026-10-08", 600, 30)
            )
        self.assertEqual(task_repo.get_unified_task(task["id"])["deadline"], task["deadline"])
        self.assertEqual(self.host.wake_calls, 0)
        enqueue.assert_not_called()
        self.assertTrue(self.host.toasts)

    def test_save_failure_leaves_database_and_input_row_unchanged(self):
        controller = self._controller()
        task = self._task()
        original = deepcopy(task)
        with (
            patch.object(task_repo, "update_unified_task", return_value=False),
            patch.object(controller.gcal_push_queue, "enqueue") as enqueue,
        ):
            self.assertFalse(
                controller.reschedule_week_schedule(self.host, task, "2026-10-08", 600, 30)
            )
        self.assertEqual(task, original)
        self.assertEqual(task_repo.get_unified_task(task["id"])["deadline"], original["deadline"])
        self.assertEqual(self.host.wake_calls, 0)
        enqueue.assert_not_called()
        self.assertTrue(self.host.refreshes)

    def test_layout_choice_is_persisted_and_restored_in_a_new_host(self):
        controller = self._controller()
        controller.set_week_layout(self.host, "date")
        self.settings.sync()
        restored_settings = QSettings(self.settings.fileName(), QSettings.Format.IniFormat)
        restored_host = CalendarRenderHost(restored_settings)
        self.addCleanup(restored_host.close)
        self.assertEqual(restored_host.cal_week_layout, "date")
        controller.set_week_layout(self.host, "time")
        self.assertEqual(self.settings.value("cal_week_layout"), "time")

    def test_search_and_calendar_visibility_feed_hourly_view_but_cache_keeps_source(self):
        seed_preview_tasks()
        calendar_repo.set_calendar_visible("local::private-preview", False)
        self.host.search_edit.setText("프로젝트")
        self._render()
        from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid

        grids = self.host.center_frame.findChildren(WeekTimeGrid)
        self.assertEqual(len(grids), 1)
        grid = grids[0]
        source = self.host._latest_calendar_range_data["rows"]
        self.assertGreater(len(source), 1)
        self.assertFalse(any(row["calendar_id"] == "local::private-preview" for row in source))
        self.assertEqual(
            [row["name"] for row, _date, _rect in grid.event_rects()], ["프로젝트 집중 작업"]
        )
        self.assertTrue(self.host.selection_status_lbl.isHidden())
        self.host.cal_week_layout = "date"
        self._render()
        self.assertFalse(self.host.selection_status_lbl.isHidden())

    def test_sunday_start_and_hidden_weekends_use_the_selected_date_columns(self):
        from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid

        task = self._task(
            name="Sunday",
            deadline="2026-10-04 09:00:00",
            end_date="2026-10-04 10:00:00",
            target_date="2026-10-04",
        )
        self.host.cal_start_monday = False
        self._render()
        grid = self.host.center_frame.findChildren(WeekTimeGrid)[0]
        self.assertEqual(self.host._latest_calendar_range_data["range_start"], "2026-10-04")
        sunday = [entry for entry in grid.event_rects() if entry[0]["id"] == task["id"]]
        self.assertEqual(len(sunday), 1)
        self.assertEqual(sunday[0][1], QDate(2026, 10, 4))

        self.host.cal_show_weekends = False
        self._render()
        self.assertEqual(self.host._latest_calendar_range_data["range_start"], "2026-10-05")
        self.assertEqual(self.host._latest_calendar_range_data["range_end"], "2026-10-09")
        grid = self.host.center_frame.findChildren(WeekTimeGrid)[0]
        self.assertFalse(any(row["id"] == task["id"] for row, _date, _rect in grid.event_rects()))

    def test_existing_all_day_rows_remain_in_the_fixed_top_section(self):
        from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid

        seed_preview_tasks()
        self._render()
        grid = self.host.center_frame.findChildren(WeekTimeGrid)[0]
        names = [item.task["name"] for item in grid._all_day]
        self.assertIn("보고서 제출", names)
        self.assertEqual(names.count("현장 출장"), 2)
        self.assertTrue(grid._all_day_rects)

    def test_modal_editor_requests_are_queued_until_the_pointer_handler_returns(self):
        from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid

        task = self._task()
        self._render()
        grid = self.host.center_frame.findChildren(WeekTimeGrid)[0]
        grid.create_requested.emit("2026-10-07", 540, 45)
        grid.edit_requested.emit(task)
        self.assertEqual(self.host.dialog_calls, [])
        self.assertEqual(self.host.modified_ids, [])
        self.qt_app.processEvents()
        self.assertEqual(self.host.dialog_calls[-1][1]["initial_time"].toString("HH:mm"), "09:00")
        self.assertEqual(self.host.modified_ids, [task["id"]])

    def test_hourly_gesture_defers_and_then_flushes_background_refresh(self):
        class RefreshHost(RefreshSchedulerMixin, QWidget):
            def __init__(self):
                super().__init__()
                self._is_dragging = False
                self._drag_pending_refresh = False
                self.loads = []

            def load_left_panel(self, force=False):
                self.loads.append("left")

            def load_center_panel(self, force=False):
                self.loads.append("center")

        host = RefreshHost()
        self.addCleanup(host.close)
        controller = self._controller()
        controller.set_week_interaction(host, True)
        host.schedule_panel_refresh(left=True, center=True)
        self.assertTrue(host._drag_pending_refresh)
        self.assertEqual(host.loads, [])
        controller.set_week_interaction(host, False)
        self.assertFalse(host._is_dragging)
        self.assertFalse(host._drag_pending_refresh)
        host._flush_scheduled_refresh()
        self.assertEqual(host.loads, ["left", "center"])
        host._ui_refresh_timer.stop()
