# -*- coding: utf-8 -*-
"""Main-window top bar visibility through the real Qt layout."""

from types import SimpleNamespace

from PyQt6.QtCore import QEvent, QPoint, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QToolButton,
    QWidget,
)
import pytest

from calendar_app.presentation.main_window import top_bar_shelf
from calendar_app.presentation.main_window.app_window import OverlayApp
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin


class _TopBarHost(WindowShellActionsMixin, QMainWindow):
    pass


@pytest.fixture
def top_bar_window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    windows = []
    settings_path = str(tmp_path / "settings.ini")
    cursor = SimpleNamespace(position=QPoint(-500, -500))
    monkeypatch.setattr(top_bar_shelf, "QCursor", SimpleNamespace(pos=lambda: cursor.position))
    monkeypatch.setattr(top_bar_shelf, "_HOVER_POLL_MS", 12)
    monkeypatch.setattr(top_bar_shelf, "_REVEAL_DELAY_MS", 30)
    monkeypatch.setattr(top_bar_shelf, "_HIDE_DELAY_MS", 50)

    def create_window(*, banner=False):
        owner = _TopBarHost()
        owner.settings = QSettings(settings_path, QSettings.Format.IniFormat)
        owner.move(200, 200)
        owner.resize(720, 460)
        frame = QFrame()
        frame_layout = QHBoxLayout(frame)
        owner.add_menu = QMenu(owner)
        owner.add_menu.addAction("New schedule")
        menu_button = QToolButton(frame)
        menu_button.setText("Add")
        menu_button.setMenu(owner.add_menu)
        frame_layout.addWidget(menu_button)
        owner.search_edit = QLineEdit(frame)
        frame_layout.addWidget(owner.search_edit)
        welcome = QLabel("Welcome") if banner else None
        shelf = top_bar_shelf.TopBarShelf(owner, frame, banner=welcome)
        owner.top_bar_frame = frame
        owner._top_bar_menu_wrapper = shelf
        owner.setMenuWidget(shelf)
        central = QWidget(owner)
        central.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        owner.setCentralWidget(central)
        dock = QDockWidget("Calendar", owner)
        owner.left_dock = dock
        dock.setWidget(QWidget(dock))
        owner.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.topLevelChanged.connect(lambda _: owner._on_any_dock_float_changed())
        owner.show()
        app.processEvents()
        windows.append(owner)
        return owner, shelf, frame, dock, welcome

    yield app, create_window, cursor

    for owner in windows:
        owner.close()
        owner.deleteLater()
    app.processEvents()


def _owner_rect(widget, owner):
    return widget.geometry().translated(widget.parentWidget().mapTo(owner, QPoint(0, 0)))


def test_revealed_bar_pushes_panels_down_instead_of_overlapping(top_bar_window):
    app, create_window, _ = top_bar_window
    owner, shelf, frame, dock, welcome = create_window(banner=True)
    assert frame.isVisible() and shelf.pin_button.isVisible() and shelf.pin_button.isChecked()
    assert not shelf.floating_pin.isVisible() and not shelf.handle.isVisible()
    pinned_dock_top = dock.geometry().top()

    OverlayApp.handle_palette_command(owner, "toggle_top_bar", {})
    QTest.qWait(120)
    assert shelf.auto_hide and frame.isHidden() and welcome.isVisible()
    assert shelf.handle.isVisible() and shelf.floating_pin.isVisible()
    assert not shelf.pin_button.isChecked()
    collapsed_dock_top = dock.geometry().top()
    assert collapsed_dock_top < pinned_dock_top

    shelf.reveal()
    app.processEvents()
    assert frame.isVisible() and shelf.pin_button.isVisible()
    assert not shelf.handle.isVisible() and not shelf.floating_pin.isVisible()
    assert dock.geometry().top() >= collapsed_dock_top + frame.height()
    assert _owner_rect(frame, owner).bottom() < dock.geometry().top()
    assert _owner_rect(frame, owner).bottom() < _owner_rect(welcome, owner).top()

    shelf.hide()  # Focus mode hides the main window's menu widget.
    app.processEvents()
    assert not frame.isVisible() and not shelf.floating_pin.isVisible()
    shelf.show()
    app.processEvents()
    assert frame.isHidden() and shelf.handle.isVisible() and shelf.floating_pin.isVisible()

    shelf.floating_pin.click()
    app.processEvents()
    assert not shelf.auto_hide and frame.isVisible() and shelf.pin_button.isChecked()
    assert not shelf.floating_pin.isVisible() and not shelf.handle.isVisible()
    assert dock.geometry().top() == pinned_dock_top

    shelf.pin_button.click()
    app.processEvents()
    assert shelf.auto_hide and frame.isHidden() and shelf.floating_pin.isVisible()


