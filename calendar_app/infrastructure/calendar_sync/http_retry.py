# -*- coding: utf-8 -*-
"""Validate Retry-After without exposing remote headers or pausing sync for long."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil

# The pause also blocks a manual "sync now"; one server header must not stop sync for days.
MAX_RETRY_AFTER_SECONDS = 3600


def retry_after_seconds(value, *, now=None):
    """Return positive seconds, capped at one hour."""
    if not isinstance(value, str) or len(value) > 128:
        return None
    value = value.strip()
    if value.isascii() and value.isdecimal():
        seconds = int(value)
    else:
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            seconds = ceil((deadline - (now or datetime.now(UTC))).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None
    return min(seconds, MAX_RETRY_AFTER_SECONDS) if seconds > 0 else None
