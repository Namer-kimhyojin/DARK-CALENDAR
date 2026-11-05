# -*- coding: utf-8 -*-
"""One type ramp preserves saved preferences and grows native control content."""

from dataclasses import FrozenInstanceError
import math
from unittest.mock import patch

from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtWidgets import QApplication, QLabel, QWidget
import pytest

from calendar_app.presentation.dialogs.dialog_token_editor_dialog import DialogTokenEditorDialog
from calendar_app.shared.theme_snapshot import (
    DIALOG_METRIC_BOUNDS,
    DIALOG_METRIC_DEFAULTS,
    build_dialog_metric_tokens,
    get_dialog_metric_bounds,
    get_dialog_metric_defaults,
    set_metric_token_overrides,
)
from calendar_app.shared.typography import get_typography_scale
from calendar_app.shared.ui_tokens import get_shared_qss, get_ui_tokens


class Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.writes = []

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value
        self.writes.append((key, value))

    def remove(self, key):
        self.values.pop(key, None)
        self.writes.append((key, None))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("base", [7, 10, 11, 14, 24, 256])
def test_saved_points_are_preserved_and_px_are_dpi_independent(base):
    settings = Settings({"font_size": base, "font_family": "Courier New"})
    before = dict(settings.values)
    scale = get_typography_scale(settings)
    assert scale.body_pt == base
    assert scale.caption_pt == max(9.5, base - 1)
    assert scale.section_pt == base + 2
    assert scale.title_pt == base + 5
    assert scale.display_pt == base + 7
    for role in ("body", "caption", "section", "title", "display"):
        assert getattr(scale, f"{role}_px") == math.ceil(getattr(scale, f"{role}_pt") * 96 / 72)
    assert settings.values == before
    assert settings.writes == []
    with pytest.raises(FrozenInstanceError):
        scale.body_pt = 20


@pytest.mark.parametrize("value", [0, -1, "bad", float("nan"), float("inf")])
def test_invalid_values_fall_back_without_rewriting_settings(value):
    settings = Settings({"font_size": value})
    assert get_typography_scale(settings).body_pt == 11
    assert settings.writes == []


def test_new_default_and_explicit_preview_override_do_not_write():
    settings = Settings({"font_size": 10})
    assert get_typography_scale(Settings()).body_pt == 11
    assert get_typography_scale(settings, base_pt=12.5).body_pt == 12.5
    assert settings.value("font_size") == 10
    assert settings.writes == []


def test_legacy_font_helpers_share_the_new_fallback_and_keep_explicit_defaults():
    from calendar_app.shared.qt_helpers import app_font_point_size, scaled_pt
    from calendar_app.shared.theme_settings import fpt

    with patch("calendar_app.shared.qt_helpers.QApplication.instance", return_value=None):
        assert app_font_point_size() == 11
        assert scaled_pt() == "11pt"
        assert fpt() == "11pt"
        assert scaled_pt(default=10) == "10pt"


@pytest.mark.parametrize("base", [7, 11, 24, 256])
def test_default_controls_fit_text_and_keep_outer_size_contract(app, base):
    settings = Settings({"font_size": base, "font_family": "Segoe UI"})
    metrics = get_dialog_metric_defaults(settings)
    scale = get_typography_scale(settings)
    assert metrics["base_font_pt"] == scale.body_px
    assert metrics["title_font_pt"] == scale.title_px
    assert metrics["subtitle_font_pt"] == scale.caption_px
    font = QFont("Segoe UI")
    font.setPixelSize(scale.body_px)
    font.setWeight(QFont.Weight.DemiBold)
    for control in ("field", "button", "toolbutton"):
        content = metrics[f"{control}_height"]
        assert content >= math.ceil(QFontMetricsF(font).height())
        assert content + 2 * metrics[f"{control}_padding_y"] + 2 >= 38
    for key, default in metrics.items():
        low, high = get_dialog_metric_bounds(settings)[key]
        assert low <= default <= high
    assert settings.writes == []


