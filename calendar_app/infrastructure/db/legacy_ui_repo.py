"""Legacy UI adapter for dialogs/panels during staged migration."""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository as _legacy
from calendar_app.infrastructure.db._adapter_proxy import bind_proxy_exports

__all__ = list(
    bind_proxy_exports(
        globals(),
        _legacy,
        [
            "get_task_by_id",
            "update_task_basic",
            "delete_task",
            "update_task_status",
            "get_all_checklists",
            "get_checklist_items",
            "save_checklist",
            "delete_checklist",
            "apply_checklist_to",
            "get_checklist_for",
            "save_checklist_items_for",
            "toggle_checklist_item",
            "get_routine_templates",
            "save_routine_template_unified",
            "delete_routine_template",
            "get_routine_status",
            "get_routine_steps",
            "toggle_routine_step",
            "save_routine_task",
            "get_routine_task",
            "delete_routine_task",
        ],
    )
)


def get_recent_routine_tasks(limit=100):
    conn = _legacy.get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, target_date, is_completed, cycle_type
            FROM routine_task
            ORDER BY target_date DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return cur.fetchall()
    except Exception:
        return []


__all__.append("get_recent_routine_tasks")
