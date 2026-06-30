"""Routine lifecycle helpers for recurring work items."""

from __future__ import annotations

from datetime import date
import logging

from calendar_app.domain.policies import routine_policy
from calendar_app.infrastructure.db import common_repo, routine_repo, task_repo

logger = logging.getLogger(__name__)

_ROLL_OVER_MAX_STEPS = 512


def calculate_next_period(current_target_date: str, cycle_type: str, recurrence: str | None = None):
    """Return the next routine target date in YYYY-MM-DD format."""
    try:
        recurrence_rule = routine_policy.parse_recurrence_rule(recurrence)
        return routine_policy.get_next_occurrence(current_target_date, cycle_type, recurrence_rule)
    except Exception:
        logger.exception(
            "calculate_next_period failed current_target_date=%s cycle_type=%s recurrence=%s",
            current_target_date,
            cycle_type,
            recurrence,
        )
        return None


def search_routines(cycle_type=None, is_completed=None):
    """Search routine rows with optional cycle/completion filters."""
    conn = common_repo.get_connection()
    if not conn:
        return []
    cur = conn.cursor()
    clauses = ["type='routine'"]
    params = []
    if cycle_type:
        clauses.append("cycle_type=?")
        params.append(cycle_type)
    if is_completed is not None:
        clauses.append("is_completed=?")
        params.append(1 if is_completed else 0)
    where = " AND ".join(clauses)
    cur.execute(
        f"SELECT * FROM unified_task WHERE {where} ORDER BY target_date DESC, id DESC", params
    )
    return [dict(row) for row in cur.fetchall()]


def batch_complete_routines(task_ids: list[int]) -> int:
    """Mark many routines as completed and return the number updated."""
    count = 0
    for tid in task_ids:
        try:
            ok = task_repo.update_unified_task(tid, {"status": "completed", "is_completed": 1})
            if ok:
                count += 1
        except Exception:
            logger.exception("batch_complete_routines failed for id=%s", tid)
    return count


def batch_update_routine_priority(task_ids: list[int], priority: str) -> int:
    """Update many routines to the same priority."""
    count = 0
    for tid in task_ids:
        try:
            ok = task_repo.update_unified_task(tid, {"priority": priority})
            if ok:
                count += 1
        except Exception:
            logger.exception("batch_update_routine_priority failed for id=%s", tid)
    return count


def batch_delete_routines(task_ids: list[int]) -> int:
    """Delete many routines and return the number removed."""
    count = 0
    for tid in task_ids:
        try:
            ok = task_repo.delete_unified_task(tid)
            if ok:
                count += 1
        except Exception:
            logger.exception("batch_delete_routines failed for id=%s", tid)
    return count


def duplicate_routine(task_id: int, new_target_date: str, include_checklist: bool = True):
    """Copy a routine instance to a new date and return the new id."""
    try:
        original = task_repo.get_unified_task(task_id)
        if not original:
            return None
        new_id = _create_routine_instance(original, new_target_date)
        if new_id and include_checklist:
            _copy_checklist_items(task_id, new_id)
        return new_id
    except Exception:
        logger.exception("duplicate_routine failed for task_id=%s", task_id)
        return None


def ensure_overdue_routines_rollover(today_str: str | None = None) -> int:
    """Create the next current/future instance for completed overdue recurring routines.

    The startup pass only examines the latest instance for each routine lineage.
    If that latest instance is completed and already in the past, one new instance
    is created at the first occurrence on or after `today_str`.
    """
    today_str = _normalize_today(today_str)
    latest_by_identity: dict[tuple, dict] = {}

    for row in search_routines():
        if not _is_repeating_routine(row):
            continue
        target_date = _routine_target_date(row)
        if not target_date:
            continue
        identity = _routine_identity(row)
        current = latest_by_identity.get(identity)
        if current is None or _sort_key(row) > _sort_key(current):
            latest_by_identity[identity] = row

    created = 0
    for row in latest_by_identity.values():
        target_date = _routine_target_date(row)
        if not target_date or target_date >= today_str:
            continue
        if not _is_completed(row):
            continue

        rollover_date = _resolve_rollover_date(
            target_date,
            row.get("cycle_type"),
            row.get("recurrence"),
            today_str=today_str,
        )
        if not rollover_date:
            continue

        existing = _find_existing_instance(row, rollover_date)
        if existing:
            continue

        new_id = _create_routine_instance(row, rollover_date)
        if not new_id:
            continue
        _copy_checklist_items(int(row["id"]), new_id)
        created += 1

    return created


