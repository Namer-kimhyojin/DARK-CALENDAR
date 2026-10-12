# -*- coding: utf-8 -*-
"""Validate Retry-After without exposing remote headers or exceeding Qt timers."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil

MAX_RETRY_AFTER_SECONDS = 2_147_483


def retry_after_seconds(value, *, now=None):
    """Return positive seconds, capped at the signed 32-bit millisecond limit."""
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
