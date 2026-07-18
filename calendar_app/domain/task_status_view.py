"""Shared view helpers for task status/priority labels."""

from __future__ import annotations

from calendar_app.domain.task_constants import PRIORITY_LABEL, STATUS_LABEL

CANONICAL_STATUSES = ("pending", "in_progress", "completed", "deferred")

_ALLOWED_STATUS_TRANSITIONS = {
    "pending": {"pending", "in_progress", "completed", "deferred"},
    "in_progress": {"in_progress", "pending", "completed", "deferred"},
    # completed -> pending is blocked; reopen should go through in_progress/deferred first.
    "completed": {"completed", "in_progress", "deferred"},
    "deferred": {"deferred", "pending", "in_progress", "completed"},
}


def normalize_status(status: str | None) -> str:
    """Normalize legacy status values into the canonical label keys."""
    if status == "done":
        return "completed"
    if status in ("overdue", "canceled"):
        return "deferred"
    if status in CANONICAL_STATUSES:
        return status
    return "pending"


def can_transition_status(current: str | None, next_status: str | None) -> bool:
    """Return whether status transition is allowed by workflow policy."""
    now = normalize_status(current)
    nxt = normalize_status(next_status)
    return nxt in _ALLOWED_STATUS_TRANSITIONS.get(now, {now})


def status_display(status: str | None) -> str:
    return STATUS_LABEL.get(status, status or "")


def priority_display(priority: str | None) -> str:
    return PRIORITY_LABEL.get(priority, priority or "")
