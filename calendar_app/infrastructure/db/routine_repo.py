"""Routine-focused adapter for legacy unified repository."""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository_unified as _legacy
from calendar_app.infrastructure.db._adapter_proxy import bind_proxy_exports

__all__ = bind_proxy_exports(
    globals(),
    _legacy,
    [
        "get_routines_by_period",
        "get_all_routines_grouped_by_cycle",
        "mark_routine_completed",
        "mark_routine_incomplete",
        "get_routine_templates",
        "get_routine_template",
        "get_routine_completion_stats",
    ],
)
