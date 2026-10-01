# -*- coding: utf-8 -*-
"""Versioned, independent settings for freely arranged widget components."""

from copy import deepcopy
import json
import logging
import math
from numbers import Real

from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    read_widget_mode_layout_id,
)

logger = logging.getLogger(__name__)
FREE_LAYOUT_MODE_KEY = "widget_mode_layout_mode"
FREE_LAYOUT_SETTING_KEY = "widget_mode_free_layout"
CANVAS_MINIMUM_SIZE = (320, 240)
CANVAS_MAXIMUM_SIZE = (2400, 1800)
BLOCK_MINIMUM_SIZES = {
    "date": (160, 48),
    "clock": (100, 48),
    "calendar": (220, 120),
    "filters": (180, 48),
    "agenda": (180, 100),
    "schedule": (180, 100),
    "work": (180, 100),
    "directive": (180, 100),
}
BLOCK_IDS = tuple(BLOCK_MINIMUM_SIZES)


def seed_free_layout(preset_id=None):
    """Use the chosen preset as a starting point, with no persistence side effects."""
    layout = get_widget_mode_layout(preset_id)
    width, height = layout.preferred_size
    gap, margin = 12, 12
    available = width - margin * 2
    rects = {
        "date": [margin, margin, max(160, available - 112), 48],
        "clock": [width - margin - 100, margin, 100, 48],
        "calendar": [margin, 72, available, 120],
        "filters": [margin, 204, available, 72],
        "agenda": [margin, 288, available, max(100, height - 300)],
    }
    if layout.layout_id in {"dashboard", "magazine"}:
        calendar_width = max(220, int(available * 0.43))
        list_width = available - calendar_width - gap
        calendar_x, list_x = margin, margin + calendar_width + gap
        if layout.layout_id == "magazine":
            list_x, calendar_x = margin, margin + list_width + gap
        rects["calendar"] = [calendar_x, 72, calendar_width, height - 84]
        rects["filters"] = [list_x, 72, list_width, 72]
        rects["agenda"] = [list_x, 156, list_width, height - 168]
    elif layout.layout_id == "agenda_first":
        rects["filters"] = [margin, 72, available, 72]
        rects["agenda"] = [margin, 156, available, height - 300]
        rects["calendar"] = [margin, height - 132, available, 120]
    elif layout.layout_id == "minimal":
        rects["filters"] = [margin, 72, available, 72]
        rects["agenda"] = [margin, 156, available, height - 168]
    for index, block_id in enumerate(("schedule", "work", "directive")):
        rects[block_id] = [
            margin + index * 16,
            156 + index * 20,
            max(180, available - index * 16),
            max(100, height - 228),
        ]
    calendar_present = any(item[0] == "calendar" for item in layout.placements)
    return validate_free_layout(
        {
            "version": 1,
            "canvas": [width, height],
            "snap": True,
            "calendar_mode": "month" if layout.layout_id in {"dashboard", "magazine"} else "week",
            "blocks": [
                {
                    "id": block_id,
                    "enabled": block_id in {"date", "clock", "filters", "agenda"}
                    or (block_id == "calendar" and calendar_present),
                    "rect": rects[block_id],
                }
                for block_id in BLOCK_IDS
            ],
        }
    )


def _finite_integer(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError("layout coordinates must be finite numbers")
    return round(value)


def _pair(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two numbers")
    return [_finite_integer(item) for item in value]


def validate_free_layout(data):
    """Return a detached, bounded layout; reject ambiguous or unsupported data."""
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("unsupported free-layout version")
    width, height = _pair(data.get("canvas"), "canvas")
    width = max(CANVAS_MINIMUM_SIZE[0], min(CANVAS_MAXIMUM_SIZE[0], width))
    height = max(CANVAS_MINIMUM_SIZE[1], min(CANVAS_MAXIMUM_SIZE[1], height))
    if not isinstance(data.get("snap", True), bool):
        raise ValueError("snap must be a boolean")
    calendar_mode = data.get("calendar_mode", "week")
    if calendar_mode not in ("week", "month"):
        raise ValueError("calendar_mode must be week or month")
    source_blocks = data.get("blocks")
    if not isinstance(source_blocks, list):
        raise ValueError("blocks must be a list")
    blocks = {}
    for block in source_blocks:
        if not isinstance(block, dict):
            raise ValueError("each block must be an object")
        block_id = block.get("id")
        if not isinstance(block_id, str) or block_id not in BLOCK_IDS or block_id in blocks:
            raise ValueError("unknown or duplicated block")
        if not isinstance(block.get("enabled"), bool):
            raise ValueError("enabled must be a boolean")
        if not isinstance(block.get("locked", False), bool):
            raise ValueError("locked must be a boolean")
        rect = block.get("rect")
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise ValueError("rect must contain four numbers")
        x, y, block_width, block_height = map(_finite_integer, rect)
        min_width, min_height = BLOCK_MINIMUM_SIZES[block_id]
        block_width = max(min_width, min(width, block_width))
        block_height = max(min_height, min(height, block_height))
        x = max(0, min(width - block_width, x))
        y = max(0, min(height - block_height, y))
        blocks[block_id] = {
            "id": block_id,
            "enabled": block["enabled"],
            "locked": block.get("locked", False),
            "rect": [x, y, block_width, block_height],
        }
    for block_id in BLOCK_IDS:
        if block_id not in blocks:
            min_width, min_height = BLOCK_MINIMUM_SIZES[block_id]
            blocks[block_id] = {
                "id": block_id,
                "enabled": False,
                "locked": False,
                "rect": [0, 0, min_width, min_height],
            }
    order = data.get("order", list(BLOCK_IDS))
    if not isinstance(order, list) or any(
        not isinstance(item, str) or item not in BLOCK_IDS for item in order
    ):
        raise ValueError("order must contain known component ids")
    if len(order) != len(set(order)):
        raise ValueError("order cannot contain duplicated component ids")
    order = order + [block_id for block_id in BLOCK_IDS if block_id not in order]
    return {
        "version": 1,
        "canvas": [width, height],
        "snap": data.get("snap", True),
        "calendar_mode": calendar_mode,
        "order": order,
        "blocks": [blocks[block_id] for block_id in BLOCK_IDS],
    }


def read_free_layout(settings, preset_id=None):
    """Recover safely from external settings without writing a migration on read."""
    raw = settings.value(FREE_LAYOUT_SETTING_KEY, None)
    if raw is not None:
        try:
            return validate_free_layout(json.loads(raw) if isinstance(raw, str) else deepcopy(raw))
        except (TypeError, ValueError, OverflowError):
            logger.warning("Invalid free widget layout; using the saved preset as a starting point")
    preset_id = preset_id or read_widget_mode_layout_id(settings)
    result = seed_free_layout(preset_id)
    for block in result["blocks"]:
        if block["id"] == "clock":
            block["enabled"] = (
                str(settings.value("widget_mode_show_clock", "true")).lower() == "true"
            )
        elif block["id"] == "calendar":
            key = f"widget_mode_calendar_visible_{get_widget_mode_layout(preset_id).layout_id}"
            block["enabled"] = str(settings.value(key, str(block["enabled"]))).lower() == "true"
    return result


def write_free_layout(settings, data):
    """Persist only validated configuration, keeping the preset and data sources intact."""
    result = validate_free_layout(data)
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    settings.setValue(FREE_LAYOUT_SETTING_KEY, payload)
    settings.setValue(FREE_LAYOUT_MODE_KEY, "free")
    return result
