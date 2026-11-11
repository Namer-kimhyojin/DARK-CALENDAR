# -*- coding: utf-8 -*-
"""Readability's text opacity: shown in the dialog, honest contrast, applied app-wide."""

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog
from calendar_app.shared.color_utils import MIN_TEXT_OPACITY, contrast_ratio, faded_text_color
from calendar_app.shared.theme_snapshot import build_shared_ui_tokens, build_theme_snapshot


@pytest.fixture(scope="module", autouse=True)
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    cfg = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    cfg.setValue("panel_base_color", "#0d1b2e")
    cfg.setValue("theme_color", "#4da6ff")
    cfg.setValue("text_theme", "dark")
    return cfg


def test_faded_text_is_an_opaque_blend_toward_the_background():
    assert faded_text_color("#ffffff", "#000000", 1.0) == "#ffffff"
    assert faded_text_color("#ffffff", "#000000", 0.5) == "#808080"
    assert faded_text_color("rgba(255,255,255,0.5)", "#000000", 1.0) == "#808080"


def test_text_opacity_applies_to_every_text_role_and_never_below_the_floor(settings):
    full = build_theme_snapshot(settings)
    assert full.text_opacity == 255

    settings.setValue("text_opacity", 153)
    faded = build_theme_snapshot(settings)
    assert faded.text_opacity == 153
    for key in ("text_primary", "text_secondary", "text_muted", "text_faint"):
        expected = faded_text_color(full.text_palette[key], "#0d1b2e", 153 / 255)
        assert faded.text_palette[key] == expected
        assert QColor(faded.text_palette[key]).isValid()
    tokens = build_shared_ui_tokens(settings, snapshot=faded)
    assert tokens["text_primary"] == faded.text_palette["text_primary"]
    assert contrast_ratio(tokens["text_primary"], "#0d1b2e") < contrast_ratio(
        full.text_palette["text_primary"], "#0d1b2e"
    )

    settings.setValue("text_opacity", 0)
    assert build_theme_snapshot(settings).text_opacity == MIN_TEXT_OPACITY


def test_readability_slider_reports_the_contrast_people_will_see_and_reverts():
    dialog = PanelColorPickerDialog(current_base="#0d1b2e", current_text_primary="#f4f7fb")
    try:
        assert dialog._text_slider.minimum() == MIN_TEXT_OPACITY
        full_status = dialog._contrast_status.text()
        dialog._text_slider.setValue(MIN_TEXT_OPACITY)
        assert dialog._contrast_status.text() != full_status
        assert not dialog._contrast_fix_btn.isEnabled() or "대비" in dialog._contrast_status.text()
        assert dialog._appearance_change_categories() == ["readability"]
        assert dialog.selected_text_opacity() == MIN_TEXT_OPACITY
        dialog._flush_preview_refresh()
        css = dialog._preview_frame.styleSheet()
        assert f"QLabel#previewItemText1 {{ color: rgba(244, 247, 251, {MIN_TEXT_OPACITY});" in css

        dialog._section_reset_buttons["readability"].click()
        assert dialog._text_slider.value() == 255
        assert dialog.selected_text_opacity() == 255
        assert dialog._appearance_change_categories() == []
    finally:
        dialog.close()
