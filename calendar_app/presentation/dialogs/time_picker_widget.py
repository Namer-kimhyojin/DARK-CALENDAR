"""Compact time editor used by task dialogs.

The previous implementation used two editable combo boxes for hour/minute,
which made focus handling and direct typing awkward inside the dialog theme.
This wrapper keeps the existing call sites but delegates to QTimeEdit so the
user can type naturally and use arrow keys or mouse wheel reliably.
"""

from PyQt6.QtCore import QTime, pyqtSignal
from PyQt6.QtWidgets import QAbstractSpinBox, QTimeEdit

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


class TimePickerWidget(QTimeEdit):
    """QTimeEdit-compatible time input with task-dialog defaults."""

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
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setObjectName("TaskTimeEdit")
        self.setMinimumWidth(metric_bundle["min_width"])
        self.setMinimumHeight(metric_bundle["min_height"])
        self.setMaximumHeight(metric_bundle["max_height"])
        super().timeChanged.connect(self._emit_time_changed)

    def _emit_time_changed(self, value: QTime):
        self.timeChanged.emit(value)
