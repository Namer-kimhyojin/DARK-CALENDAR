# -*- coding: utf-8 -*-
"""Backward-compatible calendar weekday placement preferences."""

WEEKDAY_DISPLAY_KEY = "cal_weekday_display_mode"
WEEKDAY_DISPLAY_MODES = ("header", "date", "both", "hidden")


def _legacy_flag(value):
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def normalize_weekday_display_mode(value):
    value = str(value or "").strip().lower()
    return value if value in WEEKDAY_DISPLAY_MODES else None


def read_weekday_display_mode(settings=None, *, legacy_show_weekday=False):
    """Prefer the explicit mode; reading old settings never rewrites them."""
    if settings is not None:
        mode = normalize_weekday_display_mode(settings.value(WEEKDAY_DISPLAY_KEY, None))
        if mode is not None:
            return mode
        legacy = settings.value("cal_show_weekday", None)
        if legacy is None:
            legacy = settings.value("cal_show_day_name", legacy_show_weekday)
        legacy_show_weekday = _legacy_flag(legacy)
    return "both" if _legacy_flag(legacy_show_weekday) else "header"


def weekday_display_mode_for(owner):
    mode = normalize_weekday_display_mode(getattr(owner, "cal_weekday_display_mode", None))
    return mode or read_weekday_display_mode(
        getattr(owner, "settings", None),
        legacy_show_weekday=getattr(owner, "cal_show_weekday", False),
    )


def next_weekday_display_mode(mode):
    mode = normalize_weekday_display_mode(mode) or "header"
    return WEEKDAY_DISPLAY_MODES[(WEEKDAY_DISPLAY_MODES.index(mode) + 1) % len(WEEKDAY_DISPLAY_MODES)]


def weekday_display_flags(mode):
    """Return whether weekday text belongs above columns and beside dates."""
    mode = normalize_weekday_display_mode(mode) or "header"
    return mode in {"header", "both"}, mode in {"date", "both"}
