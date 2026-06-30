"""Presentation wrapper for shared UI shape tokens."""

from __future__ import annotations

from calendar_app.shared.theme_snapshot import (
    build_shape_tokens,
    invalidate_shape_tokens,
    set_shape_preset,
)


def get_ui_shape_tokens(settings=None) -> dict:
    """Return a copy of active shape tokens."""
    return build_shape_tokens(settings=settings)


def invalidate_ui_shape_tokens():
    """Clear in-memory token cache."""
    invalidate_shape_tokens()


def set_ui_shape_preset(preset: str, settings=None):
    """Persist shape preset and invalidate cache."""
    set_shape_preset(preset, settings=settings)
