# -*- coding: utf-8 -*-
"""Date picker popup for widget-only mode.

The stock ``QCalendarWidget`` header ("11월 2026" with a tiny menu arrow and a
year spin box) made jumping to another month or year slow. This popup keeps one
header that drills up: days -> months of a year -> a 12-year block. Picking a
year opens its months, picking a month opens its days, so any date is at most
three clicks away. Colours come from the widget-mode theme tokens.
"""

from __future__ import annotations

from PyQt6.QtCore import QDate, QEvent, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.locale_names import month_name, weekday_names
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

VIEW_DAYS = "days"
VIEW_MONTHS = "months"
VIEW_YEARS = "years"
_YEAR_BLOCK = 12
_MIN_YEAR = 1900
_MAX_YEAR = 2999


def year_block_start(year: int) -> int:
    """First year of the 12-year block shown in the year view."""
    return year - ((year - _MIN_YEAR) % _YEAR_BLOCK)


def month_grid_dates(year: int, month: int) -> list[QDate]:
    """Six Monday-first weeks covering the month (same grid as the widget calendar)."""
    first = QDate(year, month, 1)
    start = first.addDays(1 - first.dayOfWeek())
    return [start.addDays(index) for index in range(42)]


def year_month_title(year: int, month: int) -> str:
    return t("widget_mode.picker_year_month", "{year}년 {month}").format(
        year=year, month=month_name(month)
    )


