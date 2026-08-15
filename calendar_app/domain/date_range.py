# -*- coding: utf-8 -*-
"""Shared date-only range policy for local and external calendar events."""

from dataclasses import dataclass
from datetime import date, timedelta


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


def inclusive_day_count(start: date, end: date) -> int:
    """Return a safe inclusive span, clamping reversed ranges to one day."""
    if end < start:
        return 1
    return InclusiveDateRange(start=start, end=end).day_count
