# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QEvent, QObject, QPoint, Qt, pyqtSlot
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from calendar_app.presentation.calendar.month_renderer import (
    _connect_calendar_cell_signals,
)
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin
from calendar_app.presentation.main_window.action_handlers_tasks import (
    TaskActionsMixin,
)
from calendar_app.presentation.main_window.refresh_scheduler import (
    RefreshSchedulerMixin,
)
from calendar_app.presentation.widgets.ui_components import ClickableCell


class _SignalHost(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    @pyqtSlot(object)
    def open_task_dialog(self, payload):
        self.calls.append(("double", payload))

    @pyqtSlot(object)
    def handle_cell_click(self, payload):
        self.calls.append(("click", payload))

    @pyqtSlot(object)
    def handle_cell_shift_click(self, payload):
        self.calls.append(("shift", payload))

    @pyqtSlot(object)
    def handle_cell_drag_range(self, payload):
        self.calls.append(("range", payload))

    @pyqtSlot(object, object, object, str)
    def handle_task_dropped(self, *_payload):
        self.calls.append(("drop", _payload))


class _RangeActionHost(TaskActionsMixin):
    def __init__(self):
        self._last_clicked_date = None
        self.refreshes = []
        self.dialog_calls = []

    def schedule_panel_refresh(self, **kwargs):
        self.refreshes.append(kwargs)

    def open_task_dialog(self, *args):
        self.dialog_calls.append(args)


class _SubscriptionCopyHost(TaskActionsMixin):
    def __init__(self):
        self.dialog_kwargs = None

    def open_task_dialog(self, **kwargs):
        self.dialog_kwargs = kwargs


class _PushOnlyHost(TaskActionsMixin):
    class _Settings:
        @staticmethod
        def value(_key, default=None):
            return "true" if default is None else default

    def __init__(self):
        self.settings = self._Settings()
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self.refreshes = []
        self.wake_calls = 0

    def schedule_panel_refresh(self, **kwargs):
        self.refreshes.append(kwargs)

    def update_task_selection_status(self):
        pass

    def wake_gcal_sync(self):
        self.wake_calls += 1


class _RefreshHost(RefreshSchedulerMixin, QObject):
    def __init__(self):
        super().__init__()
        self.center_loads = 0

    def load_left_panel(self, force=False):
        pass

    def load_center_panel(self, force=False):
        self.center_loads += 1

    def load_right_panel(self, force=False):
        pass


class _DialogRefreshHost(DialogActionsMixin, RefreshSchedulerMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.center_loads = 0
        self.loads_during_dialog = None

    def load_left_panel(self, force=False):
        pass

    def load_center_panel(self, force=False):
        self.center_loads += 1

    def load_right_panel(self, force=False):
        pass


class _RefreshDuringDialog:
    def __init__(self, parent, **_kwargs):
        self.parent = parent

    def exec(self):
        self.parent.schedule_panel_refresh(center=True)
        self.parent._flush_scheduled_refresh()
        self.parent.loads_during_dialog = self.parent.center_loads
        return 0


class CalendarRangeCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_subscription_all_day_copy_uses_inclusive_end_and_preserves_mode(self):
        host = _SubscriptionCopyHost()

        host.copy_subscription_to_local(
            {
                "name": "Conference",
                "deadline": "2026-08-15",
                "end_date": "2026-08-16",
                "_start_raw": "2026-08-15",
                "_end_raw": "2026-08-17",
                "all_day": 1,
            }
        )

        self.assertEqual(host.dialog_kwargs["initial_date"], QDate(2026, 8, 15))
        self.assertEqual(host.dialog_kwargs["end_date"], QDate(2026, 8, 16))
        self.assertTrue(host.dialog_kwargs["prefill_dict"]["all_day"])

    def test_shift_range_normalizes_dates_and_opens_inclusive_period(self):
        host = _RangeActionHost()
        host._last_clicked_date = QDate(2026, 8, 15)

        host.handle_cell_shift_click((QDate(2026, 8, 13), None))

        self.assertEqual(
            host.dialog_calls,
            [(QDate(2026, 8, 13), None, QDate(2026, 8, 15))],
        )
        self.assertEqual(host._last_clicked_date, QDate(2026, 8, 15))
        self.assertEqual(host.refreshes, [{"center": True}])

    def test_modal_opening_cell_signals_are_queued(self):
        host = _SignalHost()
        cell = ClickableCell(QDate(2026, 8, 13))
        self.addCleanup(cell.close)
        _connect_calendar_cell_signals(host, cell)

        cell.shiftClicked.emit((cell.target_date, None))
        self.assertEqual(host.calls, [])

        self.app.processEvents()
        self.assertEqual(host.calls[0][0], "shift")

    def test_create_range_preview_reports_inclusive_days_and_emits_range(self):
        root = QWidget()
        self.addCleanup(root.close)
        root.selection_status_lbl = QLabel(root)
        root._create_range_preview_cells = []
        root._drag_pending_refresh = False
        root._is_calendar_range_dragging = True
        root.update_task_selection_status = lambda: root.selection_status_lbl.setText("restored")

        dates = [QDate(2026, 8, 13).addDays(i) for i in range(3)]
        cells = [ClickableCell(date, parent=root) for date in dates]
        root._calendar_cells_by_date = {
            date.toString("yyyy-MM-dd"): cell for date, cell in zip(dates, cells, strict=True)
        }
        source = cells[0]
        source._update_create_range_preview(dates[0], dates[2])

        self.assertTrue(all(cell.property("create_range_preview") for cell in cells))
        self.assertTrue(cells[0].property("create_range_start"))
        self.assertTrue(cells[-1].property("create_range_end"))
        self.assertIn("3", root.selection_status_lbl.text())

        emitted = []
        source.rangeSelected.connect(emitted.append)
        source._range_dragging = True
        source._range_drag_anchor_date = dates[0]
        source._range_drag_end_date = dates[2]
        self.assertTrue(source._finish_create_range_drag())

        self.assertEqual(emitted, [(dates[0], dates[2])])
        self.assertFalse(root._is_calendar_range_dragging)
        self.assertTrue(all(not cell.property("create_range_preview") for cell in cells))

    def test_empty_cell_drag_emits_inclusive_range(self):
        root = QWidget()
        self.addCleanup(root.close)
        root.setGeometry(100, 100, 270, 80)
        root.selection_status_lbl = QLabel(root)
        root._create_range_preview_cells = []
        root._drag_pending_refresh = False
        root._is_calendar_range_dragging = False
        root.update_task_selection_status = lambda: None

        dates = [QDate(2026, 8, 13).addDays(i) for i in range(3)]
        cells = [ClickableCell(date, parent=root) for date in dates]
        for index, cell in enumerate(cells):
            cell.setGeometry(index * 90, 0, 90, 80)
        root._calendar_cells_by_date = {
            date.toString("yyyy-MM-dd"): cell for date, cell in zip(dates, cells, strict=True)
        }
        emitted = []
        cells[0].rangeSelected.connect(emitted.append)

        root.show()
        self.app.processEvents()
        QTest.mousePress(
            cells[0],
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(8, 8),
        )
        QTest.mouseMove(cells[0], QPoint(188, 8), 20)
        QTest.mouseRelease(
            cells[0],
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(188, 8),
        )
        self.app.processEvents()

        self.assertEqual(emitted, [(dates[0], dates[2])])
        self.assertIn("3", root.selection_status_lbl.text())

    def test_window_deactivation_cancels_range_drag_and_flushes_pending_refresh(self):
        root = QWidget()
        self.addCleanup(root.close)
        root.selection_status_lbl = QLabel(root)
        root._create_range_preview_cells = []
        root._drag_pending_refresh = True
        root._is_calendar_range_dragging = True
        root.refreshes = []
        root.update_task_selection_status = lambda: None
        root.schedule_panel_refresh = lambda **kwargs: root.refreshes.append(kwargs)
        cell = ClickableCell(QDate(2026, 8, 13), parent=root)
        cell._range_dragging = True
        cell._range_drag_anchor_date = cell.target_date
        cell._range_drag_end_date = cell.target_date.addDays(1)
        cell._install_create_range_cancel_filter()

        QApplication.sendEvent(root, QEvent(QEvent.Type.WindowDeactivate))

        self.assertFalse(cell._range_dragging)
        self.assertFalse(root._is_calendar_range_dragging)
        self.assertFalse(root._drag_pending_refresh)
        self.assertEqual(root.refreshes, [{"left": True, "center": True}])

    def test_escape_cancels_range_drag_without_emitting_selection(self):
        root = QWidget()
        self.addCleanup(root.close)
        root._create_range_preview_cells = []
        root._drag_pending_refresh = False
        root._is_calendar_range_dragging = True
        cell = ClickableCell(QDate(2026, 8, 13), parent=root)
        emitted = []
        cell.rangeSelected.connect(emitted.append)
        cell._range_dragging = True
        cell._range_drag_anchor_date = cell.target_date
        cell._range_drag_end_date = cell.target_date.addDays(2)
        cell._install_create_range_cancel_filter()

        QTest.keyClick(root, Qt.Key.Key_Escape)

        self.assertFalse(cell._range_dragging)
        self.assertFalse(root._is_calendar_range_dragging)
        self.assertEqual(emitted, [])

    def test_deferred_delete_cancels_active_range_drag(self):
        root = QWidget()
        self.addCleanup(root.close)
        root._create_range_preview_cells = []
        root._drag_pending_refresh = False
        root._is_calendar_range_dragging = True
        cell = ClickableCell(QDate(2026, 8, 13), parent=root)
        root._active_calendar_range_drag_cell = cell
        cell._range_dragging = True
        cell._range_drag_anchor_date = cell.target_date
        cell._range_drag_end_date = cell.target_date.addDays(1)
        cell._install_create_range_cancel_filter()

        cell.eventFilter(cell, QEvent(QEvent.Type.DeferredDelete))

        self.assertFalse(cell._range_dragging)
        self.assertFalse(root._is_calendar_range_dragging)
        self.assertIsNone(root._active_calendar_range_drag_cell)

    def test_push_only_task_actions_do_not_wake_full_sync(self):
        host = _PushOnlyHost()
        task = {"id": 7, "name": "Updated", "type": "schedule"}

        with (
            patch(
                "calendar_app.presentation.main_window.action_handlers_tasks."
                "task_usecases.rename_task",
                return_value=task,
            ),
            patch(
                "calendar_app.presentation.main_window.action_handlers_tasks."
                "task_usecases.resize_task_and_get_sync_payload",
                return_value=task,
            ),
            patch(
                "calendar_app.presentation.drag_drop_manager.handle_task_drop",
                return_value=(1, []),
            ),
            patch(
                "calendar_app.presentation.main_window.action_handlers_tasks.is_gcal_enabled",
                return_value=True,
            ),
            patch(
                "calendar_app.presentation.main_window.action_handlers_tasks."
                "db_task.get_unified_task",
                return_value=task,
            ),
            patch(
                "calendar_app.presentation.main_window.action_handlers_tasks."
                "gcal_push_queue.enqueue"
            ) as enqueue,
        ):
            host.handle_task_rename_requested(7, "Updated")
            host.handle_task_resized(7, 60)
            host.handle_task_dropped([7], QDate(2026, 8, 14), None, "move")

        self.assertEqual(enqueue.call_count, 3)
        self.assertEqual(host.wake_calls, 0)

    def test_modal_guard_defers_prequeued_center_render_until_close(self):
        host = _RefreshHost()
        self.addCleanup(lambda: host._ui_refresh_timer.stop())
        host._ensure_refresh_scheduler()
        host._pending_refresh["center"] = True
        host._pending_data_consumer_refresh = True

        host.begin_task_dialog_refresh_guard()
        host._flush_scheduled_refresh()

        self.assertEqual(host.center_loads, 0)
        self.assertTrue(host._task_dialog_pending_refresh["center"])

        host.end_task_dialog_refresh_guard()
        self.assertTrue(host._pending_refresh["center"])
        host._flush_scheduled_refresh()

        self.assertEqual(host.center_loads, 1)

    def test_open_task_dialog_defers_refresh_while_modal_is_running(self):
        host = _DialogRefreshHost()
        self.addCleanup(host.close)

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.UnifiedTaskDialog",
            _RefreshDuringDialog,
        ):
            host.open_task_dialog(initial_date=QDate(2026, 8, 13))

        self.assertEqual(host.loads_during_dialog, 0)
        self.assertTrue(host._pending_refresh["center"])
        host._flush_scheduled_refresh()
        self.assertEqual(host.center_loads, 1)


if __name__ == "__main__":
    unittest.main()
