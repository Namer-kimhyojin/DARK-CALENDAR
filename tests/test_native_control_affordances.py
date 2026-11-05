# -*- coding: utf-8 -*-
"""Shared numeric controls retain native behavior while showing themed glyphs."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QDialog,
    QDoubleSpinBox,
    QScrollBar,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QVBoxLayout,
)

from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_stylesheet,
)
from calendar_app.presentation.theme.control_styles import _spin_arrow_assets


class NativeControlAffordanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = QSettings(
            str(Path(temporary.name) / "controls.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("text_theme", "dark")
        self.settings.setValue("panel_base_color", "#121827")
        self.settings.setValue("theme_color", "#c5a3f5")
        self.dialog = QDialog()
        self.addCleanup(self.dialog.close)
        self.layout = QVBoxLayout(self.dialog)

    def _show(self):
        apply_common_dialog_style(self.dialog, settings=self.settings, size=(360, 180))
        self.dialog.show()
        self.app.processEvents()

    @staticmethod
    def _step_rect(spin, control):
        option = QStyleOptionSpinBox()
        spin.initStyleOption(option)
        return spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, spin)

    def test_integer_and_decimal_fields_have_same_height_and_visible_library_assets(self):
        integer = QSpinBox()
        decimal = QDoubleSpinBox()
        self.layout.addWidget(integer)
        self.layout.addWidget(decimal)
        self._show()
        self.assertEqual(integer.height(), decimal.height())
        self.assertEqual(integer.font().pixelSize(), decimal.font().pixelSize())
        for mode, base in (("dark", "#121827"), ("light", "#f3f1fa")):
            with self.subTest(mode=mode):
                self.settings.setValue("text_theme", mode)
                self.settings.setValue("panel_base_color", base)
                apply_common_dialog_style(
                    self.dialog, settings=self.settings, keep_existing_stylesheet=False
                )
                self.app.processEvents()
                assets = _spin_arrow_assets("#eef3ff" if mode == "dark" else "#202634")
                self.assertIsNotNone(assets)
                for asset in assets:
                    raster = QImage(asset)
                    self.assertFalse(raster.isNull())
                    self.assertTrue(
                        any(
                            raster.pixelColor(x, y).alpha()
                            for x in range(raster.width())
                            for y in range(raster.height())
                        )
                    )

    def test_mouse_keyboard_hold_and_limits_keep_native_integer_steps(self):
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(10)
        self.layout.addWidget(spin)
        self._show()
        up = self._step_rect(spin, QStyle.SubControl.SC_SpinBoxUp)
        down = self._step_rect(spin, QStyle.SubControl.SC_SpinBoxDown)
        self.assertGreaterEqual(up.width(), 24)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        self.assertEqual(spin.value(), 11)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=down.center())
        self.assertEqual(spin.value(), 10)
        QTest.keyClick(spin, Qt.Key.Key_Up)
        self.assertEqual(spin.value(), 11)
        QTest.mousePress(spin, Qt.MouseButton.LeftButton, pos=up.center())
        QTest.qWait(800)
        QTest.mouseRelease(spin, Qt.MouseButton.LeftButton, pos=up.center())
        self.assertGreater(spin.value(), 12)
        spin.setValue(100)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        self.assertEqual(spin.value(), 100)
        spin.setValue(0)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=down.center())
        self.assertEqual(spin.value(), 0)

    def test_decimal_direct_entry_read_only_and_hidden_buttons_remain_native(self):
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.25)
        spin.setValue(1.5)
        self.layout.addWidget(spin)
        self._show()
        spin.setFocus()
        spin.selectAll()
        QTest.keyClicks(spin, "42.25")
        QTest.keyClick(spin, Qt.Key.Key_Return)
        self.assertEqual(spin.value(), 42.25)
        QTest.keyClick(spin, Qt.Key.Key_Up)
        self.assertEqual(spin.value(), 42.5)
        spin.setReadOnly(True)
        up = self._step_rect(spin, QStyle.SubControl.SC_SpinBoxUp)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        self.assertEqual(spin.value(), 42.5)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        option = QStyleOptionSpinBox()
        spin.initStyleOption(option)
        self.assertFalse(option.subControls & QStyle.SubControl.SC_SpinBoxUp)
        self.assertFalse(option.subControls & QStyle.SubControl.SC_SpinBoxDown)

    def test_native_spin_buttons_mirror_for_rtl_without_changing_step_direction(self):
        spin = QSpinBox()
        spin.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        spin.setValue(5)
        self.layout.addWidget(spin)
        self._show()
        up = self._step_rect(spin, QStyle.SubControl.SC_SpinBoxUp)
        self.assertLess(up.center().x(), spin.width() // 2)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        self.assertEqual(spin.value(), 6)

    def test_scrollbar_pages_have_no_native_pattern_brush(self):
        scrollbar = QScrollBar(Qt.Orientation.Vertical)
        scrollbar.setRange(0, 1000)
        scrollbar.setPageStep(10)
        self.layout.addWidget(scrollbar)
        self._show()
        stylesheet = build_dialog_stylesheet(settings=self.settings)
        self.assertIn("QScrollBar::add-page:vertical", stylesheet)
        self.assertIn("QScrollBar::sub-page:horizontal", stylesheet)
        image = scrollbar.grab().toImage()
        # Inspect the page well below the thumb, away from rounded edges.
        column = scrollbar.width() // 2
        colors = {
            image.pixelColor(column, row).rgba()
            for row in range(image.height() // 2, image.height() - 8)
        }
        self.assertEqual(len(colors), 1)


if __name__ == "__main__":
    unittest.main()
