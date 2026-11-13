# -*- coding: utf-8 -*-
"""Shared date-only range policy for local and external calendar events."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class InclusiveDateRange:
    """A user-facing date range whose start and end dates are both included."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("inclusive range end must not precede start")

    @property
    def day_count(self) -> int:
        return (self.end - self.start).days + 1

    @classmethod
    def from_start_and_span(cls, start: date, day_count: int) -> "InclusiveDateRange":
        normalized_count = max(1, int(day_count or 1))
        return cls(start=start, end=start + timedelta(days=normalized_count - 1))


def inclusive_end_from_exclusive(start: date, end_exclusive: date) -> date:
    """Convert an external exclusive end date to the local inclusive policy."""
    return max(start, end_exclusive - timedelta(days=1))


def _clock_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value or "").strip()
    if len(text) <= 10:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def timed_span_last_day(start_value, end_value) -> date | None:
    """Last day a timed event touches, or None when either end has no clock time.

    An end exactly at midnight is exclusive, so 23:00-24:00 stays on one day,
    the same way the week view draws it.
    """
    start = _clock_datetime(start_value)
    end = _clock_datetime(end_value)
    if start is None or end is None:
        return None
    last = end.date()
    if end > start and end.time() == time.min:
        last -= timedelta(days=1)
    return max(start.date(), last)


def inclusive_day_count(start: date, end: date) -> int:
    """Return a safe inclusive span, clamping reversed ranges to one day."""
    if end < start:
        return 1
    return InclusiveDateRange(start=start, end=end).day_count
