# -*- coding: utf-8 -*-
"""Guaranteed application exit even when a window refuses to close."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from calendar_app.shared.app_lifecycle import (
    EXITING_PROPERTY,
    finish_application_exit,
    is_app_exiting,
    mark_app_exiting,
)


class _VetoingDialog(QDialog):
    """Mimics a dialog whose 'discard changes?' prompt was answered with No."""

    def reject(self):
        self.vetoed = True


class AppLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self._app.setProperty(EXITING_PROPERTY, False)
        self.addCleanup(self._app.setProperty, EXITING_PROPERTY, False)

    def test_marking_is_visible_to_dialogs(self):
        self.assertFalse(is_app_exiting())
        mark_app_exiting()
        self.assertTrue(is_app_exiting())

    def test_exit_completes_even_when_a_modal_dialog_vetoes_quit(self):
        host = QWidget()
        host.show()
        self.addCleanup(host.close)
        dialog = _VetoingDialog(host)
        outcome = {}

        def run_modal():
            QTimer.singleShot(50, lambda: finish_application_exit(self._app))
            outcome["dialog"] = dialog.exec()

        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(lambda: (outcome.setdefault("watchdog", True), self._app.exit(99)))
        watchdog.start(3000)
        QTimer.singleShot(0, run_modal)
        code = self._app.exec()
        watchdog.stop()
        self.assertNotIn("watchdog", outcome)
        self.assertEqual(code, 0)
        self.assertIn("dialog", outcome)
        self.assertTrue(is_app_exiting())

    def test_helper_tolerates_minimal_application_doubles(self):
        class _FakeApplication:
            def __init__(self):
                self.quit_calls = 0

            def quit(self):
                self.quit_calls += 1

        fake = _FakeApplication()
        finish_application_exit(fake)
        self.assertEqual(fake.quit_calls, 1)


if __name__ == "__main__":
    unittest.main()
