"""Application usecases for focus mode flows."""

from __future__ import annotations

from datetime import datetime, timedelta

_FOCUS_FUTURE_WINDOW_DAYS = 365


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
    try:
        from datetime import datetime

        today = datetime.now().date()
        sessions = 0
        total_secs = 0

        # get_worklog_entries returns (id, task_id, task_name, elapsed_secs, logged_at)
        logs = repo.get_worklog_entries(limit=500)
        for log in logs:
            try:
                dt_str = str(log[4] or "")
                log_date = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
                if log_date == today:
                    sessions += 1
                    total_secs += int(log[3] or 0)
            except Exception:
                continue
        return sessions, total_secs
    except Exception as e:
        print(f"Error for get_today_focus_stats: {e}")
        return 0, 0


def get_monthly_focus_stats(repo) -> tuple[int, int]:
    """Return (total_sessions, total_seconds) for the current month from the persistent store."""
    try:
        from datetime import datetime

        today = datetime.now().date()
        sessions = 0
        total_secs = 0

        logs = repo.get_worklog_entries(limit=5000)
        for log in logs:
            try:
                dt_str = str(log[4] or "")
                log_date = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
                if log_date.year == today.year and log_date.month == today.month:
                    sessions += 1
                    total_secs += int(log[3] or 0)
            except Exception:
                continue
        return sessions, total_secs
    except Exception as e:
        print(f"Error for get_monthly_focus_stats: {e}")
        return 0, 0
