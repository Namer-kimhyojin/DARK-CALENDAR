# -*- coding: utf-8 -*-
"""Compact time editor used by task dialogs.

The previous implementation used two editable combo boxes for hour/minute,
which made focus handling and direct typing awkward inside the dialog theme.
This wrapper keeps the existing call sites but delegates to QTimeEdit so the
user can type naturally and use arrow keys or mouse wheel reliably.
"""

from collections.abc import Callable

from PyQt6.QtCore import (
    QDate,
    QDateTime,
    QElapsedTimer,
    QEvent,
    QPoint,
    QSize,
    Qt,
    QTime,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFocusEvent, QKeyEvent, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QDateEdit,
    QDateTimeEdit,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)


def _time_picker_metric_bundle(metrics: dict | None = None) -> dict[str, int]:
    resolved = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    field_height = max(28, int(resolved.get("field_height", 34)))
    min_width = max(96, int(resolved.get("field_padding_x", 10)) * 4 + 56)
    return {
        "min_width": min_width,
        "min_height": field_height,
        "max_height": field_height + 4,
    }


class _CompactNumericEntryMixin:
    """Accept a continuous keypad sequence in Qt's section-based editors."""

    _numeric_entry_timeout_ms = 1800
    _numeric_entry_max_digits = 0
    _numeric_entry_separator = ""
    _numeric_entry_full_digits = 0
    _numeric_entry_final_section = QDateTimeEdit.Section.NoSection

    def _init_numeric_entry(self, accessible_hint: str):
        self._numeric_entry_buffer = ""
        self._numeric_entry_timer = QElapsedTimer()
        self._numeric_entry_original = None
        self._numeric_entry_pending = None
        self._numeric_entry_section = QDateTimeEdit.Section.NoSection
        self._numeric_entry_whole = False
        self.setToolTip(accessible_hint)
        self.setAccessibleDescription(accessible_hint)

    def _reset_numeric_entry(self):
        self._numeric_entry_buffer = ""
        self._numeric_entry_timer.invalidate()
        self._numeric_entry_original = None
        self._numeric_entry_pending = None

    def setDateTime(self, value):
        if hasattr(self, "_numeric_entry_timer"):
            self._reset_numeric_entry()
        super().setDateTime(value)

    def setDate(self, value):
        if hasattr(self, "_numeric_entry_timer"):
            self._reset_numeric_entry()
        super().setDate(value)

    def setTime(self, value):
        if hasattr(self, "_numeric_entry_timer"):
            self._reset_numeric_entry()
        super().setTime(value)

    def _finish_numeric_entry(self):
        if self._numeric_entry_original is not None:
            value = self._numeric_entry_pending or self._numeric_entry_original
            super().setDateTime(value)
        self._reset_numeric_entry()

    def _update_numeric_entry(self):
        candidate, complete = self._numeric_entry_candidate(self._numeric_entry_buffer)
        self._numeric_entry_pending = candidate
        if candidate is not None:
            super().setDateTime(candidate)
            if (
                sum(char.isdigit() for char in self._numeric_entry_buffer)
                >= self._numeric_entry_full_digits
            ):
                self.setSelectedSection(self._numeric_entry_final_section)
        elif complete and self._numeric_entry_original is not None:
            # Do not retain a valid prefix of an invalid complete value, such
            # as 02:46 from 2460 or February 21 from an invalid February 31.
            super().setDateTime(self._numeric_entry_original)

    def _append_numeric_digit(self, digit: str):
        if (
            not self._numeric_entry_timer.isValid()
            or self._numeric_entry_timer.elapsed() > self._numeric_entry_timeout_ms
            or sum(char.isdigit() for char in self._numeric_entry_buffer)
            >= self._numeric_entry_max_digits
        ):
            self._finish_numeric_entry()
            self._numeric_entry_original = self.dateTime()
            self._numeric_entry_section = self.currentSection()
            self._numeric_entry_whole = self.lineEdit().selectedText() == self.text()
        self._numeric_entry_buffer += digit
        self._numeric_entry_timer.start()
        self._update_numeric_entry()

    def keyPressEvent(self, event: QKeyEvent):
        text = event.text()
        modifiers = event.modifiers()
        allowed_modifiers = Qt.KeyboardModifier.NoModifier | Qt.KeyboardModifier.KeypadModifier
        if (
            len(text) == 1
            and text.isascii()
            and text.isdigit()
            and not (modifiers & ~allowed_modifiers)
        ):
            self._append_numeric_digit(text)
            event.accept()
            return
        if (
            text == self._numeric_entry_separator
            and self._numeric_entry_buffer
            and not (modifiers & ~(allowed_modifiers | Qt.KeyboardModifier.ShiftModifier))
        ):
            self._numeric_entry_buffer += text
            self._numeric_entry_timer.start()
            self._update_numeric_entry()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Backspace and self._numeric_entry_buffer:
            self._numeric_entry_buffer = self._numeric_entry_buffer[:-1]
            self._numeric_entry_timer.start()
            if self._numeric_entry_buffer:
                self._update_numeric_entry()
            else:
                self._numeric_entry_pending = None
                super().setDateTime(self._numeric_entry_original)
            event.accept()
            return
        self._finish_numeric_entry()
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent):
        self._finish_numeric_entry()
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        self._finish_numeric_entry()
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        self._finish_numeric_entry()
        super().wheelEvent(event)

    def _affordance_color(self) -> QColor:
        color = self.palette().color(QPalette.ColorRole.Text)
        if not color.isValid():
            color = QColor("#f4f7fb")
        if not self.isEnabled():
            color.setAlpha(110)
        return color


