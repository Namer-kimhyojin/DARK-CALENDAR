import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.dialogs.pomodoro_settings_dialog import PomodoroSettingsDialog
from calendar_app.presentation.main_window.app_initializer import _initialize_focus_timer_defaults


class FakeSettings:
    def __init__(self, initial=None):
        self._values = dict(initial or {})

    def value(self, key, default=None, type=None):
        value = self._values.get(key, default)
        if type is None or value is None:
            return value
        return type(value)

    def setValue(self, key, value):
        self._values[key] = value

    def sync(self):
        pass


class Host(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings


class PomodoroSettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_loads_values_from_settings(self):
        settings = FakeSettings(
            {
                "focus_mode_type": "stopwatch",
                "pomodoro_focus_minutes": "30",
                "pomodoro_short_break_minutes": "7",
                "pomodoro_long_break_minutes": "20",
                "pomodoro_long_break_every": "5",
                "pomodoro_auto_start_break": "true",
                "pomodoro_auto_start_focus": "false",
                "pomodoro_daily_goal_cycles": "10",
            }
        )
        host = Host(settings)
        self.addCleanup(host.close)

        dlg = PomodoroSettingsDialog(host)
        self.addCleanup(dlg.close)

        self.assertEqual(dlg.mode_combo.currentData(), "stopwatch")
        self.assertEqual(dlg.focus_minutes_spin.value(), 30)
        self.assertEqual(dlg.short_break_minutes_spin.value(), 7)
        self.assertEqual(dlg.long_break_minutes_spin.value(), 20)
        self.assertEqual(dlg.long_break_every_spin.value(), 5)
        self.assertTrue(dlg.auto_start_break_cb.isChecked())
        self.assertFalse(dlg.auto_start_focus_cb.isChecked())
        self.assertEqual(dlg.daily_goal_cycles_spin.value(), 10)

    def test_save_persists_updated_values(self):
        settings = FakeSettings()
        host = Host(settings)
        self.addCleanup(host.close)

        dlg = PomodoroSettingsDialog(host)
        self.addCleanup(dlg.close)
        dlg.mode_combo.setCurrentIndex(dlg.mode_combo.findData("pomodoro"))
        dlg.focus_minutes_spin.setValue(40)
        dlg.short_break_minutes_spin.setValue(8)
        dlg.long_break_minutes_spin.setValue(18)
        dlg.long_break_every_spin.setValue(3)
        dlg.auto_start_break_cb.setChecked(False)
        dlg.auto_start_focus_cb.setChecked(True)
        dlg.daily_goal_cycles_spin.setValue(12)

        dlg._save()

        self.assertEqual(settings.value("focus_mode_type"), "pomodoro")
        self.assertEqual(settings.value("pomodoro_focus_minutes"), 40)
        self.assertEqual(settings.value("pomodoro_short_break_minutes"), 8)
        self.assertEqual(settings.value("pomodoro_long_break_minutes"), 18)
        self.assertEqual(settings.value("pomodoro_long_break_every"), 3)
        self.assertFalse(settings.value("pomodoro_auto_start_break"))
        self.assertTrue(settings.value("pomodoro_auto_start_focus"))
        self.assertEqual(settings.value("pomodoro_daily_goal_cycles"), 12)

    def test_stopwatch_mode_disables_pomodoro_controls_then_reenables(self):
        settings = FakeSettings({"focus_mode_type": "stopwatch"})
        host = Host(settings)
        self.addCleanup(host.close)

        dlg = PomodoroSettingsDialog(host)
        self.addCleanup(dlg.close)

        self.assertEqual(dlg.mode_combo.currentData(), "stopwatch")
        self.assertFalse(dlg.focus_minutes_spin.isEnabled())
        self.assertFalse(dlg.short_break_minutes_spin.isEnabled())
        self.assertFalse(dlg.auto_start_break_cb.isEnabled())

        dlg.mode_combo.setCurrentIndex(dlg.mode_combo.findData("pomodoro"))
        self.assertTrue(dlg.focus_minutes_spin.isEnabled())
        self.assertTrue(dlg.short_break_minutes_spin.isEnabled())
        self.assertTrue(dlg.auto_start_break_cb.isEnabled())

    def test_invalid_numeric_settings_are_clamped(self):
        settings = FakeSettings(
            {
                "pomodoro_focus_minutes": "999",
                "pomodoro_short_break_minutes": "0",
                "pomodoro_long_break_minutes": "not-number",
                "pomodoro_long_break_every": "1",
                "pomodoro_daily_goal_cycles": "-1",
            }
        )
        host = Host(settings)
        self.addCleanup(host.close)

        dlg = PomodoroSettingsDialog(host)
        self.addCleanup(dlg.close)

        self.assertEqual(dlg.focus_minutes_spin.value(), 180)
        self.assertEqual(dlg.short_break_minutes_spin.value(), 1)
        self.assertEqual(dlg.long_break_minutes_spin.value(), 15)
        self.assertEqual(dlg.long_break_every_spin.value(), 2)
        self.assertEqual(dlg.daily_goal_cycles_spin.value(), 1)

    def test_missing_auto_start_focus_defaults_to_enabled(self):
        settings = FakeSettings({"pomodoro_auto_start_break": "true"})
        host = Host(settings)
        self.addCleanup(host.close)

        dlg = PomodoroSettingsDialog(host)
        self.addCleanup(dlg.close)

        self.assertTrue(dlg.auto_start_break_cb.isChecked())
        self.assertTrue(dlg.auto_start_focus_cb.isChecked())

    def test_focus_timer_defaults_migrate_existing_transition_settings(self):
        settings = FakeSettings(
            {
                "pomodoro_auto_start_break": False,
                "pomodoro_auto_start_focus": False,
            }
        )

        class App:
            def __init__(self, settings_obj):
                self.settings = settings_obj

        app = App(settings)
        _initialize_focus_timer_defaults(app)

        self.assertTrue(settings.value("pomodoro_auto_start_break"))
        self.assertTrue(settings.value("pomodoro_auto_start_focus"))
        self.assertTrue(settings.value("pomodoro_auto_start_transition_defaults_v2"))

        settings.setValue("pomodoro_auto_start_break", False)
        settings.setValue("pomodoro_auto_start_focus", False)
        _initialize_focus_timer_defaults(app)

        self.assertFalse(settings.value("pomodoro_auto_start_break"))
        self.assertFalse(settings.value("pomodoro_auto_start_focus"))


if __name__ == "__main__":
    unittest.main()