def test_explicit_legacy_px_and_height_overrides_keep_their_meaning(app):
    settings = Settings(
        {
            "font_size": 24,
            "dialog_token.metric.base_font_pt": 16,
            "dialog_token.metric.title_font_pt": 23,
            "dialog_token.metric.button_height": 31,
            "dialog_token.metric.field_height": 42,
        }
    )
    metrics = build_dialog_metric_tokens(settings)
    assert metrics["base_font_pt"] == 16
    assert metrics["title_font_pt"] == 23
    assert metrics["button_height"] == 31
    assert metrics["field_height"] == 42
    assert settings.writes == []


def test_large_font_override_expands_only_unspecified_heights(app):
    settings = Settings({"dialog_token.metric.base_font_pt": 22})
    metrics = build_dialog_metric_tokens(settings)
    font = QFont(app.font())
    font.setPixelSize(22)
    font.setWeight(QFont.Weight.DemiBold)
    assert metrics["button_height"] >= math.ceil(QFontMetricsF(font).height())


def test_saved_large_metric_remains_explicit_after_base_font_is_reduced(app):
    settings = Settings({"font_size": 11, "dialog_token.metric.base_font_pt": 32})
    assert build_dialog_metric_tokens(settings)["base_font_pt"] == 32
    assert get_dialog_metric_bounds(settings)["base_font_pt"][1] >= 32
    assert settings.writes == []


def test_sparse_metric_save_uses_dynamic_defaults_and_preserves_existing_explicit_value(app):
    settings = Settings({"font_size": 24})
    default = get_dialog_metric_defaults(settings)["base_font_pt"]
    settings.values["dialog_token.metric.base_font_pt"] = default
    set_metric_token_overrides(
        DIALOG_METRIC_DEFAULTS,
        DIALOG_METRIC_BOUNDS,
        {"base_font_pt": default},
        prefix="dialog_token.metric.",
        settings=settings,
    )
    assert settings.value("dialog_token.metric.base_font_pt") == default
    set_metric_token_overrides(
        DIALOG_METRIC_DEFAULTS,
        DIALOG_METRIC_BOUNDS,
        {},
        prefix="dialog_token.metric.",
        settings=settings,
    )
    assert settings.value("dialog_token.metric.base_font_pt") is None


def test_editor_large_defaults_reset_and_noop_apply_do_not_create_overrides(app):
    settings = Settings({"font_size": 24})
    dialog = DialogTokenEditorDialog(
        initial_color_overrides={},
        initial_metric_overrides={},
        persist_on_apply=False,
        settings=settings,
    )
    try:
        assert dialog._metric_spins["base_font_pt"].value() == 32
        assert dialog._metric_spins["title_font_pt"].value() == 39
        assert dialog.get_metric_overrides_from_spins() == {}
        assert "font-size: 32px;" in dialog.preview_root.styleSheet()
        dialog._metric_spins["base_font_pt"].setValue(20)
        dialog._reset_metric_key("base_font_pt")
        assert dialog._metric_spins["base_font_pt"].value() == 32
        dialog._apply_metric_map({})
        assert dialog._collect_metric_overrides(diff_only=True) == {}
        dialog._apply()
        assert dialog.selected_metric_overrides() == {}
    finally:
        dialog.close()


def test_shared_styles_inherit_the_selected_family_and_apply_body_role(app):
    tokens = get_ui_tokens(settings=Settings({"font_size": 11}))
    stylesheet = get_shared_qss(tokens)
    assert "font-family" not in stylesheet
    parent = QWidget()
    parent.setFont(QFont("Courier New", 11))
    label = QLabel("가나다 ABC", parent)
    parent.setStyleSheet(stylesheet)
    label.ensurePolished()
    try:
        assert label.font().family() == "Courier New"
        assert label.font().pixelSize() == 15
    finally:
        parent.close()


@pytest.mark.parametrize("reset", [False, True])
def test_editor_preserves_an_existing_explicit_default_until_user_resets_it(app, reset):
    settings = Settings({"font_size": 24, "dialog_token.metric.base_font_pt": 32})
    dialog = DialogTokenEditorDialog(
        initial_color_overrides={}, persist_on_apply=False, settings=settings
    )
    try:
        if reset:
            dialog._reset_metric_key("base_font_pt")
        dialog._apply()
        assert dialog.selected_metric_overrides() == ({} if reset else {"base_font_pt": 32})
        assert settings.writes == []
    finally:
        dialog.close()
