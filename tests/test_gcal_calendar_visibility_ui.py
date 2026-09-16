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
        class _Parent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalCalendarVisibilityUi")
                self.refresh_requests = []

            def schedule_panel_refresh(self, **kwargs):
                self.refresh_requests.append(kwargs)

        parent = _Parent()
        dialog = GCalSettingsDialog(parent=parent)
        row = dialog._make_calendar_row_widget(
            {
                "id": "gcal::team@example.com",
                "name": "숨김 테스트",
                "type": "gcal",
                "color": "#4da6ff",
                "is_default": 0,
                "is_visible": 1,
            }
        )
        try:
            visibility_button = row.findChild(QPushButton, "calendarVisibilityButton")
            self.assertIsNotNone(visibility_button)
            with patch(
                "calendar_app.infrastructure.db.calendar_repo.set_calendar_visible",
                return_value=True,
            ):
                visibility_button.click()
            self.assertEqual(
                {"left": True, "center": True},
                parent.refresh_requests[-1],
            )
        finally:
            row.close()
            dialog.close()
            parent.close()


if __name__ == "__main__":
    unittest.main()
