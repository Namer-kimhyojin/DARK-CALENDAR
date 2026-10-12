# -*- coding: utf-8 -*-
"""Pure timing helpers and guarded schedule edits for the weekly time planner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, time, timedelta, tzinfo
import math
from numbers import Real
from typing import Any

MINIMUM_DURATION_MINUTES = 15


def _enabled(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "none", "null"}
    return bool(value)


def _timed_datetime(value: object, local_timezone: tzinfo | None) -> datetime | None:
    """Convert an external instant to a naive local datetime, preserving seconds."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        # Date-only entries belong in the all-day area, even without a stored flag.
        if len(text) <= 10:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(local_timezone).replace(tzinfo=None)
    return parsed


def normalized_task_interval(
    task: Mapping[str, Any], *, local_timezone: tzinfo | None = None
) -> tuple[datetime, datetime] | None:
    """Return a timed row's local interval, or None for all-day/undated rows.

    Naive stored datetimes already represent the application's local wall time.
    Offset-aware API values are converted using the OS local zone unless a zone
    is injected. A missing or unusable end is displayed as a 15-minute block.
    """
    if _enabled(task.get("all_day")):
        return None
    start = _timed_datetime(
        task.get("_start_raw") or task.get("deadline") or task.get("start_time"), local_timezone
    )
    if start is None:
        return None
    end = _timed_datetime(
        task.get("_end_raw") or task.get("end_date") or task.get("end_time"), local_timezone
    )
    if end is None or end <= start:
        try:
            end = start + timedelta(minutes=MINIMUM_DURATION_MINUTES)
        except OverflowError:
            return None
    return start, end


