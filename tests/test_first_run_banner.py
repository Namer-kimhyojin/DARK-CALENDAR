# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from calendar_app.presentation.main_window.first_run_banner import (
    build_first_run_banner,
    should_show_first_run_banner,
)


class _FakeSettings:
    def __init__(self, values=None):
        self._values = dict(values or {})

    def value(self, key, default=None, type=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value


class _FakeHost(QWidget):
    def __init__(self, values=None):
        super().__init__()
        self.settings = _FakeSettings(values)
        self._welcome_banner = None
        self.calls = []

    def open_task_dialog(self):
        self.calls.append("schedule")

    def open_gcal_settings_dialog(self):
        self.calls.append("calendar")

    def show_shortcut_guide(self):
        self.calls.append("help")


class FirstRunBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_new_profile_gets_non_modal_banner_and_primary_action(self):
        host = _FakeHost()
        self.addCleanup(host.close)

        banner = build_first_run_banner(host)
        host._welcome_banner = banner
        self.addCleanup(banner.close)

        self.assertIsNotNone(banner)
        primary = banner.findChild(QPushButton, "primary_btn")
        self.assertIsNotNone(primary)
        self.assertGreaterEqual(primary.minimumHeight(), 32)
        primary.click()
        self.assertEqual(["schedule"], host.calls)
        self.assertTrue(host.settings.value("ux_welcome_seen_v1"))
        self.assertTrue(banner.isHidden())

    def test_existing_profile_does_not_get_banner(self):
        settings = _FakeSettings({"last_working_date": "2026-07-28"})

        self.assertFalse(should_show_first_run_banner(settings))

    def test_dismissed_profile_does_not_get_banner(self):
        settings = _FakeSettings({"ux_welcome_seen_v1": True})

        self.assertFalse(should_show_first_run_banner(settings))


if __name__ == "__main__":
    unittest.main()
