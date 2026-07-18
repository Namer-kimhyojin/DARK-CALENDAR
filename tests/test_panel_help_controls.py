import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton

from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin
from calendar_app.presentation.panels.side_panel_renderer import DockTitleBar


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


class PanelHelpControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dock_title_bar_hides_panel_help_button(self):
        title_bar = DockTitleBar("Routine", help_handler=lambda: None)
        self.addCleanup(title_bar.close)

        help_buttons = [btn for btn in title_bar.findChildren(QPushButton) if btn.text() == "?"]

        self.assertEqual([], help_buttons)

    def test_dock_title_bar_uses_compact_toolbar_button_size(self):
        title_bar = DockTitleBar(
            "Schedule",
            add_handler=lambda: None,
            manage_handler=lambda: None,
        )
        self.addCleanup(title_bar.close)

        buttons = title_bar.findChildren(QPushButton)
        self.assertEqual(2, len(buttons))
        self.assertTrue(all(btn.width() == 20 and btn.height() == 20 for btn in buttons))

    def test_panel_shortcut_help_dialog_lists_quick_recovery_shortcuts(self):
        host = _DialogHost()
        self.addCleanup(host.close)
        _FakeMessageBox.instances.clear()

        def fake_t(key, default=None, **kwargs):
            translations = {
                "panel.help.title": "패널 도움말",
                "panel.help.quick_title": "{panel} 빠른 도움말",
                "panel.help.recovery_intro": "메뉴바가 보이지 않을 때 빠르게 복구하는 단축키",
                "panel.help.magnet": "자석모드 활성화/비활성화",
                "panel.help.topbar": "메뉴바 보이기/숨기기",
                "panel.help.lock": "고정모드 활성화/비활성화",
            }
            value = translations.get(key, default if default is not None else key)
            return value.format(**kwargs) if isinstance(value, str) and kwargs else value

        with (
            patch("calendar_app.presentation.dialogs.dialog_router.QMessageBox", _FakeMessageBox),
            patch("calendar_app.presentation.dialogs.dialog_router.t", side_effect=fake_t),
        ):
            host.show_panel_shortcut_help("Routine Tasks")

        self.assertEqual(1, len(_FakeMessageBox.instances))
        self.assertEqual("패널 도움말", _FakeMessageBox.instances[0].windowTitle())
        text = _FakeMessageBox.instances[0].text()
        self.assertIn("Routine Tasks 빠른 도움말", text)
        self.assertIn(get_key("magnet_mode"), text)
        self.assertIn(get_key("topbar"), text)
        self.assertIn(get_key("lock_mode"), text)
        self.assertIn("자석모드 활성화/비활성화", text)
        self.assertIn("메뉴바 보이기/숨기기", text)
        self.assertIn("고정모드 활성화/비활성화", text)

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
                "panel.help.magnet": "자석모드 활성화/비활성화",
                "panel.help.topbar": "메뉴바 보이기/숨기기",
                "panel.help.lock": "고정모드 활성화/비활성화",
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
