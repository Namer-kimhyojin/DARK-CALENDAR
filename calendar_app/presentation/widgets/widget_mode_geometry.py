# -*- coding: utf-8 -*-
"""Portable geometry persistence for the unified widget-mode window."""

from __future__ import annotations

from collections.abc import Iterable
import json

from PyQt6.QtCore import QPoint, QRect, QSize


def geometry_key(layout_id: str) -> str:
    safe_id = str(layout_id or "stacked").strip() or "stacked"
    return f"unified_widget_geometry_{safe_id}"


def serialize_geometry(rect: QRect, available: QRect, screen_name: str) -> str:
    travel_x = max(1, available.width() - rect.width())
    travel_y = max(1, available.height() - rect.height())
    payload = {
        "version": 1,
        "screen": str(screen_name or ""),
        "x_ratio": (rect.x() - available.x()) / travel_x,
        "y_ratio": (rect.y() - available.y()) / travel_y,
        "width": rect.width(),
        "height": rect.height(),
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def deserialize_geometry(raw) -> dict[str, object] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    try:
        width = int(payload["width"])
        height = int(payload["height"])
        x_ratio = float(payload["x_ratio"])
        y_ratio = float(payload["y_ratio"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if width < 40 or height < 40:
        return None
    return {
        "screen": str(payload.get("screen") or ""),
        "x_ratio": min(1.0, max(0.0, x_ratio)),
        "y_ratio": min(1.0, max(0.0, y_ratio)),
        "width": width,
        "height": height,
    }


def restore_rect(payload: dict[str, object], available: QRect) -> QRect:
    width = min(int(payload["width"]), max(40, available.width()))
    height = min(int(payload["height"]), max(40, available.height()))
    travel_x = max(0, available.width() - width)
    travel_y = max(0, available.height() - height)
    x = available.x() + round(travel_x * float(payload["x_ratio"]))
    y = available.y() + round(travel_y * float(payload["y_ratio"]))
    return QRect(x, y, width, height)


def clamp_rect(rect: QRect, available: QRect) -> QRect:
    width = min(max(40, rect.width()), max(40, available.width()))
    height = min(max(40, rect.height()), max(40, available.height()))
    max_x = available.right() - width + 1
    max_y = available.bottom() - height + 1
    x = min(max(rect.x(), available.left()), max_x)
    y = min(max(rect.y(), available.top()), max_y)
    return QRect(x, y, width, height)


def best_available_geometry(
    screens: Iterable[object], *, screen_name: str = "", point: QPoint | None = None
) -> tuple[QRect, str] | None:
    screen_list = list(screens)
    if not screen_list:
        return None
    for screen in screen_list:
        if screen_name and screen.name() == screen_name:
            return QRect(screen.availableGeometry()), screen.name()
    if point is not None:
        for screen in screen_list:
            if screen.availableGeometry().contains(point):
                return QRect(screen.availableGeometry()), screen.name()
    screen = screen_list[0]
    return QRect(screen.availableGeometry()), screen.name()


def legacy_rect(position: QPoint, size: QSize, available: QRect) -> QRect:
    return clamp_rect(QRect(position, size), available)
