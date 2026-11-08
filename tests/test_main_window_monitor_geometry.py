# -*- coding: utf-8 -*-
"""Logical main-window placement over disconnected, differently scaled displays."""

from unittest.mock import Mock

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QGuiApplication, QMouseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow
import pytest

from calendar_app.presentation.main_window import window_events
from calendar_app.presentation.main_window.window_events import WindowEventsMixin


@pytest.fixture(scope="session", autouse=True)
def application_lifetime():
    application = QApplication.instance() or QApplication([])
    yield application


class Screen:
    def __init__(self, geometry, available=None):
        self._geometry = QRect(geometry)
        self._available = QRect(available if available is not None else geometry)

    def geometry(self):
        return QRect(self._geometry)

    def availableGeometry(self):  # noqa: N802
        return QRect(self._available)

    def devicePixelRatio(self):  # noqa: N802
        raise AssertionError("Qt window placement must not multiply logical sizes by DPR")


class Window(WindowEventsMixin):
    def __init__(self, geometry):
        self._rect = QRect(geometry)
        self.changed = []
        self._screen_fill_active = False
        self.is_fullscreen = False
        self.maximized = self.fullscreen = False

    def geometry(self):
        return QRect(self._rect)

    frameGeometry = geometry

    def x(self):
        return self._rect.x()

    def y(self):
        return self._rect.y()

    def width(self):
        return self._rect.width()

    def height(self):
        return self._rect.height()

    def setGeometry(self, *args):  # noqa: N802
        self._rect = QRect(*args)
        self.changed.append(("geometry", QRect(self._rect)))

    def move(self, *args):
        point = QPoint(*args)
        self._rect.moveTopLeft(point)
        self.changed.append(("move", point))

    def isMaximized(self):  # noqa: N802
        return self.maximized

    def isFullScreen(self):  # noqa: N802
        return self.fullscreen


@pytest.fixture
def displays(monkeypatch):
    def install(screens):
        monkeypatch.setattr(QGuiApplication, "screens", lambda: list(screens))
        monkeypatch.setattr(
            QGuiApplication, "primaryScreen", lambda: screens[0] if screens else None
        )
        monkeypatch.setattr(
            QGuiApplication,
            "screenAt",
            lambda point: next(
                (screen for screen in screens if screen.geometry().contains(point)), None
            ),
        )

    return install


def test_screen_selection_uses_overlap_when_all_probe_points_land_in_screen_gaps(displays):
    primary = Screen(QRect(0, 0, 800, 600))
    secondary = Screen(QRect(1500, 0, 500, 500))
    displays([primary, secondary])
    window = Window(QRect(1000, -200, 2200, 700))
    assert window._target_screen_geometry() == secondary.availableGeometry()


def test_fully_offscreen_window_recovers_on_nearest_monitor_instead_of_primary(displays):
    primary = Screen(QRect(0, 0, 1920, 1080))
    left = Screen(QRect(-2560, 0, 1280, 1024))
    displays([primary, left])
    window = Window(QRect(-3500, 100, 600, 400))
    window.ensure_window_on_screen()
    assert left.availableGeometry().contains(window.geometry())


def test_monitor_move_keeps_dip_size_and_available_travel_ratio_with_taskbars(displays):
    first = Screen(QRect(-1920, 0, 1920, 1080), QRect(-1920, 40, 1920, 1000))
    second = Screen(QRect(0, -200, 1280, 1024), QRect(50, -200, 1230, 964))
    displays([first, second])
    window = Window(QRect(-1260, 340, 600, 400))
    window.move_to_next_monitor()
    assert window.geometry() == QRect(365, 82, 600, 400)
    window.move_to_previous_monitor()
    assert window.geometry() == QRect(-1260, 340, 600, 400)


def test_next_monitor_is_resolved_from_max_overlap_when_window_center_is_in_a_gap(displays):
    primary = Screen(QRect(0, 0, 1920, 1080))
    left = Screen(QRect(-2560, 0, 1280, 1024))
    displays([primary, left])
    window = Window(QRect(-1500, 100, 600, 400))
    window.move_to_next_monitor()
    assert primary.availableGeometry().contains(window.geometry())
    assert window.geometry().size() == QRect(0, 0, 600, 400).size()


def test_larger_window_only_shrinks_to_target_available_area_without_scaling(displays):
    first = Screen(QRect(0, 0, 1920, 1080))
    second = Screen(QRect(2400, -100, 800, 650), QRect(2400, -100, 700, 550))
    displays([first, second])
    window = Window(QRect(250, 100, 1000, 850))
    window.move_to_next_monitor()
    assert window.geometry() == QRect(2406, -94, 688, 538)


@pytest.mark.parametrize("position", [QPoint(-100, -100), QPoint(1500, 900)])
def test_outside_source_positions_are_clamped_before_transfer(displays, position):
    first = Screen(QRect(0, 0, 1920, 1080))
    second = Screen(QRect(2300, -600, 1100, 900))
    displays([first, second])
    window = Window(QRect(position.x(), position.y(), 600, 400))
    window.move_to_next_monitor()
    assert second.availableGeometry().contains(window.geometry())
    assert window.width() == 600 and window.height() == 400


