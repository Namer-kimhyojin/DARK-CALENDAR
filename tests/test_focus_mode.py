import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


if __name__ == "__main__":
    unittest.main()
