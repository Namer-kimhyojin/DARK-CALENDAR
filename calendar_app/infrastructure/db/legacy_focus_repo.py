"""Legacy focus/worklog adapter for staged migration."""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository as _legacy
from calendar_app.infrastructure.db._adapter_proxy import bind_proxy_exports

__all__ = bind_proxy_exports(
    globals(),
    _legacy,
    [
        "get_worklog_entries",
        "insert_worklog_entry",
        "delete_worklog_entry",
        "get_incomplete_tasks",
        "get_tasks_by_date",
        "get_most_urgent_pending_task",
        "get_recent_directives",
    ],
)
