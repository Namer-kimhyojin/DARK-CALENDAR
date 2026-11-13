# -*- coding: utf-8 -*-
"""Focus-history theme updates preserve the displayed data and selection."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QWidget

from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.focus_history_panel import FocusHistoryPanel
from calendar_app.presentation.dialogs.focus_log_dialog import FocusLogDialog
from calendar_app.shared.system_theme import set_runtime_system_text_theme


class FocusLogThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(
            str(Path(self.temp.name) / "focus.ini"), QSettings.Format.IniFormat
        )
        for key, value in {
            "text_theme": "auto",
            "panel_base_color": "#121827",
            "theme_color": "#c5a3f5",
            "appearance_style_family": "navy_lilac",
            "appearance_accent_source": "family",
            "appearance_family_dark_base": "#121827",
            "appearance_family_dark_accent": "#c5a3f5",
            "appearance_family_light_base": "#f3f1fa",
            "appearance_family_light_accent": "#7950b8",
        }.items():
            self.settings.setValue(key, value)
        set_runtime_system_text_theme("dark")
        self.addCleanup(set_runtime_system_text_theme, None)
        self.parent = QWidget()
        self.parent.settings = self.settings
        self.addCleanup(self.parent.close)

    def _dialog(self):
        with patch.object(FocusLogDialog, "_load_logs"):
            dialog = FocusLogDialog(self.parent)
        self.addCleanup(dialog.close)
        return dialog

    def test_system_change_updates_visible_dialog_without_reloading_or_changing_rows(self):
        dialog = self._dialog()
        dialog.table.setRowCount(1)
        record = QTableWidgetItem("기존 집중 기록")
        record.setData(Qt.ItemDataRole.UserRole, 42)
        dialog.table.setItem(0, 0, record)
        dialog.table.selectRow(0)
        dialog.show()
        self.app.processEvents()
        before_values = {key: self.settings.value(key) for key in self.settings.allKeys()}
        set_runtime_system_text_theme("light")
        with patch.object(dialog.history_panel, "reload") as reload_mock:
            dialog.handle_system_theme_change("light")
        self.app.processEvents()
        self.assertEqual(dialog._ui_tokens["base_hex"], "#f3f1fa")
        self.assertEqual(dialog._ui_tokens["accent"], "#7950b8")
        self.assertIs(dialog.table.item(0, 0), record)
        self.assertEqual(record.data(Qt.ItemDataRole.UserRole), 42)
        self.assertTrue(record.isSelected())
        self.assertTrue(all(button.property("dialogFooter") for button in dialog._footer_buttons))
        self.assertTrue(all(button.height() >= 44 for button in dialog._footer_buttons))
        self.assertTrue(all(not button.styleSheet() for button in dialog._footer_buttons))
        reload_mock.assert_not_called()
        self.assertEqual(
            before_values, {key: self.settings.value(key) for key in self.settings.allKeys()}
        )

    def test_explicit_dark_mode_does_not_restyle_on_system_light_event(self):
        self.settings.setValue("text_theme", "dark")
        dialog = self._dialog()
        original = dialog.styleSheet()
        set_runtime_system_text_theme("light")
        dialog.handle_system_theme_change("light")
        self.assertEqual(dialog.styleSheet(), original)

    def test_history_panel_style_refresh_preserves_selection_and_control_roles(self):
        panel = FocusHistoryPanel()
        self.addCleanup(panel.close)
        panel.table.setRowCount(1)
        item = QTableWidgetItem("유지할 기록")
        panel.table.setItem(0, 0, item)
        panel.table.selectRow(0)
        set_runtime_system_text_theme("light")
        tokens = get_dialog_theme_tokens(settings=self.settings)
        metrics = get_dialog_metric_tokens(settings=self.settings)
        with patch.object(panel, "reload") as reload_mock:
            panel.apply_theme(tokens, metrics)
        self.assertIs(panel.table.item(0, 0), item)
        self.assertTrue(item.isSelected())
        self.assertEqual(panel.delete_button.objectName(), "danger_btn")
        self.assertEqual(panel.refresh_button.objectName(), "ghost_btn")
        self.assertIn(tokens["surface_item"], panel.table.styleSheet())
        reload_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
