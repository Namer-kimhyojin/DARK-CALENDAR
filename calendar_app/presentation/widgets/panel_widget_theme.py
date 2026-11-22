# -*- coding: utf-8 -*-
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget

import calendar_app.presentation.widgets.panel_widget_style as _pws

_WIDGET_COLOR_THEME_KEY = "widget_mode_color_theme"
_WIDGET_COLOR_DEFAULT = "default"
_WIDGET_COLOR_FOLLOW_MAIN = "follow_main"
_WIDGET_COLOR_PRESET_HEX = {
    "indigo": "#5856d6",
    "ocean": "#22c3ca",
    "sage": "#24b47e",
    "amber": "#f2b84b",
    "rose": "#ff6f91",
    "slate": "#5c6b82",
}


def _normalize_widget_color_mode(raw_value: object) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return _WIDGET_COLOR_DEFAULT
    lowered = raw.lower()
    if lowered in {
        _WIDGET_COLOR_DEFAULT,
        _WIDGET_COLOR_FOLLOW_MAIN,
        *_WIDGET_COLOR_PRESET_HEX.keys(),
    }:
        return lowered
    color = QColor(raw)
    if color.isValid():
        return color.name(QColor.NameFormat.HexRgb)
    return _WIDGET_COLOR_DEFAULT


def _read_widget_color_mode_from_settings(settings, *, legacy_key: str | None = None) -> str:
    if settings is None:
        return _WIDGET_COLOR_DEFAULT
    raw = settings.value(_WIDGET_COLOR_THEME_KEY, None)
    normalized = _normalize_widget_color_mode(raw)
    if raw not in (None, ""):
        return normalized
    if legacy_key:
        return _normalize_widget_color_mode(settings.value(legacy_key, None))
    return _WIDGET_COLOR_DEFAULT


def _resolve_widget_mode_tokens(
    tokens: dict[str, str] | None = None, *, app: QWidget | None = None
) -> dict[str, str]:
    settings = getattr(app, "settings", None) if app is not None else None
    preset_name = None
    if (
        settings is not None
        and _read_widget_color_mode_from_settings(settings) == _WIDGET_COLOR_FOLLOW_MAIN
    ):
        preset_name = ""
    return _pws.resolve_tokens(tokens, settings=settings, preset_name=preset_name)
