# -*- coding: utf-8 -*-
"""Regression checks for issues found by the native visual consistency audit."""

import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
)
from calendar_app.shared.color_utils import composite_color, contrast_ratio, contrasting_text_color
from calendar_app.shared.system_theme import set_runtime_system_text_theme


class DialogThemeConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = QSettings(
            str(Path(temporary.name) / "theme.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("text_theme", "light")
        self.settings.setValue("panel_base_color", "#f3f1fa")
        self.settings.setValue("theme_color", "#f7e64c")

    def test_unrelated_border_override_preserves_readable_selection_roles(self):
        original = get_dialog_theme_tokens(settings=self.settings)
        self.settings.setValue("dialog_token.border_soft", "#ccccdd")
        changed = get_dialog_theme_tokens(settings=self.settings)
        for role in ("tab_text_active", "list_selected_text", "button_primary_text"):
            self.assertEqual(changed[role], original[role], role)

    def test_system_auto_uses_paired_family_surface_and_accent_without_persisting(self):
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
        original = {key: self.settings.value(key) for key in self.settings.allKeys()}
        set_runtime_system_text_theme("light")
        self.addCleanup(set_runtime_system_text_theme, None)
        tokens = get_dialog_theme_tokens(settings=self.settings)
        self.assertEqual(tokens["base_hex"], "#f3f1fa")
        self.assertEqual(tokens["accent"], "#7950b8")
        self.assertIn("#7950b8", build_dialog_stylesheet(settings=self.settings))
        self.assertEqual(
            original, {key: self.settings.value(key) for key in self.settings.allKeys()}
        )

    def test_overridden_accent_preserves_neutral_selection_and_composited_contrast(self):
        self.settings.setValue("dialog_token.accent", "#ffff00")
        tokens = get_dialog_theme_tokens(settings=self.settings)
        surface = composite_color(tokens["floating_bg"], tokens["base_hex"])
        selected_tab = composite_color(tokens["tab_active_bg"], surface)
        self.assertGreaterEqual(contrast_ratio(tokens["tab_text_active"], selected_tab), 4.5)
        self.assertEqual(tokens["list_selected_text"], tokens["text_primary"])

    def test_rgba_and_transparent_primary_text_uses_real_surface(self):
        for mode, base in (("dark", "#121827"), ("light", "#f3f1fa")):
            self.settings.setValue("text_theme", mode)
            self.settings.setValue("panel_base_color", base)
            for background in ("rgba(255,255,0,255)", "rgba(255,255,0,0.20)"):
                with self.subTest(mode=mode, background=background):
                    self.settings.setValue("dialog_token.button_primary_bg", background)
                    tokens = get_dialog_theme_tokens(settings=self.settings)
                    surface = composite_color(tokens["floating_bg"], tokens["base_hex"])
                    actual = composite_color(background, surface)
                    self.assertGreaterEqual(
                        contrast_ratio(tokens["button_primary_text"], actual), 4.5
                    )

    def test_partial_primary_background_updates_omitted_text_and_border(self):
        stylesheet = build_dialog_stylesheet(
            settings=self.settings, tokens={"button_primary_bg": "#ffff00"}
        )
        primary = re.findall(r"QPushButton#primary_btn\s*\{([^}]+)\}", stylesheet)[-1]
        self.assertIn("background-color: #ffff00;", primary)
        self.assertIn("border-color: #ffff00;", primary)
        self.assertIn("color: #101318;", primary)

    def test_explicit_expert_text_override_is_retained(self):
        self.settings.setValue("dialog_token.button_primary_bg", "rgba(255,255,0,255)")
        self.settings.setValue("dialog_token.button_primary_text", "#245588")
        self.assertEqual(
            get_dialog_theme_tokens(settings=self.settings)["button_primary_text"], "#245588"
        )

    def test_all_neutral_accent_levels_have_readable_automatic_text(self):
        for level in range(256):
            color = f"#{level:02x}{level:02x}{level:02x}"
            self.assertGreaterEqual(
                contrast_ratio(contrasting_text_color(color), color), 4.5, color
            )

    def test_base_font_metric_reaches_visible_body_fields_and_buttons(self):
        self.settings.setValue("dialog_token.metric.base_font_pt", 22)
        dialog = QDialog()
        self.addCleanup(dialog.close)
        layout = QVBoxLayout(dialog)
        widgets = (QLabel("내용"), QLineEdit("입력"), QPushButton("저장"))
        title = QLabel("제목")
        title.setProperty("role", "dialogTitle")
        for widget in (*widgets, title):
            layout.addWidget(widget)
        apply_common_dialog_style(dialog, settings=self.settings)
        dialog.show()
        self.app.processEvents()
        self.assertTrue(all(widget.font().pixelSize() == 22 for widget in widgets))
        from calendar_app.shared.theme_snapshot import get_dialog_metric_defaults

        self.assertEqual(
            title.font().pixelSize(), get_dialog_metric_defaults(self.settings)["title_font_pt"]
        )

    def test_dark_alternating_rows_have_mode_aware_palette_and_actual_pixels(self):
        self.settings.setValue("text_theme", "dark")
        self.settings.setValue("panel_base_color", "#121827")
        dialog = QDialog()
        self.addCleanup(dialog.close)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(4, 1)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        for row in range(4):
            table.setItem(row, 0, QTableWidgetItem(f"업무 {row + 1}"))
        layout.addWidget(table)
        apply_common_dialog_style(dialog, settings=self.settings, size=(500, 300))
        dialog.show()
        self.app.processEvents()
        self.assertLess(table.palette().color(QPalette.ColorRole.AlternateBase).lightnessF(), 0.5)
        row_rect = table.visualItemRect(table.item(1, 0))
        actual = (
            table.viewport()
            .grab()
            .toImage()
            .pixelColor(row_rect.right() - 12, row_rect.center().y())
        )
        self.assertLess(actual.lightnessF(), 0.5)
