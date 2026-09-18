# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt, QTime
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.dialogs import daily_summary_dialog as daily


class _SettingsParent(QWidget):
    def __init__(self, name: str):
        super().__init__()
        self.settings = QSettings("CodexTests", name)
        self.settings.clear()


class DailySummaryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_frameless_shell_opens_settings_and_persists_visibility_rules(self):
        parent = _SettingsParent("DailySummarySettings")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        with (
            patch.object(
                daily.DailySummaryDialog,
                "_load_schedule",
                return_value=["• [아카] 5기 교육과정 홍보  [종일]"],
            ),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent)
        self.addCleanup(dialog.close)
        dialog.show()
        QApplication.processEvents()

        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertFalse(dialog.settings_panel.isVisible())

        dialog.settings_btn.click()
        QApplication.processEvents()
        self.assertTrue(dialog._settings_open)
        self.assertTrue(dialog.settings_panel.isVisible())
        if dialog._settings_overlay_mode:
            self.assertEqual(dialog.width(), dialog.COMPACT_SIZE[0])

        dialog._visibility_buttons["schedule"][daily._MODE_HIDDEN].setChecked(True)
        dialog._visibility_buttons["routine"][daily._MODE_WHEN_AVAILABLE].setChecked(True)
        dialog.startup_toggle.setChecked(False)
        dialog.daily_toggle.setChecked(True)
        dialog.time_edit.setTime(QTime(9, 30))
        dialog.weekend_checkbox.setChecked(True)
        dialog.settings_save_btn.click()
        QApplication.processEvents()

        self.assertEqual(
            parent.settings.value(daily._SETTINGS_KEY_SCHEDULE_MODE), daily._MODE_HIDDEN
        )
        self.assertEqual(
            parent.settings.value(daily._SETTINGS_KEY_ROUTINE_MODE),
            daily._MODE_WHEN_AVAILABLE,
        )
        self.assertFalse(daily._setting_bool(parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, True))
        self.assertTrue(daily._setting_bool(parent.settings, daily._SETTINGS_KEY_DAILY_ENABLED, False))
        self.assertEqual(parent.settings.value(daily._SETTINGS_KEY_TIME), "09:30")
        self.assertTrue(daily._setting_bool(parent.settings, daily._SETTINGS_KEY_HIDE_WEEKENDS, False))
        self.assertFalse(dialog._settings_open)
        self.assertFalse(dialog.has_visible_sections)

    def test_disable_auto_action_turns_off_both_automatic_entry_points(self):
        parent = _SettingsParent("DailySummaryDisableAuto")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=["• 일정"]),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent)
        self.addCleanup(dialog.close)

        dialog.disable_auto_btn.click()

        self.assertFalse(daily._setting_bool(parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, True))
        self.assertFalse(daily._setting_bool(parent.settings, daily._SETTINGS_KEY_DAILY_ENABLED, True))

    def test_manual_entry_can_open_settings_when_automatic_display_is_disabled(self):
        parent = _SettingsParent("DailySummaryManualRecovery")
        parent.settings.setValue(daily._SETTINGS_KEY_STARTUP_ENABLED, False)
        parent.settings.setValue(daily._SETTINGS_KEY_DAILY_ENABLED, False)
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=[]),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent, show_settings=True)
        self.addCleanup(dialog.close)

        self.assertTrue(dialog._settings_open)
        self.assertFalse(dialog.startup_toggle.isChecked())
        self.assertFalse(dialog.daily_toggle.isChecked())

    def test_maybe_show_respects_startup_and_daily_switches(self):
        parent = _SettingsParent("DailySummaryEntryPoints")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        parent.settings.setValue(daily._SETTINGS_KEY_STARTUP_ENABLED, False)

        class _FakeDialog:
            created = 0
            executed = 0

            def __init__(self, parent=None):
                type(self).created += 1
                self.has_content = True
                self.has_visible_sections = True

            def exec(self):
                type(self).executed += 1

            def deleteLater(self):
                return None

        with (
            patch.object(daily, "DailySummaryDialog", _FakeDialog),
            patch.object(daily, "_today_str", return_value="2026-09-18"),
        ):
            daily.maybe_show_daily_summary(parent, trigger="startup")
            self.assertEqual(_FakeDialog.created, 0)

            parent.settings.setValue(daily._SETTINGS_KEY_STARTUP_ENABLED, True)
            daily.maybe_show_daily_summary(parent, trigger="startup")
            self.assertEqual(_FakeDialog.executed, 1)
            self.assertEqual(
                parent.settings.value(daily._SETTINGS_KEY_LAST_SHOWN), "2026-09-18"
            )

            parent.settings.setValue(daily._SETTINGS_KEY_LAST_SHOWN, "")
            parent.settings.setValue(daily._SETTINGS_KEY_DAILY_ENABLED, False)
            daily.maybe_show_daily_summary(parent, trigger="daily")
            self.assertEqual(_FakeDialog.executed, 1)


if __name__ == "__main__":
    unittest.main()
