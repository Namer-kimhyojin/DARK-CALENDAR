# -*- coding: utf-8 -*-
"""Initial modal sizes should honor intent instead of the widest hidden page."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style


class _LargeHiddenPageHint(QDialog):
    def sizeHint(self):
        return QSize(1500, 1100)


class DialogSizePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_deliberate_opening_size_does_not_expand_to_hidden_page_hint(self):
        dialog = _LargeHiddenPageHint()
        self.addCleanup(dialog.close)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("설정"))
        apply_common_dialog_style(dialog)
        dialog.resize(700, 520)
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=(1800, 1000),
        ):
            dialog.show()
            for _ in range(3):
                self.app.processEvents()
        self.assertEqual(dialog.size(), QSize(700, 520))

    def test_preferred_large_modal_opens_with_margin_and_remains_resizable(self):
        dialog = QDialog()
        self.addCleanup(dialog.close)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("스크롤되는 설정"))
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=(1000, 700),
        ):
            apply_common_dialog_style(dialog, size=(1400, 1000))
            dialog.show()
            for _ in range(4):
                self.app.processEvents()
        self.assertLessEqual(dialog.width(), 900)
        self.assertLessEqual(dialog.height(), 616)
        self.assertEqual(dialog.maximumSize(), QSize(1000, 700))
