import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from calendar_app.presentation.main_window.action_handlers import (
    ActionHandlersMixin,
    _build_exit_confirmation_box,
)


class ExitConfirmationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PyQt6.QtCore import QSettings

        from calendar_app.infrastructure.i18n import I18nManager

        settings = QSettings("kimhyojin", "Dark Calendar")
        self._orig_lang = settings.value("language")
        settings.setValue("language", "ko")
        I18nManager()._load_translations()

    def tearDown(self):
        from PyQt6.QtCore import QSettings

        from calendar_app.infrastructure.i18n import I18nManager

        settings = QSettings("kimhyojin", "Dark Calendar")
        if self._orig_lang is not None:
            settings.setValue("language", self._orig_lang)
        else:
            settings.remove("language")
        I18nManager()._load_translations()

    def test_exit_confirmation_box_forces_message_font_to_ten_point(self):
        host = QWidget()
        self.addCleanup(host.close)

        box = _build_exit_confirmation_box(host)
        self.addCleanup(box.close)

        self.assertEqual(box.windowTitle(), "종료 안내")
        self.assertIn("Dark Calendar를 종료합니다.", box.text())
        self.assertEqual(
            box.standardButtons(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        self.assertEqual(box.standardButton(box.defaultButton()), QMessageBox.StandardButton.No)
        self.assertIn("font-size: 10pt;", box.styleSheet())

    def test_confirm_app_exit_returns_true_only_for_yes(self):
        host = QWidget()
        self.addCleanup(host.close)

        class _FakeBox:
            def __init__(self, result):
                self._result = result

            def exec(self):
                return self._result

        with patch(
            "calendar_app.presentation.main_window.action_handlers._build_exit_confirmation_box",
            return_value=_FakeBox(QMessageBox.StandardButton.Yes),
        ):
            self.assertTrue(ActionHandlersMixin._confirm_app_exit(host))

        with patch(
            "calendar_app.presentation.main_window.action_handlers._build_exit_confirmation_box",
            return_value=_FakeBox(QMessageBox.StandardButton.No),
        ):
            self.assertFalse(ActionHandlersMixin._confirm_app_exit(host))


if __name__ == "__main__":
    unittest.main()
