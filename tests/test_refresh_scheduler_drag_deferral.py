# -*- coding: utf-8 -*-
"""Refreshes queued before or during dragging wait without losing any panel."""

from unittest.mock import Mock

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin


class _Host(RefreshSchedulerMixin, QObject):
    def __init__(self):
        super().__init__()
        self.loads = []
        self._is_dragging = False
        self._is_calendar_range_dragging = False
        self._drag_pending_refresh = False
        self._unified_widget_controller = Mock()

    def load_left_panel(self, force=False):
        self.loads.append("left")

    def load_center_panel(self, force=False):
        self.loads.append("center")

    def load_right_panel(self, force=False):
        self.loads.append("right")


@pytest.fixture
def host():
    app = QApplication.instance() or QApplication([])
    target = _Host()
    yield target
    if hasattr(target, "_ui_refresh_timer"):
        app.processEvents()
        target._ui_refresh_timer.stop()
    target.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("drag_flag", ["_is_dragging", "_is_calendar_range_dragging"])
def test_timer_queued_before_drag_does_not_rerender_and_retains_pending_work(host, drag_flag):
    host.schedule_panel_refresh(left=True, right=True)
    QApplication.processEvents()
    host._ui_refresh_timer.stop()
    setattr(host, drag_flag, True)
    host._flush_scheduled_refresh()
    assert host.loads == []
    host._unified_widget_controller.refresh_data.assert_not_called()
    assert host._pending_refresh == {"left": True, "center": False, "right": True}
    assert host._drag_pending_refresh
    setattr(host, drag_flag, False)
    host._drag_pending_refresh = False
    host.schedule_panel_refresh(left=True, center=True)
    host._flush_scheduled_refresh()
    assert host.loads == ["left", "center", "right"]
    host._unified_widget_controller.refresh_data.assert_called_once()


def test_right_only_update_during_drag_survives_the_existing_drop_refresh(host):
    host._is_dragging = True
    host.schedule_panel_refresh(right=True)
    assert host._drag_pending_refresh
    assert host.loads == []
    host._is_dragging = False
    host._drag_pending_refresh = False
    host.schedule_panel_refresh(left=True, center=True)
    host._flush_scheduled_refresh()
    assert host.loads == ["left", "center", "right"]
    host._unified_widget_controller.refresh_data.assert_called_once()


def test_multiple_drag_updates_coalesce_and_shutdown_discards_them(host):
    host._is_calendar_range_dragging = True
    for _ in range(50):
        host.schedule_panel_refresh(left=True)
        host.schedule_panel_refresh(right=True, notify_data_consumers=False)
    host._is_shutting_down = True
    host._flush_scheduled_refresh()
    assert host.loads == []
    assert host._pending_refresh == {"left": False, "center": False, "right": False}
    assert not host._pending_data_consumer_refresh
    host._unified_widget_controller.refresh_data.assert_not_called()
