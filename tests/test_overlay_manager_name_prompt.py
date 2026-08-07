# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QLineEdit, QWidget

from calendar_app.presentation.widgets.overlay_manager import (
    OverlayWidgetManager,
    _prompt_widget_name,
    widget_type_label,
)


class OverlayManagerNamePromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_widget_type_label_removes_leading_symbol(self):
        with patch(
            "calendar_app.presentation.widgets.overlay_manager.t",
            return_value="🕐 디지털 시계",
        ):
            self.assertEqual("디지털 시계", widget_type_label("clock"))

    def test_name_prompt_is_wide_and_removes_title_and_name_symbols(self):
        parent = QWidget()
        self.addCleanup(parent.close)
        captured = {}

        def reject(dialog):
            captured["dialog"] = dialog
            return QDialog.DialogCode.Rejected

        with patch.object(QInputDialog, "exec", reject):
            text, accepted = _prompt_widget_name(
                parent,
                "🕐 디지털 시계 추가",
                "위젯 이름:",
                "🕐 디지털 시계 2",
            )

        dialog = captured["dialog"]
        self.addCleanup(dialog.close)
        name_edit = dialog.findChild(QLineEdit)

        self.assertFalse(accepted)
        self.assertEqual("디지털 시계 추가", dialog.windowTitle())
        self.assertEqual("디지털 시계 2", text)
        self.assertGreaterEqual(dialog.minimumWidth(), 380)
        self.assertIsNotNone(name_edit)
        self.assertGreaterEqual(name_edit.minimumWidth(), 324)

    def test_add_prompt_receives_clean_default_name(self):
        manager = object.__new__(OverlayWidgetManager)
        manager._owner = QWidget()
        manager._meta = {
            "clock_0": {"type": "clock"},
        }
        self.addCleanup(manager._owner.close)

        with (
            patch(
                "calendar_app.presentation.widgets.overlay_manager.widget_type_label",
                return_value="디지털 시계",
            ),
            patch(
                "calendar_app.presentation.widgets.overlay_manager._prompt_widget_name",
                return_value=("", False),
            ) as prompt,
        ):
            manager._ui_add_instance("clock")

        title = prompt.call_args.args[1]
        default_name = prompt.call_args.args[3]
        self.assertNotIn("🕐", title)
        self.assertEqual("디지털 시계 2", default_name)


if __name__ == "__main__":
    unittest.main()
