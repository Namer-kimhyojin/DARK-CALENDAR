# -*- coding: utf-8 -*-
"""One-time, idempotent migration of widget-only-mode settings to the four-layout catalog."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
from pathlib import Path

from calendar_app.presentation.widgets.widget_free_layout import (
    FREE_LAYOUT_SETTING_KEY,
    validate_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    MAX_LAYOUT_PRESETS,
    MAX_PRESET_NAME_LENGTH,
    USER_LAYOUT_PRESETS_KEY,
    create_layout_preset,
    read_layout_presets,
    write_layout_presets,
)
from calendar_app.presentation.widgets.widget_mode_display import (
    CALENDAR_STYLE_PREFIX,
    SEARCH_PINNED_PREFIX,
    SHOW_OVERVIEW_PREFIX,
    LayoutDisplay,
    default_layout_display,
    display_key,
)
from calendar_app.presentation.widgets.widget_mode_geometry import geometry_key
from calendar_app.presentation.widgets.widget_mode_skins import (
    USER_STYLES_PATH,
    _read_user_style_document,
    get_widget_mode_layout,
)
from calendar_app.presentation.widgets.widget_mode_surfaces import (
    DEFAULT_SURFACE,
    SURFACE_SETTING_KEY,
)
from calendar_app.presentation.widgets.widget_mode_visibility import (
    calendar_visibility_key,
    read_widget_calendar_visibility,
)

logger = logging.getLogger(__name__)

KEPT_LAYOUT_IDS = ("stacked", "dashboard", "work_board", "minimal")
LAYOUT_LEGACY_KEY = "widget_mode_layout_legacy"
_LAYOUT_KEY = "widget_mode_layout"
_SKIN_KEY = "widget_mode_skin"
_USER_LAYOUT_PREFIX = "user_layout_"

RETIRED_LAYOUTS: dict[str, tuple[str, LayoutDisplay]] = {
    "day_brief": ("stacked", LayoutDisplay("week", True, True)),
    "month_focus": ("stacked", LayoutDisplay("month", False, True)),
    "week_navigator": ("stacked", LayoutDisplay("week", False, True)),
    "agenda_first": ("stacked", LayoutDisplay("week", False, False)),
    "side_planner": ("dashboard", LayoutDisplay("month", True, True)),
    "magazine": ("dashboard", LayoutDisplay("month", False, False)),
    "focus_dock": ("minimal", LayoutDisplay("week", False, True)),
}

SKIN_SURFACES: dict[str, str] = {
    **dict.fromkeys(
        (
            "classic_light",
            "classic_dark",
            "midnight_blue",
            "forest_mist",
            "sunset_glow",
            "lavender_dream",
            "studio_porcelain",
            "studio_sage",
            "studio_lilac",
            "studio_midnight",
            "studio_amethyst",
        ),
        "card",
    ),
    "studio_linen": "line",
    "studio_forest": "line",
    "studio_arctic": "outline",
    "studio_contrast": "outline",
    "studio_graphite": "compact",
}

LEGACY_SKIN_LAYOUTS: dict[str, str] = {
    "midnight_blue": "dashboard",
    "forest_mist": "agenda_first",
    "sunset_glow": "magazine",
    "lavender_dream": "minimal",
}


def _normalized_id(raw: object) -> str:
    return str(raw or "").strip().lower()


def _same(stored: object, value: object) -> bool:
    if stored is None:
        return False
    if isinstance(value, bool) or str(stored).lower() in ("true", "false"):
        return str(stored).lower() == str(value).lower()
    return bool(stored == value)


def _put(settings, key: str, value: object) -> bool:
    """Write only when the stored value differs, so a repeat run writes nothing."""
    if _same(settings.value(key, None), value):
        return False
    settings.setValue(key, value)
    return True


def classify_user_layout(raw: Mapping) -> tuple[str, LayoutDisplay]:
    if raw.get("presentation") == "board":
        new_id = "work_board"
    else:
        placements = raw.get("placements") or ()
        sections = [p for p in placements if isinstance(p, (list, tuple)) and len(p) >= 3]
        if not any(p[0] == "calendar" for p in sections):
            new_id = "minimal"
        elif any(isinstance(p[2], int) and p[2] > 0 for p in sections):
            new_id = "dashboard"
        else:
            new_id = "stacked"
    default = default_layout_display(get_widget_mode_layout(new_id))
    style = raw.get("calendar_mode")
    if style not in ("week", "month"):
        style = default.calendar_style
    return new_id, LayoutDisplay(style, bool(raw.get("show_overview")), bool(raw.get("searchable")))


def _find_user_layout(path: Path, layout_id: str) -> Mapping | None:
    for entry in _read_user_style_document(path).get("layouts", []):
        if isinstance(entry, dict) and _normalized_id(entry.get("layout_id")) == layout_id:
            return entry
    return None


def _resolve(settings, user_styles_path: Path) -> tuple[str, str, LayoutDisplay | None]:
    """Return (old id, new id, display for a retired layout or None)."""
    old = _normalized_id(settings.value(_LAYOUT_KEY, None))
    if not old:
        old = LEGACY_SKIN_LAYOUTS.get(_normalized_id(settings.value(_SKIN_KEY, None)), "stacked")
    if old in RETIRED_LAYOUTS:
        new_id, display = RETIRED_LAYOUTS[old]
        return old, new_id, display
    if old.startswith(_USER_LAYOUT_PREFIX):
        raw = _find_user_layout(user_styles_path, old)
        if raw is None:
            return old, "stacked", None
        new_id, display = classify_user_layout(raw)
        return old, new_id, display
    if old in KEPT_LAYOUT_IDS:
        return old, old, None
    return old, "stacked", None


def _put_display_if_missing(settings, layout_id: str, display: LayoutDisplay) -> bool:
    changed = False
    for prefix, value in (
        (CALENDAR_STYLE_PREFIX, display.calendar_style),
        (SHOW_OVERVIEW_PREFIX, bool(display.show_overview)),
        (SEARCH_PINNED_PREFIX, bool(display.search_pinned)),
    ):
        key = display_key(prefix, layout_id)
        if settings.value(key, None) is None:
            settings.setValue(key, value)
            changed = True
    return changed


def _migrate_layout(settings, user_styles_path: Path) -> bool:
    old, new_id, display = _resolve(settings, user_styles_path)
    changed = False
    retired = old in RETIRED_LAYOUTS or old.startswith(_USER_LAYOUT_PREFIX)
    if retired:
        changed |= _put(settings, LAYOUT_LEGACY_KEY, old)
        if display is None:
            display = default_layout_display(get_widget_mode_layout(new_id))
        changed |= _put_display_if_missing(settings, new_id, display)
        for template in (
            geometry_key("{}"),
            geometry_key("{}") + "_calendar_hidden",
            "unified_widget_size_{}",
            "unified_widget_size_{}_calendar_hidden",
        ):
            value = settings.value(template.format(old), None)
            if value is not None:
                changed |= _put(settings, template.format(new_id), value)
        visible = read_widget_calendar_visibility(settings, old)
        changed |= _put(settings, calendar_visibility_key(new_id), visible)
    changed |= _put(settings, _LAYOUT_KEY, new_id)
    return changed


def _fill_kept_display_defaults(settings) -> bool:
    changed = False
    for layout_id in KEPT_LAYOUT_IDS:
        default = default_layout_display(get_widget_mode_layout(layout_id))
        if any(
            settings.value(display_key(prefix, layout_id), None) is None
            for prefix in (CALENDAR_STYLE_PREFIX, SHOW_OVERVIEW_PREFIX, SEARCH_PINNED_PREFIX)
        ):
            changed |= _put_display_if_missing(settings, layout_id, default)
    return changed


def _migrate_surface(settings) -> bool:
    current = settings.value(SURFACE_SETTING_KEY, None)
    if str(current or "").strip():
        return False
    skin_id = _normalized_id(settings.value(_SKIN_KEY, None))
    settings.setValue(SURFACE_SETTING_KEY, SKIN_SURFACES.get(skin_id, DEFAULT_SURFACE))
    return True


def _working_free_layout(settings) -> dict | None:
    raw = settings.value(FREE_LAYOUT_SETTING_KEY, None)
    if raw is None:
        return None
    try:
        return validate_free_layout(json.loads(raw) if isinstance(raw, str) else raw)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return None


def _library_is_untouchable(settings, presets: list) -> bool:
    """An unreadable stored library reads as empty; never overwrite it."""
    raw = settings.value(USER_LAYOUT_PRESETS_KEY, None)
    if presets or raw is None:
        return False
    try:
        envelope = json.loads(raw) if isinstance(raw, str) else raw
        return not (isinstance(envelope, dict) and envelope.get("presets") == [])
    except (TypeError, ValueError, RecursionError):
        return True


def _preserve_free_layout(settings, preserved_name: str) -> bool:
    layout = _working_free_layout(settings)
    if layout is None:
        return False
    presets = read_layout_presets(settings)
    if any(preset["layout"] == layout for preset in presets):
        return False
    if _library_is_untouchable(settings, presets):
        logger.warning("Saved layout library is unreadable; free layout not preserved")
        return False
    if len(presets) >= MAX_LAYOUT_PRESETS:
        logger.warning("Saved layout library is full; free layout not preserved")
        return False
    taken = {preset["name"].casefold() for preset in presets}
    name, number = preserved_name, 1
    while name.casefold() in taken:
        number += 1
        suffix = f" {number}"
        name = preserved_name[: MAX_PRESET_NAME_LENGTH - len(suffix)] + suffix
    presets, _ = create_layout_preset(presets, name, layout)
    write_layout_presets(settings, presets)
    return True


def migrate_widget_mode_settings(
    settings,
    *,
    user_styles_path: Path | None = None,
    preserved_name: str = "이전 자유 구성",
) -> bool:
    """Rewrite saved settings to the new catalog. Returns True if anything was written."""
    path = user_styles_path if user_styles_path is not None else USER_STYLES_PATH
    changed = _migrate_layout(settings, path)
    changed |= _fill_kept_display_defaults(settings)
    changed |= _migrate_surface(settings)
    changed |= _preserve_free_layout(settings, preserved_name)
    return changed


__all__ = [
    "KEPT_LAYOUT_IDS",
    "LAYOUT_LEGACY_KEY",
    "LEGACY_SKIN_LAYOUTS",
    "RETIRED_LAYOUTS",
    "SKIN_SURFACES",
    "classify_user_layout",
    "migrate_widget_mode_settings",
]
