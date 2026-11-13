# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QSettings, Qt, QTime
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
        self.assertFalse(dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
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
        self.assertFalse(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, True)
        )
        self.assertTrue(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_DAILY_ENABLED, False)
        )
        self.assertEqual(parent.settings.value(daily._SETTINGS_KEY_TIME), "09:30")
        self.assertTrue(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_HIDE_WEEKENDS, False)
        )
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

        self.assertFalse(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, True)
        )
        self.assertFalse(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_DAILY_ENABLED, True)
        )

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
            self.assertEqual(parent.settings.value(daily._SETTINGS_KEY_LAST_SHOWN), "2026-09-18")

            parent.settings.setValue(daily._SETTINGS_KEY_LAST_SHOWN, "")
            parent.settings.setValue(daily._SETTINGS_KEY_DAILY_ENABLED, False)
            daily.maybe_show_daily_summary(parent, trigger="daily")
            self.assertEqual(_FakeDialog.executed, 1)

    def test_briefing_stays_above_late_restored_widgets_and_releases_priority_on_close(self):
        parent = _SettingsParent("DailySummaryWindowPriority")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        widget = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        widget.setProperty("airCalendarOverlayWindow", True)
        self.addCleanup(widget.close)
        original_flags = widget.windowFlags()
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=["• 일정"]),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent)
        self.addCleanup(dialog.close)
        # The parent is hidden, as it is after restoring widget-only mode.
        dialog.show()
        QApplication.processEvents()
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(dialog.windowModality(), Qt.WindowModality.ApplicationModal)
        self.assertTrue(dialog._priority_guard_active)
        self.assertTrue(dialog.ok_btn.isEnabled())
        with patch.object(dialog, "raise_") as raise_dialog:
            widget.show()
            QApplication.processEvents()
            self.assertGreaterEqual(raise_dialog.call_count, 1)
            # Showing a native tool also delivers activation/z-order events.
            # Drain them before checking that one burst is coalesced.
            QApplication.processEvents()
            raise_dialog.reset_mock()
            for _ in range(12):
                QApplication.sendEvent(widget, QEvent(QEvent.Type.ZOrderChange))
            self.assertTrue(dialog._priority_raise_timer.isActive())
            QApplication.processEvents()
            self.assertEqual(raise_dialog.call_count, 1)
            # The guard does not alter a widget's flags or persisted settings.
            self.assertEqual(widget.windowFlags(), original_flags)
            unrelated = QWidget()
            QApplication.sendEvent(unrelated, QEvent(QEvent.Type.ZOrderChange))
            QApplication.processEvents()
            self.assertEqual(raise_dialog.call_count, 1)
            unrelated.close()
            dialog.ok_btn.click()
            QApplication.sendEvent(widget, QEvent(QEvent.Type.ZOrderChange))
            QApplication.processEvents()
            self.assertEqual(raise_dialog.call_count, 1)
        self.assertFalse(dialog._priority_guard_active)
        self.assertFalse(dialog._priority_raise_timer.isActive())
        self.assertFalse(dialog.isVisible())

    def test_narrow_settings_keep_footer_visible_and_cancel_draft(self):
        parent = _SettingsParent("DailySummaryNarrowDraft")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        parent.settings.setValue(daily._SETTINGS_KEY_STARTUP_ENABLED, True)
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=["• Schedule"]),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent, show_settings=True)
        self.addCleanup(dialog.close)
        dialog.setMinimumSize(420, 360)
        dialog.setMaximumSize(420, 420)
        dialog.resize(420, 420)
        dialog.show()
        for _ in range(4):
            QApplication.processEvents()
        self.assertTrue(dialog.settings_save_btn.isVisible())
        self.assertTrue(dialog.settings_cancel_btn.isVisible())
        self.assertFalse(dialog.settings_footer.visibleRegion().isEmpty())
        dialog.startup_toggle.setChecked(False)
        dialog.settings_cancel_btn.click()
        self.assertTrue(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, False)
        )
        self.assertTrue(dialog.startup_toggle.isChecked())

    def test_light_reminder_title_uses_full_width_above_time_and_toggle(self):
        parent = _SettingsParent("DailySummaryLightReminderLayout")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        for key, value in {
            "text_theme": "light",
            "panel_base_color": "#f3f1fa",
            "theme_color": "#7950b8",
        }.items():
            parent.settings.setValue(key, value)
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=[]),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent, show_settings=True)
        self.addCleanup(dialog.close)
        dialog.settings_panel.setFixedWidth(320)
        dialog.show()
        for _ in range(4):
            QApplication.processEvents()
        label = dialog.daily_reminder_label
        title_top = label.mapTo(dialog, QPoint()).y()
        time_top = dialog.time_edit.mapTo(dialog, QPoint()).y()
        toggle_top = dialog.daily_toggle.mapTo(dialog, QPoint()).y()
        self.assertGreaterEqual(label.width(), label.fontMetrics().horizontalAdvance(label.text()))
        self.assertLess(label.height(), label.fontMetrics().lineSpacing() * 2)
        self.assertLess(title_top + label.height(), time_top)
        self.assertLess(title_top + label.height(), toggle_top)
        self.assertGreater(dialog.time_edit.width(), dialog.daily_toggle.width())
        self.assertIs(label.buddy(), dialog.time_edit)

    def test_reminder_time_and_enabled_draft_are_discarded_on_cancel(self):
        parent = _SettingsParent("DailySummaryReminderDraft")
        self.addCleanup(parent.settings.clear)
        self.addCleanup(parent.close)
        parent.settings.setValue(daily._SETTINGS_KEY_DAILY_ENABLED, True)
        parent.settings.setValue(daily._SETTINGS_KEY_TIME, "08:15")
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=[]),
            patch.object(daily.DailySummaryDialog, "_load_due_routines", return_value=[]),
        ):
            dialog = daily.DailySummaryDialog(parent=parent, show_settings=True)
        self.addCleanup(dialog.close)
        dialog.daily_toggle.setChecked(False)
        dialog.time_edit.setTime(QTime(10, 45))
        self.assertFalse(dialog.time_edit.isEnabled())
        dialog.settings_cancel_btn.click()
        self.assertTrue(
            daily._setting_bool(parent.settings, daily._SETTINGS_KEY_DAILY_ENABLED, False)
        )
        self.assertEqual(parent.settings.value(daily._SETTINGS_KEY_TIME), "08:15")
        self.assertTrue(dialog.daily_toggle.isChecked())
        self.assertEqual(dialog.time_edit.time(), QTime(8, 15))
        self.assertTrue(dialog.time_edit.isEnabled())


if __name__ == "__main__":
    unittest.main()
