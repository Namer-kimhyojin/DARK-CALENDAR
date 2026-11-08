# -*- coding: utf-8 -*-
"""Color override storage preserves even a one-byte alpha through reopening."""

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
import pytest

from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_token_overrides,
    set_dialog_token_overrides,
)
from calendar_app.shared.color_utils import parse_css_color
from calendar_app.shared.theme_snapshot import normalize_color_token


@pytest.mark.parametrize("alpha", [0, 1, 2, 36, 128, 254, 255])
def test_color_token_roundtrips_through_saved_settings(tmp_path, alpha):
    settings = QSettings(str(tmp_path / "alpha.ini"), QSettings.Format.IniFormat)
    selected = QColor(17, 34, 51, alpha)
    value = selected.name(QColor.NameFormat.HexArgb)
    set_dialog_token_overrides({"accent": value}, settings=settings)
    for _ in range(3):
        stored = get_dialog_token_overrides(settings)["accent"]
        assert parse_css_color(stored).getRgb() == selected.getRgb()
        assert normalize_color_token(stored) == stored
        set_dialog_token_overrides({"accent": stored}, settings=settings)


def test_legacy_css_alpha_one_still_means_fully_opaque():
    normalized = normalize_color_token("rgba(17, 34, 51, 1)")
    assert parse_css_color(normalized).getRgb() == (17, 34, 51, 255)
