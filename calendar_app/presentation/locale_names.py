# -*- coding: utf-8 -*-
"""Names that come from Qt's locale data instead of translation keys.

Weekday names used to live in the locale files and were machine-translated word by
word ("Sat" became "sat down", "Sun" became "the sun"). Qt ships correct names for
every UI language, so screens take them from here.
"""

from PyQt6.QtCore import QLocale

from calendar_app.infrastructure.i18n import t

DEFAULT_LOCAL_CALENDAR_ID = "local::기본"
_DEFAULT_LOCAL_CALENDAR_NAME = "기본"


def _format(narrow: bool, long: bool) -> QLocale.FormatType:
    if long:
        return QLocale.FormatType.LongFormat
    if narrow:
        return QLocale.FormatType.NarrowFormat
    return QLocale.FormatType.ShortFormat


def weekday_name(
    index: int, *, narrow: bool = False, long: bool = False, locale: QLocale | None = None
) -> str:
    """Standalone weekday name; ``index`` 0 is Monday, 6 is Sunday."""
    loc = locale if locale is not None else QLocale()
    return loc.standaloneDayName(int(index) % 7 + 1, _format(narrow, long))


def weekday_names(
    *, narrow: bool = False, long: bool = False, locale: QLocale | None = None
) -> list[str]:
    """Monday-first standalone weekday names for the UI locale."""
    return [weekday_name(day, narrow=narrow, long=long, locale=locale) for day in range(7)]


def month_name(month: int, *, short: bool = False, locale: QLocale | None = None) -> str:
    """Standalone month name (nominative case, e.g. Russian "ноябрь", not "ноября")."""
    loc = locale if locale is not None else QLocale()
    fmt = QLocale.FormatType.ShortFormat if short else QLocale.FormatType.LongFormat
    return loc.standaloneMonthName(int(month), fmt)


def calendar_display_name(calendar_id, name) -> str:
    """Show the built-in local calendar as "Default" in the UI language.

    The row is stored as ``local::기본`` / ``기본`` so existing data keeps working.
    A name the user changed is shown as typed.
    """
    text = name or ""
    if calendar_id == DEFAULT_LOCAL_CALENDAR_ID and text in {"", _DEFAULT_LOCAL_CALENDAR_NAME}:
        return t("common.default", _DEFAULT_LOCAL_CALENDAR_NAME)
    return text
