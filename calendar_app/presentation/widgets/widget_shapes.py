# -*- coding: utf-8 -*-
"""Shared visual shape choices for overlay widgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WidgetShape:
    shape_id: str
    label_key: str
    label_default: str
    radius: int
    margins: tuple[int, int, int, int]
    aspect_ratio: float | None = None


DEFAULT_WIDGET_SHAPE_ID = "card"

_SHAPES = (
    WidgetShape("card", "widget.shape.card", "Card", 18, (20, 12, 20, 12)),
    WidgetShape("capsule", "widget.shape.capsule", "Capsule", 64, (26, 12, 26, 12)),
    WidgetShape("circle", "widget.shape.circle", "Circle", 160, (28, 24, 28, 24), 1.0),
    WidgetShape("poster", "widget.shape.poster", "Poster", 10, (18, 24, 18, 24), 0.72),
)
_SHAPE_BY_ID = {shape.shape_id: shape for shape in _SHAPES}


def widget_shapes() -> tuple[WidgetShape, ...]:
    return _SHAPES


def get_widget_shape(shape_id: object) -> WidgetShape:
    normalized = str(shape_id or "").strip().lower()
    return _SHAPE_BY_ID.get(normalized, _SHAPE_BY_ID[DEFAULT_WIDGET_SHAPE_ID])


__all__ = [
    "DEFAULT_WIDGET_SHAPE_ID",
    "WidgetShape",
    "get_widget_shape",
    "widget_shapes",
]