def test_floating_pin_hangs_centered_under_the_handle(top_bar_window):
    app, create_window, cursor = top_bar_window
    owner, shelf, frame, _, _ = create_window()
    shelf.set_auto_hide(True)
    app.processEvents()

    def assert_centered():
        pin = shelf.floating_pin.geometry()
        assert abs(pin.center().x() - owner.contentsRect().center().x()) <= 1
        assert pin.top() >= _owner_rect(shelf.handle, owner).bottom()

    assert_centered()
    assert shelf.floating_pin.toolTip().endswith("(Ctrl+Shift+B)")
    owner.resize(900, 460)
    app.processEvents()
    assert_centered()

    # Aiming at the tab must not open the bar first.
    cursor.position = owner.mapToGlobal(shelf.floating_pin.geometry().center())
    QTest.qWait(150)
    assert frame.isHidden()

    QTest.mouseClick(shelf.handle, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert frame.isVisible()


def test_auto_hide_preference_survives_restart_and_temporary_suppression(top_bar_window):
    app, create_window, _ = top_bar_window
    owner, *_ = create_window()
    owner.set_top_bar_auto_hide(True)
    owner.settings.sync()
    owner.close()

    restarted, restored, frame, dock, _ = create_window()
    assert restored.auto_hide and frame.isHidden()
    # A hidden bar leaves no top gap; the handle is drawn over the panels' edge.
    assert restored.height() == 0
    assert dock.geometry().top() == restarted.centralWidget().geometry().top() == 0
    handle = restored.handle.geometry()
    assert handle.top() == 0 and handle.height() == top_bar_shelf._HANDLE_HEIGHT
    assert handle.width() == restarted.contentsRect().width()
    assert restored.floating_pin.isVisible()

    dock.setFloating(True)
    restored.reveal()
    app.processEvents()
    assert frame.isHidden() and not restored.handle.isVisible()
    assert not restored.floating_pin.isVisible() and restored.height() == 0

    restarted.toggle_top_bar()  # Unavailable while a panel floats.
    assert restored.auto_hide

    dock.setFloating(False)
    app.processEvents()
    assert frame.isHidden() and restored.floating_pin.isVisible()

    restarted.set_top_bar_visible(True)  # Compatibility path pins the bar.
    app.processEvents()
    assert not restored.auto_hide and frame.isVisible()
    OverlayApp.handle_palette_command(restarted, "toggle_top_bar", {})
    app.processEvents()
    assert restored.auto_hide and frame.isHidden()


def test_hover_dwell_reveals_and_popups_keep_the_bar_open(top_bar_window, monkeypatch):
    app, create_window, cursor = top_bar_window
    owner, shelf, frame, _, _ = create_window()
    app.setActiveWindow(owner)
    owner.centralWidget().setFocus()
    shelf.set_auto_hide(True)
    QTest.qWait(120)
    assert frame.isHidden()

    cursor.position = owner.mapToGlobal(QPoint(owner.width() // 2, 2))
    with monkeypatch.context() as patch:
        patch.setattr(QApplication, "widgetAt", staticmethod(lambda _position: None))
        QTest.qWait(120)
        assert frame.isHidden()

    QTest.qWait(120)
    assert frame.isVisible()

    cursor.position = QPoint(-500, -500)
    app.sendEvent(frame, QEvent(QEvent.Type.Leave))
    QTest.qWait(120)
    assert frame.isHidden()

    shelf.reveal(focus=True)
    QTest.qWait(20)
    assert frame.isVisible() and owner.search_edit.hasFocus()

    owner.add_menu.popup(owner.mapToGlobal(QPoint(50, 50)))
    owner.centralWidget().setFocus()
    QTest.qWait(120)
    assert app.activePopupWidget() is owner.add_menu and frame.isVisible()

    owner.add_menu.hide()
    app.setActiveWindow(owner)
    owner.centralWidget().setFocus()
    QTest.qWait(120)
    assert frame.isHidden()

    owner.toggle_top_bar()  # Ctrl+Shift+B pins the bar again.
    app.processEvents()
    assert not shelf.auto_hide and frame.isVisible()


def test_quick_navigation_rail_toggles_with_its_own_shortcut(top_bar_window):
    from PyQt6.QtWidgets import QToolBar

    from calendar_app.infrastructure.runtime import keyboard_shortcuts

    app, create_window, _ = top_bar_window
    owner, *_ = create_window()
    rail = QToolBar("Quick navigation", owner)
    owner.addToolBar(Qt.ToolBarArea.LeftToolBarArea, rail)
    owner.navigation_rail = rail
    app.processEvents()

    owner.toggle_navigation_rail()
    app.processEvents()
    assert rail.isHidden()
    OverlayApp.handle_palette_command(owner, "toggle_navigation_rail", {})
    app.processEvents()
    assert rail.isVisible()

    shortcuts = keyboard_shortcuts.SHORTCUTS
    entry = next(item for item in shortcuts if item["id"] == "navigation_rail")
    assert entry["key"] == "Ctrl+Shift+R" and entry["action"] == "toggle_navigation_rail"
    keys = [item["key"].lower() for item in shortcuts]
    assert len(keys) == len(set(keys))
