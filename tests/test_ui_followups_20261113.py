# -*- coding: utf-8 -*-
"""Follow-up UI fixes: Esc routing, hidden-main shortcuts, calendar re-dock and menus."""

from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QDate, QEvent, QPoint, QRect, QSettings, Qt
from PyQt6.QtGui import QContextMenuEvent, QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu
import pytest

from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key, register_all
from calendar_app.presentation.calendar.month_renderer import _CalendarSurfaceFrame
from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid
from calendar_app.presentation.main_window import action_handlers_tasks as actions
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin
from calendar_app.presentation.widgets import unified_widget_mode as uwm
from calendar_app.presentation.widgets.command_palette import CommandPalette
from tests.test_unified_widget_mode import _FakeHost


@pytest.fixture
def qt_app():
    return QApplication.instance() or QApplication([])


def _flush(application):
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


class _MainHost(WindowShellActionsMixin, actions.TaskActionsMixin, QMainWindow):
    """Main-window stand-in with the real Esc handler and global shortcut table."""

    def __init__(self, path):
        super().__init__()
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self._panel_task_frames = {}
        self._panel_directive_frames = {}
        self._global_shortcuts = []
        self.is_focus_mode = False
        self._focus_fullscreen_btn = None
        register_all(self)

    def update_task_selection_status(self):
        pass


@pytest.fixture
def main_host(qt_app, tmp_path):
    window = _MainHost(tmp_path / "main.ini")
    window.show()
    window.activateWindow()
    qt_app.processEvents()
    yield window
    for shortcut in window._global_shortcuts:
        shortcut.setEnabled(False)
    window.close()
    window.deleteLater()
    _flush(qt_app)


def test_escape_closes_command_palette_while_main_shortcuts_are_registered(qt_app, main_host):
    palette = CommandPalette(parent=main_host)
    main_host.selected_task_ids.add(7)
    palette.show()
    palette.search_bar.setFocus()
    qt_app.processEvents()

    QTest.keyClick(palette.search_bar, Qt.Key.Key_Escape)
    for _ in range(40):
        if not palette.isVisible():
            break
        QTest.qWait(25)

    assert not palette.isVisible()
    assert main_host.selected_task_ids == {7}
    palette.close()
    palette.deleteLater()


def test_escape_leaves_focus_fullscreen_before_clearing_selection(qt_app, main_host):
    main_host.is_focus_mode = True
    main_host.selected_task_ids.add(7)
    main_host.showFullScreen()
    main_host.activateWindow()
    qt_app.processEvents()

    QTest.keyClick(main_host, Qt.Key.Key_Escape)
    qt_app.processEvents()
    assert not main_host.isFullScreen()
    assert main_host.is_focus_mode
    assert main_host.selected_task_ids == {7}

    QTest.keyClick(main_host, Qt.Key.Key_Escape)
    assert not main_host.selected_task_ids


class _WidgetModeHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.calls = []

    def toggle_widget_mode_panel(self):
        self.calls.append("widget_mode")

    def toggle_overlay(self):
        self.calls.append("show_hide")


def test_widget_window_keys_reach_main_handlers_while_main_window_is_hidden(qt_app):
    host = _WidgetModeHost()
    controller = uwm.UnifiedWidgetController(host)
    controller.show_widget()
    widget = controller.widget
    try:
        widget.activateWindow()
        QTest.qWaitForWindowActive(widget)
        assert not host.isVisible()

        QTest.keySequence(widget, QKeySequence(get_key("widget_mode")))
        QTest.keySequence(widget, QKeySequence(get_key("show_hide")))

        assert host.calls == ["widget_mode", "show_hide"]
    finally:
        widget.hide()
        widget.close()
        widget.deleteLater()
        host.deleteLater()
        _flush(qt_app)


