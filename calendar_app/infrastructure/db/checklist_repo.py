"""Checklist-focused adapter for legacy unified repository."""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository_unified as _legacy
from calendar_app.infrastructure.db._adapter_proxy import bind_proxy_exports

__all__ = bind_proxy_exports(
    globals(),
    _legacy,
    [
        "add_checklist_item",
        "toggle_checklist_item",
        "get_task_checklist_items",
        "get_task_checklist_items_for_owners",
        "set_task_checklist_display_type",
        "get_task_checklist_progress",
        "get_template_checklist_progress",
        "reset_checklist_items",
    ],
)
