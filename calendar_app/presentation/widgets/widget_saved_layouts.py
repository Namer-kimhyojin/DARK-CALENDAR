# -*- coding: utf-8 -*-
"""Saved layout setups: a built-in layout plus its display options, under a name.

They live in their own key, apart from the free-layout presets
(``widget_mode_user_layout_presets``), whose strict schema older app versions
validate: mixing a new kind into that list would make those versions drop the
whole library. Here a malformed entry is skipped, never the whole list.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from uuid import uuid4

from calendar_app.presentation.widgets.widget_mode_display import (
    LayoutDisplay,
    read_layout_display,
    write_layout_display,
)
from calendar_app.presentation.widgets.widget_mode_skins import get_widget_mode_layout
from calendar_app.presentation.widgets.widget_mode_visibility import (
    read_widget_calendar_visibility,
    write_widget_calendar_visibility,
)

logger = logging.getLogger(__name__)

SAVED_SETUPS_KEY = "widget_mode_saved_setups"
SELECTED_SETUP_KEY = "widget_mode_saved_setup_id"
MAX_SETUPS = 50
MAX_NAME_LENGTH = 80
_KEPT_LAYOUTS = ("stacked", "dashboard", "work_board", "minimal")
_CALENDAR_STYLES = ("week", "month")


def _clean_name(name) -> str:
    if not isinstance(name, str):
        raise ValueError("setup name must be text")
    if any(unicodedata.category(ch) in {"Cc", "Cf", "Cs"} for ch in name):
        raise ValueError("setup name cannot contain control characters")
    result = name.strip()
    if not result or len(result) > MAX_NAME_LENGTH:
        raise ValueError("setup name must contain 1 to 80 characters")
    return result


def _clean_setup(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    try:
        setup_id = str(raw["id"])
        if not setup_id.startswith("setup_") or len(setup_id) != 38:
            return None
        layout_id = str(raw["layout_id"])
        if layout_id not in _KEPT_LAYOUTS:
            return None
        style = str(raw.get("calendar_style", "week"))
        return {
            "id": setup_id,
            "name": _clean_name(raw["name"]),
            "layout_id": layout_id,
            "calendar_style": style if style in _CALENDAR_STYLES else "week",
            "show_overview": bool(raw.get("show_overview", False)),
            "search_pinned": bool(raw.get("search_pinned", False)),
            "calendar_visible": bool(raw.get("calendar_visible", True)),
        }
    except (KeyError, TypeError, ValueError):
        return None


def read_saved_setups(settings) -> list[dict]:
    raw = settings.value(SAVED_SETUPS_KEY, None)
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        logger.warning("Unreadable saved widget layouts; showing none")
        return []
    items = data.get("setups", []) if isinstance(data, dict) else []
    result, names = [], set()
    for item in items if isinstance(items, list) else []:
        setup = _clean_setup(item)
        if setup is None or setup["name"].casefold() in names:
            continue
        names.add(setup["name"].casefold())
        result.append(setup)
    return result[:MAX_SETUPS]


def write_saved_setups(settings, setups: list[dict]) -> list[dict]:
    cleaned = [setup for setup in (_clean_setup(item) for item in setups) if setup]
    settings.setValue(
        SAVED_SETUPS_KEY,
        json.dumps({"version": 1, "setups": cleaned[:MAX_SETUPS]}, ensure_ascii=False),
    )
    return cleaned


def capture_setup(settings, name: str, layout_id: str) -> dict:
    """The current options of ``layout_id`` as a new, unsaved setup."""
    layout = get_widget_mode_layout(layout_id)
    display = read_layout_display(settings, layout)
    return {
        "id": "setup_" + uuid4().hex,
        "name": _clean_name(name),
        "layout_id": layout.layout_id,
        "calendar_style": display.calendar_style,
        "show_overview": display.show_overview,
        "search_pinned": display.search_pinned,
        "calendar_visible": read_widget_calendar_visibility(settings, layout.layout_id),
    }


def add_setup(setups: list[dict], setup: dict) -> list[dict]:
    if len(setups) >= MAX_SETUPS:
        raise ValueError("too many saved layouts")
    if any(item["name"].casefold() == setup["name"].casefold() for item in setups):
        raise ValueError("duplicate name")
    return [*setups, setup]


def rename_setup(setups: list[dict], setup_id: str, name: str) -> list[dict]:
    name = _clean_name(name)
    if any(
        item["id"] != setup_id and item["name"].casefold() == name.casefold() for item in setups
    ):
        raise ValueError("duplicate name")
    return [dict(item, name=name) if item["id"] == setup_id else item for item in setups]


def delete_setup(setups: list[dict], setup_id: str) -> list[dict]:
    return [item for item in setups if item["id"] != setup_id]


def find_setup(setups: list[dict], setup_id: str) -> dict | None:
    return next((item for item in setups if item["id"] == setup_id), None)


def write_setup_options(settings, setup: dict) -> None:
    """Write a setup's options into the per-layout keys (does not switch layout)."""
    write_layout_display(
        settings,
        setup["layout_id"],
        LayoutDisplay(setup["calendar_style"], setup["show_overview"], setup["search_pinned"]),
    )
    write_widget_calendar_visibility(settings, setup["layout_id"], setup["calendar_visible"])


def setup_matches(settings, setup: dict, layout_id: str) -> bool:
    """True when ``layout_id`` with its current options is exactly this setup."""
    if setup["layout_id"] != layout_id:
        return False
    display = read_layout_display(settings, get_widget_mode_layout(layout_id))
    return (
        display.calendar_style == setup["calendar_style"]
        and display.show_overview == setup["show_overview"]
        and display.search_pinned == setup["search_pinned"]
        and read_widget_calendar_visibility(settings, layout_id) == setup["calendar_visible"]
    )
