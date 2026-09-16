# -*- coding: utf-8 -*-
import os
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QToolButton

from calendar_app.presentation.main_window.top_bar_builder import build_top_bar_runtime_styles
from calendar_app.presentation.main_window.top_menus.common import (
    refresh_top_menu_icons,
    set_themed_icon,
)
from calendar_app.presentation.main_window.top_menus.display_menu import (
    _update_calendar_visibility_menu,
)
from calendar_app.presentation.theme.style_builder import _build_app_menu_style
from calendar_app.presentation.widgets.ui_components import (
    _hover_info_popup_stylesheet,
    _task_title_label_style,
)
from calendar_app.shared.color_utils import (
    contrast_ratio,
    contrast_safe_color,
    derive_panel_palette,
    derive_ui_palette,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.theme_snapshot import build_theme_snapshot


class _Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value

    def contains(self, key):
        return key in self.values

    def allKeys(self):
        return list(self.values)


class LightThemeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_light_palette_has_surface_hierarchy_and_dark_boundaries(self):
        panel = derive_panel_palette("#fff0f6", 1.0)
        palette = derive_ui_palette("light", "#fff0f6", 1.0, "#d6336c")

        self.assertGreaterEqual(len(set(panel.values())), 5)
        self.assertEqual(palette["border"], "rgba(0,0,0,0.16)")
        self.assertEqual(palette["weekday_other"], palette["text_faint"])
        self.assertEqual(palette["text_secondary"], "#3f4650")
        self.assertEqual(palette["text_muted"], "#68717d")
        content_alpha = int(re.search(r",\s*(\d+)\)$", panel["content_bg"]).group(1))
        floating_alpha = int(re.search(r",\s*(\d+)\)$", panel["floating_bg"]).group(1))
        self.assertGreaterEqual(content_alpha, 220)
        self.assertGreaterEqual(floating_alpha, 248)

        adjusted_yellow = contrast_safe_color("#f6bf26", "#fff0f6", minimum=3.0)
        self.assertGreaterEqual(contrast_ratio(adjusted_yellow, "#fff0f6"), 3.0)

    def test_light_menu_uses_light_surface_and_dark_separator(self):
        settings = _Settings(
            {
                "text_theme": "light",
                "panel_base_color": "#fff0f6",
                "theme_color": "#d6336c",
                "last_opacity": 200,
                "last_opacity_unit": "byte",
            }
        )
        style = _build_app_menu_style(
            10,
            "#d6336c",
            "light",
            panel_base_color="#fff0f6",
            opacity_factor=200 / 255,
            settings=settings,
            persist_opacity=False,
        )

        self.assertIn("background-color: rgba(255,250,252,232)", style)
        self.assertIn("border: 1px solid rgba(0,0,0,0.16)", style)
        self.assertIn("background: rgba(0,0,0,0.10)", style)

    def test_dynamic_calendar_menu_prefers_latest_theme_style(self):
        settings = _Settings(
            {
                "text_theme": "light",
                "panel_base_color": "#fff0f6",
                "theme_color": "#d6336c",
                "last_opacity": 200,
                "last_opacity_unit": "byte",
            }
        )
        owner = SimpleNamespace(settings=settings, _last_menu_style="QMenu { color: #123456; }")
        menu = QMenu()
        self.addCleanup(menu.close)

        with patch(
            "calendar_app.infrastructure.db.calendar_repo.list_calendars",
            return_value=[],
        ):
            _update_calendar_visibility_menu(owner, menu, "QMenu { color: #ffffff; }")

        self.assertEqual(menu.styleSheet(), owner._last_menu_style)

    def test_stale_custom_input_is_scoped_to_custom_mode(self):
        settings = _Settings(
            {
                "text_theme": "light",
                "panel_base_color": "#fff0f6",
                "theme_color": "#d6336c",
                "custom_input_bg": "#000000",
            }
        )
        self.assertEqual(build_theme_snapshot(settings).input_bg, "#ffffff")

        settings.setValue("text_theme", "custom")
        self.assertEqual(build_theme_snapshot(settings).input_bg, "#000000")

    def test_registered_icons_are_rebuilt_for_new_mode_color(self):
        button = QToolButton()
        owner = SimpleNamespace(add_menu_btn=button)

        with patch(
            "calendar_app.presentation.main_window.top_menus.common._ic",
            return_value=QIcon(),
        ) as icon_builder:
            set_themed_icon(button, ICON.ADD, "#f4f7fb")
            refresh_top_menu_icons(
                owner,
                {
                    "neutral": "#101318",
                    "accent": "#d6336c",
                    "warning": "#9a6700",
                    "danger": "#b42318",
                },
            )

        self.assertEqual(icon_builder.call_args_list[-1].kwargs["color"], "#101318")

    def test_calendar_task_and_popup_use_light_reading_tokens(self):
        tokens = {
            "text_primary": "#101318",
            "text_muted": "#68717d",
            "floating_bg": "rgba(255,250,252,248)",
            "bg_alt": "rgba(255,250,252,180)",
            "accent_border": "rgba(214,51,108,0.40)",
            "border": "rgba(0,0,0,0.16)",
        }
        self.assertIn("color: #101318", _task_title_label_style(tokens=tokens))
        popup_style = _hover_info_popup_stylesheet(tokens=tokens)
        self.assertIn("background-color: rgba(255,250,252,248)", popup_style)
        self.assertIn("color: #101318", popup_style)

    def test_top_bar_runtime_styles_refresh_labels_and_controls(self):
        settings = _Settings(
            {
                "text_theme": "light",
                "panel_base_color": "#fff0f6",
                "theme_color": "#d6336c",
                "last_opacity": 200,
                "last_opacity_unit": "byte",
            }
        )
        styles = build_top_bar_runtime_styles(settings, 10, "#d6336c")
        self.assertIn("color: #3f4650", styles["label"])
        self.assertIn("rgba(0,0,0,0.10)", styles["divider"])
        self.assertIn("color: #101318", styles["search"])


if __name__ == "__main__":
    unittest.main()
