# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QVBoxLayout, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime import system_manager
from calendar_app.presentation.main_window.top_menus.common import set_themed_icon
from calendar_app.presentation.main_window.top_menus.system_menu import build_system_menu
from calendar_app.shared.icon_map import strip_leading_emoji


class FakeSettings:
    def __init__(self):
        self._values = {"language": "ko"}

    def value(self, key, default=None, type=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value

    def sync(self):
        pass


class MockApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = FakeSettings()
        # Mock methods that build_system_menu might call
        self.open_font_settings_dialog = lambda: None
        self.open_label_settings_dialog = lambda: None
        self.open_away_settings_dialog = lambda: None
        self.open_panel_background_color_dialog = lambda: None
        self.open_gcal_settings_dialog = lambda: None
        self.open_gcal_sync_issues_dialog = lambda: None
        self.toggle_autostart = lambda: None
        self.show_shortcut_guide = lambda: None
        self.request_app_exit = lambda: None
        self.open_locale_override_folder = lambda: None
        self.open_current_locale_file = lambda: None
        self.validate_current_locale_override = lambda: None
        self.reset_current_locale_override = lambda: None

        # This button is used for style copying in system_menu.py
        self.add_menu_btn = QWidget()
        self.add_menu_btn.setStyleSheet("")


class TestSystemMenu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_autostart_is_at_top_of_system_menu(self):
        host = MockApp()
        layout = QVBoxLayout()
        # build_system_menu(self, top_bar, menu_style)
        build_system_menu(host, layout, "")

        menu = host.sys_menu
        actions = menu.actions()

        # The first action should be the autostart action
        # Check if it's the right action by looking at its text or connection
        first_action = actions[0]

        # Based on system_menu.py:
        # self.autostart_act = QAction(t("menu.autostart"), self)
        # ...
        # self.sys_menu.addAction(self.autostart_act)

        self.assertEqual(
            first_action,
            host.autostart_act,
            "Autostart action should be the first item in the menu",
        )

        # Second item should be a separator
        self.assertTrue(actions[1].isSeparator(), "A separator should follow the autostart action")

    def test_system_menu_exposes_source_and_open_source_license(self):
        host = MockApp()
        layout = QVBoxLayout()
        build_system_menu(host, layout, "")

        action_texts = [action.text() for action in host.sys_menu.actions()]
        self.assertIn(t("menu.open_source_info", "오픈소스 정보"), action_texts)

        open_source_texts = [action.text() for action in host.open_source_menu.actions()]
        self.assertIn(t("menu.release_source_code", "이 버전의 GitHub 소스"), open_source_texts)
        self.assertIn(t("menu.open_source_license", "GPLv3 오픈소스 라이선스"), open_source_texts)

    def test_exit_icon_uses_the_same_neutral_color_role_as_other_menu_icons(self):
        host = MockApp()
        host._tb_icon_color = "#4a8bc2"
        layout = QVBoxLayout()
        with patch(
            "calendar_app.presentation.main_window.top_menus.system_menu.set_themed_icon",
            wraps=set_themed_icon,
        ) as icon_setter:
            build_system_menu(host, layout, "")

        exit_action = next(
            action for action in reversed(host.sys_menu.actions()) if not action.isSeparator()
        )

        self.assertEqual(exit_action.text(), strip_leading_emoji(t("menu.exit")))
        self.assertEqual(exit_action.property("_theme_icon_role"), "neutral")
        exit_icon_call = next(
            call for call in icon_setter.call_args_list if call.args[0] is exit_action
        )
        self.assertEqual(exit_icon_call.args[2], host._tb_icon_color)
        self.assertEqual(exit_icon_call.kwargs.get("role", "neutral"), "neutral")


if __name__ == "__main__":
    unittest.main()