def test_widget_window_keys_fire_once_while_main_window_is_also_visible(qt_app):
    from calendar_app.infrastructure.runtime import keyboard_shortcuts

    host = _WidgetModeHost()
    keyboard_shortcuts._make_shortcut(
        host, host, get_key("widget_mode"), host.toggle_widget_mode_panel
    )
    controller = uwm.UnifiedWidgetController(host)
    controller.show_widget()
    widget = controller.widget
    try:
        host.show()
        widget.activateWindow()
        QTest.qWaitForWindowActive(widget)

        QTest.keySequence(widget, QKeySequence(get_key("widget_mode")))
        host.hide()
        QTest.keySequence(widget, QKeySequence(get_key("widget_mode")))

        assert host.calls == ["widget_mode", "widget_mode"]
    finally:
        widget.hide()
        widget.close()
        widget.deleteLater()
        host.deleteLater()
        _flush(qt_app)


def test_escape_in_a_floating_panel_reaches_the_main_window_handler(qt_app):
    from PyQt6.QtWidgets import QDockWidget, QPushButton

    from calendar_app.presentation.main_window.dock_sections.floating_dock_behavior import (
        FloatingDockBehavior,
    )

    main = QMainWindow()
    main.escapes = 0
    main.handle_escape_key = lambda: setattr(main, "escapes", main.escapes + 1)
    dock = QDockWidget("panel", main)
    button = QPushButton("item", dock)
    dock.setWidget(button)
    main.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    FloatingDockBehavior(dock, app=main)
    try:
        main.show()
        QTest.keyClick(button, Qt.Key.Key_Escape)
        assert main.escapes == 0  # docked: the main window's own keyPressEvent handles it

        dock.setFloating(True)
        dock.show()
        QTest.keyClick(button, Qt.Key.Key_Escape)
        assert main.escapes == 1
    finally:
        main.hide()
        main.deleteLater()
        _flush(qt_app)


class _FloatingDock:
    def isFloating(self):
        return True

    def frameGeometry(self):
        return QRect(-5000, -5000, 10000, 10000)

    def mousePressEvent(self, event):
        pass

    def mouseMoveEvent(self, event):
        pass

    def mouseReleaseEvent(self, event):
        pass


def test_floating_calendar_redocks_only_after_a_real_drag(qt_app):
    app = SimpleNamespace(
        center_dock=_FloatingDock(),
        calendar_toolbar_widget=SimpleNamespace(is_toolbar_expanded=lambda: False),
    )
    frame = _CalendarSurfaceFrame(app)
    frame.resize(400, 300)
    frame.show()
    qt_app.processEvents()
    start = QPoint(100, 100)
    end = start + QPoint(QApplication.startDragDistance() + 2, 0)
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    try:
        with patch.object(frame, "_relaxed_redock") as redock:
            QTest.mouseClick(frame, left, none, start)
            redock.assert_not_called()

            QTest.mousePress(frame, left, none, start)
            QTest.mouseMove(frame, end)
            QTest.mouseRelease(frame, left, none, end)
            redock.assert_called_once()
    finally:
        frame.close()
        frame.deleteLater()
        _flush(qt_app)


def test_week_grid_context_menu_is_destroyed_after_it_closes(qt_app):
    grid = WeekTimeGrid()
    grid.resize(1000, 700)
    task = {
        "id": 1,
        "name": "일정 1",
        "deadline": "2026-10-05 09:00:00",
        "end_date": "2026-10-05 10:00:00",
        "all_day": 0,
    }
    grid.set_week(QDate(2026, 10, 5), [task])
    grid.show()
    qt_app.processEvents()
    canvas = grid._timeline
    x = grid.GUTTER + 0.5 * grid._column_width()
    point = QPoint(round(x), round(570 * grid.HOUR_HEIGHT / 60))
    try:
        for _ in range(3):
            event = QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, point, canvas.mapToGlobal(point)
            )
            with patch.object(QMenu, "exec", return_value=None) as shown:
                canvas.contextMenuEvent(event)
            shown.assert_called_once()
        _flush(qt_app)
        assert canvas.findChildren(QMenu) == []
    finally:
        grid.close()
        grid.deleteLater()
        _flush(qt_app)
