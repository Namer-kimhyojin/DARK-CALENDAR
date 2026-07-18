import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.main_window.calendar_view_actions import CalendarViewActionsMixin


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        if type is not None and value is not None:
            return type(value)
        return value

    def setValue(self, key, value):
        self.values[key] = value


class SignatureHost(CalendarViewActionsMixin):
    def __init__(self):
        self.settings = FakeSettings(
            {
                "theme_color": "#4da6ff",
                "text_theme": "dark",
                "panel_base_color": "#1c1c1c",
                "last_opacity": 200,
                "last_border_opacity": 80,
                "last_text_opacity": 255,
                "ui_shape_preset": "sharp",
                "left_panel_mode": "today",
            }
        )
        self.current_date = QDate.fromString("2026-04-02", "yyyy-MM-dd")
        self.selected_task_ids = set()
        self.view_mode_state = "monthly"
        self.cal_show_weekends = True
        self.cal_start_monday = True
        self.cal_show_month = False
        self.cal_show_weekday = False


class PanelRenderSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_left_signature_changes_when_panel_base_color_changes(self):
        host = SignatureHost()

        before = host._build_left_render_signature()
        host.settings.setValue("panel_base_color", "#f0f4f8")
        after = host._build_left_render_signature()

        self.assertNotEqual(before, after)

    def test_center_signature_changes_when_text_theme_changes(self):
        host = SignatureHost()

        before = host._build_center_render_signature()
        host.settings.setValue("text_theme", "light")
        after = host._build_center_render_signature()

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
