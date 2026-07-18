import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QComboBox, QMessageBox

from calendar_app.presentation.widgets import overlay_preset_ui_service as ui


class OverlayPresetUiServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_prompt_preset_name_returns_trimmed_value(self):
        with patch.object(ui.QInputDialog, "getText", return_value=("  Name  ", True)):
            self.assertEqual(ui.prompt_preset_name(None), "Name")

    def test_prompt_preset_name_returns_none_on_cancel_or_blank(self):
        with patch.object(ui.QInputDialog, "getText", return_value=("ignored", False)):
            self.assertIsNone(ui.prompt_preset_name(None))
        with patch.object(ui.QInputDialog, "getText", return_value=("   ", True)):
            self.assertIsNone(ui.prompt_preset_name(None))

    def test_require_non_empty_template_returns_trimmed_text(self):
        self.assertEqual(ui.require_non_empty_template(None, "  abc  "), "abc")

    def test_require_non_empty_template_warns_when_empty(self):
        with patch.object(ui, "warn_preset") as warn:
            self.assertIsNone(ui.require_non_empty_template(None, "   "))
            warn.assert_called_once()

    def test_prompt_new_preset_payload(self):
        with (
            patch.object(ui, "require_non_empty_template", return_value="tmpl"),
            patch.object(ui, "prompt_preset_name", return_value="N"),
        ):
            self.assertEqual(ui.prompt_new_preset_payload(None, "x"), ("N", "tmpl"))

    def test_confirm_delete_preset(self):
        with patch.object(
            ui.QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            self.assertTrue(ui.confirm_delete_preset(None, "A"))
        with patch.object(
            ui.QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.No,
        ):
            self.assertFalse(ui.confirm_delete_preset(None, "A"))

    def test_append_row_entries_sets_display_and_roles(self):
        combo = QComboBox()
        entries = [
            {"name": "Built", "template": "tmpl-b", "kind": "builtin"},
            {"name": "User", "template": "tmpl-u", "kind": "user"},
        ]

        ui.append_row_entries(
            combo,
            entries,
            builtin_label="Built-in",
            user_label="User",
        )

        self.assertEqual(combo.count(), 2)
        self.assertEqual(combo.itemText(0), "Built  [Built-in]")
        self.assertEqual(combo.itemData(0, Qt.ItemDataRole.UserRole), "tmpl-b")
        self.assertEqual(combo.itemData(0, Qt.ItemDataRole.UserRole + 1), "builtin")
        self.assertEqual(combo.itemData(0, Qt.ItemDataRole.UserRole + 2), "Built")
        self.assertEqual(combo.itemText(1), "User  [User]")
        self.assertEqual(combo.itemData(1, Qt.ItemDataRole.UserRole), "tmpl-u")
        self.assertEqual(combo.itemData(1, Qt.ItemDataRole.UserRole + 1), "user")
        self.assertEqual(combo.itemData(1, Qt.ItemDataRole.UserRole + 2), "User")

    def test_add_manager_placeholder_sets_roles(self):
        combo = QComboBox()
        ui.add_manager_placeholder(combo, "Select")

        self.assertEqual(combo.count(), 1)
        self.assertEqual(combo.itemText(0), "Select")
        self.assertEqual(combo.itemData(0, Qt.ItemDataRole.UserRole + 1), "")
        self.assertEqual(combo.itemData(0, Qt.ItemDataRole.UserRole + 2), "")
        self.assertEqual(combo.itemData(0, Qt.ItemDataRole.UserRole + 3), "placeholder")

    def test_append_manager_entries_sets_roles_and_returns_lookup(self):
        combo = QComboBox()
        ui.add_manager_placeholder(combo, "Select")
        entries = [
            {"name": "Built", "template": "tmpl-b", "kind": "builtin"},
            {"name": "User", "template": "tmpl-u", "kind": "user"},
        ]

        combo_entries = ui.append_manager_entries(combo, entries)

        self.assertEqual(
            combo_entries,
            [
                {"name": "", "kind": "placeholder"},
                {"name": "Built", "kind": "builtin"},
                {"name": "User", "kind": "user"},
            ],
        )
        self.assertEqual(combo.count(), 3)
        self.assertEqual(combo.itemText(1), "Built")
        self.assertEqual(combo.itemData(1, Qt.ItemDataRole.UserRole + 1), "Built")
        self.assertEqual(combo.itemData(1, Qt.ItemDataRole.UserRole + 2), "tmpl-b")
        self.assertEqual(combo.itemData(1, Qt.ItemDataRole.UserRole + 3), "builtin")
        self.assertEqual(combo.itemText(2), "User")
        self.assertEqual(combo.itemData(2, Qt.ItemDataRole.UserRole + 1), "User")
        self.assertEqual(combo.itemData(2, Qt.ItemDataRole.UserRole + 2), "tmpl-u")
        self.assertEqual(combo.itemData(2, Qt.ItemDataRole.UserRole + 3), "user")

    def test_find_manager_template_index(self):
        combo = QComboBox()
        ui.add_manager_placeholder(combo, "Select")
        ui.append_manager_entries(
            combo,
            [{"name": "Built", "template": "tmpl-b", "kind": "builtin"}],
        )

        self.assertEqual(ui.find_manager_template_index(combo, "tmpl-b"), 1)
        self.assertEqual(ui.find_manager_template_index(combo, "missing"), -1)


if __name__ == "__main__":
    unittest.main()
