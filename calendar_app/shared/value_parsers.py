# -*- coding: utf-8 -*-
"""Small, side-effect-free value parsing helpers."""


def as_int(value, default=0, *, minimum=None, maximum=None):
    """Recover malformed persisted integers and apply optional bounds."""
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def as_bool(value, default=False):
    """Convert loose config values to bool with a sensible default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
