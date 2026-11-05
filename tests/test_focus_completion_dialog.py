# -*- coding: utf-8 -*-

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QBoxLayout, QDialog

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.focus_completion_dialog import FocusCompletionDialog


class FocusCompletionDialogLocaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_session_summary_uses_locale_templates(self):
        dialog = FocusCompletionDialog(sessions=3, total_secs=3723)
        self.addCleanup(dialog.close)

        self.assertEqual(
            dialog._format_time_best(3723),
            t("focus.duration_hours_minutes", "{hours}h {minutes}m", hours=1, minutes=2),
        )
        self.assertEqual(
            dialog._format_session_summary(3, 3723),
            t(
                "focus.session_summary",
                "{sessions} sessions / {duration}",
                sessions=3,
                duration=t(
                    "focus.duration_hours_minutes", "{hours}h {minutes}m", hours=1, minutes=2
                ),
            ),
        )

    def test_manual_exit_hides_long_break_and_keeps_log_button(self):
        dialog = FocusCompletionDialog(
            sessions=1,
            total_secs=1500,
            allow_long_break=False,
            show_log_button=True,
        )
        self.addCleanup(dialog.close)

        self.assertIsNone(dialog.break_btn)
        self.assertIsNotNone(dialog.log_btn)
        self.assertEqual(dialog.ok_btn.text(), t("focus.return_to_main", "Return to Calendar"))

    def test_set_completion_keeps_long_break_option(self):
        dialog = FocusCompletionDialog(
            sessions=4,
            total_secs=6000,
            allow_long_break=True,
            show_log_button=True,
        )
        self.addCleanup(dialog.close)

        self.assertIsNotNone(dialog.break_btn)
        self.assertIsNotNone(dialog.log_btn)
        self.assertEqual(dialog.break_btn.objectName(), "focusCompletionLongBreakBtn")

    def test_completion_uses_one_accent_role_and_explicit_keyboard_action(self):
        dialog = FocusCompletionDialog(
            sessions=2,
            total_secs=1500,
            today_sessions=4,
            today_secs=3000,
            monthly_sessions=8,
            monthly_secs=6000,
        )
        self.addCleanup(dialog.close)

        accent = dialog._ui_tokens["tab_text_active"]
        primary = dialog._ui_tokens["text_primary"]
        self.assertIn("border: 1px solid", dialog.container.styleSheet())
        self.assertIn(f"color: {accent};", dialog.current_value_label.styleSheet())
        self.assertIn(f"color: {primary};", dialog.today_value_label.styleSheet())
        self.assertIn(f"color: {primary};", dialog.month_value_label.styleSheet())
        self.assertTrue(dialog.ok_btn.isDefault())
        self.assertFalse(dialog.break_btn.autoDefault())
        self.assertFalse(dialog.log_btn.autoDefault())

    def test_narrow_completion_keeps_all_actions_and_results(self):
        for button_name, result in (
            ("break_btn", FocusCompletionDialog.RESULT_START_LONG_BREAK),
            ("log_btn", FocusCompletionDialog.RESULT_VIEW_LOGS),
            ("ok_btn", QDialog.DialogCode.Accepted),
        ):
            with self.subTest(action=button_name):
                dialog = FocusCompletionDialog(sessions=3, total_secs=5400)
                self.addCleanup(dialog.close)
                dialog.setMaximumWidth(360)
                dialog.resize(360, 400)
                dialog.show()
                for _ in range(4):
                    self._app.processEvents()
                self.assertEqual(
                    dialog._secondary_buttons_layout.direction(), QBoxLayout.Direction.TopToBottom
                )
                self.assertTrue(dialog.ok_btn.isVisible())
                self.assertTrue(dialog.break_btn.isVisible())
                self.assertTrue(dialog.log_btn.isVisible())
                getattr(dialog, button_name).click()
                self.assertEqual(dialog.result(), result)


if __name__ == "__main__":
    unittest.main()
