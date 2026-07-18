from collections.abc import Callable
from dataclasses import dataclass
import re

from PyQt6.QtCore import QDate, QDateTime, QLocale, QPoint, QTime
from PyQt6.QtWidgets import QWidget

from calendar_app.infrastructure.i18n import t


@dataclass
class _WidgetEntry:
    title: str
    subtitle: str = ""
    callback: Callable[[], None] | None = None
    double_click_callback: Callable[[], None] | None = None
    is_section: bool = False
    secondary_text: str = ""
    secondary_tooltip: str = ""
    secondary_callback: Callable[[], None] | None = None
    delete_callback: Callable[[], None] | None = None
    context_menu_callback: Callable[[QWidget, QPoint], None] | None = None
    memo: str = ""  # 40자 이하로 잘린 메모 표시용
    memo_full: str = ""  # 팝업용 전체 메모


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _top_level_widget(parent: QWidget | None) -> QWidget | None:
    ref = parent
    while ref is not None and ref.parentWidget() is not None:
        ref = ref.parentWidget()
    return ref


def _parse_qdate(raw_value: object) -> QDate:
    raw = _safe_text(raw_value)
    if len(raw) >= 10:
        qd = QDate.fromString(raw[:10], "yyyy-MM-dd")
        if qd.isValid():
            return qd
    return QDate()


def _parse_qdatetime(raw_value: object) -> QDateTime:
    raw = _safe_text(raw_value)
    if len(raw) >= 19:
        qdt = QDateTime.fromString(raw[:19].replace("T", " "), "yyyy-MM-dd HH:mm:ss")
        if qdt.isValid():
            return qdt
    if len(raw) >= 16:
        qdt = QDateTime.fromString(raw[:16].replace("T", " "), "yyyy-MM-dd HH:mm")
        if qdt.isValid():
            return qdt
    qd = _parse_qdate(raw)
    if qd.isValid():
        return QDateTime(qd, QTime(0, 0))
    return QDateTime()


def _active_locale(locale: QLocale | None = None) -> QLocale:
    return QLocale(locale) if isinstance(locale, QLocale) else QLocale()


def _strip_year_from_qt_date_format(fmt: str) -> str:
    parts = re.findall(r"(?:'[^']*'|[A-Za-z]+|[^A-Za-z]+)", str(fmt or ""))
    cleaned: list[str] = []
    skip_separator = False

    for part in parts:
        if re.fullmatch(r"y+", part, flags=re.IGNORECASE):
            if cleaned and re.fullmatch(r"[^A-Za-z]+", cleaned[-1]):
                cleaned.pop()
            skip_separator = True
            continue
        if re.fullmatch(r"[^A-Za-z]+", part) and (skip_separator or not cleaned):
            skip_separator = False
            continue
        skip_separator = False
        cleaned.append(part)

    while cleaned and re.fullmatch(r"[^A-Za-z]+", cleaned[-1]):
        cleaned.pop()

    result = "".join(cleaned).strip()
    return result if re.search(r"[dM]", result) else "M.d"


def _format_compact_date(date: QDate, locale: QLocale | None = None) -> str:
    if not isinstance(date, QDate) or not date.isValid():
        return "-"
    loc = _active_locale(locale)
    pattern = _strip_year_from_qt_date_format(loc.dateFormat(QLocale.FormatType.ShortFormat))
    text = loc.toString(date, pattern).strip()
    if text:
        return text
    return loc.toString(date, QLocale.FormatType.ShortFormat).strip() or date.toString("M.d")


def _format_compact_date_with_weekday(date: QDate, locale: QLocale | None = None) -> str:
    if not isinstance(date, QDate) or not date.isValid():
        return "-"
    loc = _active_locale(locale)
    base = _format_compact_date(date, loc)
    weekday = loc.dayName(date.dayOfWeek(), QLocale.FormatType.ShortFormat).strip()
    return f"{base} {weekday}".strip() if weekday else base


def _relative_day_label(date: QDate) -> str:
    if not isinstance(date, QDate) or not date.isValid():
        return t("widget_mode.today", "Today")
    today = QDate.currentDate()
    delta = today.daysTo(date)
    if delta == 0:
        return t("widget_mode.today", "Today")
    if delta == 1:
        return t("widget_mode.tomorrow", "Tomorrow")
    if delta == -1:
        return t("widget_mode.yesterday", "Yesterday")
    return _format_compact_date_with_weekday(date)


def _append_date_label(label: str, date_text: str) -> str:
    base = _safe_text(label)
    date_str = _safe_text(date_text)
    if not date_str:
        return base
    if not base:
        return date_str
    if date_str in base:
        return base
    return f"{base} {date_str}"


def _format_widget_datetime_label(
    raw_dt: object, reference_date: QDate | None = None, locale: QLocale | None = None
) -> str:
    raw = _safe_text(raw_dt)
    qdt = _parse_qdatetime(raw)
    if not qdt.isValid():
        return ""

    loc = _active_locale(locale)
    ref_date = (
        reference_date
        if isinstance(reference_date, QDate) and reference_date.isValid()
        else QDate()
    )
    date_text = _format_compact_date(qdt.date(), loc)
    has_time = len(raw) >= 16
    if not has_time:
        if ref_date.isValid() and qdt.date() == ref_date:
            return ""
        return date_text

    time_text = loc.toString(qdt.time(), QLocale.FormatType.ShortFormat).strip()
    if ref_date.isValid() and qdt.date() == ref_date:
        return time_text
    if date_text and time_text:
        return f"{date_text} {time_text}"
    return time_text or date_text


def _normalize_status(raw_status: object) -> str:
    return _safe_text(raw_status).lower() or "pending"


def _priority_rank(raw_priority: object) -> int:
    key = _safe_text(raw_priority).lower()
    return {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(key, 2)


_REF_SCREEN_WIDTH = 1920
_WIDGET_PANEL_WIDTH_REF = 372
_SCHEDULE_WIDGET_HEIGHT_REF = 528
_WORK_WIDGET_DEFAULT_HEIGHT_REF = 356
_WORK_WIDGET_MIN_HEIGHT_REF = 284


def _parse_quick_add_text(text: str) -> tuple[str | None, str]:
    """Uses the central NLP engine to extract time and name."""
    try:
        from calendar_app.infrastructure.nlp.nlp_engine import parse_nlp_task

        parsed = parse_nlp_task(text)
        return parsed.get("time"), parsed.get("title")
    except Exception:
        # Fallback to basic search
        time_str, name = None, text
        match = re.search(r"(\d{1,2}:\d{2})", text)
        if match:
            time_str = match.group(1)
            name = text.replace(time_str, "").strip()
        return time_str, name
