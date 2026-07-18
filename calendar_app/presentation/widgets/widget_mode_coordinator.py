# -*- coding: utf-8 -*-
"""Single lifecycle coordinator for every widget-mode entry point."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from PyQt6.QtCore import Qt

from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController


class WidgetModeState(Enum):
    CLOSED = auto()
    OPENING = auto()
    ACTIVE = auto()
    CLOSING = auto()


@dataclass(frozen=True)
class _MainWindowSnapshot:
    visible: bool
    minimized: bool
    maximized: bool
    fullscreen: bool


class WidgetModeCoordinator:
    def __init__(self, main_window):
        self.main_window = main_window
        self.state = WidgetModeState.CLOSED
        self._snapshot: _MainWindowSnapshot | None = None
        self._internal_hide = False
        self.controller = UnifiedWidgetController(main_window, on_hidden=self._on_widget_hidden)

    def is_widget_mode_active(self) -> bool:
        return self.state in {WidgetModeState.OPENING, WidgetModeState.ACTIVE}

    def toggle(self, filter_mode: str = "all") -> None:
        if self.is_widget_mode_active():
            self.exit_widget_mode()
        else:
            self.enter(filter_mode)

    def enter(self, filter_mode: str = "all") -> None:
        if self.is_widget_mode_active():
            self.controller.show_widget(filter_mode)
            return
        window = self.main_window
        state = window.windowState()
        self._snapshot = _MainWindowSnapshot(
            visible=window.isVisible(),
            minimized=bool(state & Qt.WindowState.WindowMinimized),
            maximized=bool(state & Qt.WindowState.WindowMaximized),
            fullscreen=bool(state & Qt.WindowState.WindowFullScreen),
        )
        self.state = WidgetModeState.OPENING
        self.controller.show_widget(filter_mode)
        window.hide()
        if hasattr(window, "is_visible"):
            window.is_visible = False
        self.state = WidgetModeState.ACTIVE

    def enter_widget_mode(self, show_schedule=True, show_work=True) -> None:
        if show_schedule and not show_work:
            filter_mode = "schedule"
        elif show_work and not show_schedule:
            filter_mode = "work"
        else:
            filter_mode = "all"
        self.enter(filter_mode)

    def exit_widget_mode(self) -> None:
        self._exit(restore_main=True)

    def close_for_shutdown(self) -> None:
        self._exit(restore_main=False)

    def close_widgets(self) -> None:
        self.close_for_shutdown()

    def refresh_visible_widgets(self, schedule=True, work=True) -> None:
        del schedule, work
        if self.is_widget_mode_active():
            self.controller.refresh_data()

    def _exit(self, *, restore_main: bool) -> None:
        if self.state in {WidgetModeState.CLOSED, WidgetModeState.CLOSING}:
            return
        self.state = WidgetModeState.CLOSING
        self._internal_hide = True
        try:
            self.controller.hide_widget()
        finally:
            self._internal_hide = False
        snapshot = self._snapshot
        self._snapshot = None
        if restore_main and snapshot is not None and snapshot.visible:
            self._restore_main_window(snapshot)
        self.state = WidgetModeState.CLOSED

    def _restore_main_window(self, snapshot: _MainWindowSnapshot) -> None:
        window = self.main_window
        if snapshot.fullscreen:
            window.showFullScreen()
        elif snapshot.maximized:
            window.showMaximized()
        elif snapshot.minimized:
            window.showMinimized()
        else:
            window.showNormal()
        if hasattr(window, "is_visible"):
            window.is_visible = True
        if not snapshot.minimized:
            window.raise_()
            window.activateWindow()

    def _on_widget_hidden(self) -> None:
        if self._internal_hide or not self.is_widget_mode_active():
            return
        self._exit(restore_main=True)