class DatePickerWidget(_CompactNumericEntryMixin, QDateEdit):
    """Date editor supporting direct ``YYYYMMDD`` numeric-keypad entry."""

    _numeric_entry_max_digits = 8
    _numeric_entry_separator = "-"
    _numeric_entry_full_digits = 8
    _numeric_entry_final_section = QDateTimeEdit.Section.DaySection

    def __init__(self, initial_date: QDate | None = None, parent=None, metrics: dict | None = None):
        super().__init__(parent)
        metric_bundle = _time_picker_metric_bundle(metrics)
        self.setDate(initial_date or QDate.currentDate())
        self.setDisplayFormat("yyyy-MM-dd")
        self.setCalendarPopup(True)
        self.setKeyboardTracking(False)
        self.setAccelerated(True)
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)
        self.setMinimumWidth(max(132, metric_bundle["min_width"] + 28))
        self.setMinimumHeight(metric_bundle["min_height"])
        self.setMaximumHeight(metric_bundle["max_height"])
        self.setObjectName("NumericDateEdit")
        self.setProperty("controlAffordance", "calendar")
        self._init_numeric_entry(
            t(
                "dialog.common.numeric_date_hint",
                "숫자 8자리(예: 20260804)를 연속으로 입력하거나 달력 버튼을 사용하세요.",
            )
        )

    def _numeric_entry_candidate(self, text: str):
        original = self._numeric_entry_original
        current = original.date()
        candidate = QDate()
        complete = False
        if "-" in text:
            parts = text.split("-")
            complete = len(parts) == 3 and [len(part) for part in parts] == [4, 2, 2]
            if complete and all(part.isdigit() for part in parts):
                candidate = QDate(*(int(part) for part in parts))
        elif len(text) == 8:
            complete = True
            candidate = QDate.fromString(text, "yyyyMMdd")
        elif not self._numeric_entry_whole:
            section = self._numeric_entry_section
            if section == QDateTimeEdit.Section.YearSection and len(text) == 4:
                complete = True
                candidate = QDate(int(text), current.month(), current.day())
            elif len(text) <= 2:
                if section == QDateTimeEdit.Section.MonthSection:
                    complete = True
                    candidate = QDate(current.year(), int(text), current.day())
                elif section == QDateTimeEdit.Section.DaySection:
                    complete = True
                    candidate = QDate(current.year(), current.month(), int(text))
        if candidate.isValid() and self.minimumDate() <= candidate <= self.maximumDate():
            value = QDateTime(original)
            value.setDate(candidate)
            return value, complete
        return None, complete

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self._affordance_color(), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        center_x = self.width() - 12
        center_y = self.height() // 2
        left = center_x - 6
        top = center_y - 6
        painter.drawRoundedRect(left, top + 1, 12, 11, 2, 2)
        painter.drawLine(left, top + 5, left + 12, top + 5)
        painter.drawLine(left + 3, top, left + 3, top + 3)
        painter.drawLine(left + 9, top, left + 9, top + 3)


