# -*- coding: utf-8 -*-
"""Border color: a quiet automatic recommendation, a direct choice, and app-wide tokens."""

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QColorDialog
import pytest

from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog
from calendar_app.shared.color_utils import (
    BORDER_RECOMMENDED_CONTRAST,
    contrast_ratio,
    recommend_border_color,
)
from calendar_app.shared.theme_snapshot import (
    build_dialog_base_tokens,
    build_shared_ui_tokens,
    build_theme_snapshot,
)


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


@pytest.mark.parametrize(
    ("base", "accent"),
    [
        ("#0d1b2e", "#4da6ff"),
        ("#f8f1e7", "#b7791f"),
        ("#121212", "#f8f8f2"),
        ("#fff9db", "#e0b100"),
    ],
)
def test_recommended_border_separates_quietly_and_leans_to_the_accent(base, accent):
    border = recommend_border_color(base, accent)
    ratio = contrast_ratio(border, base)
    assert BORDER_RECOMMENDED_CONTRAST <= ratio < 2.4
    neutral = recommend_border_color(base, base)
    assert border != neutral or QColor(accent).name() == QColor(base).name()


def test_neutral_borders_stay_until_a_border_is_chosen(settings):
    before = build_shared_ui_tokens(settings)
    assert build_theme_snapshot(settings).border_tokens == {}
    assert before["border"] == "rgba(255,255,255,0.12)"

    settings.setValue("appearance_border_source", "custom")
    settings.setValue("panel_border_color", "#336699")
    settings.setValue("last_border_opacity", 255)
    snapshot = build_theme_snapshot(settings)
    expected = "rgba(51, 102, 153, 255)"
    assert snapshot.border_tokens["border"] == expected
    assert snapshot.ui_palette["border"] == expected
    assert build_shared_ui_tokens(settings, snapshot=snapshot)["border"] == expected
    assert build_dialog_base_tokens(settings, snapshot=snapshot)["border"] == expected
    assert snapshot.border_tokens["border_soft"] == "rgba(51, 102, 153, 153)"

    settings.setValue("last_border_opacity", 0)
    assert build_theme_snapshot(settings).border_tokens["border"] == "rgba(51, 102, 153, 0)"

    settings.setValue("appearance_border_source", "auto")
    automatic = QColor(recommend_border_color("#0d1b2e", "#4da6ff"))
    settings.setValue("last_border_opacity", 255)
    assert build_theme_snapshot(settings).border_tokens["border"] == (
        f"rgba({automatic.red()}, {automatic.green()}, {automatic.blue()}, 255)"
    )


def _dialog(**kwargs):
    options = {
        "current_base": "#0d1b2e",
        "current_theme": "#4da6ff",
        "current_style_family": "ocean",
        "current_accent_source": "family",
        "current_base_source": "family",
    }
    options.update(kwargs)
    return PanelColorPickerDialog(**options)


def test_border_row_recommends_follows_the_draft_and_accepts_a_direct_color(monkeypatch):
    dialog = _dialog()
    try:
        background = dialog._section_contents["background"]
        assert not background.isAncestorOf(dialog._text_slider)  # it lives in Readability
        assert background.isAncestorOf(dialog._btn_auto_border)
        assert dialog._btn_auto_border.isChecked() and not dialog._btn_custom_border.isChecked()
        recommended = recommend_border_color(dialog._base_hex, dialog._point_hex)
        assert dialog._border_hex_lbl.text() == recommended
        assert dialog._current_preview_state()[11] == recommended
        assert dialog.selected_border_source() == ""  # never chosen: keep neutral lines

        dialog._set_appearance_mode("light")
        light_recommended = recommend_border_color(dialog._base_hex, dialog._point_hex)
        assert light_recommended != recommended
        assert dialog._border_hex_lbl.text() == light_recommended

        monkeypatch.setattr(QColorDialog, "getColor", lambda *_args, **_kwargs: QColor("#aa3355"))
        dialog._open_custom_border_color()
        assert dialog._btn_custom_border.isChecked()
        assert dialog.selected_border_source() == "custom"
        assert dialog.selected_border_hex() == "#aa3355"
        assert dialog._border_hex_lbl.text() == "#aa3355"
        assert "background" in dialog._appearance_change_categories()
        css = dialog._preview_frame.styleSheet()
        assert "rgba(170, 51, 85," in css

        dialog._section_reset_buttons["background"].click()
        assert dialog._btn_auto_border.isChecked()
        assert dialog.selected_border_source() == ""
        assert dialog.selected_border_hex() == ""
    finally:
        dialog.close()


def test_changing_border_opacity_turns_on_the_chosen_border():
    dialog = _dialog()
    try:
        dialog._border_slider.setValue(dialog._border_slider.value() + 10)
        assert dialog.selected_border_source() == "auto"
        dialog._border_slider.setValue(dialog._border_slider.value() - 10)
        assert dialog.selected_border_source() == ""
    finally:
        dialog.close()


def test_saved_custom_border_reopens_as_custom():
    dialog = _dialog(current_border_source="custom", current_border_color="#123abc")
    try:
        assert dialog._btn_custom_border.isChecked()
        assert dialog._border_hex_lbl.text() == "#123abc"
        assert dialog.selected_border_source() == "custom"
        assert dialog.selected_border_hex() == "#123abc"
        assert dialog._appearance_change_categories() == []
    finally:
        dialog.close()


def test_every_palette_path_follows_the_chosen_border_but_panel_gaps_stay_neutral(settings):
    from calendar_app.presentation.main_window.dock_factory import build_dock_manager_style
    from calendar_app.shared.color_utils import derive_ui_palette

    settings.setValue("appearance_border_source", "custom")
    settings.setValue("panel_border_color", "#ff2d55")
    settings.setValue("last_border_opacity", 255)
    # Callers that skip the snapshot and build the palette directly.
    palette = derive_ui_palette("dark", "#0d1b2e", 1.0, "#4da6ff", settings)
    for key in ("border", "border_soft", "border_strong", "divider"):
        assert palette[key].startswith("rgba(255, 45, 85,"), key
    # The gaps between panels stay a faint neutral so outlines are never doubled.
    assert not palette["separator_bg"].startswith("rgba(255, 45, 85,")
    # Grid lines (divider) and the gaps between panels (separator) included.
    assert build_shared_ui_tokens(settings)["divider"].startswith("rgba(255, 45, 85,")
    separator_rule = build_dock_manager_style(settings, "#4da6ff").split(
        "QMainWindow::separator {"
    )[1]
    assert "255, 45, 85" not in separator_rule.split("}")[0]


def test_main_window_keeps_its_panel_separator_rules_after_a_font_change(settings, monkeypatch):
    from types import SimpleNamespace

    from calendar_app.presentation.main_window import window_ui_actions

    applied = {}
    host = SimpleNamespace(
        settings=settings,
        setStyleSheet=lambda css: applied.setdefault("css", css),
    )
    monkeypatch.setattr(QApplication.instance(), "setStyleSheet", lambda *_a: None)
    monkeypatch.setattr(QApplication.instance(), "setFont", lambda *_a: None)
    window_ui_actions.MainWindowUiActionsMixin.apply_font_settings(
        host, "Malgun Gothic", 11, refresh=False
    )
    assert "QMainWindow::separator" in applied["css"]
