"""Shared payload validation/normalization for unified task flows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from calendar_app.domain.task_status_view import CANONICAL_STATUSES, normalize_status

ALLOWED_TASK_TYPES = {"schedule", "routine"}
ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}
ALLOWED_CYCLE_TYPES = {
    "single",
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "half_yearly",
    "yearly",
}
_LEGACY_STATUSES = {"done", "overdue", "canceled"}
_TEXT_MAX = {
    "name": 200,
    "description": 4000,
    "memo": 4000,
    "location": 255,
    "assignee": 255,
    "calendar_id": 255,
    "alarm_time": 255,
    "recurrence": 255,
    "gcal_event_id": 255,
    "gcal_source_calendar_id": 255,
    "gcal_source_summary": 255,
    "gcal_target_calendar_id": 255,
    "gcal_sync_mode": 32,
    "series_id": 64,
}


@dataclass(frozen=True)
class TaskValidationIssue:
    field: str
    code: str
    message: str


def _normalize_text(value: Any, *, max_len: int, required: bool = False) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[:max_len]
    if required and not text:
        return None
    return text


def _normalize_datetime(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, True
    text = str(value).strip()
    if not text:
        return None, True
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text[:19] if fmt.endswith("%S") else text[:16], fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S"), True
        except ValueError:
            continue
    return None, False


def _normalize_date(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, True
    text = str(value).strip()
    if not text:
        return None, True
    try:
        dt = datetime.strptime(text[:10], "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d"), True
    except ValueError:
        return None, False


def _coerce_positive_int(value: Any, *, allow_none: bool = True) -> tuple[int | None, bool]:
    if value is None:
        return (None, True) if allow_none else (None, False)
    text = str(value).strip()
    if not text:
        return (None, True) if allow_none else (None, False)
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None, False
    if iv <= 0:
        return None, False
    return iv, True


def normalize_task_payload(
    payload: Mapping[str, Any] | None,
    *,
    is_update: bool = False,
    existing_task: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[TaskValidationIssue]]:
    """Return normalized payload + validation issues.

    - `is_update=False`: create validation.
    - `is_update=True`: partial update validation (only passed keys are validated).
    """
    raw = dict(payload or {})
    existing = dict(existing_task or {})
    issues: list[TaskValidationIssue] = []
    normalized: dict[str, Any] = {}
    handled: set[str] = set()

    def _set(field: str, value: Any):
        normalized[field] = value
        handled.add(field)

    # name (required on create / optional on update when present)
    if (not is_update) or ("name" in raw):
        name = _normalize_text(raw.get("name"), max_len=_TEXT_MAX["name"], required=not is_update)
        if not name:
            issues.append(TaskValidationIssue("name", "required", "Task name is required."))
        _set("name", name)

    # type
    if (not is_update) or ("type" in raw):
        raw_type = str(raw.get("type") or existing.get("type") or "schedule").strip().lower()
        if raw_type not in ALLOWED_TASK_TYPES:
            issues.append(TaskValidationIssue("type", "invalid", f"Invalid task type: {raw_type}"))
            raw_type = "schedule"
        _set("type", raw_type)
    else:
        raw_type = str(existing.get("type") or "schedule").strip().lower()

    # priority
    if (not is_update) or ("priority" in raw):
        priority = str(raw.get("priority") or existing.get("priority") or "normal").strip().lower()
        if priority not in ALLOWED_PRIORITIES:
            issues.append(
                TaskValidationIssue("priority", "invalid", f"Invalid priority: {priority}")
            )
            priority = "normal"
        _set("priority", priority)

    # status
    if (not is_update) or ("status" in raw):
        status_raw = raw.get("status")
        status_text = str(status_raw or "").strip().lower()
        status = normalize_status(status_raw)
        if (
            status_text
            and status_text not in CANONICAL_STATUSES
            and status_text not in _LEGACY_STATUSES
        ):
            issues.append(
                TaskValidationIssue("status", "invalid", f"Invalid status: {status_text}")
            )
        _set("status", status)

    # common text fields (trim + length clamp)
    for field, max_len in _TEXT_MAX.items():
        if field == "name":
            continue
        if (not is_update) or (field in raw):
            _set(field, _normalize_text(raw.get(field), max_len=max_len))

    # Local datetime fields that are expected in "YYYY-MM-DD HH:MM[:SS]" format.
    for field in ("deadline", "end_date", "completed_at", "resolved_at"):
        if field in {"completed_at", "resolved_at"} and ((not is_update) and field not in raw):
            continue
        if (not is_update) or (field in raw):
            normalized_value, ok = _normalize_datetime(raw.get(field))
            if not ok:
                issues.append(
                    TaskValidationIssue(
                        field, "invalid_datetime", f"Invalid datetime: {raw.get(field)}"
                    )
                )
            _set(field, normalized_value)

    # date fields
    for field in ("target_date", "period_start", "period_end"):
        if (not is_update) or (field in raw):
            normalized_value, ok = _normalize_date(raw.get(field))
            if not ok:
                issues.append(
                    TaskValidationIssue(field, "invalid_date", f"Invalid date: {raw.get(field)}")
                )
            _set(field, normalized_value)

    # derive target_date when omitted but deadline exists (create only)
    if not is_update and not normalized.get("target_date") and normalized.get("deadline"):
        _set("target_date", str(normalized["deadline"])[:10])

    # cycle_type for routine
    if (not is_update) or ("cycle_type" in raw):
        cycle_raw = str(raw.get("cycle_type") or existing.get("cycle_type") or "").strip().lower()
        if raw_type == "routine":
            if not cycle_raw:
                cycle_raw = "monthly"
            if cycle_raw not in ALLOWED_CYCLE_TYPES:
                issues.append(
                    TaskValidationIssue("cycle_type", "invalid", f"Invalid cycle type: {cycle_raw}")
                )
                cycle_raw = "monthly"
            _set("cycle_type", cycle_raw)
        else:
            _set("cycle_type", cycle_raw or None)

    # recurrence default for single routine
    if raw_type == "routine":
        cycle = (
            normalized.get("cycle_type") or str(existing.get("cycle_type") or "").strip().lower()
        )
        recurrence = normalized.get("recurrence")
        if cycle == "single" and not recurrence:
            _set("recurrence", "mode=single")

    # all_day + completion booleans
    if (not is_update) or ("all_day" in raw):
        _set("all_day", 1 if bool(raw.get("all_day")) else 0)

    if not is_update:
        if "is_completed" in raw:
            _set("is_completed", 1 if bool(raw.get("is_completed")) else 0)
        else:
            _set("is_completed", 1 if normalized.get("status") == "completed" else 0)
    elif "is_completed" in raw:
        _set("is_completed", 1 if bool(raw.get("is_completed")) else 0)

    # series metadata
    for field in ("series_order", "series_total"):
        if (not is_update) or (field in raw):
            iv, ok = _coerce_positive_int(raw.get(field), allow_none=True)
            if not ok:
                issues.append(
                    TaskValidationIssue(
                        field, "invalid_int", f"Invalid positive integer: {raw.get(field)}"
                    )
                )
            _set(field, iv)

    # cross-field constraints
    if normalized.get("deadline") and normalized.get("end_date"):
        try:
            start_dt = datetime.strptime(normalized["deadline"], "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(normalized["end_date"], "%Y-%m-%d %H:%M:%S")
            if end_dt < start_dt:
                # Keep backward compatibility with legacy callers that may only shift start date.
                normalized["end_date"] = None
        except Exception:
            pass

    # copy-through unknown keys for forward compatibility
    for key, value in raw.items():
        if key not in handled:
            normalized[key] = value

    return normalized, issues
