# -*- coding: utf-8 -*-
"""Palette icons must follow the app surface even when Windows uses another mode."""

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.theme.style_builder import build_global_stylesheet
from calendar_app.presentation.widgets.command_palette import CommandPalette
from calendar_app.presentation.widgets.command_palette_runtime import _palette_qcolor
from calendar_app.shared.color_utils import contrast_ratio
from tests.support import TemporaryDatabaseTestCase
from tests.test_command_palette import _PaletteHost


class CommandPaletteThemeIconTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def _host(self, mode, system_text):
        original = QPalette(self._app.palette())
        self.addCleanup(self._app.setPalette, original)
        system_palette = QPalette(original)
        system_palette.setColor(QPalette.ColorRole.Text, QColor(system_text))
        system_palette.setColor(QPalette.ColorRole.WindowText, QColor(system_text))
        self._app.setPalette(system_palette)
        host = _PaletteHost()
        self.addCleanup(host.close)
        self._set_mode(host, mode)
        return host

    @staticmethod
    def _set_mode(host, mode):
        background = "#1c1c1c" if mode == "dark" else "#f5f7fb"
        host.settings.setValue("text_theme", mode)
        host.settings.setValue("panel_base_color", background)
        host.setStyleSheet(build_global_stylesheet(text_theme=mode, panel_base_color=background))

    def _assert_visible_icons(self, palette):
        search_icon = palette.search_bar.actions()[0].icon()
        self.assertGreater(palette.result_list.count(), 0)
        cases = [("search", search_icon, palette._style_bundle["input_bg"])]
        cases += [
            (
                f"result-{index}",
                palette.result_list.item(index).icon(),
                palette._style_bundle["container_bg"],
            )
            for index in range(palette.result_list.count())
        ]
        for name, icon, background in cases:
            with self.subTest(icon=name):
                image = icon.pixmap(32, 32).toImage()
                self.assertFalse(image.isNull())
                colors = [
                    image.pixelColor(x, y)
                    for x in range(image.width())
                    for y in range(image.height())
                ]
                strongest = max(colors, key=lambda color: color.alpha())
                self.assertGreater(strongest.alpha(), 200)
                self.assertGreaterEqual(
                    contrast_ratio(strongest.name(), _palette_qcolor(background).name()), 3.0
                )

    def test_dark_app_icons_remain_visible_with_light_windows_palette(self):
        host = self._host("dark", "#000000")
        palette = CommandPalette(host)
        self.addCleanup(palette.close)
        palette._on_search_changed(">")
        self._assert_visible_icons(palette)

    def test_light_app_icons_remain_visible_with_dark_windows_palette(self):
        host = self._host("light", "#ffffff")
        palette = CommandPalette(host)
        self.addCleanup(palette.close)
        palette._on_search_changed(">")
        self._assert_visible_icons(palette)

    def test_reopening_palette_refreshes_search_and_result_icon_colors(self):
        host = self._host("dark", "#000000")
        palette = CommandPalette(host)
        self.addCleanup(palette.close)
        for mode in ("light", "dark", "light"):
            with self.subTest(mode=mode):
                self._set_mode(host, mode)
                palette.show_at_center(QRect(0, 0, 1024, 768))
                self._assert_visible_icons(palette)
                palette.hide()
