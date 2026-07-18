"""Infrastructure bootstrap compatibility module."""

from __future__ import annotations

from calendar_app.infrastructure.runtime.infra_wiring import (
    setup_app_infrastructure,
    toggle_fullscreen,
    toggle_overlay,
)

__all__ = ["setup_app_infrastructure", "toggle_overlay", "toggle_fullscreen"]