def auto_create_next_routine(task_id: int):
    """Create the immediate next occurrence for a completed recurring routine.

    Returns the created task id. If the next instance already exists, returns that
    existing id instead of creating a duplicate.
    """
    try:
        task = task_repo.get_unified_task(task_id)
        if not task or task.get("type") != "routine":
            return None
        if not _is_repeating_routine(task):
            return None

        current_target_date = _routine_target_date(task)
        if not current_target_date:
            return None

        next_date = calculate_next_period(
            current_target_date,
            str(task.get("cycle_type") or ""),
            task.get("recurrence"),
        )
        if not next_date:
            return None

        existing = _find_existing_instance(task, next_date)
        if existing:
            return existing.get("id")

        new_id = _create_routine_instance(task, next_date)
        if not new_id:
            return None

        _copy_checklist_items(task_id, new_id)
        logger.info(
            "Auto-created next routine instance source_id=%s template_id=%s next_date=%s new_id=%s",
            task_id,
            task.get("template_id"),
            next_date,
            new_id,
        )
        return new_id
    except Exception:
        logger.exception("Error in auto_create_next_routine for task_id=%s", task_id)
        return None


def _normalize_today(today_str: str | None) -> str:
    if today_str:
        return str(today_str)[:10]
    return date.today().strftime("%Y-%m-%d")


def _sort_key(task: dict) -> tuple[str, int]:
    target_date = _routine_target_date(task) or ""
    task_id = int(task.get("id") or 0)
    return target_date, task_id


def _routine_target_date(task: dict) -> str | None:
    target_date = str(task.get("target_date") or "").strip()
    if target_date:
        return target_date[:10]
    deadline = str(task.get("deadline") or "").strip()
    if deadline:
        return deadline[:10]
    return None


def _deadline_time(task: dict) -> str:
    deadline = str(task.get("deadline") or "").strip()
    if len(deadline) >= 19:
        return deadline[11:19]
    return "23:59:59"


def _is_completed(task: dict) -> bool:
    status = str(task.get("status") or "").strip().lower()
    return status == "completed" or int(task.get("is_completed") or 0) == 1


def _is_repeating_routine(task: dict) -> bool:
    cycle_type = str(task.get("cycle_type") or "").strip().lower()
    return cycle_type not in ("", "single")


def _routine_identity(task: dict) -> tuple:
    template_id = task.get("template_id")
    if template_id not in (None, ""):
        return ("template", int(template_id))
    return (
        "ad_hoc",
        str(task.get("name") or "").strip().casefold(),
        str(task.get("cycle_type") or "").strip().lower(),
        str(task.get("recurrence") or "").strip(),
        _deadline_time(task),
        str(task.get("location") or "").strip().casefold(),
        str(task.get("assignee") or "").strip().casefold(),
    )


def _find_existing_instance(task: dict, target_date: str) -> dict | None:
    cycle_type = str(task.get("cycle_type") or "").strip().lower()
    if not cycle_type:
        return None
    period_start, period_end = common_repo.calculate_period_bounds(target_date, cycle_type)
    rows = (
        routine_repo.get_routines_by_period(cycle_type, period_start, period_end=period_end) or []
    )
    source_identity = _routine_identity(task)
    for row in rows:
        if _routine_target_date(row) != target_date:
            continue
        if _routine_identity(row) == source_identity:
            return row
    return None


def _resolve_rollover_date(
    current_target_date: str,
    cycle_type: str | None,
    recurrence: str | None,
    *,
    today_str: str,
) -> str | None:
    cycle = str(cycle_type or "").strip().lower()
    next_date = current_target_date
    for _ in range(_ROLL_OVER_MAX_STEPS):
        next_date = calculate_next_period(next_date, cycle, recurrence)
        if not next_date:
            return None
        if next_date >= today_str:
            return next_date
    logger.warning(
        "Routine rollover exceeded safety limit current_target_date=%s cycle_type=%s recurrence=%s today=%s",
        current_target_date,
        cycle,
        recurrence,
        today_str,
    )
    return None


def _create_routine_instance(task: dict, target_date: str) -> int | None:
    new_task_data = {
        "name": task.get("name"),
        "type": "routine",
        "template_id": task.get("template_id"),
        "target_date": target_date,
        "cycle_type": task.get("cycle_type"),
        "recurrence": task.get("recurrence"),
        "priority": task.get("priority", "normal"),
        "icon": task.get("icon"),
        "bg_color": task.get("bg_color"),
        "description": task.get("description"),
        "memo": task.get("memo"),
        "location": task.get("location"),
        "assignee": task.get("assignee"),
        "deadline": f"{target_date} {_deadline_time(task)}",
        "is_completed": 0,
        "status": "in_progress",
        "gcal_event_id": None,
        "gcal_dirty": 1,
    }
    return task_repo.create_unified_task(new_task_data)


def _copy_checklist_items(source_task_id: int, target_task_id: int) -> None:
    try:
        items = task_repo.get_task_checklist_items(source_task_id)
        for item in items:
            task_repo.add_checklist_item(
                target_task_id,
                item.get("item_text"),
                item.get("item_order", 0),
                item.get("display_type", "list"),
            )
    except Exception:
        logger.exception(
            "Failed to copy checklist items source_id=%s target_id=%s",
            source_task_id,
            target_task_id,
        )