def _schedule_duration_text(seconds: int) -> str:
    minutes = max(0, int(seconds) // 60)
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return t(
            "dialog.schedule_input.hours_minutes",
            "{hours}시간 {minutes}분",
            hours=hours,
            minutes=minutes,
        )
    if hours:
        return t("dialog.schedule_input.hours", "{count}시간", count=hours)
    return t("dialog.schedule_input.minutes", "{count}분", count=minutes)


class _TimeChoiceList(QListWidget):
    def event(self, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        ):
            forward = event.key() == Qt.Key.Key_Tab and not (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
            owner = self.window().parentWidget()
            self.window().hide()
            owner.window().activateWindow()
            owner.setFocus(Qt.FocusReason.TabFocusReason)
            owner.window().focusNextPrevChild(forward)
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.currentItem() is not None:
                self.itemActivated.emit(self.currentItem())
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.window().hide()
            self.window().parentWidget().setFocus(Qt.FocusReason.PopupFocusReason)
            event.accept()
            return
        super().keyPressEvent(event)


class TimePickerWidget(_CompactNumericEntryMixin, QTimeEdit):
    """QTimeEdit-compatible time input with task-dialog defaults."""

    _numeric_entry_max_digits = 4
    _numeric_entry_separator = ":"
    _numeric_entry_full_digits = 3
    _numeric_entry_final_section = QDateTimeEdit.Section.MinuteSection
    dateTimeSelected = pyqtSignal(QDateTime)

    def __init__(self, initial_time: QTime | None = None, parent=None, metrics: dict | None = None):
        super().__init__(parent)
        self._dropdown_enabled = False
        self._dropdown_button = None
        self._dropdown_popup = None
        self._dropdown_list = None
        self._schedule_context = None
        metric_bundle = _time_picker_metric_bundle(metrics)
        self.setTime(initial_time or QTime(0, 0))
        self.setDisplayFormat("HH:mm")
        self.setKeyboardTracking(False)
        self.setWrapping(True)
        self.setAccelerated(True)
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setObjectName("TaskTimeEdit")
        self.setProperty("controlAffordance", "stepper")
        self.setMinimumWidth(metric_bundle["min_width"])
        self.setMinimumHeight(metric_bundle["min_height"])
        self.setMaximumHeight(metric_bundle["max_height"])
        self._init_numeric_entry(
            t(
                "dialog.common.numeric_time_hint",
                "숫자 3~4자리(예: 930 또는 0930)를 연속으로 입력하세요. 위아래 키는 5분 단위입니다.",
            )
        )

    def enable_dropdown(self, enabled: bool = True):
        """Offer clock choices without changing the editor's typing/stepper API."""
        enabled = bool(enabled)
        if enabled == self._dropdown_enabled:
            return
        self._dropdown_enabled = enabled
        self.setMinimumWidth(self.minimumWidth() + (28 if enabled else -28))
        self.lineEdit().setTextMargins(0, 0, 28 if enabled else 0, 0)
        if enabled and self._dropdown_button is None:
            self._dropdown_button = QToolButton(self)
            self._dropdown_button.setObjectName("ScheduleTimeDropdownButton")
            self._dropdown_button.setArrowType(Qt.ArrowType.DownArrow)
            self._dropdown_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._dropdown_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._dropdown_button.setAutoRaise(True)
            label = t("dialog.schedule_input.time_list", "시간 목록")
            self._dropdown_button.setAccessibleName(label)
            self._dropdown_button.setToolTip(label)
            self._dropdown_button.setStyleSheet(
                "QToolButton#ScheduleTimeDropdownButton {"
                " background: transparent; border: none; padding: 0; min-width: 0; }"
            )
            self._dropdown_button.clicked.connect(self.show_time_dropdown)
        if self._dropdown_button is not None:
            self._dropdown_button.setVisible(enabled)
            self._position_dropdown_button()
        if not enabled and self._dropdown_popup is not None:
            self._dropdown_popup.hide()

    def set_schedule_context(self, provider: Callable[[], tuple[QDateTime, QDateTime]] | None):
        """Set an end-time context; selected datetimes are emitted atomically.

        The owner must handle ``dateTimeSelected`` and set its end date/time
        together. No intermediate ``timeChanged`` is emitted by a choice.
        """
        self._schedule_context = provider

    def _time_choices(self) -> list[tuple[str, QDateTime]]:
        if self._schedule_context is None:
            day = QDate.currentDate()
            times = {QTime(hour, minute) for hour in range(24) for minute in (0, 30)}
            times.add(self.time())
            return [(value.toString("HH:mm"), QDateTime(day, value)) for value in sorted(times)]

        start, current = self._schedule_context()
        if not start.isValid() or not current.isValid():
            return []
        if current.date() > start.date():
            # A manually selected end date is authoritative. Clock choices on a
            # multi-day event must not silently shorten it to the start date.
            values = []
            for hour in range(24):
                for minute in (0, 30):
                    value = QDateTime(current)
                    value.setTime(QTime(hour, minute))
                    values.append(value)
        else:
            slot = QDateTime(start)
            slot.setTime(QTime(start.time().hour(), (start.time().minute() // 30) * 30))
            slot = slot.addSecs(30 * 60)
            limit = start.addSecs(24 * 60 * 60)
            values = []
            while slot <= limit:
                values.append(QDateTime(slot))
                slot = slot.addSecs(30 * 60)
        if current not in values:
            values.append(QDateTime(current))
        choices = []
        for value in sorted(values):
            label = value.time().toString("HH:mm")
            days = start.date().daysTo(value.date())
            if days == 1:
                label = f"{t('dialog.schedule_input.next_day', '다음 날')} {label}"
            elif days > 1:
                day_label = t("dialog.schedule_input.days_later", "{count}일 후", count=days)
                label = f"{day_label} {label}"
            elif days < 0:
                label = f"{value.date().toString('yyyy-MM-dd')} {label}"
            if value >= start:
                label = f"{label} · {_schedule_duration_text(start.secsTo(value))}"
            choices.append((label, value))
        return choices

    def _popup_tokens(self) -> dict:
        tokens = dict(get_dialog_theme_tokens())
        parent = self.parentWidget()
        while parent is not None:
            inherited = getattr(parent, "_ui_tokens", None)
            if callable(inherited):
                inherited = inherited()
            if isinstance(inherited, dict):
                tokens.update(inherited)
                break
            parent = parent.parentWidget()
        return tokens

    def show_time_dropdown(self):
        if not self._dropdown_enabled or not self.isEnabled() or self.isReadOnly():
            return
        if self._dropdown_popup is not None and self._dropdown_popup.isVisible():
            self._dropdown_popup.hide()
            return
        self._finish_numeric_entry()
        self.interpretText()
        if self._dropdown_popup is None:
            self._dropdown_popup = QFrame(self, Qt.WindowType.Popup)
            self._dropdown_popup.setObjectName("ScheduleTimePopup")
            layout = QVBoxLayout(self._dropdown_popup)
            layout.setContentsMargins(4, 4, 4, 4)
            self._dropdown_list = _TimeChoiceList(self._dropdown_popup)
            self._dropdown_list.setObjectName("ScheduleTimeChoices")
            self._dropdown_list.setAccessibleName(t("dialog.schedule_input.time_list", "시간 목록"))
            self._dropdown_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._dropdown_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            self._dropdown_list.itemClicked.connect(self._select_time_choice)
            self._dropdown_list.itemActivated.connect(self._select_time_choice)
            layout.addWidget(self._dropdown_list)

        tokens = self._popup_tokens()
        self._dropdown_popup.setStyleSheet(
            "QFrame#ScheduleTimePopup {"
            f" background: {tokens['surface_bg']}; border: 1px solid {tokens['border']};"
            " border-radius: 6px; }"
            "QListWidget#ScheduleTimeChoices {"
            f" background: {tokens['surface_bg']}; color: {tokens['text_primary']};"
            " border: none; outline: none; }"
            "QListWidget#ScheduleTimeChoices::item { padding: 6px 10px; border-radius: 3px; }"
            "QListWidget#ScheduleTimeChoices::item:hover {"
            f" background: {tokens['surface_hover']}; }}"
            "QListWidget#ScheduleTimeChoices::item:selected {"
            f" background: {tokens['accent']}; color: {tokens['accent_text']}; }}"
            "QListWidget#ScheduleTimeChoices QScrollBar:vertical {"
            f" background: {tokens['surface_bg']}; width: 10px; margin: 0; }}"
            "QListWidget#ScheduleTimeChoices QScrollBar::handle:vertical {"
            f" background: {tokens['text_muted']}; min-height: 24px; border-radius: 4px; }}"
            "QListWidget#ScheduleTimeChoices QScrollBar::add-line:vertical,"
            "QListWidget#ScheduleTimeChoices QScrollBar::sub-line:vertical { height: 0; }"
            "QListWidget#ScheduleTimeChoices QScrollBar::add-page:vertical,"
            "QListWidget#ScheduleTimeChoices QScrollBar::sub-page:vertical { background: transparent; }"
        )
        self._dropdown_list.clear()
        choices = self._time_choices()
        current = self._schedule_context()[1] if self._schedule_context else None
        selected_row = 0
        row_height = max(32, self.fontMetrics().height() + 14)
        widest = 0
        for index, (label, value) in enumerate(choices):
            item = QListWidgetItem(label, self._dropdown_list)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setSizeHint(QSize(0, row_height))
            widest = max(widest, self.fontMetrics().horizontalAdvance(label))
            if (current is not None and value == current) or (
                current is None and value.time() == self.time()
            ):
                selected_row = index
        self._dropdown_list.setCurrentRow(selected_row)
        self._dropdown_popup.resize(max(self.width(), widest + 56), row_height * 7 + 10)
        position = self.mapToGlobal(QPoint(0, self.height() + 2))
        screen = self.screen()
        if screen is not None:
            bounds = screen.availableGeometry()
            position.setX(
                max(bounds.left(), min(position.x(), bounds.right() - self._dropdown_popup.width()))
            )
            if position.y() + self._dropdown_popup.height() > bounds.bottom():
                position.setY(
                    self.mapToGlobal(QPoint(0, 0)).y() - self._dropdown_popup.height() - 2
                )
            position.setY(max(bounds.top(), position.y()))
        self._dropdown_popup.move(position)
        self._dropdown_popup.show()
        self._dropdown_list.scrollToItem(
            self._dropdown_list.currentItem(), QAbstractItemView.ScrollHint.PositionAtCenter
        )
        self._dropdown_list.setFocus(Qt.FocusReason.PopupFocusReason)

    def _select_time_choice(self, item: QListWidgetItem):
        value = item.data(Qt.ItemDataRole.UserRole)
        self._dropdown_popup.hide()
        if self._schedule_context is not None:
            self.dateTimeSelected.emit(value)
        else:
            self.setTime(value.time())
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _position_dropdown_button(self):
        if self._dropdown_button is not None:
            editor = self.lineEdit().geometry()
            self._dropdown_button.setGeometry(
                editor.right() - 26, editor.top(), 26, editor.height()
            )
            self._dropdown_button.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_dropdown_button()

    def keyPressEvent(self, event: QKeyEvent):
        if self._dropdown_enabled and (
            event.key() == Qt.Key.Key_F4
            or (
                event.key() == Qt.Key.Key_Down
                and event.modifiers() & Qt.KeyboardModifier.AltModifier
            )
        ):
            self.show_time_dropdown()
            event.accept()
            return
        super().keyPressEvent(event)

    def stepBy(self, steps: int):
        """Use practical five-minute increments while the minute section is active."""
        if self.currentSection() == QDateTimeEdit.Section.MinuteSection:
            self.setTime(self.time().addSecs(int(steps) * 5 * 60))
            return
        super().stepBy(steps)

    def _numeric_entry_candidate(self, text: str):
        original = self._numeric_entry_original
        current = original.time()
        candidate = QTime()
        complete = False
        if ":" in text:
            parts = text.split(":")
            complete = len(parts) == 2 and len(parts[0]) in (1, 2) and len(parts[1]) == 2
            if complete and all(part.isdigit() for part in parts):
                candidate = QTime(*(int(part) for part in parts))
        elif len(text) >= 3:
            complete = True
            candidate = QTime(int(text[:-2]), int(text[-2:]))
        elif not self._numeric_entry_whole:
            complete = True
            if self._numeric_entry_section == QDateTimeEdit.Section.MinuteSection:
                candidate = QTime(current.hour(), int(text), current.second())
            else:
                candidate = QTime(int(text), current.minute(), current.second())
        if candidate.isValid():
            value = QDateTime(original)
            value.setTime(candidate)
            return value, complete
        return None, complete

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self._affordance_color(), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        center_x = self.width() - 10
        upper_y = max(6, self.height() // 4)
        lower_y = min(self.height() - 6, (self.height() * 3) // 4)
        painter.drawLine(center_x - 3, upper_y, center_x + 3, upper_y)
        painter.drawLine(center_x, upper_y - 3, center_x, upper_y + 3)
        painter.drawLine(center_x - 3, lower_y, center_x + 3, lower_y)