class WidgetDatePickerPopup(QFrame):
    """Popup calendar whose header switches between day, month and year views."""

    dateSelected = pyqtSignal(QDate)

    def __init__(self, selected: QDate, tokens: dict[str, str] | None = None, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("widget_date_picker")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAccessibleName(t("widget_mode.pick_date", "날짜 선택"))
        if not isinstance(selected, QDate) or not selected.isValid():
            selected = QDate.currentDate()
        self._selected = QDate(selected)
        self._cursor = QDate(selected)  # keyboard focus day in the day view
        self._year = selected.year()
        self._month = selected.month()
        self._block_start = year_block_start(selected.year())
        self._view = VIEW_DAYS
        self._tokens = dict(tokens or {})

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(4)
        self.prev_btn = self._nav_button(ICON.NAV_PREV, self._step_previous)
        self.title_btn = QToolButton(self)
        self.title_btn.setObjectName("picker_title")
        self.title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_btn.clicked.connect(self._zoom_out)
        self.next_btn = self._nav_button(ICON.NAV_NEXT, self._step_next)
        header.addWidget(self.prev_btn)
        header.addWidget(self.title_btn, 1)
        header.addWidget(self.next_btn)
        root.addLayout(header)

        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_day_page())
        self.stack.addWidget(self._build_grid_page("month"))
        self.stack.addWidget(self._build_grid_page("year"))

        footer = QHBoxLayout()
        footer.setSpacing(6)
        footer.addStretch(1)
        self.today_btn = QToolButton(self)
        self.today_btn.setObjectName("picker_footer")
        self.today_btn.setText(t("widget_mode.today", "오늘"))
        self.today_btn.setToolTip(t("widget_mode.picker_today_help", "오늘 날짜로 이동합니다"))
        self.today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_btn.clicked.connect(lambda: self._choose(QDate.currentDate()))
        footer.addWidget(self.today_btn)
        root.addLayout(footer)

        self._apply_style()
        self._render()

    # ----- construction -------------------------------------------------
    def _nav_button(self, key: str, callback) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("picker_nav")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(32, 32)
        button.setProperty("iconKey", key)
        button.clicked.connect(callback)
        return button

    def _build_day_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        weekdays = QHBoxLayout()
        weekdays.setSpacing(2)
        self.weekday_labels: list[QLabel] = []
        for name, long_name in zip(
            weekday_names(narrow=True), weekday_names(long=True), strict=True
        ):
            label = QLabel(name, page)
            label.setObjectName("picker_weekday")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAccessibleName(long_name)
            label.setFixedHeight(24)
            weekdays.addWidget(label, 1)
            self.weekday_labels.append(label)
        layout.addLayout(weekdays)
        grid = QGridLayout()
        grid.setSpacing(2)
        self.day_buttons: list[QToolButton] = []
        for index in range(42):
            button = QToolButton(page)
            button.setObjectName("picker_day")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(36, 32)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _checked=False, idx=index: self._day_clicked(idx))
            grid.addWidget(button, index // 7, index % 7)
            self.day_buttons.append(button)
        layout.addLayout(grid)
        self._day_dates: list[QDate] = []
        page.installEventFilter(self)
        return page

    def _build_grid_page(self, kind: str) -> QWidget:
        page = QWidget(self)
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setSpacing(6)
        buttons: list[QToolButton] = []
        for index in range(12):
            button = QToolButton(page)
            button.setObjectName("picker_cell")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumSize(76, 44)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if kind == "month":
                button.clicked.connect(lambda _checked=False, m=index + 1: self._month_clicked(m))
            else:
                button.clicked.connect(lambda _checked=False, i=index: self._year_clicked(i))
            grid.addWidget(button, index // 3, index % 3)
            buttons.append(button)
        if kind == "month":
            self.month_buttons = buttons
        else:
            self.year_buttons = buttons
        return page

    # ----- state ----------------------------------------------------------
    @property
    def view(self) -> str:
        return self._view

    def selected_date(self) -> QDate:
        return QDate(self._selected)

    def _set_view(self, view: str) -> None:
        self._view = view
        self._render()

    def _zoom_out(self) -> None:
        if self._view == VIEW_DAYS:
            self._set_view(VIEW_MONTHS)
        elif self._view == VIEW_MONTHS:
            self._block_start = year_block_start(self._year)
            self._set_view(VIEW_YEARS)

    def _step(self, delta: int) -> None:
        if self._view == VIEW_DAYS:
            moved = QDate(self._year, self._month, 1).addMonths(delta)
            self._year, self._month = moved.year(), moved.month()
            day = min(self._cursor.day(), moved.daysInMonth())
            self._cursor = QDate(self._year, self._month, day)
        elif self._view == VIEW_MONTHS:
            self._year = max(_MIN_YEAR, min(_MAX_YEAR, self._year + delta))
        else:
            self._block_start = max(
                _MIN_YEAR, min(_MAX_YEAR - _YEAR_BLOCK + 1, self._block_start + delta * _YEAR_BLOCK)
            )
        self._render()

    def _step_previous(self) -> None:
        self._step(-1)

    def _step_next(self) -> None:
        self._step(1)

    def _day_clicked(self, index: int) -> None:
        if 0 <= index < len(self._day_dates):
            self._choose(self._day_dates[index])

    def _month_clicked(self, month: int) -> None:
        self._month = month
        day = min(self._cursor.day(), QDate(self._year, month, 1).daysInMonth())
        self._cursor = QDate(self._year, month, day)
        self._set_view(VIEW_DAYS)

    def _year_clicked(self, index: int) -> None:
        self._year = self._block_start + index
        self._set_view(VIEW_MONTHS)

    def _choose(self, date: QDate) -> None:
        if not date.isValid():
            return
        self._selected = QDate(date)
        self.dateSelected.emit(QDate(date))
        self.close()

    # ----- rendering -------------------------------------------------------
    def _render(self) -> None:
        tk = self._tokens
        icon_color = tk.get("text_secondary", "#c8ccd8")
        for button in (self.prev_btn, self.next_btn):
            key = button.property("iconKey")
            if self.isRightToLeft():
                key = ICON.NAV_NEXT if key == ICON.NAV_PREV else ICON.NAV_PREV
            button.setIcon(_ic(key, color=icon_color))
        if self._view == VIEW_DAYS:
            self.stack.setCurrentIndex(0)
            self.title_btn.setText(year_month_title(self._year, self._month))
            self.title_btn.setToolTip(t("widget_mode.picker_pick_month", "눌러서 월 선택"))
            self.prev_btn.setToolTip(t("widget_mode.month_prev", "이전 달"))
            self.next_btn.setToolTip(t("widget_mode.month_next", "다음 달"))
            self._render_days()
        elif self._view == VIEW_MONTHS:
            self.stack.setCurrentIndex(1)
            self.title_btn.setText(t("widget_mode.picker_year", "{year}년").format(year=self._year))
            self.title_btn.setToolTip(t("widget_mode.picker_pick_year", "눌러서 연도 선택"))
            self.prev_btn.setToolTip(t("widget_mode.picker_prev_year", "이전 해"))
            self.next_btn.setToolTip(t("widget_mode.picker_next_year", "다음 해"))
            today = QDate.currentDate()
            for month, button in enumerate(self.month_buttons, start=1):
                button.setText(month_name(month, short=True))
                button.setAccessibleName(month_name(month))
                button.setProperty(
                    "state",
                    self._cell_state(
                        self._year == self._selected.year() and month == self._selected.month(),
                        self._year == today.year() and month == today.month(),
                    ),
                )
                self._repolish(button)
        else:
            self.stack.setCurrentIndex(2)
            last = self._block_start + _YEAR_BLOCK - 1
            self.title_btn.setText(f"{self._block_start} – {last}")
            self.title_btn.setToolTip("")
            self.prev_btn.setToolTip(t("widget_mode.picker_prev_years", "이전 12년"))
            self.next_btn.setToolTip(t("widget_mode.picker_next_years", "다음 12년"))
            today = QDate.currentDate()
            for index, button in enumerate(self.year_buttons):
                year = self._block_start + index
                button.setText(str(year))
                button.setAccessibleName(str(year))
                button.setEnabled(_MIN_YEAR <= year <= _MAX_YEAR)
                button.setProperty(
                    "state", self._cell_state(year == self._selected.year(), year == today.year())
                )
                self._repolish(button)
        self.title_btn.setEnabled(self._view != VIEW_YEARS)
        self.title_btn.setAccessibleName(self.title_btn.text())
        self.prev_btn.setAccessibleName(self.prev_btn.toolTip())
        self.next_btn.setAccessibleName(self.next_btn.toolTip())

    @staticmethod
    def _cell_state(selected: bool, today: bool) -> str:
        if selected:
            return "selected"
        return "today" if today else ""

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)

    def _render_days(self) -> None:
        self._day_dates = month_grid_dates(self._year, self._month)
        today = QDate.currentDate()
        for date, button in zip(self._day_dates, self.day_buttons, strict=True):
            button.setText(str(date.day()))
            button.setAccessibleName(date.toString(Qt.DateFormat.ISODate))
            if date == self._selected:
                state = "selected"
            elif date == self._cursor:
                state = "cursor"
            elif date == today:
                state = "today"
            else:
                state = ""
            button.setProperty("state", state)
            button.setProperty("outside", date.month() != self._month)
            button.setProperty(
                "weekend",
                "sat" if date.dayOfWeek() == 6 else "sun" if date.dayOfWeek() == 7 else "",
            )
            self._repolish(button)

    def _apply_style(self) -> None:
        tk = self._tokens

        def c(key: str, fallback: str) -> str:
            return tk.get(key) or fallback

        primary = c("text_primary", "#eef0f6")
        secondary = c("text_secondary", "#b8bdcc")
        faint = c("text_faint", secondary)
        accent = c("accent", "#a78bfa")
        hover = c("button_hover", c("surface_alt", "rgba(255,255,255,0.08)"))
        selected_bg = c("hero_bg_strong", c("surface_alt", "rgba(167,139,250,0.22)"))
        border = c("panel_border", "rgba(255,255,255,0.14)")
        background = c("panel_bg", "#1d2130")
        sat = c("calendar_weekday_sat", secondary)
        sun = c("calendar_weekday_sun", secondary)
        self.setStyleSheet(
            f"""
            QFrame#widget_date_picker {{ background: {background}; border: 1px solid {border};
                border-radius: 10px; }}
            QFrame#widget_date_picker QToolButton {{ color: {primary}; background: transparent; border: 1px solid transparent;
                border-radius: 7px; }}
            QFrame#widget_date_picker QToolButton:hover {{ background: {hover}; }}
            QFrame#widget_date_picker QToolButton:focus {{ border: 2px solid {accent}; }}
            QFrame#widget_date_picker QToolButton#picker_title {{ font-weight: 700; padding: 4px 10px; min-height: 24px; }}
            QFrame#widget_date_picker QToolButton#picker_title:disabled {{ color: {primary}; }}
            QFrame#widget_date_picker QLabel#picker_weekday {{ color: {secondary}; font-weight: 600; background: transparent; }}
            QFrame#widget_date_picker QToolButton#picker_day[outside="true"] {{ color: {faint}; }}
            QFrame#widget_date_picker QToolButton#picker_day[outside="false"][weekend="sat"] {{ color: {sat}; }}
            QFrame#widget_date_picker QToolButton#picker_day[outside="false"][weekend="sun"] {{ color: {sun}; }}
            QFrame#widget_date_picker QToolButton[state="today"] {{ border: 1px solid {accent}; }}
            QFrame#widget_date_picker QToolButton[state="cursor"] {{ border: 1px dashed {accent}; }}
            QFrame#widget_date_picker QToolButton[state="selected"] {{ background: {selected_bg}; border: 1px solid {accent};
                color: {primary}; font-weight: 700; }}
            QFrame#widget_date_picker QToolButton#picker_cell:disabled {{ color: {faint}; }}
            QFrame#widget_date_picker QToolButton#picker_footer {{ color: {accent}; font-weight: 600; padding: 4px 12px; }}
            """
        )

    # ----- keyboard ---------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            return
        if self._view == VIEW_DAYS:
            rtl = self.isRightToLeft()
            moves = {
                Qt.Key.Key_Left: 1 if rtl else -1,
                Qt.Key.Key_Right: -1 if rtl else 1,
                Qt.Key.Key_Up: -7,
                Qt.Key.Key_Down: 7,
            }
            if key in moves:
                self._move_cursor(self._cursor.addDays(moves[key]))
                return
            if key == Qt.Key.Key_PageUp:
                self._move_cursor(self._cursor.addMonths(-1))
                return
            if key == Qt.Key.Key_PageDown:
                self._move_cursor(self._cursor.addMonths(1))
                return
            if key == Qt.Key.Key_Home:
                self._move_cursor(QDate.currentDate())
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._choose(self._cursor)
                return
        elif key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self._step(-1 if key == Qt.Key.Key_PageUp else 1)
            return
        super().keyPressEvent(event)

    def _move_cursor(self, date: QDate) -> None:
        if not date.isValid():
            return
        self._cursor = QDate(date)
        self._year, self._month = date.year(), date.month()
        self._render()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel and self._view == VIEW_DAYS:
            delta = event.angleDelta().y()
            if delta:
                self._step(-1 if delta > 0 else 1)
                return True
        return super().eventFilter(watched, event)

    # ----- placement --------------------------------------------------------
    def popup_below(self, anchor: QWidget) -> None:
        """Show under ``anchor``, flipped or shifted to stay on the anchor's screen."""
        self.adjustSize()
        size = self.sizeHint().expandedTo(self.minimumSizeHint())
        below = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        above = anchor.mapToGlobal(QPoint(0, -size.height() - 4))
        screen = anchor.screen() or QApplication.screenAt(below) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect(below, size)
        x = below.x()
        if self.isRightToLeft():
            x = anchor.mapToGlobal(QPoint(anchor.width(), 0)).x() - size.width()
        y = below.y() if below.y() + size.height() <= area.bottom() else above.y()
        x = max(area.left(), min(x, area.right() - size.width() + 1))
        y = max(area.top(), min(y, area.bottom() - size.height() + 1))
        self.move(x, y)
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
