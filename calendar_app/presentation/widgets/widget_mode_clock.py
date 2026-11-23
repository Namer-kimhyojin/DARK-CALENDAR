# -*- coding: utf-8 -*-
"""Clock display options for widget-only mode (format, seconds, size, date line)."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QDate, QLocale, QTime

from calendar_app.infrastructure.i18n import t

CLOCK_FORMAT_KEY = "widget_mode_clock_format"
CLOCK_SECONDS_KEY = "widget_mode_clock_seconds"
CLOCK_SIZE_KEY = "widget_mode_clock_size"
CLOCK_DATE_KEY = "widget_mode_clock_show_date"
CLOCK_SETTING_KEYS = (CLOCK_FORMAT_KEY, CLOCK_SECONDS_KEY, CLOCK_SIZE_KEY, CLOCK_DATE_KEY)

CLOCK_FORMATS = ("24h", "12h")
CLOCK_SIZES = ("small", "large")


@dataclass(frozen=True)
class ClockOptions:
    hour_format: str = "24h"
    seconds: bool = False
    size: str = "small"
    show_date: bool = False

    @property
    def large(self) -> bool:
        return self.size == "large"


def _read_bool(settings, key: str, default: bool) -> bool:
    raw = settings.value(key, None)
    if raw is True or str(raw).lower() == "true":
        return True
    if raw is False or str(raw).lower() == "false":
        return False
    return default


def read_clock_options(settings) -> ClockOptions:
    hour_format = str(settings.value(CLOCK_FORMAT_KEY, "24h") or "24h")
    size = str(settings.value(CLOCK_SIZE_KEY, "small") or "small")
    return ClockOptions(
        hour_format if hour_format in CLOCK_FORMATS else "24h",
        _read_bool(settings, CLOCK_SECONDS_KEY, False),
        size if size in CLOCK_SIZES else "small",
        _read_bool(settings, CLOCK_DATE_KEY, False),
    )


def format_clock_time(time: QTime, options: ClockOptions, locale: QLocale | None = None) -> str:
    if options.hour_format == "24h":
        return time.toString("HH:mm:ss" if options.seconds else "HH:mm")
    loc = locale if locale is not None else QLocale()
    hour = time.hour() % 12 or 12
    clock = f"{hour}:{time.minute():02d}"
    if options.seconds:
        clock += f":{time.second():02d}"
    meridiem = loc.amText() if time.hour() < 12 else loc.pmText()
    return t("widget_mode.clock_12h_format", "{ampm} {time}").format(ampm=meridiem, time=clock)


def format_clock_date(date: QDate, options: ClockOptions, locale: QLocale | None = None) -> str:
    """Long date under the large clock; a short month/day + weekday next to the small one."""
    loc = locale if locale is not None else QLocale()
    if options.large:
        return loc.toString(date, QLocale.FormatType.LongFormat)
    weekday = loc.dayName(date.dayOfWeek(), QLocale.FormatType.ShortFormat)
    return t("widget_mode.clock_short_date", "{month}/{day} ({weekday})").format(
        month=date.month(), day=date.day(), weekday=weekday
    )


def ms_until_next_tick(time: QTime, options: ClockOptions) -> int:
    period = 1000 if options.seconds else 60000
    remaining = period - (time.msecsSinceStartOfDay() % period)
    return max(200 if options.seconds else 1000, int(remaining or period))
