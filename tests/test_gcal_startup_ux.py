# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.google_sync.common import ensure_gcal_startup_defaults
from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin


class _FakeSettings:
    def __init__(self, initial=None):
        self.data = dict(initial or {})

    def value(self, key, default=None, type=None):
        value = self.data.get(key, default)
        if type is not None and value is not None:
            return type(value)
        return value

    def setValue(self, key, value):
        self.data[key] = value


class _FakeGCalApp(QWidget, GCalActionsMixin):
    def __init__(self, initial=None):
        super().__init__()
        self.settings = _FakeSettings(initial)
        self._sync_worker = None
        self._auth_worker = None
        self._is_shutting_down = False
        self.gcal_sync = None
        self.status_updates = 0
        self.refresh_calls = []

    def update_sync_status(self):
        self.status_updates += 1

    def schedule_panel_refresh(self, **kwargs):
        self.refresh_calls.append(kwargs)


class GCalStartupUxTests(unittest.TestCase):
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

    def test_fresh_install_defaults_to_local_only_and_skips_first_run_prompt(self):
        settings = _FakeSettings()
        with patch(
            "calendar_app.infrastructure.google_sync.common.os.path.exists", return_value=False
        ):
            enabled = ensure_gcal_startup_defaults(settings)

        self.assertFalse(enabled)
        self.assertEqual(settings.data["gcal_enabled"], "false")
        self.assertEqual(settings.data["gcal_setup_wizard_shown"], "true")

    def test_existing_token_keeps_google_sync_enabled(self):
        settings = _FakeSettings()
        with patch(
            "calendar_app.infrastructure.google_sync.common.os.path.exists", return_value=True
        ):
            enabled = ensure_gcal_startup_defaults(settings)

        self.assertTrue(enabled)
        self.assertEqual(settings.data["gcal_enabled"], "true")

    def test_importing_common_does_not_eagerly_import_google_service(self):
        script = (
            "import sys; "
            "import calendar_app.infrastructure.google_sync.common; "
            "print(int('calendar_app.infrastructure.google_sync.service' in sys.modules)); "
            "print(int('googleapiclient.discovery' in sys.modules))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        self.assertEqual(result.stdout.strip().splitlines(), ["0", "0"])

    def test_check_first_time_setup_no_longer_opens_modal_prompt(self):
        host = _FakeGCalApp()
        self.addCleanup(host.close)
        self.addCleanup(host.deleteLater)

        with patch(
            "calendar_app.presentation.main_window.action_handlers_gcal.QMessageBox.question"
        ) as question_mock:
            host.check_first_time_setup()

        question_mock.assert_not_called()
        self.assertEqual(host.settings.data["gcal_setup_wizard_shown"], "true")

    def test_manual_sync_without_setup_shows_simple_guidance(self):
        host = _FakeGCalApp({"gcal_enabled": "true"})
        self.addCleanup(host.close)
        self.addCleanup(host.deleteLater)
        messages = []

        with (
            patch(
                "calendar_app.presentation.main_window.action_handlers_gcal.os.path.exists",
                return_value=False,
            ),
            patch(
                "calendar_app.presentation.main_window.action_handlers_gcal.QMessageBox.information",
                side_effect=lambda parent, title, message: messages.append((title, message)),
            ),
        ):
            host.sync_google_calendar(silent=False)

        self.assertEqual(len(messages), 1)
        self.assertIn("Google Calendar", messages[0][1])
        self.assertIn("인증", messages[0][1])
        self.assertIsNone(host._sync_worker)


if __name__ == "__main__":
    unittest.main()
