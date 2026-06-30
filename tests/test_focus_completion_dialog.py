import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
