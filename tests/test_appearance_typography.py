# -*- coding: utf-8 -*-
"""Appearance controls use the shared ramp without clipping large user fonts."""

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog
from calendar_app.shared.typography import get_typography_scale


@pytest.fixture(params=[10, 11, 14, 24])
def appearance(request, tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = QFont(app.font())
    app.setFont(QFont("Malgun Gothic", request.param))
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    parent.settings.setValue("font_size", request.param)
    parent.settings.setValue("font_family", "Malgun Gothic")
    parent.settings.setValue("text_theme", "light")
    dialog = PanelColorPickerDialog(
        parent,
        current_base="#f6f7fb",
        current_theme="#7653c4",
        current_text_theme="light",
        current_font_family="Malgun Gothic",
        current_font_size=request.param,
    )
    dialog.show()
    app.processEvents()
    yield app, dialog, get_typography_scale(parent.settings), parent.settings
    dialog.close()
    dialog.deleteLater()
    parent.close()
    parent.deleteLater()
    app.processEvents()
    app.setFont(previous)


def test_appearance_text_roles_match_the_user_scale(appearance):
    _, dialog, scale, _ = appearance
    assert dialog._preview_selection_label.font().pixelSize() == scale.caption_px
    assert dialog._section_toggles["style"].font().pixelSize() == scale.section_px
    assert next(iter(dialog._family_btns.values())).font().pixelSize() == scale.body_px


def test_large_style_cards_and_font_controls_fit_without_rewriting_preferences(appearance):
    app, dialog, scale, settings = appearance
    dialog._ensure_section_content("font")
    app.processEvents()
    assert dialog._font_size_spin.value() == scale.body_pt
    assert dialog._font_combo.height() >= dialog._font_combo.fontMetrics().height()
    assert dialog._font_popup_btn.height() >= dialog._font_popup_btn.iconSize().height()
    card = next(iter(dialog._family_btns.values()))
    assert card.height() >= card.fontMetrics().lineSpacing() * 2 + 4
    assert not dialog._apply_btn.visibleRegion().isEmpty()
    if scale.body_px > 20:
        assert dialog._family_columns == 1
        assert not dialog._wide_appearance_layout
        assert dialog._settings_scroll.width() >= dialog.width() - 60
        assert dialog._settings_scroll.height() > dialog.height() // 3
        assert not dialog._preview_frame.isVisible()
        dialog._compact_preview_toggle.click()
        app.processEvents()
        assert dialog._preview_frame.isVisible()
        dialog._compact_preview_toggle.click()
        app.processEvents()
        assert dialog._settings_scroll.height() > dialog.height() // 3
        for button in (dialog._revert_all_btn, dialog._apply_btn):
            assert button.width() >= button.sizeHint().width()
    assert settings.value("font_size", type=int) == scale.body_pt
