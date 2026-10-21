# -*- coding: utf-8 -*-
"""Interactive weekly time grid; persistence belongs to the connected controller."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from html import escape
import math
import re

from PyQt6.QtCore import QDate, QEvent, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QMenu, QScrollArea, QVBoxLayout, QWidget

from calendar_app.application.week_planner_usecases import (
    normalized_task_interval,
    scheduling_block_reason,
)
from calendar_app.infrastructure.i18n import t
from calendar_app.shared.ui_tokens import get_ui_tokens


def _truth(value) -> bool:
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "null", "none"}


def _css_color(value, fallback: QColor) -> QColor:
    """Accept the semantic tokens' hex and CSS rgba forms without raw QSS."""
    if isinstance(value, QColor):
        return QColor(value)
    color = QColor(str(value or ""))
    if color.isValid():
        return color
    match = re.fullmatch(r"rgba?\(([^)]+)\)", str(value or "").strip())
    if match:
        try:
            parts = [float(part.strip()) for part in match.group(1).split(",")]
            if len(parts) in {3, 4}:
                alpha = parts[3] if len(parts) == 4 else 1.0
                if alpha <= 1.0:
                    alpha *= 255
                return QColor(
                    *(max(0, min(255, round(part))) for part in parts[:3]),
                    max(0, min(255, round(alpha))),
                )
        except ValueError:
            pass
    return QColor(fallback)


def _mix(foreground: QColor, background: QColor, amount: float) -> QColor:
    """Interpolate semantic colors without silently making them opaque."""
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        *(
            round(a * amount + b * (1.0 - amount))
            for a, b in zip(
                (foreground.red(), foreground.green(), foreground.blue(), foreground.alpha()),
                (background.red(), background.green(), background.blue(), background.alpha()),
                strict=True,
            )
        )
    )


def _date_from_value(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _time_text(minutes: float) -> str:
    value = max(0, min(1440, round(minutes)))
    return f"{value // 60:02d}:{value % 60:02d}"


def _fitted_time_text(start: float, end: float, metrics, width: float) -> str:
    """Use a complete start time when a narrow overlap lane cannot fit the range."""
    text = f"{_time_text(start)} – {_time_text(end)}"
    if metrics.horizontalAdvance(text) > width:
        text = _time_text(start)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1, round(width)))


@dataclass
class _Segment:
    task: dict
    day: int
    start: float
    end: float
    original_start: dt.datetime | None = None
    original_end: dt.datetime | None = None
    offset: float = 0.0
    duration: int = 15
    final: bool = True
    all_day: bool = False
    lane: int = 0
    lanes: int = 1


