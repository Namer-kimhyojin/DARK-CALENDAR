import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog
from calendar_app.presentation.panels.side_panel_renderer import (
    _panel_surface_style,
    _panel_toolbar_style,
)
from calendar_app.shared.theme_settings import opacity_percent_label

_RGBA_ALPHA_RE = re.compile(
    r"background-color:\s*rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(\d+)\s*\)"
)


class PanelOpacityUiTests(unittest.TestCase):
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

    def test_panel_toolbar_uses_same_alpha_as_panel_surface(self):
        surface_style = _panel_surface_style()
        toolbar_style = _panel_toolbar_style()

        surface_match = _RGBA_ALPHA_RE.search(surface_style)
        toolbar_match = _RGBA_ALPHA_RE.search(toolbar_style)

        self.assertIsNotNone(surface_match)
        self.assertIsNotNone(toolbar_match)
        self.assertEqual(surface_match.group(1), toolbar_match.group(1))

    def test_theme_dialog_opacity_labels_use_percent_text(self):
        dialog = PanelColorPickerDialog(
            current_opacity=51,
            current_border_opacity=128,
            current_text_opacity=255,
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._op_lbl.text(), opacity_percent_label(51))
        self.assertEqual(dialog._bd_op_lbl.text(), opacity_percent_label(128))
        self.assertEqual(dialog._txt_op_lbl.text(), opacity_percent_label(255))

        dialog._slider.setValue(102)
        dialog._border_slider.setValue(64)
        dialog._text_slider.setValue(153)

        self.assertEqual(dialog._op_lbl.text(), opacity_percent_label(102))
        self.assertEqual(dialog._bd_op_lbl.text(), opacity_percent_label(64))
        self.assertEqual(dialog._txt_op_lbl.text(), opacity_percent_label(153))

    def test_theme_dialog_preserves_fully_transparent_background(self):
        dialog = PanelColorPickerDialog(current_opacity=0)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._slider.value(), 0)
        self.assertEqual(dialog.selected_opacity(), 0)
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertIn("0% = 완전 투명, 100% = 완전 불투명", labels)

    def test_border_and_text_opacity_update_preview_immediately(self):
        dialog = PanelColorPickerDialog(
            current_opacity=255,
            current_border_opacity=255,
            current_text_opacity=255,
            current_text_primary="#ffffff",
            current_text_secondary="#cccccc",
            current_text_muted="#999999",
        )
        self.addCleanup(dialog.close)

        dialog._border_slider.setValue(0)
        self.assertIn("border: 1px solid rgba(255,255,255,0.0)", dialog._preview_frame.styleSheet())

        dialog._text_slider.setValue(0)
        stylesheet = dialog._preview_frame.styleSheet()
        self.assertIn("QLabel#previewItemText1 { color: rgba(255, 255, 255, 0);", stylesheet)
        self.assertIn("QLabel#previewInputHint { color: rgba(153, 153, 153, 0);", stylesheet)


if __name__ == "__main__":
    unittest.main()
