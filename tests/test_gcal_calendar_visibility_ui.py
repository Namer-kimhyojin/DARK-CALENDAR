# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from calendar_app.presentation.dialogs.gcal_settings_dialog import GCalSettingsDialog


class GCalCalendarVisibilityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_visibility_toggle_refreshes_today_panel_and_calendar(self):
        from types import SimpleNamespace

        from calendar_app.presentation.dialogs.calendar_manager_page import CalendarManagerPage

        parent = QWidget()
        parent.settings = QSettings("CodexTests", "GCalCalendarVisibilityUi")
        parent.schedule_panel_refresh = __import__("unittest.mock", fromlist=["Mock"]).Mock()
        calendar = {"id": "gcal::team", "name": "Team", "type": "gcal", "is_visible": 1}
        coordinator = SimpleNamespace(
            calendar_rows=[calendar],
            calendar_providers={"gcal::team": "google"},
            states={},
            refresh=lambda: None,
        )
        page = CalendarManagerPage(parent, coordinator, lambda *args: None)
        try:
            with patch(
                "calendar_app.infrastructure.db.calendar_repo.set_calendar_visible",
                return_value=True,
            ) as save:
                page.visible.click()
            save.assert_called_once_with("gcal::team", False)
            parent.schedule_panel_refresh.assert_called_once_with(
                left=True, center=True, right=True
            )
        finally:
            page.close()
            parent.close()


if __name__ == "__main__":
    unittest.main()
