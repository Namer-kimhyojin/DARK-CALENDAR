# -*- coding: utf-8 -*-
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.widgets.widget_mode_coordinator import (
    WidgetModeCoordinator,
    WidgetModeState,
)


class _FakeSettings:
    def __init__(self):
        self.values = {"overlay_instances": "keep", "oi_clock_x": 17}

    def value(self, key, default=None, type=None):
        del type
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class _Host(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = _FakeSettings()
        self.current_date = QDate(2026, 7, 11)
        self._latest_agenda_data = None
        self._latest_calendar_range_data = None
        self._latest_directive_data = None
        self.is_visible = True

    def schedule_panel_refresh(self, **kwargs):
        del kwargs


_QT_APP = QApplication.instance() or QApplication([])


def test_enter_and_exit_use_one_window_and_restore_main_window():
    host = _Host()
    host.show()
    coordinator = WidgetModeCoordinator(host)

    coordinator.enter("schedule")

    assert coordinator.state is WidgetModeState.ACTIVE
    assert coordinator.controller.widget.isVisible()
    assert coordinator.controller.widget._active_filter == "schedule"
    assert not host.isVisible()

    coordinator.exit_widget_mode()

    assert coordinator.state is WidgetModeState.CLOSED
    assert host.isVisible()
    coordinator.controller.widget.close()
    host.close()


def test_external_widget_hide_restores_main_window():
    host = _Host()
    host.show()
    coordinator = WidgetModeCoordinator(host)
    coordinator.enter("work")

    coordinator.controller.widget.hide()

    assert coordinator.state is WidgetModeState.CLOSED
    assert host.isVisible()
    host.close()


def test_shutdown_close_does_not_restore_main_or_touch_overlay_settings():
    host = _Host()
    host.show()
    coordinator = WidgetModeCoordinator(host)
    coordinator.enter()
    overlay_before = {
        key: value
        for key, value in host.settings.values.items()
        if key == "overlay_instances" or key.startswith("oi_")
    }

    coordinator.close_for_shutdown()

    overlay_after = {
        key: value
        for key, value in host.settings.values.items()
        if key == "overlay_instances" or key.startswith("oi_")
    }
    assert coordinator.state is WidgetModeState.CLOSED
    assert not host.isVisible()
    assert overlay_after == overlay_before
    coordinator.controller.widget.close()
    host.close()