@pytest.mark.parametrize("screens", [[], [Screen(QRect(0, 0, 800, 600))]])
def test_less_than_two_displays_does_not_change_geometry(displays, screens):
    displays(screens)
    original = QRect(100, 100, 600, 400)
    window = Window(original)
    window.move_to_next_monitor()
    assert window.geometry() == original and not window.changed


def test_screen_fill_moves_to_exact_available_area_and_keeps_fill_mode(displays):
    first = Screen(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040))
    second = Screen(QRect(2400, 0, 1280, 1024), QRect(2400, 0, 1280, 984))
    displays([first, second])
    window = Window(first.availableGeometry())
    window._screen_fill_active = True
    window.move_to_next_monitor()
    assert window.geometry() == second.availableGeometry()
    assert window._screen_fill_active is True


@pytest.mark.parametrize("state", ["maximized", "fullscreen", "is_fullscreen"])
def test_native_fullscreen_or_maximized_monitor_move_does_not_rewrite_window_state(displays, state):
    first = Screen(QRect(0, 0, 1920, 1080))
    second = Screen(QRect(2400, 0, 1280, 1024))
    displays([first, second])
    window = Window(first.availableGeometry())
    setattr(window, state, True)
    window.move_to_next_monitor()
    assert getattr(window, state) is True
    assert window.changed == [("move", second.availableGeometry().topLeft())]


class DragWindow(WindowEventsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.old_pos_drag = None
        self._native_window_drag = False
        self._resize_dir = None
        self.is_locked = False
        self.is_fullscreen = False
        self._screen_fill_active = False
        self.ensure_window_on_screen = Mock()
        self.setGeometry(100, 100, 600, 400)

    def _schedule_geometry_persist(self):
        pass


@pytest.fixture
def drag_window(monkeypatch):
    lowered = Mock()
    monkeypatch.setattr(window_events, "_set_window_bottom", lowered)
    monkeypatch.setattr(QApplication, "activePopupWidget", lambda: None)
    monkeypatch.setattr(QApplication, "activeModalWidget", lambda: None)
    host = DragWindow()
    handle = Mock()
    host.windowHandle = Mock(return_value=handle)
    yield host, handle, lowered
    host.deleteLater()
    QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _mouse(kind, local=(100, 25), global_pos=(500, 600)):
    return QMouseEvent(
        kind,
        QPointF(*local),
        QPointF(*global_pos),
        Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton
        if kind == QEvent.Type.MouseButtonRelease
        else Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_native_drag_handles_mixed_screen_motion_without_applying_a_second_delta(drag_window):
    window, handle, lowered = drag_window
    handle.startSystemMove.return_value = True
    press = _mouse(QEvent.Type.MouseButtonPress)
    window.mousePressEvent(press)
    handle.startSystemMove.assert_called_once_with()
    assert press.isAccepted() and window._native_window_drag
    assert window.old_pos_drag is None
    window.move = Mock()
    window.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, global_pos=(2500, -400)))
    window.move.assert_not_called()
    window.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease))
    assert window._native_window_drag is False
    window.ensure_window_on_screen.assert_called_once_with()
    lowered.assert_called_once_with(int(window.winId()))


@pytest.mark.parametrize("support", [False, "deleted", "no_handle"])
def test_unavailable_native_drag_retains_the_existing_manual_move(drag_window, support):
    window, handle, _ = drag_window
    if support == "deleted":
        handle.startSystemMove.side_effect = RuntimeError("deleted native handle")
    elif support == "no_handle":
        window.windowHandle.return_value = None
    else:
        handle.startSystemMove.return_value = False
    window.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress))
    assert not window._native_window_drag
    assert window.old_pos_drag == QPoint(500, 600)
    window.move = Mock()
    window.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, global_pos=(510, 620)))
    window.move.assert_called_once_with(QPoint(110, 120))


@pytest.mark.parametrize(
    "state", ["is_locked", "is_fullscreen", "_screen_fill_active", "maximized", "fullscreen"]
)
def test_native_drag_does_not_change_locked_or_filled_window_behavior(drag_window, state):
    window, handle, _ = drag_window
    if state == "maximized":
        window.isMaximized = Mock(return_value=True)
    elif state == "fullscreen":
        window.isFullScreen = Mock(return_value=True)
    else:
        setattr(window, state, True)
    window.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress))
    handle.startSystemMove.assert_not_called()
    assert not window._native_window_drag


def test_edge_resize_keeps_the_existing_resize_path(drag_window):
    window, handle, _ = drag_window
    window.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, local=(1, 100)))
    handle.startSystemMove.assert_not_called()
    assert window._resize_dir == "l" and window.old_pos_drag == QPoint(500, 600)


def test_leave_and_next_body_press_cannot_reuse_a_stale_native_drag(drag_window):
    window, _, lowered = drag_window
    window._native_window_drag = True
    window.leaveEvent(QEvent(QEvent.Type.Leave))
    assert not window._native_window_drag
    window._native_window_drag = True
    window.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, local=(100, 100)))
    assert not window._native_window_drag
    window.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, local=(100, 100)))
    window.ensure_window_on_screen.assert_not_called()
    lowered.assert_not_called()
