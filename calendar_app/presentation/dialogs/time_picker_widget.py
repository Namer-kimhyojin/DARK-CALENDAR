# -*- coding: utf-8 -*-
"""Compact time editor used by task dialogs.

The previous implementation used two editable combo boxes for hour/minute,
which made focus handling and direct typing awkward inside the dialog theme.
This wrapper keeps the existing call sites but delegates to QTimeEdit so the
user can type naturally and use arrow keys or mouse wheel reliably.
"""

from PyQt6.QtCore import QDate, QElapsedTimer, Qt, QTime, pyqtSignal
from PyQt6.QtGui import QColor, QFocusEvent, QKeyEvent, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QAbstractSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_metric_tokens


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

    def _init_numeric_entry(self, accessible_hint: str):
        self._numeric_entry_buffer = ""
        self._numeric_entry_timer = QElapsedTimer()
        self.setToolTip(accessible_hint)
        self.setAccessibleDescription(accessible_hint)

    def _reset_numeric_entry(self):
        self._numeric_entry_buffer = ""
        self._numeric_entry_timer.invalidate()

    def _append_numeric_digit(self, digit: str):
        if (
            not self._numeric_entry_timer.isValid()
            or self._numeric_entry_timer.elapsed() > self._numeric_entry_timeout_ms
            or len(self._numeric_entry_buffer) >= self._numeric_entry_max_digits
        ):
            self._numeric_entry_buffer = ""
        self._numeric_entry_buffer += digit
        self._numeric_entry_timer.start()
        self._apply_numeric_entry(self._numeric_entry_buffer)

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
        if event.key() == Qt.Key.Key_Backspace and self._numeric_entry_buffer:
            self._numeric_entry_buffer = self._numeric_entry_buffer[:-1]
            self._numeric_entry_timer.start()
            if self._numeric_entry_buffer:
                self._apply_numeric_entry(self._numeric_entry_buffer)
            event.accept()
            return
        self._reset_numeric_entry()
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent):
        self._reset_numeric_entry()
        super().focusOutEvent(event)

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

    def _apply_numeric_entry(self, digits: str):
        current = self.date()
        if len(digits) == 4:
            year = int(digits)
            candidate = QDate(year, current.month(), current.day())
            if candidate.isValid() and self.minimumDate() <= candidate <= self.maximumDate():
                self.setDate(candidate)
        elif len(digits) == 6:
            candidate = QDate(int(digits[:4]), int(digits[4:6]), current.day())
            if candidate.isValid() and self.minimumDate() <= candidate <= self.maximumDate():
                self.setDate(candidate)
        elif len(digits) == 8:
            candidate = QDate.fromString(digits, "yyyyMMdd")
            if candidate.isValid() and self.minimumDate() <= candidate <= self.maximumDate():
                self.setDate(candidate)
                self.setSelectedSection(QDateTimeEdit.Section.DaySection)
            self._reset_numeric_entry()

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


class TimePickerWidget(_CompactNumericEntryMixin, QTimeEdit):
    """QTimeEdit-compatible time input with task-dialog defaults."""

    _numeric_entry_max_digits = 4
    timeChanged = pyqtSignal(QTime)

    def __init__(self, initial_time: QTime | None = None, parent=None, metrics: dict | None = None):
        super().__init__(parent)
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
        super().timeChanged.connect(self._emit_time_changed)

    def _emit_time_changed(self, value: QTime):
        self.timeChanged.emit(value)

    def stepBy(self, steps: int):
        """Use practical five-minute increments while the minute section is active."""
        if self.currentSection() == QDateTimeEdit.Section.MinuteSection:
            self.setTime(self.time().addSecs(int(steps) * 5 * 60))
            return
        super().stepBy(steps)

    def _apply_numeric_entry(self, digits: str):
        current = self.time()
        if len(digits) <= 2:
            hour = int(digits)
            if 0 <= hour <= 23:
                self.setTime(QTime(hour, current.minute(), current.second()))
            return

        if len(digits) == 3:
            hour, minute = int(digits[0]), int(digits[1:3])
        else:
            hour, minute = int(digits[:2]), int(digits[2:4])
        candidate = QTime(hour, minute)
        if candidate.isValid():
            self.setTime(candidate)
            self.setSelectedSection(QDateTimeEdit.Section.MinuteSection)
        if len(digits) >= 4:
            self._reset_numeric_entry()

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
