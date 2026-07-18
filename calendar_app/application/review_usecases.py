"""Daily/weekly review summaries for schedule, routine, and directive work."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from calendar_app.domain.task_status_view import normalize_status


def _parse_date(date_str: str) -> datetime.date:
    return datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()


def _to_day(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:10]


def _is_completed(task: dict) -> bool:
    status = normalize_status(task.get("status"))
    return status == "completed" or int(task.get("is_completed") or 0) == 1


def _is_overdue(task: dict, date_str: str) -> bool:
    if _is_completed(task):
        return False
    deadline_day = _to_day(task.get("deadline")) or _to_day(task.get("target_date"))
    if not deadline_day:
        return False
    return deadline_day < date_str


def _normalize_task_row(row) -> dict:
    task = dict(row or {})
    task.setdefault("type", str(task.get("type") or "schedule").lower())
    return task


def _normalize_event_row(row) -> dict:
    values = list(row or [])
    return {
        "id": values[0] if len(values) > 0 else None,
        "name": values[1] if len(values) > 1 else "",
        "priority": values[2] if len(values) > 2 else "normal",
        "deadline": values[3] if len(values) > 3 else None,
        "end_date": values[4] if len(values) > 4 else None,
        "status": "in_progress",
        "type": "schedule",
    }


def _normalize_directive_row(row) -> dict:
    if isinstance(row, dict):
        directive = dict(row)
        directive["type"] = "directive"
        directive.setdefault("priority", "normal")
        directive.setdefault("status", "pending")
        return directive

    values = list(row or [])
    return {
        "id": values[0] if len(values) > 0 else None,
        "content": values[1] if len(values) > 1 else "",
        "status": values[2] if len(values) > 2 else "pending",
        "receiver_name": values[3] if len(values) > 3 else "",
        "deadline": values[4] if len(values) > 4 else None,
        "memo": values[5] if len(values) > 5 else "",
        "bg_color": values[6] if len(values) > 6 else None,
        "priority": values[7] if len(values) > 7 else "normal",
        "type": "directive",
    }


def _load_task_rows(repo, date_str: str) -> list[dict]:
    if hasattr(repo, "get_all_tasks_by_date"):
        return [_normalize_task_row(row) for row in (repo.get_all_tasks_by_date(date_str) or [])]
    if hasattr(repo, "get_calendar_events"):
        return [_normalize_event_row(row) for row in (repo.get_calendar_events(date_str) or [])]
    return []


def _load_directive_rows(repo, date_str: str) -> list[dict]:
    if repo is None:
        return []
    if hasattr(repo, "get_directives_by_date"):
        return [
            _normalize_directive_row(row) for row in (repo.get_directives_by_date(date_str) or [])
        ]
    if hasattr(repo, "get_recent_directives"):
        rows = []
        for row in repo.get_recent_directives(limit=200) or []:
            normalized = _normalize_directive_row(row)
            if _to_day(normalized.get("deadline")) == date_str:
                rows.append(normalized)
        return rows
    return []


def _collect_rows(repo, date_str: str, directive_repo=None) -> list[dict]:
    rows = _load_task_rows(repo, date_str)
    directive_source = directive_repo if directive_repo is not None else repo
    rows.extend(_load_directive_rows(directive_source, date_str))
    return rows


def _row_key(row: dict, fallback_idx: int) -> tuple[str, object]:
    row_type = str(row.get("type") or "schedule").lower()
    row_id = row.get("id")
    if row_id is None:
        return row_type, f"fallback:{fallback_idx}"
    return row_type, row_id


def _build_summary(rows: Iterable[dict], date_str: str) -> dict:
    row_list = [dict(r or {}) for r in (rows or [])]
    total = len(row_list)
    completed = sum(1 for r in row_list if _is_completed(r))
    deferred = sum(1 for r in row_list if normalize_status(r.get("status")) == "deferred")
    in_progress = sum(1 for r in row_list if normalize_status(r.get("status")) == "in_progress")
    pending = sum(1 for r in row_list if normalize_status(r.get("status")) == "pending")
    overdue = sum(1 for r in row_list if _is_overdue(r, date_str))
    high_priority = sum(
        1 for r in row_list if str(r.get("priority") or "").lower() in {"high", "urgent"}
    )
    schedule_count = sum(1 for r in row_list if str(r.get("type") or "").lower() == "schedule")
    routine_count = sum(1 for r in row_list if str(r.get("type") or "").lower() == "routine")
    directive_count = sum(1 for r in row_list if str(r.get("type") or "").lower() == "directive")
    completion_rate = round((completed / total) * 100.0, 1) if total else 0.0
    return {
        "date": date_str,
        "total": total,
        "completed": completed,
        "pending": pending,
        "in_progress": in_progress,
        "deferred": deferred,
        "overdue": overdue,
        "high_priority": high_priority,
        "schedule": schedule_count,
        "routine": routine_count,
        "directive": directive_count,
        "completion_rate": completion_rate,
    }


def build_daily_review(repo, date_str: str, directive_repo=None) -> dict:
    day = _parse_date(date_str)
    normalized = day.strftime("%Y-%m-%d")
    rows = _collect_rows(repo, normalized, directive_repo=directive_repo)
    return _build_summary(rows, normalized)


def build_weekly_review(repo, week_start_str: str, days: int = 7, directive_repo=None) -> dict:
    start_day = _parse_date(week_start_str)
    span = max(1, int(days or 7))
    daily = []
    unique_rows: dict[tuple[str, object], dict] = {}

    for offset in range(span):
        day = start_day + timedelta(days=offset)
        day_str = day.strftime("%Y-%m-%d")
        rows = _collect_rows(repo, day_str, directive_repo=directive_repo)
        daily.append(_build_summary(rows, day_str))
        for idx, row in enumerate(rows or []):
            key = _row_key(row, idx)
            if key not in unique_rows:
                unique_rows[key] = dict(row or {})

    summary = _build_summary(
        unique_rows.values(), (start_day + timedelta(days=span - 1)).strftime("%Y-%m-%d")
    )
    return {
        "period_start": start_day.strftime("%Y-%m-%d"),
        "period_end": (start_day + timedelta(days=span - 1)).strftime("%Y-%m-%d"),
        "days": daily,
        "summary": summary,
    }
