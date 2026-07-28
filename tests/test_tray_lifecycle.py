# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMainWindow

from calendar_app.infrastructure.runtime.infra_wiring import (
    _set_overlay_visible,
    init_tray_icon,
    toggle_overlay,
)
from calendar_app.presentation.main_window.action_handlers import ActionHandlersMixin
from calendar_app.presentation.main_window.window_events import WindowEventsMixin


class _FakeOverlay:
    def __init__(self, *, visible: bool, minimized: bool = False):
        self._visible = visible
        self._minimized = minimized
        self.is_visible = not visible
        self.show_calls = 0
        self.show_normal_calls = 0
        self.hide_calls = 0
        self.refresh_calls = 0

    def isVisible(self):
        return self._visible

    def isMinimized(self):
        return self._minimized

    def show(self):
        self.show_calls += 1
        self._visible = True

    def showNormal(self):
        self.show_normal_calls += 1
        self._minimized = False
        self._visible = True

    def hide(self):
        self.hide_calls += 1
        self._visible = False

    def _refresh_all_panels(self):
        self.refresh_calls += 1


class _FakeTrayIcon:
    def __init__(self, visible=True):
        self._visible = visible
        self.hide_calls = 0

    def isVisible(self):
        return self._visible

    def hide(self):
        self.hide_calls += 1
        self._visible = False


class _TrayLifecycleWindow(WindowEventsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self._exit_requested = False
        self._tray_available = True
        self._is_shutting_down = False
        self.is_visible = True
        self.tray_icon = _FakeTrayIcon()


_QT_APP = QApplication.instance() or QApplication([])


def test_toggle_overlay_uses_actual_window_visibility_instead_of_stale_flag():
    overlay = _FakeOverlay(visible=True)
    overlay.is_visible = False

    toggle_overlay(overlay)

    assert overlay.hide_calls == 1
    assert not overlay.isVisible()
    assert overlay.is_visible is False

    overlay.is_visible = True
    toggle_overlay(overlay)

    assert overlay.show_calls == 1
    assert overlay.isVisible()
    assert overlay.is_visible is True


def test_show_transition_restores_minimized_window_and_refreshes_once():
    overlay = _FakeOverlay(visible=False, minimized=True)

    _set_overlay_visible(overlay, True, refresh=True)

    assert overlay.show_normal_calls == 1
    assert overlay.show_calls == 0
    assert overlay.refresh_calls == 1
    assert overlay.is_visible is True


def test_regular_close_hides_to_tray_without_entering_shutdown():
    window = _TrayLifecycleWindow()
    window.show()
    QApplication.processEvents()

    with patch(
        "calendar_app.presentation.main_window.window_events.QSystemTrayIcon.isSystemTrayAvailable",
        return_value=True,
    ):
        closed = window.close()
        QApplication.processEvents()

    assert closed is False
    assert not window.isVisible()
    assert window.is_visible is False
    assert window._is_shutting_down is False
    assert window._exit_requested is False

    window._exit_requested = True
    window.close()


def test_unavailable_system_tray_is_recorded_for_close_fallback():
    overlay = _FakeOverlay(visible=True)
    overlay._tray_available = True

    with patch(
        "calendar_app.infrastructure.runtime.infra_wiring.QSystemTrayIcon.isSystemTrayAvailable",
        return_value=False,
    ):
        available = init_tray_icon(overlay)

    assert available is False
    assert overlay._tray_available is False


def test_confirmed_exit_marks_explicit_exit_before_closing_window():
    class _FakeApplication:
        def __init__(self):
            self.quit_calls = 0

        def quit(self):
            self.quit_calls += 1

    class _ExitHost:
        def __init__(self):
            self._exit_requested = False
            self.tray_icon = _FakeTrayIcon()
            self.shutdown_calls = 0
            self.close_saw_exit_requested = False

        def _confirm_app_exit(self):
            return True

        def shutdown_background_workers(self):
            self.shutdown_calls += 1

        def close(self):
            self.close_saw_exit_requested = self._exit_requested

    host = _ExitHost()
    application = _FakeApplication()

    with (
        patch(
            "calendar_app.presentation.main_window.action_handlers.QApplication.instance",
            return_value=application,
        ),
        patch("calendar_app.presentation.main_window.window_restore_helpers.save_window_layout"),
    ):
        ActionHandlersMixin.request_app_exit(host)

    assert host._exit_requested is True
    assert host.close_saw_exit_requested is True
    assert host.shutdown_calls == 1
    assert host.tray_icon.hide_calls == 1
    assert application.quit_calls == 1


def test_shutdown_uses_cooperative_worker_stop_without_qthread_terminate():
    class _FakeWorker:
        def __init__(self):
            self.interruption_calls = 0
            self.quit_calls = 0
            self.wait_calls = []
            self.terminate_calls = 0

        def isRunning(self):
            return True

        def requestInterruption(self):
            self.interruption_calls += 1

        def quit(self):
            self.quit_calls += 1

        def wait(self, timeout):
            self.wait_calls.append(timeout)
            return False

        def terminate(self):
            self.terminate_calls += 1

    class _ShutdownHost:
        def __init__(self, worker):
            self._is_shutting_down = False
            self._sync_worker = worker
            self._bg_workers = []
            self.alarm_worker = None
            self.task_alarm_checker = None

    worker = _FakeWorker()
    host = _ShutdownHost(worker)

    ActionHandlersMixin.shutdown_background_workers(host, wait_ms=1)

    assert host._is_shutting_down is True
    assert worker.interruption_calls == 1
    assert worker.quit_calls == 1
    assert worker.wait_calls == [1, 1500]
    assert worker.terminate_calls == 0
