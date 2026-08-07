# -*- coding: utf-8 -*-
"""Printer-independent calendar document planning.

The presentation layer renders the immutable document produced here to a
``QPrinter``.  Keeping range calculations and event normalization free of Qt
also makes pagination and completeness rules straightforward to test.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

PageUnit = Literal["month", "week"]
DetailPageMode = Literal["all", "overflow"]

MAX_PRINT_RANGE_DAYS = 3660


@dataclass(frozen=True)
class CalendarPrintRequest:
    start_date: date
    end_date: date
    page_unit: PageUnit = "month"
    show_weekends: bool = True
    start_monday: bool = True
    selected_calendar_ids: tuple[str, ...] = ()
    include_completed: bool = True
    include_location: bool = False
    grayscale: bool = False
    detail_page_mode: DetailPageMode = "all"

    def validate(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("print range end must not precede start")
        if self.page_unit not in {"month", "week"}:
            raise ValueError(f"unsupported print page unit: {self.page_unit}")
        if self.detail_page_mode not in {"all", "overflow"}:
            raise ValueError(f"unsupported detail page mode: {self.detail_page_mode}")
        if (self.end_date - self.start_date).days > MAX_PRINT_RANGE_DAYS:
            raise ValueError(f"print range exceeds {MAX_PRINT_RANGE_DAYS + 1} days")


@dataclass(frozen=True)
class CalendarPrintCalendar:
    calendar_id: str
    name: str
    color: str
    calendar_type: str = "local"
    is_visible: bool = True


@dataclass(frozen=True)
class CalendarPrintEvent:
    event_key: str
    name: str
    start_date: date
    end_date: date
    start_time: time | None
    end_time: time | None
    all_day: bool
    calendar_id: str
    calendar_name: str
    calendar_color: str
    priority: str
    status: str
    location: str

    @property
    def is_multiday(self) -> bool:
        return self.end_date > self.start_date

    def overlaps(self, start: date, end: date) -> bool:
        return self.start_date <= end and self.end_date >= start

    def occurs_on(self, target: date) -> bool:
        return self.start_date <= target <= self.end_date


@dataclass(frozen=True)
class CalendarPrintPage:
    page_unit: PageUnit
    anchor_date: date
    period_start: date
    period_end: date
    grid_dates: tuple[date, ...]
    events: tuple[CalendarPrintEvent, ...]


@dataclass(frozen=True)
class CalendarPrintDocument:
    request: CalendarPrintRequest
    calendars: tuple[CalendarPrintCalendar, ...]
    pages: tuple[CalendarPrintPage, ...]
    created_at: datetime
    source_row_count: int
    warnings: tuple[str, ...] = ()


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_time(value) -> time | None:
    if isinstance(value, datetime):
        return value.timetz().replace(tzinfo=None)
    text = str(value or "").strip()
    if not text or len(text) <= 10:
        return None
    candidate = text.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(candidate).timetz().replace(tzinfo=None)
    except ValueError:
        pass
    for token in (text[11:19], text[11:16]):
        try:
            return time.fromisoformat(token)
        except ValueError:
            continue
    return None


def _calendar_from_row(row: Mapping) -> CalendarPrintCalendar:
    calendar_id = str(row.get("id") or "").strip()
    return CalendarPrintCalendar(
        calendar_id=calendar_id,
        name=str(row.get("name") or calendar_id or "Calendar").strip(),
        color=str(row.get("color") or "#4d7cff").strip(),
        calendar_type=str(row.get("type") or "local").strip().lower(),
        is_visible=_as_bool(row.get("is_visible"), default=True),
    )


def _event_identity(row: Mapping, calendar_id: str) -> str:
    gcal_event_id = str(row.get("gcal_event_id") or row.get("_gcal_event_id") or "").strip()
    if gcal_event_id:
        source = str(
            row.get("gcal_source_calendar_id")
            or row.get("_subscription_calendar_id")
            or calendar_id
            or "primary"
        ).strip()
        return f"gcal:{source}:{gcal_event_id}"
    row_id = row.get("id")
    if row_id not in (None, ""):
        return f"local:{row_id}"
    start = str(row.get("deadline") or row.get("target_date") or "")
    name = str(row.get("name") or "")
    return f"content:{calendar_id}:{start}:{name}"


def _event_from_row(
    row: Mapping,
    calendars_by_id: Mapping[str, CalendarPrintCalendar],
) -> CalendarPrintEvent | None:
    start_value = row.get("deadline") or row.get("target_date")
    start_date = _parse_date(start_value)
    if start_date is None:
        return None

    end_value = row.get("end_date") or start_value
    end_date = _parse_date(end_value) or start_date
    if end_date < start_date:
        end_date = start_date

    calendar_id = str(row.get("calendar_id") or "").strip()
    if not calendar_id:
        source = str(
            row.get("gcal_source_calendar_id") or row.get("_subscription_calendar_id") or ""
        ).strip()
        if source:
            calendar_id = f"gcal::{source}"

    calendar = calendars_by_id.get(calendar_id)
    calendar_name = str(
        row.get("_subscription_summary")
        or (calendar.name if calendar is not None else "")
        or calendar_id
        or "Calendar"
    ).strip()
    calendar_color = str(
        row.get("bg_color") or (calendar.color if calendar is not None else "") or "#4d7cff"
    ).strip()
    all_day = _as_bool(row.get("all_day"), default=False)

    return CalendarPrintEvent(
        event_key=_event_identity(row, calendar_id),
        name=str(row.get("name") or "(No title)").strip(),
        start_date=start_date,
        end_date=end_date,
        start_time=None if all_day else _parse_time(start_value),
        end_time=None if all_day else _parse_time(end_value),
        all_day=all_day,
        calendar_id=calendar_id,
        calendar_name=calendar_name,
        calendar_color=calendar_color,
        priority=str(row.get("priority") or "").strip().lower(),
        status=str(row.get("status") or "").strip().lower(),
        location=str(row.get("location") or "").strip(),
    )


def _event_preference(event: CalendarPrintEvent) -> tuple[int, int, int]:
    return (
        1 if event.calendar_id else 0,
        1 if event.location else 0,
        1 if event.calendar_name else 0,
    )


def _is_completed_row(row: Mapping) -> bool:
    if _as_bool(row.get("is_completed"), default=False):
        return True
    return str(row.get("status") or "").strip().lower() in {
        "completed",
        "complete",
        "done",
        "finished",
    }


def _event_sort_key(event: CalendarPrintEvent):
    return (
        event.start_date,
        0 if event.all_day or event.is_multiday else 1,
        event.start_time or time.min,
        event.end_date,
        event.name.casefold(),
        event.event_key,
    )


def normalize_print_events(
    rows: Iterable[Mapping],
    calendars: Sequence[CalendarPrintCalendar],
    request: CalendarPrintRequest,
) -> tuple[CalendarPrintEvent, ...]:
    calendars_by_id = {calendar.calendar_id: calendar for calendar in calendars}
    selected = set(request.selected_calendar_ids)
    deduped: dict[str, CalendarPrintEvent] = {}

    for row in rows:
        if not request.include_completed and _is_completed_row(row):
            continue
        event = _event_from_row(row, calendars_by_id)
        if event is None or not event.overlaps(request.start_date, request.end_date):
            continue
        if selected and event.calendar_id and event.calendar_id not in selected:
            continue
        current = deduped.get(event.event_key)
        if current is None or _event_preference(event) > _event_preference(current):
            deduped[event.event_key] = event

    return tuple(sorted(deduped.values(), key=_event_sort_key))


def _week_start(target: date, start_monday: bool) -> date:
    if start_monday:
        offset = target.weekday()
    else:
        offset = (target.weekday() + 1) % 7
    return target - timedelta(days=offset)


def _week_dates(start: date, show_weekends: bool) -> tuple[date, ...]:
    dates = tuple(start + timedelta(days=offset) for offset in range(7))
    if show_weekends:
        return dates
    return tuple(item for item in dates if item.weekday() < 5)


def _month_grid_dates(
    anchor: date,
    *,
    show_weekends: bool,
    start_monday: bool,
) -> tuple[date, ...]:
    month_start = anchor.replace(day=1)
    next_month = _add_month(month_start)
    month_end = next_month - timedelta(days=1)
    grid_start = _week_start(month_start, start_monday)
    grid_end = _week_start(month_end, start_monday) + timedelta(days=6)

    result: list[date] = []
    current = grid_start
    while current <= grid_end:
        if show_weekends or current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return tuple(result)


def _add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _build_period_pages(
    request: CalendarPrintRequest,
    events: Sequence[CalendarPrintEvent],
) -> tuple[CalendarPrintPage, ...]:
    pages: list[CalendarPrintPage] = []
    if request.page_unit == "month":
        anchor = request.start_date.replace(day=1)
        while anchor <= request.end_date:
            next_month = _add_month(anchor)
            month_end = next_month - timedelta(days=1)
            period_start = max(anchor, request.start_date)
            period_end = min(month_end, request.end_date)
            pages.append(
                CalendarPrintPage(
                    page_unit="month",
                    anchor_date=anchor,
                    period_start=period_start,
                    period_end=period_end,
                    grid_dates=_month_grid_dates(
                        anchor,
                        show_weekends=request.show_weekends,
                        start_monday=request.start_monday,
                    ),
                    events=tuple(
                        event for event in events if event.overlaps(period_start, period_end)
                    ),
                )
            )
            anchor = next_month
        return tuple(pages)

    week_anchor = _week_start(request.start_date, request.start_monday)
    while week_anchor <= request.end_date:
        week_end = week_anchor + timedelta(days=6)
        period_start = max(week_anchor, request.start_date)
        period_end = min(week_end, request.end_date)
        pages.append(
            CalendarPrintPage(
                page_unit="week",
                anchor_date=week_anchor,
                period_start=period_start,
                period_end=period_end,
                grid_dates=_week_dates(week_anchor, request.show_weekends),
                events=tuple(event for event in events if event.overlaps(period_start, period_end)),
            )
        )
        week_anchor += timedelta(days=7)
    return tuple(pages)


def build_calendar_print_document(
    request: CalendarPrintRequest,
    rows: Sequence[Mapping],
    calendar_rows: Sequence[Mapping],
    *,
    warnings: Sequence[str] = (),
    created_at: datetime | None = None,
) -> CalendarPrintDocument:
    request.validate()
    calendars = tuple(_calendar_from_row(row) for row in calendar_rows)
    events = normalize_print_events(rows, calendars, request)
    pages = _build_period_pages(request, events)
    return CalendarPrintDocument(
        request=request,
        calendars=calendars,
        pages=pages,
        created_at=created_at or datetime.now(),
        source_row_count=len(rows),
        warnings=tuple(str(item) for item in warnings if str(item).strip()),
    )


def events_for_day(
    page: CalendarPrintPage,
    target: date,
) -> tuple[CalendarPrintEvent, ...]:
    if target < page.period_start or target > page.period_end:
        return ()
    return tuple(event for event in page.events if event.occurs_on(target))
