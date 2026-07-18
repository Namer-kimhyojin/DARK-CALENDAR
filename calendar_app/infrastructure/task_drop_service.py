# -*- coding: utf-8 -*-
"""Shared task drop move/copy logic used by UI and sync flows."""

from __future__ import annotations

from datetime import datetime
import logging

from calendar_app.infrastructure.db import calendar_repo, task_repo
from calendar_app.infrastructure.db import db_repository_unified as _dbu

logger = logging.getLogger(__name__)


def _qdate_to_str(value):
    if hasattr(value, "toString"):
        return value.toString("yyyy-MM-dd")
    return str(value)[:10]


def _qtime_to_hhmmss(value):
    if value is None:
        return None
    if hasattr(value, "toString"):
        return value.toString("HH:mm:00")
    s = str(value)
    if len(s) == 5:
        return f"{s}:00"
    return s


def _apply_datetime_move(task, date_str, time_str):
    updates = {"target_date": date_str}
    deadline = task.get("deadline")
    if deadline:
        try:
            dt = datetime.fromisoformat(str(deadline).replace(" ", "T"))
            if time_str:
                hh, mm, ss = (time_str.split(":") + ["00", "00"])[:3]
                dt = dt.replace(hour=int(hh), minute=int(mm), second=int(ss))
            dt = datetime.combine(datetime.fromisoformat(date_str).date(), dt.time())
            updates["deadline"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            updates["deadline"] = f"{date_str} {time_str or '00:00:00'}"

    end_date = task.get("end_date")
    if end_date and deadline:
        try:
            old_deadline = datetime.fromisoformat(str(deadline).replace(" ", "T"))
            old_end = datetime.fromisoformat(str(end_date).replace(" ", "T"))
            duration = old_end - old_deadline
            new_deadline = datetime.fromisoformat(updates["deadline"].replace(" ", "T"))
            updates["end_date"] = (new_deadline + duration).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return updates


def _default_writable_calendar():
    try:
        default_row = calendar_repo.get_default_calendar()
        rows = calendar_repo.list_calendars(include_inactive=True) or []
    except Exception:
        return None

    candidates = []
    if default_row:
        candidates.append(default_row)
    candidates.extend(row for row in rows if row not in candidates)
    for row in candidates:
        if not row or not row.get("id"):
            continue
        if not row.get("is_active", True):
            continue
        if calendar_repo.is_calendar_row_read_only(row):
            continue
        return row
    return None


def _copy_calendar_route(task, read_only_by_calendar):
    calendar_id = str((task or {}).get("calendar_id") or "").strip()
    if not calendar_id:
        source_id = str(
            (task or {}).get("gcal_target_calendar_id")
            or (task or {}).get("gcal_source_calendar_id")
            or ""
        ).strip()
        if source_id:
            calendar_id = source_id if source_id.startswith("gcal::") else f"gcal::{source_id}"

    if _is_task_in_read_only_calendar(task, read_only_by_calendar):
        writable = _default_writable_calendar()
        if not writable:
            raise RuntimeError("No writable calendar is available for copied task")
        calendar_id = str(writable.get("id") or "").strip()

    target_gcal_id = None
    if calendar_id.startswith("gcal::"):
        target_gcal_id = calendar_id[len("gcal::") :] or None
    return calendar_id or None, target_gcal_id


def _clone_task(task, target_date, target_time, read_only_by_calendar, *, commit=True):
    payload = dict(task)
    for key in (
        "id",
        "gcal_event_id",
        "gcal_source_calendar_id",
        "gcal_source_summary",
        "gcal_target_calendar_id",
        "gcal_last_synced_at",
        "gcal_remote_updated_at",
        "gcal_sync_error",
        "series_id",
        "series_order",
        "series_total",
        "created_at",
        "updated_at",
    ):
        payload.pop(key, None)

    calendar_id, target_gcal_id = _copy_calendar_route(task, read_only_by_calendar)
    payload["calendar_id"] = calendar_id
    payload["gcal_target_calendar_id"] = target_gcal_id
    payload["gcal_sync_mode"] = "local_owned"
    payload["gcal_dirty"] = 1
    payload["status"] = "in_progress"
    updates = _apply_datetime_move(task, target_date, target_time)
    payload.update(updates)
    return task_repo.create_unified_task(payload, commit=commit)


def _load_tasks_by_ids(task_ids):
    if not task_ids:
        return {}
    try:
        conn = _dbu.get_connection()
        if not conn:
            return {}
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(task_ids))
        cur.execute(f"SELECT * FROM unified_task WHERE id IN ({placeholders})", task_ids)
        rows = cur.fetchall()
        result = {}
        for row in rows:
            item = dict(row)
            result[int(item["id"])] = item
        return result
    except Exception:
        return {}


