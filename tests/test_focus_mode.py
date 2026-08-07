# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QPushButton, QVBoxLayout

from calendar_app.application.pomodoro_engine import PHASE_FOCUS, PomodoroSnapshot
from calendar_app.infrastructure.runtime.infra_wiring import toggle_fullscreen
from calendar_app.presentation import focus_mode
from calendar_app.presentation.focus_mode import _apply_auto_start_pause


class FakeSettings:
    def __init__(self, initial=None):
        self._values = dict(initial or {})

    def value(self, key, default=None, type=None):
        value = self._values.get(key, default)
        if type is None or value is None:
            return value
        return type(value)


class FakePomodoro:
    def __init__(self):
        self.pause_calls = 0

    def pause(self):
        self.pause_calls += 1


class FakeVisibilityWidget:
    def __init__(self, visible=True):
        self.visible = visible

    def isVisible(self):
        return self.visible

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True

    def setVisible(self, visible):
        self.visible = bool(visible)


class FakeFocusWindow:
    def __init__(self):
        self.is_focus_mode = True
        self.is_fullscreen = False
        self._fullscreen = False
        self._maximized = False
        self._focus_windowed_was_maximized = False
        self._focus_entry_was_fullscreen = False
        self._focus_entry_was_maximized = False
        self._focus_saved_dock_visibility = None
        self._focus_saved_chrome_visibility = None
        self._focus_fullscreen_btn = None
        self.focus_frame = FakeVisibilityWidget(False)
        self.left_dock = FakeVisibilityWidget(True)
        self.center_dock = FakeVisibilityWidget(False)
        self.routine_dock = FakeVisibilityWidget(True)
        self.directive_dock = FakeVisibilityWidget(True)
        self._top_bar_menu_wrapper = FakeVisibilityWidget(True)
        self.size_grip = FakeVisibilityWidget(True)
        self._central_widget = object()
        self.show_calls = 0

    def centralWidget(self):
        return self._central_widget

    def setCentralWidget(self, widget):
        self._central_widget = widget

    def show(self):
        self.show_calls += 1

    def isFullScreen(self):
        return self._fullscreen

    def isMaximized(self):
        return self._maximized

    def showFullScreen(self):
        self._fullscreen = True
        self._maximized = False

    def showMaximized(self):
        self._fullscreen = False
        self._maximized = True

    def showNormal(self):
        self._fullscreen = False
        self._maximized = False


class FocusModeAutoStartTests(unittest.TestCase):
    def test_focus_transition_stays_running_when_setting_missing(self):
        app = type("App", (), {})()
        app.settings = FakeSettings()
        app._focus_pomodoro = FakePomodoro()

        with patch("calendar_app.presentation.focus_mode._render_pomodoro_state") as render_state:
            _apply_auto_start_pause(app, "focus")

        self.assertEqual(app._focus_pomodoro.pause_calls, 0)
        render_state.assert_not_called()

    def test_focus_transition_pauses_when_explicitly_disabled(self):
        app = type("App", (), {})()
        app.settings = FakeSettings({"pomodoro_auto_start_focus": False})
        app._focus_pomodoro = FakePomodoro()

        with patch("calendar_app.presentation.focus_mode._render_pomodoro_state") as render_state:
            _apply_auto_start_pause(app, "focus")

        self.assertEqual(app._focus_pomodoro.pause_calls, 1)
        render_state.assert_called_once()


class FocusModeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_pomodoro_controls_have_visible_labels_and_accessible_names(self):
        snapshot = PomodoroSnapshot(
            phase=PHASE_FOCUS,
            phase_elapsed_secs=300,
            phase_remaining_secs=1200,
            focus_sessions_completed=1,
            focus_secs_total=1500,
            cycle_size=4,
            current_focus_index=2,
            paused=False,
        )
        app = type("App", (), {})()
        app._focus_pomodoro = type("Pomodoro", (), {"snapshot": lambda self: snapshot})()
        app.focus_phase_lbl = QLabel()
        app.timer_lbl = QLabel()
        app.focus_progress = QProgressBar()
        app.focus_summary_lbl = QLabel()
        app._focus_pause_btn = QPushButton()
        app._focus_skip_btn = QPushButton()

        tokens = {
            "accent": "#7c6ff2",
            "warning": "#d39a2a",
            "warning_soft_bg": "rgba(211,154,42,0.16)",
        }

        def fallback_t(key, default=None, **kwargs):
            text = default if default is not None else key
            return str(text).format(**kwargs)

        with (
            patch.object(focus_mode, "_focus_ui_tokens", return_value=tokens),
            patch.object(focus_mode, "_ic", return_value=QIcon()),
            patch.object(focus_mode, "t", side_effect=fallback_t),
        ):
            focus_mode._render_pomodoro_state(app)

        self.assertEqual("20:00", app.timer_lbl.text())
        self.assertEqual(20, app.focus_progress.value())
        self.assertEqual("Pause", app._focus_pause_btn.text())
        self.assertEqual("Pause", app._focus_pause_btn.accessibleName())
        self.assertEqual("Skip Focus", app._focus_skip_btn.text())
        self.assertEqual("Skip Focus", app._focus_skip_btn.accessibleName())
        self.assertEqual("Focus 2/4", app.focus_phase_lbl.accessibleName())

    def test_focus_shell_replaces_popup_and_restores_previous_chrome(self):
        app = FakeFocusWindow()

        focus_mode._activate_focus_shell(app)

        self.assertIs(app.focus_frame, app.centralWidget())
        self.assertTrue(app.focus_frame.isVisible())
        self.assertFalse(app.left_dock.isVisible())
        self.assertFalse(app.routine_dock.isVisible())
        self.assertFalse(app._top_bar_menu_wrapper.isVisible())
        self.assertFalse(app.size_grip.isVisible())

        focus_mode._restore_focus_shell(app)

        self.assertFalse(app.focus_frame.isVisible())
        self.assertTrue(app.left_dock.isVisible())
        self.assertFalse(app.center_dock.isVisible())
        self.assertTrue(app.routine_dock.isVisible())
        self.assertTrue(app._top_bar_menu_wrapper.isVisible())
        self.assertTrue(app.size_grip.isVisible())

    def test_focus_canvas_layout_can_be_rebuilt_for_a_second_session(self):
        app = type("App", (), {})()
        app.focus_frame = QFrame()
        layout = QVBoxLayout(app.focus_frame)
        layout.addWidget(QLabel("first session"))

        focus_mode._clear_focus_frame_layout(app)

        self.assertIsNone(app.focus_frame.layout())

    def test_focus_fullscreen_toggle_and_escape_keep_session_active(self):
        app = FakeFocusWindow()
        app._maximized = True

        self.assertTrue(focus_mode.toggle_focus_fullscreen(app))
        self.assertTrue(app.isFullScreen())
        self.assertTrue(app.is_focus_mode)

        self.assertTrue(focus_mode.exit_focus_fullscreen(app))
        self.assertTrue(app.isMaximized())
        self.assertTrue(app.is_focus_mode)
        self.assertFalse(app.is_fullscreen)

    def test_global_f11_action_delegates_to_focus_fullscreen(self):
        app = FakeFocusWindow()

        toggle_fullscreen(app)

        self.assertTrue(app.isFullScreen())
        self.assertTrue(app.is_focus_mode)


if __name__ == "__main__":
    unittest.main()
