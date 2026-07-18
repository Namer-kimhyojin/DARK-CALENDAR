import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget


class OverlayTextMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.owner = QWidget()
        self.owner.settings = QSettings("codex_test", "dark_calendar_overlay_text")
        self.owner.settings.clear()
        from calendar_app.infrastructure.i18n import I18nManager

        s = QSettings("kimhyojin", "Dark Calendar")
        self._orig_lang = s.value("language")
        s.setValue("language", "ko")
        I18nManager()._load_translations()

    def tearDown(self):
        self.owner.settings.clear()
        self.owner.close()
        from calendar_app.infrastructure.i18n import I18nManager

        s = QSettings("kimhyojin", "Dark Calendar")
        if self._orig_lang is not None:
            s.setValue("language", self._orig_lang)
        else:
            s.remove("language")
        I18nManager()._load_translations()
        super().tearDown()

    def test_context_menu_has_single_settings_entry(self):
        widget = OverlayTextWidget(self.owner)
        self.addCleanup(widget.close)
        menu = QMenu()

        widget._build_context_menu(menu)

        action_texts = [action.text() for action in menu.actions() if not action.isSeparator()]
        self.assertNotEqual(len(action_texts), 0)
        self.assertNotIn("Template", action_texts)
        self.assertNotIn("TEMPLATE", action_texts)
        self.assertTrue(any("위젯" in text or "Widget" in text for text in action_texts))

    def test_context_menu_settings_action_opens_dialog(self):
        widget = OverlayTextWidget(self.owner)
        self.addCleanup(widget.close)
        menu = QMenu()

        called = []
        widget._open_settings = lambda *args, **kwargs: called.append(True)
        widget._build_context_menu(menu)
        non_separator = [action for action in menu.actions() if not action.isSeparator()]
        self.assertEqual(len(non_separator), 1)
        non_separator[0].trigger()
        self.assertEqual(called, [True])
