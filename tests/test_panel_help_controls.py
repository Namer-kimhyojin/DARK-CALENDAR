# -*- coding: utf-8 -*-
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit, QMainWindow, QPushButton, QWidget
from scripts.i18n_sync import flatten_locale, load_locale

from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin
from calendar_app.presentation.panels.side_panel_renderer import DockTitleBar, _panel_empty_items

ROOT = Path(__file__).resolve().parents[1]


class _DialogHost(DialogActionsMixin, QMainWindow):
    pass


class _FakeMessageBox:
    instances = []

    def __init__(self, *args, **kwargs):
        self._title = ""
        self._text = ""
        self._format = None
        _FakeMessageBox.instances.append(self)

    def setWindowTitle(self, title):
        self._title = title

    def windowTitle(self):
        return self._title

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setTextFormat(self, text_format):
        self._format = text_format

    def exec(self):
        return 0


def _bundled_locales():
    """Flat translations of every bundled locale file."""
    return {
        path.stem: flatten_locale(load_locale(path))
        for path in sorted((ROOT / "locales").glob("*.json"))
    }


def _render_panel_help(flat, panel_name):
    """Open the panel help with t() backed by one locale's strings; return (titles, text)."""

    def locale_t(key, default=None, **kwargs):
        value = flat.get(key, default if default is not None else key)
        return value.format(**kwargs) if isinstance(value, str) and kwargs else value

    host = _DialogHost()
    _FakeMessageBox.instances.clear()
    try:
        with (
            patch("calendar_app.presentation.dialogs.dialog_router.QMessageBox", _FakeMessageBox),
            patch("calendar_app.presentation.dialogs.dialog_router.t", side_effect=locale_t),
        ):
            host.show_panel_shortcut_help(panel_name)
    finally:
        host.close()
    return [box.windowTitle() for box in _FakeMessageBox.instances], (
        _FakeMessageBox.instances[0].text() if _FakeMessageBox.instances else ""
    )


class PanelHelpControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dock_title_bar_hides_panel_help_button(self):
        title_bar = DockTitleBar("Routine", help_handler=lambda: None)
        self.addCleanup(title_bar.close)

        help_buttons = [btn for btn in title_bar.findChildren(QPushButton) if btn.text() == "?"]

        self.assertEqual([], help_buttons)

    def test_dock_title_bar_uses_accessible_toolbar_button_size(self):
        title_bar = DockTitleBar(
            "Schedule",
            add_handler=lambda: None,
            manage_handler=lambda: None,
        )
        self.addCleanup(title_bar.close)

        buttons = title_bar.findChildren(QPushButton)
        self.assertEqual(2, len(buttons))
        self.assertTrue(all(btn.width() == 28 and btn.height() == 28 for btn in buttons))
        self.assertTrue(all(btn.accessibleName() for btn in buttons))

    def test_panel_empty_state_offers_primary_action(self):
        host = QWidget()
        self.addCleanup(host.close)
        calls = []

        items = _panel_empty_items(
            host,
            "No schedules yet.",
            "Create schedule",
            lambda: calls.append("create"),
        )

        self.assertEqual(1, len(items))
        action = items[0].findChild(QPushButton, "panel_empty_action")
        self.assertIsNotNone(action)
        self.assertGreaterEqual(action.minimumHeight(), 32)
        stylesheet = items[0].styleSheet()
        self.assertIn(
            "QFrame#panel_empty_state {\n            background: transparent;", stylesheet
        )
        self.assertIn("QPushButton#panel_empty_action {\n            color:", stylesheet)
        self.assertIn("background: transparent;", stylesheet)
        self.assertNotIn("background: rgba(255,255,255", stylesheet)
        self.assertIn("font-weight: 500", stylesheet)
        action.click()
        self.assertEqual(["create"], calls)

    def test_search_empty_state_clears_the_current_query(self):
        host = QWidget()
        host.search_edit = QLineEdit(host)
        host.search_edit.setText("quarterly review")
        self.addCleanup(host.close)

        items = _panel_empty_items(
            host,
            "No schedules yet.",
            "Create schedule",
            lambda: None,
            search_query=host.search_edit.text(),
        )

        action = items[0].findChild(QPushButton, "panel_empty_action")
        self.assertIsNotNone(action)
        action.click()
        self.assertEqual("", host.search_edit.text())

    def test_panel_shortcut_help_dialog_lists_quick_recovery_shortcuts(self):
        host = _DialogHost()
        self.addCleanup(host.close)
        _FakeMessageBox.instances.clear()

        def fake_t(key, default=None, **kwargs):
            translations = {
                "panel.help.title": "{panel} 단축키",
                "panel.help.quick_title": "{panel} 빠른 도움말",
                "panel.help.recovery_intro": "메뉴바가 보이지 않을 때 빠르게 복구하는 단축키",
                "panel.help.magnet": "{key}: 자석모드 활성화/비활성화",
                "panel.help.topbar": "{key}: 상단바 표시/숨김",
                "panel.help.lock": "{key}: 고정모드 활성화/비활성화",
            }
            value = translations.get(key, default if default is not None else key)
            return value.format(**kwargs) if isinstance(value, str) and kwargs else value

        with (
            patch("calendar_app.presentation.dialogs.dialog_router.QMessageBox", _FakeMessageBox),
            patch("calendar_app.presentation.dialogs.dialog_router.t", side_effect=fake_t),
        ):
            host.show_panel_shortcut_help("Routine Tasks")

        self.assertEqual(1, len(_FakeMessageBox.instances))
        self.assertEqual("Routine Tasks 단축키", _FakeMessageBox.instances[0].windowTitle())
        text = _FakeMessageBox.instances[0].text()
        self.assertIn("Routine Tasks 빠른 도움말", text)
        self.assertIn(f"<b>{get_key('magnet_mode')}</b>: 자석모드 활성화/비활성화", text)
        self.assertIn(f"<b>{get_key('topbar')}</b>: 상단바 표시/숨김", text)
        self.assertIn(f"<b>{get_key('lock_mode')}</b>: 고정모드 활성화/비활성화", text)
        self.assertNotIn("{", text)

    def test_panel_shortcut_help_formats_title_and_rows_from_every_locale(self):
        # t() only formats when given keyword arguments, so this stand-in does the same:
        # a call that forgets panel= or key= leaves the braces in the dialog.
        for code, flat in _bundled_locales().items():
            with self.subTest(locale=code):
                titles, text = _render_panel_help(flat, "Routine Tasks")
                self.assertEqual(1, len(titles))
                self.assertIn("Routine Tasks", titles[0])
                self.assertNotIn("{", titles[0] + text)
                self.assertNotIn("}", titles[0] + text)
                for shortcut_id in ("magnet_mode", "topbar", "lock_mode"):
                    self.assertIn(f"<b>{get_key(shortcut_id)}</b>", text)

    def test_panel_shortcut_help_through_the_real_translator(self):
        host = _DialogHost()
        self.addCleanup(host.close)
        _FakeMessageBox.instances.clear()

        with patch("calendar_app.presentation.dialogs.dialog_router.QMessageBox", _FakeMessageBox):
            host.show_panel_shortcut_help("Routine Tasks")

        title = _FakeMessageBox.instances[0].windowTitle()
        text = _FakeMessageBox.instances[0].text()
        self.assertIn("Routine Tasks", title)
        self.assertNotIn("{", title + text)
        for shortcut_id in ("magnet_mode", "topbar", "lock_mode"):
            self.assertIn(f"<b>{get_key(shortcut_id)}</b>", text)

    def test_panel_shortcut_help_without_name_uses_default_panel_name(self):
        flat = _bundled_locales()["ko"]

        titles, _text = _render_panel_help(flat, "")

        self.assertEqual(["패널 단축키"], titles)

    def test_panel_shortcut_help_english_title_spaces_the_panel_name(self):
        titles, text = _render_panel_help(_bundled_locales()["en"], "Routine Tasks")

        self.assertEqual(["Routine Tasks shortcuts"], titles)
        self.assertIn(f"<b>{get_key('magnet_mode')}</b>: toggle magnet mode", text)

    def test_calendar_help_includes_quick_recovery_shortcuts(self):
        host = _DialogHost()
        self.addCleanup(host.close)
        _FakeMessageBox.instances.clear()

        def fake_t(key, default=None, **kwargs):
            translations = {
                "help.title": "캘린더 사용 안내",
                "help.content": "<h3>캘린더 사용 안내</h3><p>날짜를 더블클릭해 일정을 추가하세요.</p>",
                "panel.main_calendar": "메인 캘린더",
                "panel.help.quick_title": "{panel} 빠른 도움말",
                "panel.help.recovery_intro": "메뉴바가 보이지 않을 때 빠르게 복구하는 단축키",
                "panel.help.magnet": "{key}: 자석모드 활성화/비활성화",
                "panel.help.topbar": "{key}: 상단바 표시/숨김",
                "panel.help.lock": "{key}: 고정모드 활성화/비활성화",
            }
            value = translations.get(key, default if default is not None else key)
            return value.format(**kwargs) if isinstance(value, str) and kwargs else value

        with (
            patch("calendar_app.presentation.dialogs.dialog_router.QMessageBox", _FakeMessageBox),
            patch("calendar_app.presentation.dialogs.dialog_router.t", side_effect=fake_t),
        ):
            host.show_calendar_help()

        self.assertEqual(1, len(_FakeMessageBox.instances))
        self.assertEqual("캘린더 사용 안내", _FakeMessageBox.instances[0].windowTitle())
        text = _FakeMessageBox.instances[0].text()
        self.assertIn("메인 캘린더 빠른 도움말", text)
        self.assertIn(get_key("magnet_mode"), text)
        self.assertIn(get_key("topbar"), text)
        self.assertIn(get_key("lock_mode"), text)
        self.assertIn("캘린더 사용 안내", text)


if __name__ == "__main__":
    unittest.main()
