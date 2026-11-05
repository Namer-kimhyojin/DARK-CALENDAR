# -*- coding: utf-8 -*-
"""Modal actions use one accent family without changing color-choice data."""

import json
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout
import pytest

from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    _checklist_main_style_bundle,
)
from calendar_app.presentation.dialogs.color_swatch_widget import GoogleColorSwatch
from calendar_app.presentation.dialogs.dialog_editor_styles import build_editor_quick_button_style
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.management_dialogs import _status_background
from calendar_app.presentation.dialogs.routine_bulk_operations_dialog import (
    _routine_bulk_row_colors,
)
from calendar_app.presentation.widgets.alarm_popup import _alarm_popup_style_bundle
from calendar_app.shared.color_utils import (
    composite_color,
    contrast_ratio,
    derive_modal_state_palette,
    derive_state_palette,
    hex_to_rgba,
    parse_css_color,
)
from calendar_app.shared.theme_snapshot import build_dialog_base_tokens
from calendar_app.shared.ui_tokens import get_modal_ui_tokens, get_ui_tokens

OUTPUT = Path("artifacts/modal-palette-20261105/offscreen-palette")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _settings(tmp_path, mode, accent):
    settings = QSettings(str(tmp_path / "palette.ini"), QSettings.Format.IniFormat)
    for key, value in {
        "text_theme": mode,
        "panel_base_color": "#f6f7fb" if mode == "light" else "#121827",
        "theme_color": accent,
        "last_opacity": 255,
        "last_opacity_unit": "byte",
    }.items():
        settings.setValue(key, value)
    return settings


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("accent", ["#7653c4", "#008e82", "#fdba74"])
def test_modal_roles_and_actual_button_text_share_the_accent_family(app, tmp_path, mode, accent):
    settings = _settings(tmp_path, mode, accent)
    original = {key: settings.value(key) for key in settings.allKeys()}
    tokens = get_dialog_theme_tokens(settings=settings)
    surface = composite_color(tokens["floating_bg"], tokens["base_hex"]).name()
    states = derive_modal_state_palette(accent, surface)
    assert len(set(states.values())) == 1
    for role, color in states.items():
        assert tokens[f"{role}_hex"] == color
        for alpha in (0, 0.14, 0.16, 0.20, 0.22, 0.32):
            background = composite_color(hex_to_rgba(color, alpha), surface)
            assert contrast_ratio(color, background) >= 4.5
        assert abs(QColor(color).hslHueF() - QColor(accent).hslHueF()) < 0.03
    shared = get_ui_tokens(settings=settings)
    assert {role: shared[role] for role in states} == derive_state_palette(mode)
    modal = get_modal_ui_tokens(settings=settings)
    assert {role: modal[role] for role in states} == states
    alarm = _alarm_popup_style_bundle(settings=settings)
    assert alarm["accent_ok"].name() == states["success"]
    assert alarm["accent_error"].name() == states["danger"]
    bundle = _checklist_main_style_bundle(tokens=tokens)
    assert states["success"] in bundle["button_success"]
    assert states["danger"] in bundle["button_danger"]
    for status in ("pending", "in_progress", "completed", "deferred"):
        status_color = _status_background(status, tokens)
        expected = accent if status == "in_progress" else states["success"]
        assert status_color.name() == expected
        assert status_color.alpha() == 48
    row_colors = _routine_bulk_row_colors(tokens)
    for priority in ("normal", "high", "urgent", "completed"):
        assert row_colors[priority].name() == states["success"]
    assert row_colors["low"].name() == parse_css_color(tokens["text_secondary"]).name()

    dialog = QDialog()
    dialog.setWindowTitle("모달 팔레트 검증")
    layout = QVBoxLayout(dialog)
    title = QLabel("추가·삭제도 선택한 포인트 색상으로")
    title.setProperty("role", "dialogTitle")
    layout.addWidget(title)
    layout.addWidget(QLabel("본문과 보조 설명은 읽기 쉬운 중립색을 유지합니다."))
    apply_common_dialog_style(dialog, settings=settings)
    buttons = []
    for tone, text in (("success", "항목 추가"), ("danger", "삭제"), ("warning", "상태 확인")):
        button = QPushButton(text)
        button.setStyleSheet(build_editor_quick_button_style(tokens, tone=tone))
        layout.addWidget(button)
        button.ensurePolished()
        assert button.palette().color(QPalette.ColorRole.ButtonText).name() == states[tone]
        buttons.append(button)
    dialog.resize(540, 300)
    dialog.ensurePolished()
    try:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        name = f"{mode}-{accent.removeprefix('#')}"
        assert dialog.grab().save(str(OUTPUT / f"{name}.png"))
        (OUTPUT / f"{name}.json").write_text(
            json.dumps(
                {
                    "capture_kind": "offscreen Qt fixture, not native Windows",
                    "mode": mode,
                    "accent": accent,
                    "surface": surface,
                    "states": states,
                    "button_text": [
                        button.palette().color(QPalette.ColorRole.ButtonText).name()
                        for button in buttons
                    ],
                    "settings_unchanged": {key: settings.value(key) for key in settings.allKeys()}
                    == original,
                },
                indent=2,
            ),
            encoding="utf-8",
            errors="strict",
        )
        assert {key: settings.value(key) for key in settings.allKeys()} == original
    finally:
        dialog.close()


def test_explicit_expert_colors_and_calendar_swatches_remain_user_controlled(app, tmp_path):
    settings = _settings(tmp_path, "light", "#7653c4")
    settings.setValue("dialog_token.button_danger_text", "#b12345")
    tokens = get_dialog_theme_tokens(settings=settings)
    assert tokens["button_danger_text"] == "#b12345"
    swatches = GoogleColorSwatch(tokens=tokens)
    try:
        original = [button.color_hex for button in swatches._buttons]
        assert len(set(original)) == 12
        swatches.set_color("#dc2127")
        assert swatches.selected_color() == "#dc2127"
        swatches.apply_dialog_theme(tokens=build_dialog_base_tokens(theme_color="#008e82"))
        assert [button.color_hex for button in swatches._buttons] == original
        assert swatches.selected_color() == "#dc2127"
    finally:
        swatches.close()


def test_expert_accent_rebuilds_implicit_roles_and_preserves_explicit_action_color(app, tmp_path):
    settings = _settings(tmp_path, "light", "#7653c4")
    original = get_dialog_theme_tokens(settings=settings)
    settings.setValue("dialog_token.accent", "#008e82")
    settings.setValue("dialog_token.button_danger_text", "#b12345")
    changed = get_dialog_theme_tokens(settings=settings)
    expected = derive_modal_state_palette("#008e82", changed["floating_bg"])["success"]
    for role in ("success", "warning", "danger"):
        assert changed[f"{role}_hex"] == expected
    assert changed["button_success_text"] == expected
    assert changed["button_danger_text"] == "#b12345"
    for role in ("text_primary", "text_secondary", "text_muted", "text_faint"):
        assert changed[role] == original[role]


def test_partial_modal_builder_inputs_derive_missing_state_colors_from_the_supplied_accent(app):
    accent = "#008e82"
    alarm = _alarm_popup_style_bundle(tokens={"accent": accent})
    assert abs(alarm["accent_ok"].hslHueF() - QColor(accent).hslHueF()) < 0.03
    for tone in ("success", "danger", "warning"):
        stylesheet = build_editor_quick_button_style(tokens={"accent": accent}, tone=tone)
        assert any(color in stylesheet for color in ("#008e82", alarm["accent_ok"].name()))
