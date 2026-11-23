# -*- coding: utf-8 -*-
"""Layout registry for widget-only mode."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from calendar_app.app_paths import get_app_data_dir

if TYPE_CHECKING:
    from calendar_app.presentation.widgets.widget_mode_display import LayoutDisplay

logger = logging.getLogger(__name__)

WIDGET_MODE_LAYOUT_SETTING_KEY = "widget_mode_layout"
DEFAULT_WIDGET_MODE_LAYOUT_ID = "stacked"


@dataclass(frozen=True, slots=True)
class WidgetModeLayout:
    layout_id: str
    label_key: str
    label_default: str
    placements: tuple[tuple[str, int, int, int, int], ...]
    preferred_size: tuple[int, int] = (360, 560)
    row_stretches: tuple[tuple[int, int], ...] = ()
    column_stretches: tuple[tuple[int, int], ...] = ()
    spacing: int = 14
    content_margins: tuple[int, int, int, int] = (18, 18, 18, 18)
    hero_margins: tuple[int, int, int, int] = (16, 16, 16, 16)
    hero_spacing: int = 12
    calendar_cell_size: tuple[int, int] = (42, 54)
    calendar_spacing: int = 6
    calendar_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    filter_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    filter_spacing: int = 6
    agenda_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    agenda_spacing: int = 8
    show_eyebrow: bool = True
    show_hint: bool = True
    calendar_mode: str = "auto"
    responsive_breakpoint: int = 0
    presentation: str = "list"
    show_overview: bool = False
    searchable: bool = False

    def __post_init__(self) -> None:
        normalized_id = str(self.layout_id or "").strip().lower()
        if self.calendar_mode not in {"auto", "week", "month"} or self.presentation not in {
            "list",
            "board",
        }:
            raise ValueError("invalid workspace presentation or calendar mode")
        if not normalized_id or not normalized_id.replace("_", "").isalnum():
            raise ValueError("layout_id must contain only letters, numbers, and underscores")
        valid_sections = {"hero", "calendar", "filters", "agenda"}
        seen: set[str] = set()
        for section, row, column, row_span, column_span in self.placements:
            if section not in valid_sections or section in seen:
                raise ValueError(f"invalid or duplicated layout section: {section}")
            if min(row, column) < 0 or min(row_span, column_span) < 1:
                raise ValueError("layout grid coordinates and spans must be positive")
            seen.add(section)
        if "hero" not in seen or "agenda" not in seen:
            raise ValueError("widget-mode layouts must contain hero and agenda sections")
        width, height = self.preferred_size
        if width < 300 or height < 360:
            raise ValueError("preferred_size is too small for widget mode")
        object.__setattr__(self, "layout_id", normalized_id)
        object.__setattr__(self, "placements", tuple(tuple(item) for item in self.placements))
        object.__setattr__(self, "preferred_size", (int(width), int(height)))
        for field_name in ("row_stretches", "column_stretches"):
            object.__setattr__(
                self, field_name, tuple(tuple(item) for item in getattr(self, field_name))
            )
        for field_name in (
            "content_margins",
            "hero_margins",
            "calendar_cell_size",
            "calendar_margins",
            "filter_margins",
            "agenda_margins",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


_LAYOUTS: dict[str, WidgetModeLayout] = {}
USER_STYLES_PATH = get_app_data_dir() / "widget_mode_styles.json"


def register_widget_mode_layout(layout: WidgetModeLayout, *, replace: bool = False) -> None:
    if not isinstance(layout, WidgetModeLayout):
        raise TypeError("layout must be a WidgetModeLayout")
    if layout.layout_id in _LAYOUTS and not replace:
        raise ValueError(f"widget-mode layout already registered: {layout.layout_id}")
    _LAYOUTS[layout.layout_id] = layout


# Switch for every place a layout is chosen: the 화면 형태 tab in 꾸미기, the
# 더 보기 ▸ 배치 menu and the widget manager's layout line. Hidden briefly on
# 2026-11-23 and turned back on the same day at the user's request.
LAYOUT_SELECTION_ENABLED = True


def widget_mode_layouts() -> tuple[WidgetModeLayout, ...]:
    return tuple(_LAYOUTS.values())


def get_widget_mode_layout(layout_id: object) -> WidgetModeLayout:
    normalized = str(layout_id or "").strip().lower()
    return _LAYOUTS.get(normalized, _LAYOUTS[DEFAULT_WIDGET_MODE_LAYOUT_ID])


def widget_layout_calendar_mode(
    layout: WidgetModeLayout,
    width: int | None = None,
    display: LayoutDisplay | None = None,
) -> str:
    if display is not None:
        if display.search_pinned and width is not None and width < 520:
            return "week"
        return display.calendar_style
    if layout.searchable and width is not None and width < 520:
        return "week"
    if layout.calendar_mode != "auto":
        return layout.calendar_mode
    return "month" if layout.layout_id == "dashboard" else "week"


def widget_layout_has_columns(layout: WidgetModeLayout) -> bool:
    return any(column > 0 for _section, _row, column, *_ in layout.placements)


def widget_layout_is_compact(layout: WidgetModeLayout, width: int) -> bool:
    return widget_layout_has_columns(layout) and width < (layout.responsive_breakpoint or 640)


def read_widget_mode_layout_id(settings) -> str:
    """Read the selected layout; map retired layout and legacy skin values to the four kept ones.

    This only reads. The one-time migration is what rewrites stored settings.
    """
    from calendar_app.presentation.widgets.widget_mode_migration import (
        LEGACY_SKIN_LAYOUTS,
        RETIRED_LAYOUTS,
    )

    raw = settings.value(WIDGET_MODE_LAYOUT_SETTING_KEY, None) if settings is not None else None
    normalized = str(raw or "").strip().lower()
    if normalized in _LAYOUTS:
        return normalized
    if normalized in RETIRED_LAYOUTS:
        return RETIRED_LAYOUTS[normalized][0]
    skin = (
        str(settings.value("widget_mode_skin", None) or "").strip().lower()
        if settings is not None
        else ""
    )
    legacy = LEGACY_SKIN_LAYOUTS.get(skin, DEFAULT_WIDGET_MODE_LAYOUT_ID)
    if legacy in _LAYOUTS:
        return legacy
    if legacy in RETIRED_LAYOUTS:
        return RETIRED_LAYOUTS[legacy][0]
    return DEFAULT_WIDGET_MODE_LAYOUT_ID


def write_widget_mode_layout_id(settings, layout_id: object) -> str:
    layout = get_widget_mode_layout(layout_id)
    if settings is not None:
        settings.setValue(WIDGET_MODE_LAYOUT_SETTING_KEY, layout.layout_id)
    return layout.layout_id


def _read_user_style_document(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": 1, "skins": [], "layouts": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.exception("Failed to read widget-mode user styles: %s", path)
        return {"version": 1, "skins": [], "layouts": []}
    if not isinstance(payload, dict):
        return {"version": 1, "skins": [], "layouts": []}
    for collection in ("skins", "layouts"):
        if not isinstance(payload.get(collection, []), list):
            logger.warning("Invalid widget-mode %s collection; ignoring it", collection)
            payload[collection] = []
    return payload


def _register_builtin_layouts() -> None:
    layouts = (
        WidgetModeLayout(
            "stacked",
            "widget_mode.layout_stacked",
            "세로형",
            placements=(
                ("hero", 0, 0, 1, 1),
                ("calendar", 1, 0, 1, 1),
                ("filters", 2, 0, 1, 1),
                ("agenda", 3, 0, 1, 1),
            ),
            row_stretches=((3, 1),),
        ),
        WidgetModeLayout(
            "dashboard",
            "widget_mode.layout_dashboard",
            "좌우형",
            placements=(
                ("hero", 0, 0, 1, 2),
                ("calendar", 1, 0, 2, 1),
                ("filters", 1, 1, 1, 1),
                ("agenda", 2, 1, 1, 1),
            ),
            preferred_size=(720, 520),
            row_stretches=((2, 1),),
            column_stretches=((0, 1), (1, 1)),
            hero_margins=(18, 14, 18, 14),
            hero_spacing=9,
            calendar_cell_size=(38, 50),
            calendar_spacing=5,
            calendar_margins=(12, 12, 12, 12),
            filter_margins=(10, 8, 10, 8),
            agenda_margins=(16, 14, 16, 14),
            agenda_spacing=10,
        ),
        WidgetModeLayout(
            "work_board",
            "widget_mode.layout_work_board",
            "보드형",
            placements=(
                ("hero", 0, 0, 1, 1),
                ("calendar", 1, 0, 1, 1),
                ("filters", 2, 0, 1, 1),
                ("agenda", 3, 0, 1, 1),
            ),
            preferred_size=(1080, 700),
            row_stretches=((3, 1),),
            column_stretches=((0, 1),),
            calendar_cell_size=(42, 44),
            calendar_spacing=4,
            spacing=10,
            calendar_mode="week",
            responsive_breakpoint=0,
            presentation="board",
            show_overview=True,
            searchable=True,
        ),
        WidgetModeLayout(
            "minimal",
            "widget_mode.layout_minimal",
            "목록형",
            placements=(
                ("hero", 0, 0, 1, 1),
                ("filters", 1, 0, 1, 1),
                ("agenda", 2, 0, 1, 1),
            ),
            preferred_size=(350, 500),
            row_stretches=((2, 1),),
            spacing=10,
            content_margins=(14, 14, 14, 14),
            hero_margins=(14, 12, 14, 12),
            hero_spacing=7,
            filter_margins=(8, 6, 8, 6),
            filter_spacing=5,
            agenda_margins=(10, 9, 10, 9),
            agenda_spacing=6,
            show_eyebrow=False,
            show_hint=False,
        ),
    )
    for layout in layouts:
        register_widget_mode_layout(layout)


_register_builtin_layouts()


__all__ = [
    "DEFAULT_WIDGET_MODE_LAYOUT_ID",
    "WIDGET_MODE_LAYOUT_SETTING_KEY",
    "WidgetModeLayout",
    "get_widget_mode_layout",
    "read_widget_mode_layout_id",
    "register_widget_mode_layout",
    "widget_mode_layouts",
    "write_widget_mode_layout_id",
]
