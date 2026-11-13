# -*- coding: utf-8 -*-
"""Appearance action glyphs must be readable on their own dialog surface."""

import unittest

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QPushButton

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog
from calendar_app.shared.color_utils import contrast_ratio


class AppearanceIconContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _check_mode(self, mode):
        settings = QSettings("kimhyojin", "Dark Calendar")
        before = {key: settings.value(key) for key in settings.allKeys()}
        original = QPalette(self._app.palette())
        try:
            settings.clear()
            settings.setValue("text_theme", mode)
            background = "#1c1c1c" if mode == "dark" else "#f5f7fb"
            settings.setValue("panel_base_color", background)
            system = QPalette(original)
            system.setColor(QPalette.ColorRole.Text, QColor("#000000"))
            self._app.setPalette(system)
            dialog = PanelColorPickerDialog(current_base=background, current_text_theme=mode)
            try:
                advanced = next(
                    button
                    for button in dialog.findChildren(QPushButton)
                    if button.text() == t("dialog.theme.details_action", "세부 모양 조정…")
                )
                buttons = (
                    advanced,
                    dialog._contrast_fix_btn,
                    dialog._btn_apply_preset_text,
                    dialog.findChild(QPushButton, "btn_point_custom"),
                )
                for button in buttons:
                    with self.subTest(mode=mode, action=button.text()):
                        image = button.icon().pixmap(32, 32).toImage()
                        self.assertFalse(image.isNull())
                        colors = [
                            image.pixelColor(x, y)
                            for x in range(image.width())
                            for y in range(image.height())
                        ]
                        glyph = max(colors, key=lambda color: color.alpha())
                        self.assertGreater(glyph.alpha(), 200)
                        self.assertGreaterEqual(contrast_ratio(glyph.name(), background), 3.0)
            finally:
                dialog.reject()
                dialog.close()
        finally:
            self._app.setPalette(original)
            settings.clear()
            for key, value in before.items():
                settings.setValue(key, value)

    def test_dark_appearance_action_icons_are_visible(self):
        self._check_mode("dark")

    def test_light_appearance_action_icons_are_visible(self):
        self._check_mode("light")
