# -*- coding: utf-8 -*-
"""Layout-scoped visibility preferences for the unified widget window."""

from __future__ import annotations

BOARD_CALENDAR_LAYOUT_IDS = frozenset({"dashboard", "magazine"})
LEGACY_CALENDAR_VISIBILITY_KEY = "widget_mode_show_week"


def calendar_visibility_key(layout_id: object) -> str:
    normalized = str(layout_id or "stacked").strip().lower() or "stacked"
    return f"widget_mode_calendar_visible_{normalized}"


def read_widget_calendar_visibility(settings, layout_id: object) -> bool:
    """Read calendar visibility, defaulting board layouts to visible."""

    normalized = str(layout_id or "stacked").strip().lower() or "stacked"
    scoped = settings.value(calendar_visibility_key(normalized), None)
    if scoped is not None:
        return str(scoped).lower() == "true"
    if normalized in BOARD_CALENDAR_LAYOUT_IDS:
        return True
    legacy = settings.value(LEGACY_CALENDAR_VISIBILITY_KEY, "true")
    return str(legacy).lower() == "true"


def write_widget_calendar_visibility(settings, layout_id: object, visible: bool) -> None:
    """Persist per-layout state while keeping the legacy key compatible."""

    value = bool(visible)
    settings.setValue(calendar_visibility_key(layout_id), value)
    settings.setValue(LEGACY_CALENDAR_VISIBILITY_KEY, value)
