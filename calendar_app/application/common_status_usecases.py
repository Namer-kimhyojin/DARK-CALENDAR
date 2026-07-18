"""Shared status display helpers for application-layer usecases."""

from __future__ import annotations

from calendar_app.domain.task_status_view import (
    normalize_status as _normalize_status,
)
from calendar_app.domain.task_status_view import (
    priority_display as _priority_display,
)
from calendar_app.domain.task_status_view import (
    status_display as _status_display,
)


def normalized_status(status: str | None) -> str:
    return _normalize_status(status)


def status_display(status: str | None) -> str:
    return _status_display(status)


def priority_display(priority: str | None) -> str:
    return _priority_display(priority)
