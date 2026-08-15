# -*- coding: utf-8 -*-
"""Application usecases for focus mode flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

_FOCUS_FUTURE_WINDOW_DAYS = 365


@dataclass(frozen=True)
class FocusLogEntry:
    """UI-independent representation of one persisted focus session."""

    id: int | None
    task_id: int | None
    task_name: str
    elapsed_secs: int
    logged_at: str
    task_type: str | None = None


@dataclass(frozen=True)
class FocusStatsSnapshot:
    """Today and current-month totals calculated from one log collection."""

    today_sessions: int = 0
    today_secs: int = 0
    monthly_sessions: int = 0
    monthly_secs: int = 0


@dataclass(frozen=True)
class FocusHistorySnapshot:
    """Recent entries and their aggregate statistics from one repository read."""

    entries: tuple[FocusLogEntry, ...]
    stats: FocusStatsSnapshot
    load_error: str | None = None


def normalize_focus_log_entry(row) -> FocusLogEntry | None:
    """Normalize legacy tuple rows and mapping rows to one stable shape."""
    if isinstance(row, dict):
        log_id = row.get("id")
        task_id = row.get("task_id")
        task_name = row.get("task_name")
        elapsed_secs = row.get("elapsed_secs")
        logged_at = row.get("logged_at")
        task_type = row.get("task_type")
    else:
        try:
            values = tuple(row)
        except TypeError:
            return None
        if len(values) < 5:
            return None
        log_id, task_id, task_name, elapsed_secs, logged_at = values[:5]
        task_type = values[5] if len(values) > 5 else None

    try:
        normalized_secs = max(0, int(elapsed_secs or 0))
    except (TypeError, ValueError):
        normalized_secs = 0

    return FocusLogEntry(
        id=log_id,
        task_id=task_id,
        task_name=str(task_name or ""),
        elapsed_secs=normalized_secs,
        logged_at=str(logged_at or ""),
        task_type=str(task_type) if task_type not in (None, "") else None,
    )


def get_focus_history_snapshot(
    repo, *, limit: int = 100, stats_limit: int = 5000, now: datetime | None = None
) -> FocusHistorySnapshot:
    """Fetch recent rows and use an uncapped SQL aggregate for statistics."""
    del stats_limit  # compatibility argument; aggregate stats are no longer row-capped
    fetch_limit = max(0, int(limit or 0))
    errors = []
    try:
        rows = repo.get_worklog_entries(limit=fetch_limit)
    except Exception as exc:
        errors.append(str(exc) or exc.__class__.__name__)
        rows = []

    entries = tuple(
        entry
        for entry in (normalize_focus_log_entry(row) for row in (rows or []))
        if entry is not None
    )
    try:
        reference_day = (now or datetime.now()).strftime("%Y-%m-%d")
        raw_stats = repo.get_worklog_stats(reference_day)
        if raw_stats is None:
            raise RuntimeError("focus statistics unavailable")
        stats = FocusStatsSnapshot(
            today_sessions=max(0, int(raw_stats.get("today_sessions", 0) or 0)),
            today_secs=max(0, int(raw_stats.get("today_secs", 0) or 0)),
            monthly_sessions=max(0, int(raw_stats.get("monthly_sessions", 0) or 0)),
            monthly_secs=max(0, int(raw_stats.get("monthly_secs", 0) or 0)),
        )
    except Exception as exc:
        errors.append(str(exc) or exc.__class__.__name__)
        stats = FocusStatsSnapshot()

    return FocusHistorySnapshot(
        entries=entries,
        stats=stats,
        load_error="; ".join(errors) if errors else None,
    )


def get_focus_stats_snapshot(
    repo, *, limit: int = 5000, now: datetime | None = None
) -> FocusStatsSnapshot:
    """Return focus totals; ``limit`` remains only for API compatibility."""
    return get_focus_history_snapshot(repo, limit=0, stats_limit=limit, now=now).stats


def persist_focus_log(repo, task_id: int, elapsed_secs: int) -> bool:
    """Persist focus worklog entry when data is valid."""
    if not task_id or elapsed_secs <= 0:
        return False
    return bool(repo.insert_worklog_entry(task_id, elapsed_secs))


def get_focus_logs(repo, limit: int = 50):
    """Fetch recent focus logs."""
    return repo.get_worklog_entries(limit=limit)


def delete_focus_log(repo, log_id: int) -> bool:
    """Delete a specific focus session by ID."""
    if not log_id:
        return False
    return bool(repo.delete_worklog_entry(log_id))


def _directives_as_tasks(repo) -> list[dict]:
    """Return incomplete directives formatted as task dicts."""
    tasks = []
    try:
        rows = repo.get_recent_directives(limit=200)
        for row in rows:
            # row: (id, content, status, receiver, deadline, memo, bg_color)
            did = row[0]
            content = str(row[1] or "")
            status = str(row[2] or "pending")
            if status in ("done", "completed"):
                continue
            deadline = row[4] if len(row) > 4 else None
            tasks.append(
                {
                    "id": did,
                    "name": content,
                    "priority": "normal",
                    "deadline": deadline,
                    "type": "directive",
                    "is_completed": False,
                }
            )
    except Exception:
        pass
    return tasks


def _to_day(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:10]


def _parse_day(value):
    day = _to_day(value)
    if not day:
        return None
    try:
        return datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return None


def _task_window(task: dict):
    start_day = _parse_day(task.get("deadline")) or _parse_day(task.get("target_date"))
    end_day = _parse_day(task.get("end_date")) or start_day
    return start_day, end_day


def _is_focus_candidate_in_window(
    task: dict, today_str: str, max_future_days: int = _FOCUS_FUTURE_WINDOW_DAYS
) -> bool:
    today = _parse_day(today_str)
    if today is None:
        return True

    horizon = today + timedelta(days=max(0, int(max_future_days or 0)))
    start_day, end_day = _task_window(task)

    if start_day is None and end_day is None:
        return True

    if start_day is None:
        start_day = end_day
    if end_day is None:
        end_day = start_day

    if end_day is not None and end_day < today:
        return False
    return not (start_day is not None and start_day > horizon)


def _filter_focus_candidates(
    tasks, today_str: str, max_future_days: int = _FOCUS_FUTURE_WINDOW_DAYS
):
    return [
        dict(task or {})
        for task in (tasks or [])
        if _is_focus_candidate_in_window(
            dict(task or {}), today_str, max_future_days=max_future_days
        )
    ]


def get_filtered_focus_tasks(repo, selected_filter: str, today_str: str):
    """Return focus candidate tasks by selected filter key."""
    if selected_filter == "today_and_directives":
        today_tasks = [
            t for t in repo.get_tasks_by_date(today_str) if not t.get("is_completed", False)
        ]
        directives = _directives_as_tasks(repo)
        # Deduplicate by id+type
        seen = set()
        result = []
        for item in today_tasks + directives:
            key = (item.get("type"), item.get("id"))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return _filter_focus_candidates(result, today_str)

    if selected_filter == "all":
        return _filter_focus_candidates(
            repo.get_incomplete_tasks() + _directives_as_tasks(repo), today_str
        )

    if selected_filter == "today":
        rows = repo.get_tasks_by_date(today_str)
        return _filter_focus_candidates(
            [t for t in rows if not t.get("is_completed", False)], today_str
        )

    if selected_filter == "urgent":
        rows = repo.get_incomplete_tasks()
        return _filter_focus_candidates(
            [t for t in rows if t.get("priority") in ["high", "urgent"]],
            today_str,
        )

    if selected_filter == "incomplete":
        return _filter_focus_candidates(repo.get_incomplete_tasks(), today_str)

    return []


def select_auto_focus_task(repo, today_str: str, fallback_tasks=None):
    """Select most urgent pending task, with fallback to first available list item."""
    task_id, task_name = repo.get_most_urgent_pending_task(today_str)
    if task_id:
        return task_id, task_name

    fallback_tasks = _filter_focus_candidates(fallback_tasks or [], today_str)
    if fallback_tasks:
        first = fallback_tasks[0]
        return first.get("id"), first.get("name")
    return None, None


def get_today_focus_stats(repo) -> tuple[int, int]:
    """Return (total_sessions, total_seconds) for today from the persistent store."""
    stats = get_focus_stats_snapshot(repo, limit=500)
    return stats.today_sessions, stats.today_secs


def get_monthly_focus_stats(repo) -> tuple[int, int]:
    """Return (total_sessions, total_seconds) for the current month from the persistent store."""
    stats = get_focus_stats_snapshot(repo, limit=5000)
    return stats.monthly_sessions, stats.monthly_secs