def _has_effective_updates(task, updates):
    for key, new_value in updates.items():
        old_value = task.get(key)
        if str(old_value) != str(new_value):
            return True
    return False


def _normalize_task_ids(task_id_list):
    seen = set()
    ids = []
    for raw in task_id_list or []:
        try:
            task_id = int(raw)
        except (TypeError, ValueError):
            continue
        if task_id in seen:
            continue
        seen.add(task_id)
        ids.append(task_id)
    return ids


def _calendar_read_only_map():
    try:
        rows = calendar_repo.list_calendars(include_inactive=True)
    except Exception:
        rows = []
    mapping = {}
    for row in rows or []:
        cal_id = str((row or {}).get("id") or "").strip()
        if not cal_id:
            continue
        mapping[cal_id] = bool(calendar_repo.is_calendar_row_read_only(row))
    return mapping


def _is_task_in_read_only_calendar(task, read_only_by_calendar):
    task_row = task or {}
    cal_id = str(task_row.get("calendar_id") or "").strip()
    if not cal_id:
        source_cal_id = str(
            task_row.get("gcal_source_calendar_id") or task_row.get("gcal_target_calendar_id") or ""
        ).strip()
        if source_cal_id:
            cal_id = (
                source_cal_id if source_cal_id.startswith("gcal::") else f"gcal::{source_cal_id}"
            )
    if not cal_id:
        return False
    if cal_id in read_only_by_calendar:
        return bool(read_only_by_calendar.get(cal_id))
    return bool(calendar_repo.is_calendar_read_only(cal_id))


def _finalize_drop(app, changed):
    if hasattr(app, "_is_dragging"):
        app._is_dragging = False
    if changed > 0 and hasattr(app, "schedule_panel_refresh"):
        if hasattr(app, "_drag_pending_refresh"):
            app._drag_pending_refresh = False
        # Clear dragging state first so refresh is not deferred by the scheduler.
        app.schedule_panel_refresh(left=True, center=True, right=False)
    elif getattr(app, "_drag_pending_refresh", False) and hasattr(app, "schedule_panel_refresh"):
        # If refresh was deferred during drag, flush it right after drag ends.
        app._drag_pending_refresh = False
        app.schedule_panel_refresh(left=True, center=True, right=False)


def finalize_task_drag(app, changed=0):
    """Finish a drag session and flush refreshes deferred while dragging."""
    _finalize_drop(app, changed)


def handle_task_drop(app, task_id_list, target_date, target_time, action):
    if app is not None:
        app._last_drop_blocked_readonly_ids = []
        app._last_drop_failed_ids = []

    ids = _normalize_task_ids(task_id_list)
    if not ids:
        _finalize_drop(app, 0)
        return 0, []

    action_str = str(action or "").strip().lower()
    if action_str not in {"move", "copy"}:
        _finalize_drop(app, 0)
        return 0, []

    target_date_str = _qdate_to_str(target_date)
    target_time_str = _qtime_to_hhmmss(target_time)
    task_map = _load_tasks_by_ids(ids)
    read_only_by_calendar = _calendar_read_only_map()
    conn = _dbu.get_connection()
    if conn is None:
        _finalize_drop(app, 0)
        return 0, []

    changed = 0
    copied_ids = []
    blocked_readonly_ids = []
    try:
        for task_id in ids:
            task = task_map.get(task_id) or task_repo.get_unified_task(task_id)
            if not task:
                continue
            if action_str == "copy":
                new_id = _clone_task(
                    task,
                    target_date_str,
                    target_time_str,
                    read_only_by_calendar,
                    commit=False,
                )
                if not new_id:
                    raise RuntimeError(f"Failed to copy task {task_id}")
                changed += 1
                copied_ids.append(new_id)
                continue

            if _is_task_in_read_only_calendar(task, read_only_by_calendar):
                blocked_readonly_ids.append(task_id)
                continue

            updates = _apply_datetime_move(task, target_date_str, target_time_str)
            if not _has_effective_updates(task, updates):
                continue
            if not task_repo.update_unified_task(task_id, updates, commit=False):
                raise RuntimeError(f"Failed to move task {task_id}")
            changed += 1
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception(
            "Task drop transaction rolled back action=%s task_ids=%s",
            action_str,
            ids,
        )
        changed = 0
        copied_ids = []
        if app is not None:
            app._last_drop_failed_ids = list(ids)

    if app is not None:
        app._last_drop_blocked_readonly_ids = blocked_readonly_ids

    _finalize_drop(app, changed)
    return changed, copied_ids
