# -*- coding: utf-8 -*-
"""High-quality vector renderer for calendar printing and PDF export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
import math

from PyQt6.QtCore import QMarginsF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
)
from PyQt6.QtPrintSupport import QPrinter

from calendar_app.app_metadata import APP_NAME
from calendar_app.application.calendar_print_service import (
    CalendarPrintDocument,
    CalendarPrintEvent,
    CalendarPrintPage,
)
from calendar_app.infrastructure.i18n import t


@dataclass(frozen=True)
class CalendarPrintRenderOptions:
    paper_size: str = "A4"
    orientation: str = "landscape"
    margin_mm: float = 10.0
    document_title: str = APP_NAME


@dataclass(frozen=True)
class CalendarPrintRenderReport:
    sheet_count: int
    calendar_sheet_count: int
    detail_sheet_count: int
    overflow_event_count: int
    drawn_event_keys: tuple[str, ...]
    missing_event_keys: tuple[str, ...]


@dataclass(frozen=True)
class _SheetPlan:
    kind: str
    period_index: int
    page: CalendarPrintPage
    detail_events: tuple[CalendarPrintEvent, ...] = ()


@dataclass(frozen=True)
class _MultidaySegment:
    event: CalendarPrintEvent
    row: int
    start_col: int
    end_col: int
    lane: int
    visible_start: date
    visible_end: date


@dataclass(frozen=True)
class _WeekLayout:
    row: int
    visible_lane_count: int
    segments: tuple[_MultidaySegment, ...]
    single_events: tuple[tuple[CalendarPrintEvent, ...], ...]
    hidden_counts: tuple[int, ...]


_PAPER_SIZE_IDS = {
    "A4": QPageSize.PageSizeId.A4,
    "LETTER": QPageSize.PageSizeId.Letter,
    "A3": QPageSize.PageSizeId.A3,
}


def configure_printer(
    printer: QPrinter,
    options: CalendarPrintRenderOptions,
    *,
    grayscale: bool = False,
) -> None:
    page_id = _PAPER_SIZE_IDS.get(str(options.paper_size).upper(), QPageSize.PageSizeId.A4)
    orientation = (
        QPageLayout.Orientation.Portrait
        if str(options.orientation).lower() == "portrait"
        else QPageLayout.Orientation.Landscape
    )
    margin = max(5.0, min(30.0, float(options.margin_mm)))
    layout = QPageLayout(
        QPageSize(page_id),
        orientation,
        QMarginsF(margin, margin, margin, margin),
        QPageLayout.Unit.Millimeter,
    )
    printer.setPageLayout(layout)
    printer.setFullPage(False)
    printer.setDocName(options.document_title)
    printer.setCreator(APP_NAME)
    printer.setColorMode(QPrinter.ColorMode.GrayScale if grayscale else QPrinter.ColorMode.Color)


def _valid_color(value: str, fallback: str = "#4d7cff") -> QColor:
    color = QColor(str(value or fallback))
    if not color.isValid():
        color = QColor(fallback)
    return color


def _mix(left: QColor, right: QColor, right_ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, right_ratio))
    return QColor(
        round(left.red() * (1.0 - ratio) + right.red() * ratio),
        round(left.green() * (1.0 - ratio) + right.green() * ratio),
        round(left.blue() * (1.0 - ratio) + right.blue() * ratio),
    )


def _gray(color: QColor) -> QColor:
    value = round(0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue())
    return QColor(value, value, value)


def _event_color(event: CalendarPrintEvent, grayscale: bool) -> tuple[QColor, QColor]:
    accent = _valid_color(event.calendar_color)
    if grayscale:
        accent = _gray(accent)
    fill = _mix(accent, QColor("#ffffff"), 0.90)
    return accent.darker(115), fill


def _font(size_pt: float, *, bold: bool = False) -> QFont:
    font = QFont("Malgun Gothic")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSizeF(size_pt)
    font.setBold(bold)
    return font


def _weekday_names() -> list[str]:
    raw = t("calendar.weekdays", ["월", "화", "수", "목", "금", "토", "일"])
    if isinstance(raw, list) and len(raw) >= 7:
        return [str(item) for item in raw[:7]]
    return ["월", "화", "수", "목", "금", "토", "일"]


def _period_title(page: CalendarPrintPage) -> str:
    if page.page_unit == "month":
        return t(
            "print.month_title",
            "{year}년 {month}월",
            year=page.anchor_date.year,
            month=page.anchor_date.month,
        )
    return t(
        "print.week_title",
        "{start} ~ {end}",
        start=page.period_start.isoformat(),
        end=page.period_end.isoformat(),
    )


def _event_time_text(event: CalendarPrintEvent) -> str:
    if event.all_day:
        return t("print.all_day", "종일")
    if event.start_time is None:
        return ""
    return event.start_time.strftime("%H:%M")


def _priority_marker(event: CalendarPrintEvent) -> str:
    return {
        "urgent": f"{t('priority.urgent', '긴급')} · ",
        "high": f"{t('priority.high', '높음')} · ",
    }.get(event.priority, "")


def _event_cell_text(event: CalendarPrintEvent, target: date) -> str:
    del target
    time_text = "" if event.all_day or event.is_multiday else _event_time_text(event)
    timed = f"{time_text} " if time_text else ""
    return f"{timed}{_priority_marker(event)}{event.name}"


def _multiday_segment_text(segment: _MultidaySegment) -> str:
    event = segment.event
    continued = event.start_date < segment.visible_start
    prefix = "... " if continued else ""
    time_text = ""
    if not event.all_day and not continued and event.start_time is not None:
        time_text = f"{event.start_time.strftime('%H:%M')} "
    return f"{prefix}{time_text}{_priority_marker(event)}{event.name}"


def _details_event_sort_key(event: CalendarPrintEvent):
    return (
        event.start_date,
        0 if event.all_day or event.is_multiday else 1,
        event.start_time or time.min,
        event.name.casefold(),
        event.event_key,
    )


class _RenderContext:
    def __init__(self, painter: QPainter, printer: QPrinter):
        self.painter = painter
        self.printer = printer
        self.scale = max(1.0, float(printer.resolution()) / 72.0)
        viewport = painter.viewport()
        self.width_pt = float(viewport.width()) / self.scale
        self.height_pt = float(viewport.height()) / self.scale

    def rect(self, x: float, y: float, width: float, height: float) -> QRectF:
        return QRectF(
            x * self.scale,
            y * self.scale,
            width * self.scale,
            height * self.scale,
        )

    def pen(self, color: QColor | str, width_pt: float = 0.5) -> QPen:
        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(max(0.5, width_pt * self.scale))
        return pen

    def draw_text(
        self,
        rect: QRectF,
        text: str,
        *,
        size: float,
        color: QColor | str = "#111827",
        bold: bool = False,
        align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        elide: bool = False,
    ) -> None:
        self.painter.setPen(QColor(color) if isinstance(color, str) else color)
        font = _font(size, bold=bold)
        self.painter.setFont(font)
        value = str(text or "")
        if elide:
            metrics = QFontMetricsF(font, self.printer)
            value = metrics.elidedText(
                value,
                Qt.TextElideMode.ElideRight,
                max(0, round(rect.width() - 2 * self.scale)),
            )
        self.painter.drawText(rect, int(align), value)


def _calendar_geometry(page: CalendarPrintPage, width_pt: float, height_pt: float) -> dict:
    columns = 7 if len(page.grid_dates) % 7 == 0 else 5
    rows = max(1, math.ceil(len(page.grid_dates) / columns))
    header_height = 60.0
    weekday_height = 20.0
    footer_height = 18.0
    grid_height = max(80.0, height_pt - header_height - weekday_height - footer_height)
    cell_height = grid_height / rows
    event_line_height = 13.5
    day_header_height = 16.0
    capacity = max(1, math.floor((cell_height - day_header_height - 4.0) / event_line_height))
    return {
        "columns": columns,
        "rows": rows,
        "header_height": header_height,
        "weekday_height": weekday_height,
        "footer_height": footer_height,
        "grid_height": grid_height,
        "cell_width": width_pt / columns,
        "cell_height": cell_height,
        "event_line_height": event_line_height,
        "day_header_height": day_header_height,
        "capacity": capacity,
    }


def _assign_multiday_segments(
    page: CalendarPrintPage,
    row: int,
    row_dates: tuple[date, ...],
) -> tuple[_MultidaySegment, ...]:
    candidates: list[tuple[int, int, date, date, CalendarPrintEvent]] = []
    for event in page.events:
        if not event.is_multiday:
            continue
        visible_indices = [
            index
            for index, target in enumerate(row_dates)
            if page.period_start <= target <= page.period_end and event.occurs_on(target)
        ]
        if not visible_indices:
            continue
        start_col = min(visible_indices)
        end_col = max(visible_indices)
        candidates.append(
            (
                start_col,
                end_col,
                row_dates[start_col],
                row_dates[end_col],
                event,
            )
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            -(item[1] - item[0]),
            item[4].start_date,
            item[4].name.casefold(),
            item[4].event_key,
        )
    )
    lane_ends: list[int] = []
    segments: list[_MultidaySegment] = []
    for start_col, end_col, visible_start, visible_end, event in candidates:
        lane = next(
            (index for index, occupied_end in enumerate(lane_ends) if start_col > occupied_end),
            len(lane_ends),
        )
        if lane == len(lane_ends):
            lane_ends.append(end_col)
        else:
            lane_ends[lane] = end_col
        segments.append(
            _MultidaySegment(
                event=event,
                row=row,
                start_col=start_col,
                end_col=end_col,
                lane=lane,
                visible_start=visible_start,
                visible_end=visible_end,
            )
        )
    return tuple(segments)


def _build_week_layouts(
    page: CalendarPrintPage,
    width_pt: float,
    height_pt: float,
) -> tuple[tuple[_WeekLayout, ...], set[str]]:
    geometry = _calendar_geometry(page, width_pt, height_pt)
    columns = int(geometry["columns"])
    capacity = int(geometry["capacity"])
    layouts: list[_WeekLayout] = []
    overflow_keys: set[str] = set()

    for row in range(int(geometry["rows"])):
        row_dates = tuple(page.grid_dates[row * columns : (row + 1) * columns])
        segments = _assign_multiday_segments(page, row, row_dates)
        lane_count = max((segment.lane for segment in segments), default=-1) + 1
        row_has_singles = any(
            not event.is_multiday
            and any(
                page.period_start <= target <= page.period_end and event.occurs_on(target)
                for target in row_dates
            )
            for event in page.events
        )
        visible_lane_count = min(lane_count, capacity)
        if lane_count > capacity or (lane_count >= capacity and row_has_singles):
            visible_lane_count = max(0, capacity - 1)
        visible_segments = tuple(
            segment for segment in segments if segment.lane < visible_lane_count
        )

        single_events: list[tuple[CalendarPrintEvent, ...]] = []
        hidden_counts: list[int] = []
        for col, target in enumerate(row_dates):
            singles = tuple(
                event
                for event in page.events
                if not event.is_multiday
                and page.period_start <= target <= page.period_end
                and event.occurs_on(target)
            )
            hidden_multiday = tuple(
                segment.event
                for segment in segments
                if segment.lane >= visible_lane_count
                and segment.start_col <= col <= segment.end_col
            )
            remaining = max(0, capacity - visible_lane_count)
            needs_more_line = bool(hidden_multiday) or len(singles) > remaining
            visible_single_count = (
                max(0, remaining - 1) if needs_more_line else min(len(singles), remaining)
            )
            visible_singles = singles[:visible_single_count]
            hidden_singles = singles[visible_single_count:]
            single_events.append(visible_singles)
            hidden_counts.append(len(hidden_multiday) + len(hidden_singles))
            overflow_keys.update(event.event_key for event in hidden_multiday)
            overflow_keys.update(event.event_key for event in hidden_singles)

        layouts.append(
            _WeekLayout(
                row=row,
                visible_lane_count=visible_lane_count,
                segments=visible_segments,
                single_events=tuple(single_events),
                hidden_counts=tuple(hidden_counts),
            )
        )
    return tuple(layouts), overflow_keys


def _calendar_overflow_keys(page: CalendarPrintPage, width_pt: float, height_pt: float) -> set[str]:
    layouts, hidden = _build_week_layouts(page, width_pt, height_pt)
    drawn = {segment.event.event_key for layout in layouts for segment in layout.segments}
    drawn.update(
        event.event_key for layout in layouts for events in layout.single_events for event in events
    )
    hidden.update(event.event_key for event in page.events if event.event_key not in drawn)
    return hidden


def _detail_capacity(height_pt: float) -> int:
    return max(8, math.floor((height_pt - 86.0) / 23.0))


def _build_sheet_plan(
    document: CalendarPrintDocument,
    width_pt: float,
    height_pt: float,
) -> tuple[list[_SheetPlan], int]:
    sheets: list[_SheetPlan] = []
    overflow_total = 0
    detail_capacity = _detail_capacity(height_pt)
    for period_index, page in enumerate(document.pages):
        sheets.append(_SheetPlan("calendar", period_index, page))
        overflow = _calendar_overflow_keys(page, width_pt, height_pt)
        overflow_total += len(overflow)
        if not page.events:
            continue
        if document.request.detail_page_mode == "overflow" and not overflow:
            continue
        detail_events = (
            tuple(event for event in page.events if event.event_key in overflow)
            if document.request.detail_page_mode == "overflow"
            else page.events
        )
        ordered = tuple(sorted(detail_events, key=_details_event_sort_key))
        for offset in range(0, len(ordered), detail_capacity):
            sheets.append(
                _SheetPlan(
                    "details",
                    period_index,
                    page,
                    ordered[offset : offset + detail_capacity],
                )
            )
    return sheets, overflow_total


def _draw_header(
    ctx: _RenderContext,
    page: CalendarPrintPage,
    document: CalendarPrintDocument,
) -> None:
    ctx.draw_text(
        ctx.rect(0, 0, ctx.width_pt * 0.62, 28),
        _period_title(page),
        size=16.0,
        bold=True,
    )
    scope = t(
        "print.scope_summary",
        "출력 범위: {start} ~ {end}",
        start=document.request.start_date.isoformat(),
        end=document.request.end_date.isoformat(),
    )
    ctx.draw_text(
        ctx.rect(0, 27, ctx.width_pt * 0.62, 17),
        scope,
        size=8.0,
        color="#4b5563",
        elide=True,
    )
    ctx.painter.setPen(ctx.pen("#d7dce4", 0.45))
    ctx.painter.drawLine(
        ctx.rect(0, 52, ctx.width_pt, 0).topLeft(),
        ctx.rect(0, 52, ctx.width_pt, 0).topRight(),
    )

    used_calendars: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for event in page.events:
        if event.calendar_id in seen:
            continue
        seen.add(event.calendar_id)
        used_calendars.append((event.calendar_id, event.calendar_name, event.calendar_color))

    legend_x = ctx.width_pt * 0.62
    legend_width = ctx.width_pt - legend_x
    item_width = max(72.0, legend_width / max(1, min(4, len(used_calendars))))
    for index, (_, name, color_value) in enumerate(used_calendars[:8]):
        row = index // 4
        col = index % 4
        x = legend_x + col * item_width
        y = 5.0 + row * 17.0
        accent = (
            _gray(_valid_color(color_value))
            if document.request.grayscale
            else _valid_color(color_value)
        )
        ctx.painter.setPen(Qt.PenStyle.NoPen)
        ctx.painter.setBrush(QBrush(accent))
        ctx.painter.drawEllipse(ctx.rect(x, y + 4, 7, 7))
        ctx.painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        ctx.draw_text(
            ctx.rect(x + 10, y, item_width - 12, 15),
            name,
            size=7.0,
            color="#374151",
            elide=True,
        )
    if len(used_calendars) > 8:
        ctx.draw_text(
            ctx.rect(legend_x, 38, legend_width, 14),
            t("print.more_calendars", "+{count}개 캘린더", count=len(used_calendars) - 8),
            size=7.0,
            color="#4b5563",
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )


def _draw_weekday_header(
    ctx: _RenderContext,
    page: CalendarPrintPage,
    geometry: dict,
) -> None:
    columns = int(geometry["columns"])
    cell_width = float(geometry["cell_width"])
    y = float(geometry["header_height"])
    height = float(geometry["weekday_height"])
    names = _weekday_names()
    first_week = page.grid_dates[:columns]
    for col, target in enumerate(first_week):
        rect = ctx.rect(col * cell_width, y, cell_width, height)
        ctx.painter.fillRect(rect, QBrush(QColor("#f4f6f8")))
        ctx.painter.setPen(ctx.pen("#d5dae2", 0.45))
        ctx.painter.drawRect(rect)
        color = "#111827"
        if page.page_unit != "week" or len(first_week) >= 5:
            if target.weekday() == 5:
                color = "#2563a8"
            elif target.weekday() == 6:
                color = "#b4232f"
        ctx.draw_text(
            rect,
            names[target.weekday()],
            size=8.5,
            color=color,
            bold=True,
            align=Qt.AlignmentFlag.AlignCenter,
        )


def _draw_event_line(
    ctx: _RenderContext,
    rect: QRectF,
    event: CalendarPrintEvent,
    target: date,
    *,
    grayscale: bool,
) -> None:
    accent, fill = _event_color(event, grayscale)
    radius = 2.5 * ctx.scale
    ctx.painter.setPen(ctx.pen(_mix(accent, QColor("#ffffff"), 0.52), 0.35))
    ctx.painter.setBrush(QBrush(fill))
    ctx.painter.drawRoundedRect(rect, radius, radius)
    strip = QRectF(rect.x(), rect.y(), max(ctx.scale * 2.2, 1.0), rect.height())
    ctx.painter.fillRect(strip, QBrush(accent))
    text_rect = QRectF(
        rect.x() + 4.0 * ctx.scale,
        rect.y(),
        max(0.0, rect.width() - 5.0 * ctx.scale),
        rect.height(),
    )
    ctx.draw_text(
        text_rect,
        _event_cell_text(event, target),
        size=8.0,
        color="#111827",
        elide=True,
    )


def _draw_multiday_bar(
    ctx: _RenderContext,
    rect: QRectF,
    segment: _MultidaySegment,
    *,
    grayscale: bool,
) -> None:
    accent, fill = _event_color(segment.event, grayscale)
    radius = 3.2 * ctx.scale
    ctx.painter.setPen(ctx.pen(_mix(accent, QColor("#ffffff"), 0.35), 0.55))
    ctx.painter.setBrush(QBrush(fill))
    ctx.painter.drawRoundedRect(rect, radius, radius)
    if segment.event.start_date == segment.visible_start:
        strip = QRectF(rect.x(), rect.y(), max(ctx.scale * 2.6, 1.0), rect.height())
        ctx.painter.fillRect(strip, QBrush(accent))
    text_rect = QRectF(
        rect.x() + 5.0 * ctx.scale,
        rect.y(),
        max(0.0, rect.width() - 8.0 * ctx.scale),
        rect.height(),
    )
    ctx.draw_text(
        text_rect,
        _multiday_segment_text(segment),
        size=8.0,
        color="#111827",
        bold=segment.event.priority in {"urgent", "high"},
        elide=True,
    )


def _draw_calendar_sheet(
    ctx: _RenderContext,
    sheet: _SheetPlan,
    document: CalendarPrintDocument,
) -> set[str]:
    page = sheet.page
    geometry = _calendar_geometry(page, ctx.width_pt, ctx.height_pt)
    _draw_header(ctx, page, document)
    _draw_weekday_header(ctx, page, geometry)

    columns = int(geometry["columns"])
    cell_width = float(geometry["cell_width"])
    cell_height = float(geometry["cell_height"])
    grid_y = float(geometry["header_height"] + geometry["weekday_height"])
    day_header_height = float(geometry["day_header_height"])
    event_line_height = float(geometry["event_line_height"])
    drawn: set[str] = set()

    # Draw the calendar paper first, then place event layers over the complete
    # grid. This lets multi-day events read as one continuous weekly ribbon.
    for index, target in enumerate(page.grid_dates):
        row = index // columns
        col = index % columns
        x = col * cell_width
        y = grid_y + row * cell_height
        cell = ctx.rect(x, y, cell_width, cell_height)
        in_scope = page.period_start <= target <= page.period_end
        is_other_month = page.page_unit == "month" and target.month != page.anchor_date.month
        background = QColor("#ffffff")
        if not in_scope:
            background = QColor("#f3f4f6")
        elif is_other_month:
            background = QColor("#fafbfc")
        ctx.painter.fillRect(cell, QBrush(background))
        ctx.painter.setPen(ctx.pen("#d4d9e1", 0.38))
        ctx.painter.drawRect(cell)

        date_color = "#9aa0a8" if not in_scope or is_other_month else "#20242a"
        if in_scope and not document.request.grayscale:
            if target.weekday() == 5:
                date_color = "#2563a8"
            elif target.weekday() == 6:
                date_color = "#b4232f"
        date_text = str(target.day)
        if is_other_month:
            date_text = f"{target.month}/{target.day}"
        ctx.draw_text(
            ctx.rect(x + 3, y + 1, cell_width - 6, day_header_height - 1),
            date_text,
            size=9.0,
            color=date_color,
            bold=in_scope and target == date.today(),
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

    layouts, _ = _build_week_layouts(page, ctx.width_pt, ctx.height_pt)
    for layout in layouts:
        row_y = grid_y + layout.row * cell_height
        for segment in layout.segments:
            event_rect = ctx.rect(
                segment.start_col * cell_width + 2.5,
                row_y + day_header_height + segment.lane * event_line_height,
                (segment.end_col - segment.start_col + 1) * cell_width - 5,
                event_line_height - 1.2,
            )
            _draw_multiday_bar(
                ctx,
                event_rect,
                segment,
                grayscale=document.request.grayscale,
            )
            drawn.add(segment.event.event_key)

        row_dates = page.grid_dates[layout.row * columns : (layout.row + 1) * columns]
        for col, target in enumerate(row_dates):
            x = col * cell_width
            for event_index, event in enumerate(layout.single_events[col]):
                line_index = layout.visible_lane_count + event_index
                event_rect = ctx.rect(
                    x + 2.5,
                    row_y + day_header_height + line_index * event_line_height,
                    cell_width - 5,
                    event_line_height - 1.2,
                )
                _draw_event_line(
                    ctx,
                    event_rect,
                    event,
                    target,
                    grayscale=document.request.grayscale,
                )
                drawn.add(event.event_key)

            hidden_count = layout.hidden_counts[col]
            if hidden_count <= 0:
                continue
            hidden_y = (
                row_y
                + day_header_height
                + (layout.visible_lane_count + len(layout.single_events[col])) * event_line_height
            )
            ctx.draw_text(
                ctx.rect(x + 4, hidden_y, cell_width - 8, event_line_height),
                t("print.more_events", "+{count}건 · 상세 페이지", count=hidden_count),
                size=7.4,
                color="#334155",
                bold=True,
                elide=True,
            )

    return drawn


def _detail_period_text(event: CalendarPrintEvent) -> str:
    if event.start_date == event.end_date:
        return event.start_date.isoformat()
    return f"{event.start_date.isoformat()} ~ {event.end_date.isoformat()}"


def _draw_details_sheet(
    ctx: _RenderContext,
    sheet: _SheetPlan,
    document: CalendarPrintDocument,
) -> set[str]:
    page = sheet.page
    ctx.draw_text(
        ctx.rect(0, 0, ctx.width_pt, 28),
        t("print.details_title", "{period} 상세 일정", period=_period_title(page)),
        size=15.0,
        bold=True,
    )
    details_hint = (
        t("print.details_hint_all", "선택한 기간의 전체 일정 목록입니다.")
        if document.request.detail_page_mode == "all"
        else t(
            "print.details_hint",
            "달력 칸에 표시되지 않은 일정만 모았습니다.",
        )
    )
    ctx.draw_text(
        ctx.rect(0, 28, ctx.width_pt, 16),
        details_hint,
        size=8.0,
        color="#4b5563",
    )

    header_y = 50.0
    row_height = 23.0
    columns = (76.0, 48.0, 96.0)
    ctx.painter.fillRect(ctx.rect(0, header_y, ctx.width_pt, 20), QBrush(QColor("#f0f3f7")))
    detail_accent = QColor("#6b7280" if document.request.grayscale else "#4d7cff")
    ctx.painter.fillRect(ctx.rect(0, header_y, 3.0, 20), QBrush(detail_accent))
    headers = (
        t("print.column_date", "날짜"),
        t("print.column_time", "시간"),
        t("print.column_calendar", "캘린더"),
        t("print.column_schedule", "일정"),
    )
    x = 0.0
    widths = (*columns, ctx.width_pt - sum(columns))
    for label, width in zip(headers, widths, strict=True):
        ctx.draw_text(
            ctx.rect(x + 4, header_y, width - 8, 20),
            label,
            size=8.0,
            bold=True,
            elide=True,
        )
        x += width

    drawn: set[str] = set()
    for index, event in enumerate(sheet.detail_events):
        y = header_y + 20.0 + index * row_height
        if index % 2:
            ctx.painter.fillRect(
                ctx.rect(0, y, ctx.width_pt, row_height), QBrush(QColor("#fafbfc"))
            )
        accent, _ = _event_color(event, document.request.grayscale)
        ctx.painter.fillRect(ctx.rect(0, y, 2.5, row_height), QBrush(accent))
        ctx.painter.setPen(ctx.pen("#d2d7df", 0.35))
        ctx.painter.drawLine(
            ctx.rect(0, y + row_height, ctx.width_pt, 0).topLeft(),
            ctx.rect(0, y + row_height, ctx.width_pt, 0).topRight(),
        )

        time_text = _event_time_text(event)
        title = f"{_priority_marker(event)}{event.name}"
        if document.request.include_location and event.location:
            title = f"{title} · {event.location}"
        values = (_detail_period_text(event), time_text, event.calendar_name, title)
        x = 0.0
        for value, width in zip(values, widths, strict=True):
            ctx.draw_text(
                ctx.rect(x + 4, y, width - 8, row_height),
                value,
                size=8.3,
                color="#111827",
                elide=True,
            )
            x += width
        drawn.add(event.event_key)
    return drawn


def _draw_footer(
    ctx: _RenderContext,
    document: CalendarPrintDocument,
    sheet_number: int,
    total_sheets: int,
    *,
    details_follow_count: int = 0,
) -> None:
    y = ctx.height_pt - 15.0
    created = document.created_at.strftime("%Y-%m-%d %H:%M")
    ctx.draw_text(
        ctx.rect(0, y, ctx.width_pt * 0.42, 13),
        t("print.generated_at", "생성: {created}", created=created),
        size=6.8,
        color="#6b7280",
    )
    if details_follow_count > 0:
        ctx.draw_text(
            ctx.rect(ctx.width_pt * 0.42, y, ctx.width_pt * 0.36, 13),
            t(
                "print.details_follow",
                "상세 일정 {count}건 · 다음 페이지",
                count=details_follow_count,
            ),
            size=6.8,
            color="#2563a8",
            bold=True,
            align=Qt.AlignmentFlag.AlignCenter,
            elide=True,
        )
    ctx.draw_text(
        ctx.rect(ctx.width_pt * 0.78, y, ctx.width_pt * 0.22, 13),
        t(
            "print.page_number",
            "{current} / {total}",
            current=sheet_number,
            total=total_sheets,
        ),
        size=7.0,
        color="#4b5563",
        align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    )


def render_calendar_document(
    printer: QPrinter,
    document: CalendarPrintDocument,
) -> CalendarPrintRenderReport:
    if not printer.isValid() and printer.outputFormat() != QPrinter.OutputFormat.PdfFormat:
        raise RuntimeError(t("print.error_invalid_printer", "사용 가능한 프린터가 없습니다."))

    page_rect_points = printer.pageLayout().paintRect(QPageLayout.Unit.Point)
    sheets, overflow_total = _build_sheet_plan(
        document,
        float(page_rect_points.width()),
        float(page_rect_points.height()),
    )
    if not sheets:
        raise RuntimeError(t("print.error_no_pages", "출력할 페이지가 없습니다."))

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(t("print.error_begin", "인쇄 출력을 시작하지 못했습니다."))

    drawn: set[str] = set()
    try:
        for index, sheet in enumerate(sheets):
            if index > 0 and not printer.newPage():
                raise RuntimeError(
                    t("print.error_new_page", "다음 인쇄 페이지를 만들지 못했습니다.")
                )
            painter.fillRect(painter.viewport(), QBrush(QColor("#ffffff")))
            ctx = _RenderContext(painter, printer)
            if sheet.kind == "details":
                drawn.update(_draw_details_sheet(ctx, sheet, document))
            else:
                drawn.update(_draw_calendar_sheet(ctx, sheet, document))
            has_details_after = (
                sheet.kind == "calendar"
                and index + 1 < len(sheets)
                and sheets[index + 1].kind == "details"
                and sheets[index + 1].period_index == sheet.period_index
            )
            details_follow_count = (
                sum(
                    len(candidate.detail_events)
                    for candidate in sheets[index + 1 :]
                    if candidate.kind == "details" and candidate.period_index == sheet.period_index
                )
                if has_details_after
                else 0
            )
            _draw_footer(
                ctx,
                document,
                index + 1,
                len(sheets),
                details_follow_count=details_follow_count,
            )
    finally:
        painter.end()

    expected = {event.event_key for page in document.pages for event in page.events}
    missing = tuple(sorted(expected - drawn))
    return CalendarPrintRenderReport(
        sheet_count=len(sheets),
        calendar_sheet_count=sum(1 for sheet in sheets if sheet.kind == "calendar"),
        detail_sheet_count=sum(1 for sheet in sheets if sheet.kind == "details"),
        overflow_event_count=overflow_total,
        drawn_event_keys=tuple(sorted(drawn)),
        missing_event_keys=missing,
    )
