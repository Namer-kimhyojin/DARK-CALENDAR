# -*- coding: utf-8 -*-
"""Explicit recovery actions reveal a usable main window from hidden states."""

import os
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QMainWindow
import pytest

from calendar_app.presentation.main_window.window_events import WindowEventsMixin
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin


class _RecoveryWindow(WindowShellActionsMixin, WindowEventsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_fullscreen = False
        self.is_visible = False
        self.resize(600, 400)
        self._widget_active = False
        self._coordinator = Mock()
        self._coordinator.return_to_main.side_effect = self.showNormal

    def _schedule_geometry_persist(self):
        pass

    def _safe_screen_rect(self):
        return QRect(10, 10, 1200, 800)

    def ensure_window_on_screen(self):
        pass

    def is_widget_mode_active(self):
        return self._widget_active

    def _ensure_widget_mode_coordinator(self):
        return self._coordinator


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    with patch("calendar_app.presentation.main_window.window_events._set_window_bottom"):
        host = _RecoveryWindow()
        yield host
        host.hide()
        host.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("minimized", [False, True])
def test_tray_menu_returns_from_widget_mode_to_a_visible_main_window(window, minimized):
    if minimized:
        window.showMinimized()
    else:
        window.hide()
    window._widget_active = True

    window.toggle_overlay()

    window._coordinator.return_to_main.assert_called_once_with()
    assert window.isVisible()
    assert not window.isMinimized()


@pytest.mark.parametrize("minimized", [False, True])
def test_safe_area_recovery_reveals_hidden_or_minimized_window(window, minimized):
    if minimized:
        window.showMinimized()
    else:
        window.hide()
    window.move(-4000, -4000)

    window.restore_window_to_safe_area()

    assert window.isVisible()
    assert not window.isMinimized()
    assert window.is_visible is True
    assert window._safe_screen_rect().contains(window.geometry())
