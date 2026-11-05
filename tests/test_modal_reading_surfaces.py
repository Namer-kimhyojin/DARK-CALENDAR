# -*- coding: utf-8 -*-
"""Opaque modal reading surfaces preserve decorative main-window transparency."""

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.dialogs.daily_summary_dialog import DailySummaryDialog
from calendar_app.presentation.dialogs.dialog_styles import (
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
)
from calendar_app.shared.color_utils import parse_css_color
from calendar_app.shared.ui_tokens import get_ui_tokens

_SURFACES = (
    "floating_bg",
    "content_bg",
    "surface_bg",
    "surface_alt",
    "surface_item",
    "surface_hover",
    "surface_top",
)


@pytest.fixture
def modal_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "modal.ini"), QSettings.Format.IniFormat)
    settings.setValue("last_opacity_unit", "byte")
    yield app, settings


@pytest.mark.parametrize(
    "mode,base", [("dark", "#121827"), ("light", "#f3f1fa"), ("custom", "#24413f")]
)
@pytest.mark.parametrize("opacity", [0, 96, 150, 255])
def test_modal_surfaces_do_not_inherit_decorative_shell_opacity(
    modal_settings, mode, base, opacity
):
    _app, settings = modal_settings
    settings.setValue("text_theme", mode)
    settings.setValue("panel_base_color", base)
    settings.setValue("last_opacity", opacity)
    before = {key: settings.value(key) for key in settings.allKeys()}
    dialog = get_dialog_theme_tokens(settings=settings)
    shared = get_ui_tokens(settings=settings)
    assert all(parse_css_color(dialog[role]).alpha() == 255 for role in _SURFACES)
    shell_alpha = parse_css_color(shared["bg_main"]).alpha()
    if opacity < 255:
        assert shell_alpha < 255
    else:
        assert shell_alpha == 255
    assert before == {key: settings.value(key) for key in settings.allKeys()}


def test_translucent_expert_modal_overrides_are_composited_without_rewriting_settings(
    modal_settings,
):
    _app, settings = modal_settings
    settings.setValue("panel_base_color", "#24413f")
    settings.setValue("last_opacity", 20)
    settings.setValue("dialog_token.surface_bg", "rgba(22, 40, 38, 38)")
    settings.setValue("dialog_token.surface_item", "rgba(45, 80, 76, 64)")
    before = {key: settings.value(key) for key in settings.allKeys()}
    tokens = get_dialog_theme_tokens(settings=settings)
    assert parse_css_color(tokens["floating_bg"]).alpha() == 255
    assert parse_css_color(tokens["surface_item"]).alpha() == 255
    style = build_dialog_stylesheet(settings=settings, tokens={"floating_bg": "transparent"})
    assert "background-color: transparent;\n    font-family:" not in style
    assert before == {key: settings.value(key) for key in settings.allKeys()}


@pytest.mark.parametrize(
    "mode,base", [("dark", "#121827"), ("light", "#f3f1fa"), ("custom", "#24413f")]
)
def test_daily_briefing_gradient_is_opaque_while_rounded_shell_remains_translucent(
    modal_settings, mode, base
):
    app, settings = modal_settings
    settings.setValue("text_theme", mode)
    settings.setValue("panel_base_color", base)
    settings.setValue("last_opacity", 50)
    parent = QWidget()
    parent.settings = settings
    with (
        patch.object(DailySummaryDialog, "_load_schedule", return_value=[]),
        patch.object(DailySummaryDialog, "_load_due_routines", return_value=[]),
    ):
        dialog = DailySummaryDialog(parent, show_settings=True)
    try:
        dialog.show()
        app.processEvents()
        assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        image = dialog.container.grab().toImage()
        for x, y in ((20, 20), (image.width() - 20, image.height() - 20)):
            assert image.pixelColor(x, y).alpha() == 255
    finally:
        dialog.close()
        dialog.deleteLater()
        parent.close()
        app.processEvents()
