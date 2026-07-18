"""Legacy task-table adapter used during staged migration."""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository as _legacy
from calendar_app.infrastructure.db._adapter_proxy import bind_proxy_exports

__all__ = bind_proxy_exports(
    globals(),
    _legacy,
    [
        "update_task_basic",
        "update_task_status",
        "insert_task",
        "save_checklist_items_for",
    ],
)
