# -*- coding: utf-8 -*-
"""Per-layout display options for widget-only mode, stored in settings."""

from __future__ import annotations

from dataclasses import dataclass

from calendar_app.presentation.widgets.widget_mode_skins import WidgetModeLayout

CALENDAR_STYLE_PREFIX = "widget_mode_calendar_style_"
SHOW_OVERVIEW_PREFIX = "widget_mode_show_overview_"
SEARCH_PINNED_PREFIX = "widget_mode_search_pinned_"

_CALENDAR_STYLES = ("week", "month")
_MONTH_BY_DEFAULT = {"dashboard", "magazine"}


@dataclass(frozen=True)
class LayoutDisplay:
    calendar_style: str
    show_overview: bool
    search_pinned: bool


def display_key(prefix: str, layout_id: str) -> str:
    return f"{prefix}{layout_id}"


def default_layout_display(layout: WidgetModeLayout) -> LayoutDisplay:
    if layout.calendar_mode == "auto":
        style = "month" if layout.layout_id in _MONTH_BY_DEFAULT else "week"
    else:
        style = layout.calendar_mode
    return LayoutDisplay(style, bool(layout.show_overview), bool(layout.searchable))


def _read_bool(settings, key: str, default: bool) -> bool:
    raw = settings.value(key, None)
    if raw is True or raw == "true":
        return True
    if raw is False or raw == "false":
        return False
    return default


def read_layout_display(settings, layout: WidgetModeLayout) -> LayoutDisplay:
    default = default_layout_display(layout)
    style = settings.value(
        display_key(CALENDAR_STYLE_PREFIX, layout.layout_id), default.calendar_style
    )
    if style not in _CALENDAR_STYLES:
        style = default.calendar_style
    return LayoutDisplay(
        style,
        _read_bool(
            settings, display_key(SHOW_OVERVIEW_PREFIX, layout.layout_id), default.show_overview
        ),
        _read_bool(
            settings, display_key(SEARCH_PINNED_PREFIX, layout.layout_id), default.search_pinned
        ),
    )


def write_layout_display(settings, layout_id: str, display: LayoutDisplay) -> None:
    settings.setValue(display_key(CALENDAR_STYLE_PREFIX, layout_id), display.calendar_style)
    settings.setValue(display_key(SHOW_OVERVIEW_PREFIX, layout_id), bool(display.show_overview))
    settings.setValue(display_key(SEARCH_PINNED_PREFIX, layout_id), bool(display.search_pinned))
