# -*- coding: utf-8 -*-
"""Routine editor surface and footer regressions from native Windows evidence."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QSettings
from PyQt6.QtWidgets import QApplication, QPushButton, QScrollArea, QWidget

from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class RoutineEditorSurfaceTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.host = QWidget()
        self.addCleanup(self.host.close)
        self.host.settings = QSettings(
            str(Path(temporary.name) / "routine-theme.ini"), QSettings.Format.IniFormat
        )
        for key, value in {
            "text_theme": "dark",
            "theme_color": "#6ca7ff",
            "panel_base_color": "#101820",
            "last_opacity": 255,
            "dialog_token.tab_active_bg": "rgba(20,110,190,200)",
        }.items():
            self.host.settings.setValue(key, value)

    def _dialog(self):
        dialog = UnifiedTaskDialog(
            task_type="routine", parent=self.host, initial_date=QDate(2026, 11, 5)
        )
        self.addCleanup(dialog.close)
        dialog.show()
        for _ in range(3):
            self.app.processEvents()
        return dialog

    def test_editor_surface_uses_owner_reading_color_not_selection_fill(self):
        dialog = self._dialog()
        expected = get_dialog_theme_tokens(settings=self.host.settings)
        self.assertEqual(dialog._ui_tokens()["accent"], "#6ca7ff")
        self.assertEqual(dialog._ui_tokens()["floating_bg"], expected["floating_bg"])
        pane_start = dialog.styleSheet().index(
            "QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs::pane"
        )
        pane = dialog.styleSheet()[pane_start:].split("}", 1)[0]
        self.assertIn(f"background: {expected['floating_bg']};", pane)
        self.assertNotIn("rgba(20,110,190,200)", pane)
        selected_tab = dialog.styleSheet().split(
            "QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs QTabBar::tab:selected", 1
        )[1].split("}", 1)[0]
        self.assertIn(f"background: {expected['tab_active_bg']};", selected_tab)

    def test_each_tab_explicitly_keeps_viewport_and_content_transparent(self):
        dialog = self._dialog()
        self.assertEqual(dialog.tabs.count(), 3)
        for index in range(dialog.tabs.count()):
            with self.subTest(tab=index):
                dialog.tabs.setCurrentIndex(index)
                self.app.processEvents()
                scroll = dialog.tabs.widget(index)
                self.assertIsInstance(scroll, QScrollArea)
                self.assertFalse(scroll.viewport().autoFillBackground())
                self.assertFalse(scroll.widget().autoFillBackground())

    def test_routine_footer_has_one_consistent_height_and_visible_full_labels(self):
        dialog = self._dialog()
        buttons = [button for button in dialog.findChildren(QPushButton) if button.property("dialogFooter")]
        self.assertEqual(len(buttons), 4)
        self.assertEqual(len({button.height() for button in buttons}), 1)
        for button in buttons:
            with self.subTest(label=button.text()):
                self.assertGreaterEqual(button.height(), 44)
                self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()))
                self.assertTrue(button.isVisible())
