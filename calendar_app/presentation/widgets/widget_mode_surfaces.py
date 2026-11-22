# -*- coding: utf-8 -*-
"""Surface styles (card shape and item treatment) for widget-only mode."""

from __future__ import annotations

from dataclasses import dataclass

SURFACE_SETTING_KEY = "widget_mode_surface"
DEFAULT_SURFACE = "card"


@dataclass(frozen=True)
class WidgetModeSurface:
    key: str
    label_key: str
    label_default: str
    radius: int
    item_radius: int
    item_background: str  # "card" | "transparent"
    item_border: str  # "full" | "bottom"


_SURFACES = (
    WidgetModeSurface("card", "widget_mode.surface_card", "카드", 10, 8, "card", "full"),
    WidgetModeSurface("line", "widget_mode.surface_line", "구분선", 6, 2, "transparent", "bottom"),
    WidgetModeSurface(
        "outline", "widget_mode.surface_outline", "테두리", 10, 6, "transparent", "full"
    ),
    WidgetModeSurface("compact", "widget_mode.surface_compact", "촘촘", 8, 4, "card", "full"),
)
_BY_KEY = {surface.key: surface for surface in _SURFACES}


def widget_mode_surfaces() -> tuple[WidgetModeSurface, ...]:
    return _SURFACES


def _normalise(key: object) -> str:
    text = str(key or "").strip().lower()
    return text if text in _BY_KEY else DEFAULT_SURFACE


def get_widget_mode_surface(key: object) -> WidgetModeSurface:
    return _BY_KEY[_normalise(key)]


def read_widget_mode_surface(settings) -> str:
    return _normalise(settings.value(SURFACE_SETTING_KEY, DEFAULT_SURFACE))


def write_widget_mode_surface(settings, key: object) -> str:
    value = _normalise(key)
    settings.setValue(SURFACE_SETTING_KEY, value)
    return value