def _calendar_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("A valid ISO date is required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("A valid ISO date is required") from exc
    if parsed.isoformat() != value:
        raise ValueError("A valid ISO date is required")
    return parsed


def split_task_into_day_segments(
    task: Mapping[str, Any],
    week_start: str | date,
    *,
    local_timezone: tzinfo | None = None,
) -> list[dict[str, Any]]:
    """Clip a timed interval to seven visible days with exclusive midnight ends."""
    interval = normalized_task_interval(task, local_timezone=local_timezone)
    if interval is None:
        return []
    first_date = _calendar_date(week_start)
    start, end = interval
    duration_minutes = (end - start).total_seconds() / 60
    segments = []
    for index in range(7):
        try:
            day_start = datetime.combine(first_date + timedelta(days=index), time.min)
            day_end = day_start + timedelta(days=1)
        except OverflowError:
            break
        clipped_start = max(start, day_start)
        clipped_end = min(end, day_end)
        if clipped_start >= clipped_end:
            continue
        segments.append(
            {
                "date": day_start.date().isoformat(),
                "start_minutes": (clipped_start - day_start).total_seconds() / 60,
                "end_minutes": (clipped_end - day_start).total_seconds() / 60,
                "offset_minutes": (clipped_start - start).total_seconds() / 60,
                "duration_minutes": duration_minutes,
                "continues_before": start < day_start,
                "continues_after": end > day_end,
                "task": task,
            }
        )
    return segments


def _minutes(value: Real, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{field} must be finite minutes")
    return float(value)


def build_week_schedule_updates(
    task: Mapping[str, Any],
    date_str: str,
    start_minutes: Real,
    duration_minutes: Real,
    *,
    minimum_duration_minutes: Real = MINIMUM_DURATION_MINUTES,
) -> dict[str, Any]:
    """Build a single update, retaining calendar ownership and a full timed span.

    Interactions create/resize blocks of at least 15 minutes. The guarded move
    usecase can explicitly lower this minimum to retain an existing short event.
    Multi-day durations are allowed; only datetime's date bounds limit the end.
    """
    target_date = _calendar_date(date_str)
    start_value = _minutes(start_minutes, "start_minutes")
    duration_value = _minutes(duration_minutes, "duration_minutes")
    minimum_value = _minutes(minimum_duration_minutes, "minimum_duration_minutes")
    if not 0 <= start_value < 1440:
        raise ValueError("start_minutes must be within the selected day")
    if minimum_value <= 0 or duration_value < minimum_value:
        raise ValueError("duration_minutes is shorter than the permitted minimum")
    try:
        start = datetime.combine(target_date, time.min) + timedelta(minutes=start_value)
        end = start + timedelta(minutes=duration_value)
    except OverflowError as exc:
        raise ValueError("The schedule exceeds supported date bounds") from exc
    if end <= start:
        raise ValueError("The schedule must end after it starts")
    return {
        "deadline": start.isoformat(sep=" "),
        "end_date": end.isoformat(sep=" "),
        "target_date": target_date.isoformat(),
        "all_day": 0,
        "calendar_id": task.get("calendar_id"),
    }


def scheduling_block_reason(task: Mapping[str, Any]) -> str | None:
    """Describe restrictions visible on a row without performing a DB lookup."""
    if any(_enabled(task.get(key)) for key in ("read_only", "is_read_only", "is_subscription")):
        return "read_only"
    if str(task.get("calendar_id") or "").strip().startswith("ics::"):
        return "read_only"
    recurrence = str(task.get("recurrence") or "").strip().lower()
    nonrecurring = {"", "none", "null", "false", "0", "{}", "[]", "mode=single"}
    if recurrence not in nonrecurring:
        return "recurring"
    if any(
        task.get(key)
        for key in (
            "gcal_recurring_series_id",
            "gcal_instance_original_start",
            "gcal_recurrence_rule",
            "gcal_original_start",
            "recurring_event_id",
            "recurrence_id",
            "series_id",
        )
    ):
        return "recurring"
    cycle = str(task.get("cycle_type") or "").strip().lower()
    if cycle not in {"", "single", "none"}:
        return "recurring"
    return None


def _permission_calendar_id(task: Mapping[str, Any]) -> str | None:
    calendar_id = str(task.get("calendar_id") or "").strip()
    if calendar_id:
        return calendar_id
    gcal_id = str(
        task.get("gcal_source_calendar_id") or task.get("gcal_target_calendar_id") or ""
    ).strip()
    if not gcal_id:
        return None
    return gcal_id if gcal_id.startswith("gcal::") else f"gcal::{gcal_id}"


def reschedule_task_and_get_sync_payload(
    repo: Any,
    task_id: int,
    date_str: str,
    start_minutes: Real,
    duration_minutes: Real,
    *,
    is_calendar_read_only: Callable[[str | None], bool],
    preserve_duration: bool = False,
    local_timezone: tzinfo | None = None,
) -> dict[str, Any] | None:
    """Fresh-read, recheck permissions, save once, then return the persisted row.

    The injected repository and permission lookup keep this module independent
    of infrastructure. A move preserves the exact original duration (seconds
    included) only when the UI's ceiling-minute duration still matches the row.
    Denied, stale, missing, unchanged, and failed updates return None.
    """
    task = repo.get_unified_task(task_id)
    if not task or scheduling_block_reason(task):
        return None
    if is_calendar_read_only(_permission_calendar_id(task)):
        return None
    minimum = MINIMUM_DURATION_MINUTES
    if preserve_duration:
        interval = normalized_task_interval(task, local_timezone=local_timezone)
        if interval is None:
            return None
        exact_duration = (interval[1] - interval[0]).total_seconds() / 60
        if _minutes(duration_minutes, "duration_minutes") != math.ceil(exact_duration):
            return None
        duration_minutes = exact_duration
        minimum = min(MINIMUM_DURATION_MINUTES, exact_duration)
    updates = build_week_schedule_updates(
        task,
        date_str,
        start_minutes,
        duration_minutes,
        minimum_duration_minutes=minimum,
    )
    if all(task.get(key) == value for key, value in updates.items()):
        return None
    if not repo.update_unified_task(task_id, updates):
        return None
    return repo.get_unified_task(task_id)
