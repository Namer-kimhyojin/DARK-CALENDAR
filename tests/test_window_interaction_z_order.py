# -*- coding: utf-8 -*-
"""Protect toolbar interactions while retaining desktop drag layering."""

from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
import pytest

from calendar_app.presentation.main_window import window_events as module


class _InteractionWindow(module.WindowEventsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.old_pos_drag = None
        self._resize_dir = None
        self.is_locked = False
        self.ensure_window_on_screen = Mock()

    def _schedule_geometry_persist(self):
        pass


@pytest.fixture
def host(monkeypatch):
    app = QApplication.instance() or QApplication([])
    lowered = Mock()
    monkeypatch.setattr(module, "_set_window_bottom", lowered)
    window = _InteractionWindow()
    window.resize(500, 300)
    window.show()
    app.processEvents()
    lowered.reset_mock()
    window.ensure_window_on_screen.reset_mock()
    yield window, lowered
    window.hide()
    window.deleteLater()
    app.processEvents()


def _release(window):
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(100, 100),
        QPointF(window.mapToGlobal(QPoint(100, 100))),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.mouseReleaseEvent(event)


def test_plain_body_click_does_not_lower_window(host):
    window, lowered = host
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    lowered.assert_not_called()
    window.ensure_window_on_screen.assert_not_called()


def test_toolbar_button_click_does_not_lower_window(host):
    window, lowered = host
    button = QPushButton("Sync", window)
    button.setGeometry(80, 15, 100, 30)
    clicked = Mock()
    button.clicked.connect(clicked)
    button.show()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    clicked.assert_called_once()
    lowered.assert_not_called()
    assert window.isVisible()


@pytest.mark.parametrize("resize_dir", [None, "r", "br"])
def test_window_gesture_release_keeps_bottom_layering(host, resize_dir):
    window, lowered = host
    window.old_pos_drag = QPoint(80, 80)
    window._resize_dir = resize_dir
    _release(window)
    window.ensure_window_on_screen.assert_called_once()
    lowered.assert_called_once_with(int(window.winId()))
    assert window.old_pos_drag is None and window._resize_dir is None


@pytest.mark.parametrize("active_widget", ["activePopupWidget", "activeModalWidget"])
def test_gesture_release_keeps_active_popup_or_dialog_visible(host, monkeypatch, active_widget):
    window, lowered = host
    window.old_pos_drag = QPoint(80, 80)
    monkeypatch.setattr(module.QApplication, active_widget, lambda: window)
    _release(window)
    lowered.assert_not_called()
    assert window.old_pos_drag is None and window._resize_dir is None