class _Canvas(QWidget):
    def __init__(self, grid: WeekTimeGrid, role: str):
        super().__init__(grid)
        self.grid = grid
        self.role = role
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(t("week_planner.accessible_name", "주간 시간표"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.grid._paint(painter, self.role, event.rect())
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.grid._press(self, event.position(), event.globalPosition())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.grid._move(self, event.position(), event.globalPosition())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.grid._release(self, event.position(), event.globalPosition())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.grid._cancel()
            hit = self.grid._hit(self.role, event.position())
            if hit:
                self.grid.edit_requested.emit(hit.task)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        hit = self.grid._hit(self.role, QPointF(event.pos()))
        if hit:
            self.grid._cancel()
            self.grid._selected = hit.task
            menu = QMenu(self)
            menu.addAction(
                t("week_planner.open", "일정 열기"), lambda: self.grid.edit_requested.emit(hit.task)
            )
            menu.exec(event.globalPos())
            event.accept()


class WeekTimeGrid(QWidget):
    """Fixed day/all-day headers above a 24-hour, 15-minute-snapping timeline.

    Task dictionaries are never mutated. All requested changes are signals, so
    controllers can apply fresh DB reads, permissions, undo and sync policies.
    ``dates`` supports the main calendar's Sunday start and hidden weekends.
    """

    create_requested = pyqtSignal(str, int, int)
    reschedule_requested = pyqtSignal(dict, str, int, int)
    edit_requested = pyqtSignal(dict)
    day_selected = pyqtSignal(QDate)
    scroll_position_changed = pyqtSignal(int)
    interaction_changed = pyqtSignal(bool)

    GUTTER = 62
    HOUR_HEIGHT = 72
    HEADER_HEIGHT = 52
    ALL_DAY_ROW = 26
    SNAP = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("week_time_grid")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(300, 220)
        self.setAccessibleName(t("week_planner.accessible_name", "주간 시간표"))
        self.setAccessibleDescription(
            t(
                "week_planner.accessible_help",
                "빈 시간 클릭 또는 드래그로 추가, 일정 드래그로 이동, 아래 가장자리로 시간 조절. "
                "방향키로 일정 선택, Enter로 열기, Esc로 취소.",
            )
        )
        self._dates: list[QDate] = []
        self._segments: list[_Segment] = []
        self._all_day: list[_Segment] = []
        self._timed_rects: list[tuple[_Segment, QRectF]] = []
        self._all_day_rects: list[tuple[_Segment, QRectF]] = []
        self._selected: dict | None = None
        self._selected_date = QDate()
        self._gesture: dict | None = None
        self._preview: tuple[dt.datetime, int] | None = None
        self._pointer_global: QPointF | None = None
        self._tokens: dict = {}
        self._pending_scroll: int | None = None
        self._restoring_scroll = False
        self._header = _Canvas(self, "header")
        self._header.setFixedHeight(self.HEADER_HEIGHT)
        self._all_day_canvas = _Canvas(self, "all_day")
        self._timeline = _Canvas(self, "timeline")
        self._timeline.setMinimumHeight(self.HOUR_HEIGHT * 24 + 16)
        self._all_day_scroll = self._scroll_area(self._all_day_canvas)
        self._all_day_scroll.setFixedHeight(self.ALL_DAY_ROW + 8)
        self._all_day_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll = self._scroll_area(self._timeline)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._all_day_scroll)
        layout.addWidget(self._scroll, 1)
        self._now_timer = QTimer(self)
        self._now_timer.setInterval(60_000)
        self._now_timer.timeout.connect(self._timeline.update)
        self._now_timer.start()
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(50)
        self._autoscroll_timer.timeout.connect(self._autoscroll_tick)
        self.set_week(QDate.currentDate(), [])

    def _scroll_area(self, canvas: QWidget) -> QScrollArea:
        area = QScrollArea(self)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        area.setWidget(canvas)
        self._transparent_scroll_children(area)
        return area

    @staticmethod
    def _transparent_scroll_children(area: QScrollArea):
        # QScrollArea.setWidget() enables autofill on its child. Leave the
        # calendar surface as the only owner of the decorative background.
        for widget in (area, area.viewport(), area.widget()):
            widget.setAutoFillBackground(False)
            palette = widget.palette()
            for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base):
                palette.setColor(role, QColor(Qt.GlobalColor.transparent))
            widget.setPalette(palette)

    def apply_theme(self, tokens=None):
        """Refresh appearance without cancelling gestures or rebuilding tasks.

        ``calendar_bg`` may be transparent when the containing calendar frame
        already paints the live-opacity surface. Standalone grids use bg_main.
        """
        resolved = dict(get_ui_tokens())
        if tokens:
            resolved.update(tokens)
        if resolved == self._tokens:
            return
        self._tokens = resolved
        self._apply_scrollbar_theme()
        self.update()
        self._repaint()

    def set_selected_date(self, date: QDate):
        selected = QDate(date) if isinstance(date, QDate) and date in self._dates else QDate()
        if selected != self._selected_date:
            self._selected_date = selected
            self._header.update()

    def set_week(
        self,
        start_date: QDate,
        tasks: list[dict],
        *,
        days=7,
        dates: list[QDate] | None = None,
        tokens=None,
    ):
        self._cancel()
        if not isinstance(start_date, QDate) or not start_date.isValid():
            raise ValueError("A valid start_date is required")
        requested_dates = (
            dates if dates is not None else [start_date.addDays(i) for i in range(days)]
        )
        self._dates = []
        for date in requested_dates:
            if isinstance(date, QDate) and date.isValid() and date not in self._dates:
                self._dates.append(QDate(date))
        if not self._dates:
            raise ValueError("At least one visible date is required")
        self.set_selected_date(self._selected_date)
        self.apply_theme(tokens)
        self._segments = []
        self._all_day = []
        self._selected = None
        for task in tasks:
            if not isinstance(task, dict):
                continue
            interval = normalized_task_interval(task)
            if interval is not None:
                start, end = interval
                duration = max(1, math.ceil((end - start).total_seconds() / 60))
                for index, date in enumerate(self._dates):
                    midnight = dt.datetime.combine(date.toPyDate(), dt.time())
                    next_midnight = midnight + dt.timedelta(days=1)
                    visible_start, visible_end = max(start, midnight), min(end, next_midnight)
                    if visible_start < visible_end:
                        self._segments.append(
                            _Segment(
                                task,
                                index,
                                (visible_start - midnight).total_seconds() / 60,
                                (visible_end - midnight).total_seconds() / 60,
                                start,
                                end,
                                (visible_start - start).total_seconds() / 60,
                                duration,
                                end <= next_midnight,
                            )
                        )
            else:
                start_value = (
                    task.get("deadline") or task.get("_start_raw") or task.get("target_date")
                )
                start = _date_from_value(start_value)
                if start is None:
                    continue
                raw_start = task.get("_start_raw") or start_value
                is_date_only = isinstance(raw_start, dt.date) and not isinstance(
                    raw_start, dt.datetime
                )
                is_date_only = is_date_only or len(str(raw_start or "").strip()) == 10
                if not _truth(task.get("all_day", 0)) and not is_date_only:
                    continue
                end = _date_from_value(task.get("end_date"))
                if end is None:
                    end = _date_from_value(task.get("_end_raw"))
                    if end is not None and task.get("_end_raw"):
                        end -= dt.timedelta(days=1)
                end = max(start, end or start)
                for index, date in enumerate(self._dates):
                    if start <= date.toPyDate() <= end:
                        self._all_day.append(_Segment(task, index, 0, 0, all_day=True))
        self._assign_lanes()
        max_rows = max(
            (sum(item.day == day for item in self._all_day) for day in range(len(self._dates))),
            default=0,
        )
        self._all_day_canvas.setMinimumHeight(max(1, max_rows) * self.ALL_DAY_ROW + 8)
        self._all_day_scroll.setFixedHeight(min(max(1, max_rows), 3) * self.ALL_DAY_ROW + 8)
        self._relayout()
        QTimer.singleShot(0, self._relayout)

    def _apply_scrollbar_theme(self):
        def css(color: QColor) -> str:
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"

        track = self._color("bg_alt", QPalette.ColorRole.Window)
        track.setAlpha(min(track.alpha(), 32))
        muted = self._color("text_muted", QPalette.ColorRole.Mid)
        accent = self._color("accent", QPalette.ColorRole.Highlight)
        border = self._color("border", QPalette.ColorRole.Mid)
        style = f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: {css(track)}; width: 10px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {css(muted)}; border: 1px solid {css(border)};
                border-radius: 4px; min-height: 32px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {css(accent)}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none; background: transparent;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """
        for area in (self._all_day_scroll, self._scroll):
            area.setStyleSheet(style)
            self._transparent_scroll_children(area)

    def scroll_to_time(self, minutes: int):
        """Restore a top minute after Qt has finalized the scroll viewport."""
        self._pending_scroll = max(0, min(1440, int(minutes)))
        self._restore_scroll()
        QTimer.singleShot(0, self._restore_scroll)

    def _restore_scroll(self):
        if self._pending_scroll is None:
            return
        self._restoring_scroll = True
        self._scroll.verticalScrollBar().setValue(
            round(self._pending_scroll * self.HOUR_HEIGHT / 60)
        )
        self._restoring_scroll = False
        if self.isVisible():
            self._pending_scroll = None

    def _scroll_changed(self, value: int):
        if not self._restoring_scroll:
            self.scroll_position_changed.emit(round(value * 60 / self.HOUR_HEIGHT))

    def event_rects(self) -> list[tuple[dict, QDate, QRectF]]:
        """Return timeline-local event geometry for QA and integrations."""
        self._relayout()
        return [
            (item.task, QDate(self._dates[item.day]), QRectF(rect))
            for item, rect in self._timed_rects
        ]

    def _assign_lanes(self):
        for day in range(len(self._dates)):
            events = sorted(
                (item for item in self._segments if item.day == day),
                key=lambda item: (item.start, item.end),
            )
            group: list[_Segment] = []
            group_end = -1.0

            def finish(items):
                lane_ends: list[float] = []
                for item in items:
                    lane = next(
                        (i for i, end in enumerate(lane_ends) if end <= item.start), len(lane_ends)
                    )
                    if lane == len(lane_ends):
                        lane_ends.append(0.0)
                    lane_ends[lane] = max(item.end, item.start + self.SNAP)
                    item.lane = lane
                for item in items:
                    item.lanes = max(1, len(lane_ends))

            for item in events:
                if group and item.start >= group_end:
                    finish(group)
                    group = []
                group.append(item)
                group_end = max(
                    group_end if len(group) > 1 else 0, item.end, item.start + self.SNAP
                )
            finish(group)

    def _column_width(self) -> float:
        return max(1.0, (self._timeline.width() - self.GUTTER) / max(1, len(self._dates)))

    def _relayout(self):
        width = max(self.GUTTER + len(self._dates) * 24, self._scroll.viewport().width())
        if self._timeline.width() != width:
            self._timeline.setFixedWidth(width)
        self._header.setFixedWidth(width)
        self._all_day_canvas.setFixedWidth(width)
        column = self._column_width()
        self._timed_rects = []
        for item in self._segments:
            lane_width = (column - 6) / item.lanes
            rect = QRectF(
                self.GUTTER + item.day * column + 3 + item.lane * lane_width,
                item.start * self.HOUR_HEIGHT / 60 + 1,
                max(1, lane_width - 2),
                max(14, (item.end - item.start) * self.HOUR_HEIGHT / 60 - 2),
            )
            self._timed_rects.append((item, rect))
        self._all_day_rects = []
        for day in range(len(self._dates)):
            items = [item for item in self._all_day if item.day == day]
            for row, item in enumerate(items):
                rect = QRectF(
                    self.GUTTER + day * column + 3,
                    4 + row * self.ALL_DAY_ROW,
                    max(1, column - 6),
                    self.ALL_DAY_ROW - 4,
                )
                self._all_day_rects.append((item, rect))
        self._repaint()

    def _repaint(self):
        self._header.update()
        self._all_day_canvas.update()
        self._timeline.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._relayout)

    def showEvent(self, event):
        super().showEvent(event)
        self._relayout()
        QTimer.singleShot(0, self._restore_scroll)

    def hideEvent(self, event):
        self._cancel()
        super().hideEvent(event)

    def event(self, event):
        if event.type() in {QEvent.Type.WindowDeactivate, QEvent.Type.DeferredDelete} and hasattr(
            self, "_gesture"
        ):
            self._cancel()
        return super().event(event)

    def _color(self, key: str, role=QPalette.ColorRole.WindowText) -> QColor:
        return _css_color(self._tokens.get(key), self.palette().color(role))

    def _surface(self) -> QColor:
        key = "calendar_bg" if "calendar_bg" in self._tokens else "bg_main"
        return self._color(key, QPalette.ColorRole.Window)

    def _reading_surface(self) -> QColor:
        return self._color("content_bg", QPalette.ColorRole.Window)

    def paintEvent(self, event):
        # Paint once, rather than once each for the scroll area, viewport and
        # canvas. This retains the caller's alpha over the desktop wallpaper.
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._surface())
        painter.end()

    def _paint(self, painter: QPainter, role: str, clip):
        border, accent = (
            self._color("border", QPalette.ColorRole.Mid),
            self._color("accent", QPalette.ColorRole.Highlight),
        )
        primary, muted = self._color("text_primary"), self._color("text_muted")
        column = self._column_width()
        if role == "header":
            for index, date in enumerate(self._dates):
                x = self.GUTTER + index * column
                current = date == QDate.currentDate()
                selected = date == self._selected_date
                if selected:
                    highlight = QColor(accent)
                    highlight.setAlpha(24)
                    painter.fillRect(
                        QRectF(x + 2, 2, column - 4, self.HEADER_HEIGHT - 4), highlight
                    )
                    painter.setPen(QPen(accent, 2))
                    painter.drawLine(
                        QPointF(x + 10, self.HEADER_HEIGHT - 4),
                        QPointF(x + column - 10, self.HEADER_HEIGHT - 4),
                    )
                painter.setPen(accent if current else muted)
                small = QFont(self.font())
                small.setPointSizeF(max(8, self.font().pointSizeF() - 1))
                painter.setFont(small)
                weekdays = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
                label = t(
                    f"weekday.{weekdays[date.dayOfWeek() - 1]}",
                    ("월", "화", "수", "목", "금", "토", "일")[date.dayOfWeek() - 1],
                )
                painter.drawText(QRectF(x, 4, column, 17), Qt.AlignmentFlag.AlignCenter, str(label))
                number = QFont(self.font())
                number.setPointSizeF(max(11, self.font().pointSizeF() + 2))
                number.setBold(current)
                painter.setFont(number)
                painter.setPen(accent if current else primary)
                painter.drawText(
                    QRectF(x, 21, column, 25), Qt.AlignmentFlag.AlignCenter, str(date.day())
                )
            painter.setPen(QPen(border, 1))
            painter.drawLine(
                QPointF(0, self.HEADER_HEIGHT - 1),
                QPointF(self._header.width(), self.HEADER_HEIGHT - 1),
            )
            return
        if role == "all_day":
            painter.setPen(muted)
            painter.setFont(self.font())
            painter.drawText(
                QRectF(0, 4, self.GUTTER - 8, self.ALL_DAY_ROW - 4),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                t("week_planner.all_day", "종일"),
            )
            rects = self._all_day_rects
        else:
            for index, date in enumerate(self._dates):
                if date == QDate.currentDate():
                    today_tint = QColor(accent)
                    today_tint.setAlpha(6)
                    painter.fillRect(
                        QRectF(self.GUTTER + index * column, 0, column, self._timeline.height()),
                        today_tint,
                    )
            for minute in range(0, 1441, 15):
                y = minute * self.HOUR_HEIGHT / 60
                if y < clip.top() - 14 or y > clip.bottom() + 14:
                    continue
                strong = minute % 60 == 0
                line_color = QColor(border)
                if not strong:
                    line_color.setAlphaF(border.alphaF() * 0.22)
                painter.setPen(QPen(line_color, 1))
                painter.drawLine(QPointF(self.GUTTER, y), QPointF(self._timeline.width(), y))
                if strong:
                    painter.setPen(muted)
                    painter.drawText(
                        QRectF(
                            0,
                            max(self._scroll.verticalScrollBar().value(), y - 9),
                            self.GUTTER - 9,
                            18,
                        ),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        _time_text(minute),
                    )
            rects = self._timed_rects
        painter.setPen(QPen(border, 1))
        for index in range(len(self._dates) + 1):
            x = self.GUTTER + index * column
            painter.drawLine(QPointF(x, 0), QPointF(x, max(clip.bottom(), 0)))
        for item, rect in rects:
            if rect.intersects(QRectF(clip)):
                self._paint_event(painter, item, rect)
        if role == "timeline":
            self._paint_preview(painter)
            now = dt.datetime.now()
            today = QDate(now.year, now.month, now.day)
            if today in self._dates:
                x = self.GUTTER + self._dates.index(today) * column
                y = (now.hour * 60 + now.minute) * self.HOUR_HEIGHT / 60
                painter.setPen(QPen(accent, 1.5))
                painter.drawLine(QPointF(x, y), QPointF(x + column, y))
                painter.setBrush(accent)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(x, y), 3, 3)

    def _paint_event(self, painter: QPainter, item: _Segment, rect: QRectF):
        surface, accent = (
            self._reading_surface(),
            self._color("accent", QPalette.ColorRole.Highlight),
        )
        identity = _css_color(item.task.get("bg_color"), accent)
        selected = self._selected is item.task
        fill = _mix(identity, surface, 0.23 if selected else 0.14)
        fill.setAlpha(max(fill.alpha(), surface.alpha()))
        painter.setPen(
            QPen(accent if selected else _mix(identity, surface, 0.44), 1.5 if selected else 0.8)
        )
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(identity)
        painter.drawRoundedRect(QRectF(rect.left(), rect.top(), 3, rect.height()), 1, 1)
        painter.save()
        painter.setClipRect(rect.adjusted(5, 0, -3, 0))
        painter.setPen(self._color("text_primary"))
        font = QFont(self.font())
        font.setPointSizeF(max(8, self.font().pointSizeF() - 0.5))
        font.setBold(selected)
        painter.setFont(font)
        title = str(
            item.task.get("name")
            or item.task.get("title")
            or t("week_planner.untitled", "제목 없음")
        )
        title = painter.fontMetrics().elidedText(
            title, Qt.TextElideMode.ElideRight, max(1, round(rect.width() - 12))
        )
        painter.drawText(
            rect.adjusted(7, 0, -4, 0)
            if rect.height() < 32
            else QRectF(rect.left() + 7, rect.top() + 3, rect.width() - 11, 19),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        if not item.all_day and rect.height() >= 36:
            painter.setPen(self._color("text_secondary"))
            painter.drawText(
                QRectF(rect.left() + 7, rect.top() + 21, rect.width() - 11, 17),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _fitted_time_text(item.start, item.end, painter.fontMetrics(), rect.width() - 12),
            )
        painter.restore()
        if selected and item.final and not item.all_day and not self._read_only(item.task):
            painter.setPen(QPen(accent, 1.5))
            painter.drawLine(
                QPointF(rect.center().x() - min(9, rect.width() / 4), rect.bottom() - 3),
                QPointF(rect.center().x() + min(9, rect.width() / 4), rect.bottom() - 3),
            )

    def _paint_preview(self, painter: QPainter):
        if self._preview is None:
            return
        start, duration = self._preview
        end = start + dt.timedelta(minutes=duration)
        accent = self._color("accent", QPalette.ColorRole.Highlight)
        painter.setPen(QPen(accent, 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(_mix(accent, self._reading_surface(), 0.22))
        column = self._column_width()
        for day, date in enumerate(self._dates):
            midnight = dt.datetime.combine(date.toPyDate(), dt.time())
            lower, upper = max(start, midnight), min(end, midnight + dt.timedelta(days=1))
            if lower >= upper:
                continue
            minutes = (lower - midnight).total_seconds() / 60
            height = (upper - lower).total_seconds() / 60 * self.HOUR_HEIGHT / 60
            rect = QRectF(
                self.GUTTER + day * column + 3,
                minutes * self.HOUR_HEIGHT / 60 + 1,
                column - 6,
                max(14, height - 2),
            )
            painter.drawRoundedRect(rect, 4, 4)
            caption = rect.adjusted(4, 2, -4, -2)
            caption.setHeight(min(caption.height(), 39 if rect.height() >= 36 else 18))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._color("floating_bg", QPalette.ColorRole.Window))
            painter.drawRoundedRect(caption, 3, 3)
            painter.save()
            painter.setClipRect(caption)
            painter.setPen(self._color("text_primary"))
            painter.drawText(
                QRectF(caption.left() + 3, caption.top(), max(1, caption.width() - 6), 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                _fitted_time_text(
                    minutes,
                    minutes + height * 60 / self.HOUR_HEIGHT,
                    painter.fontMetrics(),
                    rect.width() - 12,
                ),
            )
            if rect.height() >= 36:
                duration_text = t("week_planner.duration", "{minutes}분").format(minutes=duration)
                painter.setPen(self._color("text_secondary"))
                painter.drawText(
                    QRectF(caption.left() + 3, caption.top() + 18, max(1, caption.width() - 6), 18),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    painter.fontMetrics().elidedText(
                        duration_text,
                        Qt.TextElideMode.ElideRight,
                        max(1, round(caption.width() - 6)),
                    ),
                )
            painter.restore()
            painter.setPen(QPen(accent, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(_mix(accent, self._reading_surface(), 0.22))

    @staticmethod
    def _read_only(task: dict) -> bool:
        return scheduling_block_reason(task) is not None

    def _hit(self, role: str, position: QPointF) -> _Segment | None:
        rects = (
            self._all_day_rects
            if role == "all_day"
            else self._timed_rects
            if role == "timeline"
            else []
        )
        return next((item for item, rect in reversed(rects) if rect.contains(position)), None)

    def _day_at(self, x: float) -> int | None:
        if x < self.GUTTER or x >= self._timeline.width():
            return None
        return min(len(self._dates) - 1, int((x - self.GUTTER) / self._column_width()))

    def _minute_at(self, y: float, *, end=False) -> int:
        minute = round(y * 60 / self.HOUR_HEIGHT / self.SNAP) * self.SNAP
        return max(0, min(1440 if end else 1440 - self.SNAP, minute))

    def _press(self, canvas: _Canvas, position: QPointF, global_position: QPointF):
        self._cancel()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        day = self._day_at(position.x())
        if day is None:
            return
        self.set_selected_date(self._dates[day])
        self.day_selected.emit(self._dates[day])
        if canvas.role == "header":
            return
        hit = self._hit(canvas.role, position)
        self._selected = hit.task if hit else None
        self._repaint()
        if hit and self._read_only(hit.task):
            return
        if canvas.role == "all_day" and hit is None:
            return
        kind = "all_day" if canvas.role == "all_day" else "move" if hit else "create"
        if hit and canvas.role == "timeline" and hit.final:
            rect = next(rect for item, rect in self._timed_rects if item is hit)
            if position.y() >= rect.bottom() - 5:
                kind = "resize"
        minute = self._minute_at(position.y()) if canvas.role == "timeline" else 0
        self._gesture = {
            "kind": kind,
            "item": hit,
            "day": day,
            "minute": minute,
            "origin": QPointF(global_position),
            "moved": False,
            "anchor": position.y() * 60 / self.HOUR_HEIGHT - hit.start
            if hit and not hit.all_day
            else 0.0,
        }
        self.interaction_changed.emit(True)
        if kind == "create":
            self._preview = (
                dt.datetime.combine(self._dates[day].toPyDate(), dt.time())
                + dt.timedelta(minutes=minute),
                self.SNAP,
            )
            self._timeline.update()

    def _move(self, canvas: _Canvas, position: QPointF, global_position: QPointF):
        if self._gesture is None:
            hit = self._hit(canvas.role, position)
            cursor = Qt.CursorShape.ArrowCursor
            if hit:
                title = str(
                    hit.task.get("name")
                    or hit.task.get("title")
                    or t("week_planner.untitled", "제목 없음")
                )
                period = (
                    t("week_planner.all_day", "종일")
                    if hit.all_day
                    else f"{_time_text(hit.start)} – {_time_text(hit.end)}"
                )
                reason = scheduling_block_reason(hit.task)
                suffix = ""
                if reason:
                    suffix = "\n" + (
                        t("week_planner.recurring_hint", "반복 일정은 편집 창에서 수정하세요.")
                        if reason == "recurring"
                        else t("week_planner.read_only", "읽기 전용")
                    )
                source = str(
                    hit.task.get("_calendar_name") or hit.task.get("_subscription_summary") or ""
                ).strip()
                if source:
                    suffix = "\n" + t("tooltip.label_calendar", "캘린더") + ": " + source + suffix
                canvas.setToolTip(
                    "<qt>"
                    + escape(
                        f"{title}\n{self._dates[hit.day].toString('yyyy-MM-dd')} · {period}{suffix}",
                        quote=False,
                    ).replace("\n", "<br>")
                    + "</qt>"
                )
                cursor = (
                    Qt.CursorShape.PointingHandCursor
                    if self._read_only(hit.task)
                    else Qt.CursorShape.OpenHandCursor
                )
                if canvas.role == "timeline" and hit.final and not self._read_only(hit.task):
                    rect = next(rect for item, rect in self._timed_rects if item is hit)
                    if position.y() >= rect.bottom() - 5:
                        cursor = Qt.CursorShape.SizeVerCursor
            else:
                canvas.setToolTip(
                    t(
                        "week_planner.create_hint",
                        "빈 시간을 클릭하거나 드래그해 일정을 추가하세요.",
                    )
                    if canvas.role == "timeline"
                    else ""
                )
            canvas.setCursor(cursor)
            return
        gesture = self._gesture
        self._pointer_global = QPointF(global_position)
        if (
            global_position - gesture["origin"]
        ).manhattanLength() >= QApplication.startDragDistance():
            gesture["moved"] = True
        if not gesture["moved"]:
            return
        self._autoscroll_timer.start()
        point = QPointF(self._timeline.mapFromGlobal(global_position.toPoint()))
        day = self._day_at(point.x())
        if day is None:
            self._preview = None
            self._timeline.update()
            return
        # Header-to-timeline dragging must actually enter the timeline viewport.
        if gesture["kind"] == "all_day":
            viewport_point = self._scroll.viewport().mapFromGlobal(global_position.toPoint())
            if not self._scroll.viewport().rect().contains(viewport_point):
                self._preview = None
                self._timeline.update()
                return
        midnight = dt.datetime.combine(self._dates[day].toPyDate(), dt.time())
        item = gesture["item"]
        if gesture["kind"] == "create":
            minute = self._minute_at(point.y(), end=True)
            low = min(gesture["minute"], minute)
            high = max(gesture["minute"], minute)
            self._preview = (
                dt.datetime.combine(self._dates[gesture["day"]].toPyDate(), dt.time())
                + dt.timedelta(minutes=low),
                max(self.SNAP, high - low),
            )
        elif gesture["kind"] == "resize":
            minute = self._minute_at(point.y(), end=True)
            end = dt.datetime.combine(self._dates[item.day].toPyDate(), dt.time()) + dt.timedelta(
                minutes=minute
            )
            self._preview = (
                item.original_start,
                max(self.SNAP, math.ceil((end - item.original_start).total_seconds() / 60)),
            )
        elif gesture["kind"] == "all_day":
            self._preview = (midnight + dt.timedelta(minutes=self._minute_at(point.y())), self.SNAP)
        else:
            new_segment_minute = (
                round((point.y() * 60 / self.HOUR_HEIGHT - gesture["anchor"]) / self.SNAP)
                * self.SNAP
            )
            new_segment_minute = max(0, min(1440 - self.SNAP, new_segment_minute))
            original_start = midnight + dt.timedelta(minutes=new_segment_minute - item.offset)
            # Every requested start remains on a visible 15-minute snap boundary.
            day_start = original_start.replace(hour=0, minute=0, second=0, microsecond=0)
            original_minute = (original_start - day_start).total_seconds() / 60
            original_start = day_start + dt.timedelta(
                minutes=round(original_minute / self.SNAP) * self.SNAP
            )
            self._preview = (original_start, item.duration)
        self._timeline.update()

    def _autoscroll_tick(self):
        if not self._gesture or self._pointer_global is None:
            self._autoscroll_timer.stop()
            return
        point = self._scroll.viewport().mapFromGlobal(self._pointer_global.toPoint())
        viewport = self._scroll.viewport().rect()
        if (
            point.x() < self.GUTTER
            or point.x() > viewport.right()
            or point.y() < -24
            or point.y() > viewport.bottom() + 24
        ):
            return
        amount = -10 if point.y() < 24 else 10 if point.y() > viewport.bottom() - 24 else 0
        bar = self._scroll.verticalScrollBar()
        before = bar.value()
        if amount:
            bar.setValue(before + amount)
        if bar.value() != before:
            self._move(
                self._timeline,
                QPointF(self._timeline.mapFromGlobal(self._pointer_global.toPoint())),
                self._pointer_global,
            )

    def _release(self, canvas: _Canvas, position: QPointF, global_position: QPointF):
        gesture = self._gesture
        if gesture is None:
            hit = self._hit(canvas.role, position)
            if hit and self._read_only(hit.task):
                self.edit_requested.emit(hit.task)
            return
        self._move(canvas, position, global_position)
        preview = self._preview
        moved = gesture["moved"]
        self._cancel()
        if gesture["kind"] == "create" and preview:
            start, duration = preview
            self.create_requested.emit(
                start.date().isoformat(), start.hour * 60 + start.minute, duration
            )
        elif moved and preview:
            start, duration = preview
            item = gesture["item"]
            if gesture["kind"] == "resize" and item.duration == duration:
                return
            if gesture["kind"] == "move" and item.original_start == start:
                return
            self.reschedule_requested.emit(
                item.task, start.date().isoformat(), start.hour * 60 + start.minute, duration
            )
        elif not moved and gesture["item"]:
            self.edit_requested.emit(gesture["item"].task)

    def _cancel(self):
        active = self._gesture is not None
        self._gesture = None
        self._preview = None
        self._pointer_global = None
        if hasattr(self, "_autoscroll_timer"):
            self._autoscroll_timer.stop()
        if active:
            self.interaction_changed.emit(False)
        if hasattr(self, "_timeline"):
            self._timeline.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._cancel()
            self._selected = None
            self._repaint()
            event.accept()
            return
        tasks = []
        for item in sorted(self._all_day + self._segments, key=lambda item: (item.day, item.start)):
            if not any(task is item.task for task in tasks):
                tasks.append(item.task)
        if key in {Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right} and tasks:
            step = -1 if key in {Qt.Key.Key_Up, Qt.Key.Key_Left} else 1
            index = next(
                (i for i, task in enumerate(tasks) if task is self._selected),
                -1 if step > 0 else 0,
            )
            self._selected = tasks[(index + step) % len(tasks)]
            self._repaint()
            visible = next(
                ((item, rect) for item, rect in self._timed_rects if item.task is self._selected),
                None,
            )
            if visible:
                rect = visible[1]
                margin = min(
                    max(30, math.ceil(rect.height() / 2) + 8),
                    max(0, (self._scroll.viewport().height() - 1) // 2),
                )
                self._scroll.ensureVisible(
                    round(rect.center().x()), round(rect.center().y()), 8, margin
                )
            else:
                all_day = next(
                    (rect for item, rect in self._all_day_rects if item.task is self._selected),
                    None,
                )
                if all_day:
                    self._all_day_scroll.ensureVisible(
                        round(all_day.center().x()), round(all_day.center().y()), 8, 8
                    )
            event.accept()
            return
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space} and self._selected:
            self._cancel()
            self.edit_requested.emit(self._selected)
            event.accept()
            return
        super().keyPressEvent(event)
