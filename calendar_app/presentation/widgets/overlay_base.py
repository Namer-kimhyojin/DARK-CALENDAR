"""Shared infrastructure for all overlay widgets.

Contains:
  - RGBA color helpers (_parse_rgba, _to_rgba_str, _rgba_css)
  - UI helpers (_FontPickerDialog, _pick_rgba_color, _SliderAction)
  - Layout measurement helper (_measure_face_height)
  - _GripFrame: QFrame with resize-grip paint
  - _BaseOverlayWidget: abstract base with drag/resize/context-menu logic
"""

from __future__ import annotations

import contextlib
import functools
import json
import os as _os
import re as _re
import time

from PyQt6.QtCore import QDate, QEvent, QPoint, QRect, QSize, Qt, QTime
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_stylesheet,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets import overlay_preset_logic as _preset_logic
from calendar_app.presentation.widgets import overlay_preset_service as _preset_service
from calendar_app.presentation.widgets import overlay_preset_store as _preset_store
from calendar_app.presentation.widgets import overlay_preset_ui_service as _preset_ui
from calendar_app.presentation.widgets.overlay_color_utils import (
    _parse_rgba,
    _pick_rgba_color,
    _rgba_css,
    _to_rgba_str,
)
from calendar_app.presentation.widgets.overlay_measure_utils import (
    _measure_face_size_precise,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.ui_tokens import get_ui_tokens

# Grammar hint fallback strings — kept on one line so the guardrail test can
# verify that color= aliases stay within their allowed_line_markers bucket.
_GRAMMAR_TOKEN_FALLBACK = (
    "Variable or text style: {value|size=36|bold|italic|color=accent}"  # grammar_token
)
_GRAMMAR_PLAIN_FALLBACK = (
    "Plain text with style: {Focus Mode|size=18|bold|color=warning}"  # grammar_plain_text
)

# ---------------------------------------------------------------------------
# FlowLayout — wrapping button flow (used in Quick Insert panel)
# ---------------------------------------------------------------------------


class _FlowLayout(QLayout):
    """A layout that wraps its children to the next row when the row is full."""

    def __init__(self, parent=None, h_spacing: int = 4, v_spacing: int = 4):
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        row_height = 0
        right_limit = rect.right() - margins.right()

        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > right_limit and row_height > 0:
                x = rect.x() + margins.left()
                y += row_height + self._v
                row_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += w + self._h
            row_height = max(row_height, h)

        return y + row_height - rect.y() + margins.bottom()


# ---------------------------------------------------------------------------
# strftime ??Qt format conversion helper
# ---------------------------------------------------------------------------

# Full mapping of Python strftime tokens ??Qt date/time format tokens.
_STRFTIME_TO_QT: dict[str, str] = {
    "%Y": "yyyy",
    "%y": "yy",
    "%m": "MM",
    "%n": "M",
    "%d": "dd",
    "%H": "HH",
    "%M": "mm",
    "%S": "ss",
    "%A": "dddd",
    "%a": "ddd",
    "%B": "MMMM",
    "%b": "MMM",
}


def _strftime_to_qt(fmt: str) -> str:
    """Convert a Python strftime format string to a Qt date/time format string.

    Only common tokens are converted; unknown tokens are left unchanged.
    """
    result = fmt
    for py_tok, qt_tok in _STRFTIME_TO_QT.items():
        result = result.replace(py_tok, qt_tok)
    return result


# ---------------------------------------------------------------------------
# Widget style / preset data ??JSON with Python fallback
# ---------------------------------------------------------------------------

_STYLES_JSON_PATH = _os.path.join(_os.path.dirname(__file__), "widget_styles.json")
_PRESETS_JSON_PATH = _os.path.join(_os.path.dirname(__file__), "widget_presets.json")

# Python fallback constants ??identical structure to JSON files.
# Used automatically when the JSON files are missing or corrupt.
# Literal rgba values in this fallback table are preset/style data, not runtime QSS.
# Keep live widget shell/menu/button styling on token helpers and limit new literals here
# to intentionally authored preset visuals only.
_STYLE_PARAMS_FALLBACK: dict = {
    "$schema_version": 1,
    "common_styles": {
        "default": {"margins": [18, 10, 18, 10], "radius": 12},
        "minimal": {"margins": [12, 6, 12, 6], "radius": 6, "border_type": "transparent"},
        "pill": {"margins": [24, 10, 24, 10], "radius": 50},
        "neon": {"margins": [16, 10, 16, 10], "radius": 10, "border_width": 3},
        "glass": {
            "margins": [20, 12, 20, 10],
            "radius": 16,
            "glass": True,
            "glass_bg_cap": 100,
            "glass_border_boost": 60,
        },
        "compact": {"margins": [10, 6, 10, 6], "radius": 8},
        "banner": {
            "margins": [16, 10, 16, 10],
            "radius": 0,
            "border_type": "left_only",
            "border_width": 4,
        },
    },
    "widget_styles": {
        "clock": {
            "glass": {"glass_bg_cap": 120, "glass_border_boost": 40},
            "multiline": {"margins": [18, 10, 18, 8], "radius": 12},
            "digital": {
                "margins": [20, 12, 20, 8],
                "radius": 4,
                "border_width": 2,
                "letter_spacing": 4,
            },
            "retro": {"margins": [18, 8, 18, 10], "radius": 10, "border_width": 2},
            "split": {"margins": [16, 8, 16, 8], "radius": 12},
        },
        "stopwatch": {
            "labeled": {"margins": [18, 8, 18, 10], "radius": 12},
            "round": {"margins": [22, 16, 22, 16], "radius": 60},
            "neon": {"margins": [16, 10, 16, 8], "radius": 10, "border_width": 3},
            "pill": {"margins": [26, 10, 26, 10], "radius": 50},
            "ticker": {
                "margins": [14, 6, 14, 6],
                "radius": 0,
                "border_type": "bottom_only",
                "border_width": 2,
            },
            "frame": {
                "margins": [20, 12, 20, 12],
                "radius": 14,
                "border_type": "double",
                "border_width": 3,
            },
            "glass": {
                "margins": [20, 12, 20, 10],
                "radius": 16,
                "glass": True,
                "glass_bg_cap": 100,
                "glass_border_boost": 60,
            },
        },
        "countdown": {
            "dday": {"margins": [20, 14, 20, 12], "radius": 14},
            "compact": {"margins": [12, 6, 12, 6], "radius": 8},
            "titled": {"margins": [18, 8, 18, 10], "radius": 12},
            "neon": {"margins": [18, 12, 18, 10], "radius": 10, "border_width": 3},
            "pill": {"margins": [28, 10, 28, 10], "radius": 50},
            "urgent": {
                "margins": [18, 12, 18, 10],
                "radius": 12,
                "border_width": 3,
                "accent_border_color": "rgba(224,80,80,200)",
            },
            "glass": {
                "margins": [20, 14, 20, 12],
                "radius": 16,
                "glass": True,
                "glass_bg_cap": 100,
                "glass_border_boost": 60,
            },
            "flip": {"margins": [16, 10, 16, 10], "radius": 12},
        },
        "dday": {
            "minimal": {"margins": [14, 8, 14, 8], "radius": 6, "border_type": "transparent"},
            "pill": {"margins": [28, 10, 28, 10], "radius": 50},
            "neon": {"margins": [18, 12, 18, 10], "radius": 10, "border_width": 3},
            "compact": {"margins": [12, 6, 12, 6], "radius": 8},
            "glass": {
                "margins": [20, 14, 20, 12],
                "radius": 16,
                "glass": True,
                "glass_bg_cap": 100,
                "glass_border_boost": 60,
            },
            "big": {"margins": [20, 14, 20, 12], "radius": 12},
            "retro": {
                "margins": [20, 14, 20, 12],
                "radius": 14,
                "border_type": "double",
                "border_width": 3,
            },
            "urgent": {
                "margins": [18, 12, 18, 10],
                "radius": 12,
                "border_width": 3,
                "accent_border_color": "rgba(224,80,80,200)",
                "accent_text_color": "rgba(255,120,120,240)",
            },
        },
        "datecard": {
            "horizontal": {"margins": [16, 10, 16, 10], "radius": 12},
            "compact": {"margins": [14, 8, 14, 8], "radius": 8},
            "dday": {"margins": [18, 12, 18, 10], "radius": 12},
            "fulldate": {"margins": [18, 10, 18, 10], "radius": 12},
            "minimal": {"margins": [14, 8, 14, 8], "radius": 6, "border_type": "transparent"},
            "pill": {"margins": [26, 10, 26, 10], "radius": 50},
            "week_strip": {
                "margins": [14, 8, 14, 8],
                "radius": 0,
                "border_type": "bottom_only",
                "border_width": 2,
            },
            "big_day": {"margins": [16, 10, 16, 10], "radius": 12},
            "neon": {"margins": [18, 12, 18, 12], "radius": 10, "border_width": 3},
            "glass": {
                "margins": [20, 12, 20, 12],
                "radius": 16,
                "glass": True,
                "glass_bg_cap": 100,
                "glass_border_boost": 60,
            },
            "retro": {
                "margins": [18, 12, 18, 12],
                "radius": 14,
                "border_type": "double",
                "border_width": 3,
            },
            "banner": {
                "margins": [18, 12, 18, 12],
                "radius": 0,
                "border_type": "left_only",
                "border_width": 5,
            },
            "mini_grid": {"margins": [10, 8, 10, 8], "radius": 12},
        },
        "text": {
            "outlined": {
                "margins": [14, 8, 14, 8],
                "radius": 10,
                "border_type": "outlined",
                "border_width": 2,
            },
            "neon": {"margins": [16, 10, 16, 10], "radius": 10, "border_width": 3},
            "sticky": {
                "margins": [14, 10, 14, 10],
                "radius": 4,
                "accent_bg_color": "rgba(255,230,80,220)",
                "accent_border_color": "rgba(200,170,0,160)",
                "accent_text_color": "rgba(40,30,0,230)",
            },
            "code": {
                "margins": [14, 10, 14, 10],
                "radius": 4,
                "letter_spacing": 1,
                "accent_bg_color": "rgba(10,12,20,220)",
                "accent_border_color": "rgba(80,200,120,80)",
                "accent_text_color": "rgba(80,220,120,240)",
            },
            "tag": {
                "margins": [12, 6, 16, 6],
                "radius": 0,
                "border_type": "right_only",
                "border_width": 4,
            },
            "pill": {"margins": [22, 8, 22, 8], "radius": 50},
            "glass": {
                "margins": [18, 12, 18, 12],
                "radius": 16,
                "glass": True,
                "glass_bg_cap": 100,
                "glass_border_boost": 60,
            },
        },
    },
}

# Template samples below use semantic color aliases so built-in presets track theme
# tokens while custom user templates may still keep explicit hex color values.
_PRESET_FALLBACK: dict = {
    "$schema_version": 1,
    "clock": [
        {
            "label_key": "widget.clock.preset_focus",
            "label_default": "Focus",
            "template": "{time:%H:%M|size=40|bold}\n{date:%Y.%m.%d|size=11|color=muted}",
        },
        {
            "label_key": "widget.clock.preset_timezone",
            "label_default": "Timezone",
            "template": "{time:%H:%M|size=34|bold}\n{tz_label|size=11|color=muted}",
        },
        {
            "label_key": "widget.clock.preset_weekday",
            "label_default": "Weekday+Time",
            "template": "{weekday|size=12|color=muted}\n{time:%H:%M|size=38|bold}",
        },
        {
            "label_key": "widget.clock.preset_seconds",
            "label_default": "With Seconds",
            "template": "{time:%H:%M:%S|size=32|bold}\n{date:%Y.%m.%d|size=10|color=muted}",
        },
        {
            "label_key": "widget.clock.preset_full",
            "label_default": "Full Date+Time",
            "template": "{date:%Y.%m.%d|size=12|color=muted}  {weekday:short|size=12|color=muted}\n{time:%H:%M|size=36|bold}",
        },
        {
            "label_key": "widget.clock.preset_minimal_hm",
            "label_default": "Minimal HH:mm",
            "template": "{time:%H:%M|size=48|bold}",
        },
        {
            "label_key": "widget.clock.preset_ampm",
            "label_default": "AM/PM 12h",
            "template": "{time:%p|size=12|color=muted}\n{time:%I:%M|size=38|bold}",
        },
        {
            "label_key": "widget.clock.preset_world",
            "label_default": "World Clock",
            "template": "{time:%H:%M|size=30|bold}  {tz_label|size=12|color=muted}\n{date:%m/%d|size=11|color=muted}  {weekday:short|size=11|color=muted}",
        },
    ],
    "stopwatch": [
        {
            "label_key": "widget.stopwatch.preset_default",
            "label_default": "Default",
            "template": "__DEFAULT__",
        },
        {
            "label_key": "widget.stopwatch.preset_compact",
            "label_default": "Compact",
            "template": "{elapsed|size=34|bold}",
        },
        {
            "label_key": "widget.stopwatch.preset_status",
            "label_default": "Icon+Status",
            "template": "{status_icon|size=14}  {elapsed|size=32|bold}\n{status|size=11|color=muted}",
        },
        {
            "label_key": "widget.stopwatch.preset_split",
            "label_default": "Split M:S",
            "template": "{minutes|size=40|bold}:{seconds|size=40|bold}.{tenths|size=22|color=muted}",
        },
        {
            "label_key": "widget.stopwatch.preset_hms",
            "label_default": "H:M:S Full",
            "template": "{hours|size=26|bold}h {minutes|size=26|bold}m {seconds|size=26|bold}s",
        },
        {
            "label_key": "widget.stopwatch.preset_tenths",
            "label_default": "Tenths Focus",
            "template": "{elapsed|size=30|bold}.{tenths|size=22|bold|color=accent}\n{status|size=10|color=muted}",
        },
        {
            "label_key": "widget.stopwatch.preset_minimal",
            "label_default": "Minimal",
            "template": "{elapsed|size=42|bold}",
        },
        {
            "label_key": "widget.stopwatch.preset_lab",
            "label_default": "Lab Timer",
            "template": "{status_icon|size=18|color=accent}\n{hours|size=20|bold}h {minutes|size=20|bold}m {seconds|size=20|bold}s",
        },
    ],
    "countdown": [
        {
            "label_key": "widget.countdown.preset_default",
            "label_default": "Default",
            "template": "__DEFAULT__",
        },
        {
            "label_key": "widget.countdown.preset_d_day",
            "label_default": "D-Day",
            "template": "D-{days|size=38|bold}\n{target:%Y.%m.%d|size=11|color=muted}",
        },
        {
            "label_key": "widget.countdown.preset_flip",
            "label_default": "H:M:S",
            "template": "{hours|size=32|bold}:{minutes|size=32|bold}:{seconds|size=32|bold}",
        },
        {
            "label_key": "widget.countdown.preset_days_big",
            "label_default": "Days Big",
            "template": "{days|size=48|bold}\n{target:%Y.%m.%d|size=11|color=muted}",
        },
        {
            "label_key": "widget.countdown.preset_compact",
            "label_default": "Compact",
            "template": "{remaining|size=28|bold}",
        },
        {
            "label_key": "widget.countdown.preset_full",
            "label_default": "Full H:M:S",
            "template": "{days|size=13|color=muted}d  {hours|size=30|bold}:{minutes|size=30|bold}:{seconds|size=30|bold}",
        },
        {
            "label_key": "widget.countdown.preset_alarm",
            "label_default": "Alarm Style",
            "template": "{remaining|size=36|bold}\n{target:%Y.%m.%d %H:%M|size=10|color=muted}",
        },
    ],
    "dday": [
        {
            "label_key": "widget.dday.preset_default",
            "label_default": "Default",
            "template": "__DEFAULT__",
        },
        {
            "label_key": "widget.dday.preset_big",
            "label_default": "Big D-Day",
            "template": "{dday|size=60|bold|color=accent}\n{label|size=13|italic}",
        },
        {
            "label_key": "widget.dday.preset_days",
            "label_default": "Days Count",
            "template": "{days|size=48|bold}\n{date:%Y.%m.%d|size=11|color=muted}",
        },
        {
            "label_key": "widget.dday.preset_sign",
            "label_default": "Sign+Days",
            "template": "{sign|size=18|color=muted}{days|size=48|bold}\n{label|size=12}",
        },
        {
            "label_key": "widget.dday.preset_label_top",
            "label_default": "Label+Date",
            "template": "{label|size=13|italic|color=muted}\n{dday|size=44|bold}\n{date:%Y.%m.%d|size=10|color=muted}",
        },
        {
            "label_key": "widget.dday.preset_compact",
            "label_default": "Compact",
            "template": "{dday|size=28|bold}  {label|size=11|color=muted}",
        },
        {
            "label_key": "widget.dday.preset_days_left",
            "label_default": "Days Left",
            "template": "{days|size=42|bold}\n{date_short|size=11|color=muted}",
        },
        {
            "label_key": "widget.dday.preset_minimal",
            "label_default": "Minimal",
            "template": "{dday|size=52|bold}",
        },
    ],
    "datecard": [
        {
            "label_key": "widget.datecard.preset_default",
            "label_default": "Default",
            "template": "__DEFAULT__",
        },
        {
            "label_key": "widget.datecard.preset_big_day",
            "label_default": "Big Day",
            "template": "{day|size=42|bold}\n{weekday|size=12|color=muted}\n{date|size=10|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_strip",
            "label_default": "Strip",
            "template": "{weekday:short|size=12|color=muted}  {day|size=22|bold}  {date:%m/%d|size=12}",
        },
        {
            "label_key": "widget.datecard.preset_doy",
            "label_default": "Day of Year",
            "template": "{doy|size=32|bold}\n{date|size=11|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_month_day",
            "label_default": "Month.Day",
            "template": "{month|size=18|color=muted}\n{day|size=48|bold}",
        },
        {
            "label_key": "widget.datecard.preset_en_week",
            "label_default": "EN Weekday",
            "template": "{weekday:en|size=13|color=muted}\n{day|size=40|bold}\n{date:%Y/%m/%d|size=10|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_full_date",
            "label_default": "Full Date",
            "template": "{date:%Y.%m.%d|size=22|bold}\n{weekday|size=12|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_year_week",
            "label_default": "Year+DOY",
            "template": "{year|size=12|color=muted}\n{doy|size=38|bold}  {weekday:short|size=13|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_glass",
            "label_default": "Glass",
            "template": "{weekday|size=12|color=muted}\n{day|size=44|bold}\n{date|size=10|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_week_num",
            "label_default": "Week Num",
            "template": "W{week_num|size=40|bold}\n{date|size=10|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_quarter",
            "label_default": "Quarter",
            "template": "{quarter|size=36|bold|color=accent}\n{date|size=11|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_month_end",
            "label_default": "Month End",
            "template": "{days_left_month|size=42|bold}\n{date:%Y.%m|size=11|color=muted}",
        },
        {
            "label_key": "widget.datecard.preset_tomorrow",
            "label_default": "Tomorrow",
            "template": "{tomorrow|size=18|bold}\n{weekday|size=12|color=muted}",
        },
    ],
    "text": [
        {
            "label_key": "widget_text.preset_clock_date",
            "label_default": "Clock + Date",
            "template": "{time:%H:%M|size=36|bold}\n{date:%Y.%m.%d|size=12|color=muted}",
        },
        {
            "label_key": "widget_text.preset_task_overview",
            "label_default": "Task Overview",
            "template": "{task_count|size=32|bold}\n{next_event|size=11|color=muted}",
        },
        {
            "label_key": "widget_text.preset_stopwatch",
            "label_default": "Stopwatch",
            "template": "{stopwatch:stopwatch_0|size=32|bold}\n{time:%H:%M|size=11|color=muted}",
        },
        {
            "label_key": "widget_text.preset_countdown",
            "label_default": "Countdown",
            "template": "{countdown:countdown_0|size=28|bold}\n{date:%Y.%m.%d|size=11|color=muted}",
        },
        {
            "label_key": "widget_text.preset_dday",
            "label_default": "D-Day",
            "template": "{dday:dday_0|size=40|bold|color=accent}\n{date:%Y.%m.%d|size=11|color=muted}",
        },
        {
            "label_key": "widget_text.preset_conditional_task",
            "label_default": "Conditional Tasks",
            "template": "{if task_count > 0}Tasks {task_count|size=28|bold}\n{next_event|size=11|color=muted}{else}No tasks today{/if}",
        },
        {
            "label_key": "widget_text.preset_clock_stopwatch",
            "label_default": "Clock + Stopwatch",
            "template": "{time:%H:%M|size=30|bold}\n{stopwatch:stopwatch_0|size=16|color=muted}",
        },
        {
            "label_key": "widget_text.preset_dashboard",
            "label_default": "Dashboard",
            "template": "{time:%H:%M|size=26|bold}  {date:%m.%d|size=11|color=muted}\nTasks {task_count|size=13|bold}  {next_event|size=10|color=muted}",
        },
        {
            "label_key": "widget_text.preset_time_only",
            "label_default": "Time Only",
            "template": "{time:%H:%M|size=52|bold}",
        },
        {
            "label_key": "widget_text.preset_world_time",
            "label_default": "World Time",
            "template": "{time:%H:%M|size=28|bold}  KST\n{time:tz=UTC:%H:%M|size=20|color=muted}  UTC",
        },
        {
            "label_key": "widget_text.preset_custom_var",
            "label_default": "Custom Variable",
            "template": "{custom_var|size=28|bold}",
        },
        {
            "label_key": "widget_text.preset_countdown_alert",
            "label_default": "Countdown Alert",
            "template": "{if countdown:countdown_0 < 1h}Less than 1 hour left{else}{countdown:countdown_0|size=24|bold}{/if}",
        },
    ],
}


@functools.lru_cache(maxsize=1)
def _load_widget_styles() -> dict:
    """Load widget_styles.json (cached). Falls back to _STYLE_PARAMS_FALLBACK on any error."""
    try:
        with open(_STYLES_JSON_PATH, encoding="utf-8", errors="strict") as _f:
            _data = json.load(_f)
        if _data.get("$schema_version") != 1:
            return _STYLE_PARAMS_FALLBACK
        return _data
    except Exception:
        return _STYLE_PARAMS_FALLBACK


@functools.lru_cache(maxsize=1)
def _load_widget_presets_json() -> dict:
    """Load widget_presets.json (cached). Falls back to _PRESET_FALLBACK on any error."""
    try:
        with open(_PRESETS_JSON_PATH, encoding="utf-8", errors="strict") as _f:
            _data = json.load(_f)
        if _data.get("$schema_version") != 1:
            return _PRESET_FALLBACK
        return _data
    except Exception:
        return _PRESET_FALLBACK


def _style_params_for(widget_type: str, style_id: str) -> dict:
    """Return merged style-params dict for *widget_type* + *style_id*.

    Merge order (later wins):
        common_styles[style_id] + widget_styles[widget_type][style_id]

    Falls back to common "default" when *style_id* is not found in either.
    """
    _data = _load_widget_styles()
    _common = _data.get("common_styles", {})
    _widget = _data.get("widget_styles", {}).get(widget_type, {})
    _base = dict(
        _common.get(style_id)
        or _common.get("default")
        or {"margins": [18, 10, 18, 10], "radius": 12}
    )
    _base.update(_widget.get(style_id, {}))
    return _base


def _get_widget_presets(widget_type: str, translate_fn, default_template: str = "") -> list:
    """Return ``[(translated_label, template_str), ...]`` for *widget_type*.

    Entries whose template is ``"__DEFAULT__"`` are replaced with *default_template*.
    """
    _data = _load_widget_presets_json()
    _result = []
    for _entry in _data.get(widget_type, []):
        _lkey = _entry.get("label_key", "")
        _ldefault = _entry.get("label_default", "")
        _label = translate_fn(_lkey, _ldefault) if _lkey else _ldefault
        _tmpl = _entry.get("template", "")
        if _tmpl == "__DEFAULT__":
            _tmpl = default_template
        _result.append((_label, _tmpl))
    return _result


def _build_face_ss(
    obj_name: str,
    sp: dict,
    bg_c: QColor,
    bg_a: int,
    bd_c: QColor,
    bd_a: int,
    fg_c: QColor,
    fg_a: int,
) -> str:
    """Generate a ``QFrame#<obj_name>`` stylesheet from style-params dict *sp*.

    Supported ``border_type`` values:
        ``"solid"`` (default), ``"transparent"``, ``"double"``,
        ``"bottom_only"``, ``"left_only"``, ``"right_only"``, ``"outlined"``

    Optional *sp* keys: ``glass``, ``glass_bg_cap``, ``glass_border_boost``,
    ``accent_bg_color``, ``accent_border_color``, ``border_width``, ``radius``.
    """
    _radius = sp.get("radius", 12)
    _btype = sp.get("border_type", "solid")
    _bwidth = sp.get("border_width", 1)

    # Generate a sophisticated dark glassmorphism gradient
    # We use a multi-stop gradient to give it a "depth" feel
    _g1 = _rgba_css(bg_c, min(255, bg_a + 20))
    _g2 = _rgba_css(bg_c, bg_a)
    _g3 = _rgba_css(bg_c, max(0, bg_a - 15))

    _bg_css = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {_g1}, stop:0.5 {_g2}, stop:1 {_g3})"

    if "accent_bg_color" in sp:
        _bg_css = sp["accent_bg_color"]
    elif sp.get("glass"):
        # Extra translucency for glass mode
        _bg_css = _rgba_css(bg_c, min(bg_a, sp.get("glass_bg_cap", 140)))

    # --- border color ---
    if bd_a == 0:
        _bd_css = "transparent"
    else:
        # We boost the border visibility slightly for "Standard" styles to help on bright backgrounds
        _bd_val = min(255, bd_a + 40)
        _bd_css = _rgba_css(bd_c, _bd_val)

        if "accent_border_color" in sp:
            _bd_css = sp["accent_border_color"]
        elif sp.get("glass"):
            _bd_css = _rgba_css(bd_c, min(bd_a + sp.get("glass_border_boost", 80), 255))

    # --- border style ---
    if bd_a == 0:
        _border = "border: none;"
    elif _btype == "transparent":
        _border = "border: 1px solid transparent;"
    elif _btype == "double":
        _border = f"border: {_bwidth + 1}px double {_bd_css};"
    elif _btype == "bottom_only":
        _border = (
            f"border-bottom: {_bwidth + 1}px solid {_bd_css};"
            f" border-top: none; border-left: none; border-right: none;"
        )
    elif _btype == "left_only":
        _border = (
            f"border-left: {_bwidth + 2}px solid {_bd_css};"
            f" border-top: none; border-right: none; border-bottom: none;"
        )
    elif _btype == "outlined":
        _bg_css = "transparent"
        _border = f"border: {_bwidth}px solid {_bd_css};"
    else:  # "solid"
        _border = f"border: {_bwidth}px solid {_bd_css};"

    return (
        f"QFrame#{obj_name} {{"
        f" background: {_bg_css}; {_border} border-radius: {_radius}px;"
        f" color: {_rgba_css(fg_c, fg_a)}; }}"
    )


# ---------------------------------------------------------------------------
# Font + color picker dialogs
# ---------------------------------------------------------------------------


class _FontPickerDialog(QDialog):
    """Simple font family + size picker."""

    def __init__(self, family: str, size: int, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("widget.font_picker.title", "Choose Font"))
        self.setModal(True)
        apply_common_dialog_style(self, minimum_width=360, size=(420, 180))
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self._combo = QFontComboBox(self)
        self._combo.setCurrentFont(QFont(family))
        self._spin = QSpinBox(self)
        self._spin.setRange(6, 400)
        self._spin.setValue(size)
        row.addWidget(self._combo, 1)
        row.addWidget(QLabel(t("widget.font_picker.size", "Size:")))
        row.addWidget(self._spin)
        layout.addLayout(row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = btns.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryBtn")
        if cancel_btn is not None:
            cancel_btn.setObjectName("SecondaryBtn")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def result_font(self) -> tuple[str, int]:
        return self._combo.currentFont().family(), self._spin.value()


# ---------------------------------------------------------------------------
# Inline alpha slider widget (for context menus)
# ---------------------------------------------------------------------------


class _SliderAction(QWidget):
    """Horizontal slider embeddable as a QWidgetAction in QMenu."""

    def __init__(self, label: str, value: int, lo: int, hi: int, callback, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        lbl = QLabel(label)
        lbl.setMinimumWidth(90)
        layout.addWidget(lbl)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(lo, hi)
        self._slider.setValue(value)
        self._val_label = QLabel(str(value))
        self._val_label.setMinimumWidth(28)
        self._slider.valueChanged.connect(lambda v: (self._val_label.setText(str(v)), callback(v)))
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._val_label)


# ---------------------------------------------------------------------------
# Shared dialog stylesheet (used by all widget settings dialogs)
# ---------------------------------------------------------------------------

# This template intentionally keeps literal colors as token-mapper inputs.
# _apply_widget_dialog_tokens() rewrites these placeholders to live theme values.
_DLG_SS = (
    "QDialog { background: #1a1e2e; color: #d0d8f0; }"
    # Hero banner
    "QFrame#settingsHero { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    "  stop:0 rgba(60,140,255,50), stop:1 rgba(77,166,255,16));"
    "  border: 1px solid rgba(77,166,255,55); border-radius: 10px; }"
    "QLabel#settingsHeroTitle { color: #eef4ff; font-size: 12pt; font-weight: bold; }"
    "QLabel#settingsHeroBody { color: #9fb4d8; font-size: 9pt; }"
    # Section separator label
    "QLabel#sectionLabel { color: #3c8cff; font-size: 8pt; font-weight: bold;"
    "  letter-spacing: 1px; padding: 0; margin: 0; }"
    # Preview card
    "QFrame#previewCard { background: #111522; border: 1px solid rgba(255,255,255,22);"
    "  border-radius: 10px; min-height: 80px; }"
    "QLabel#previewCaption { color: #8090b0; font-size: 8pt; font-weight: bold; letter-spacing: 1px; }"
    "QLabel#previewMeta { color: #6d7fa8; font-size: 8pt; padding: 0 2px; }"
    # Hint box
    "QFrame#hintBox { background: #141828; border: 1px solid rgba(60,140,255,30);"
    "  border-radius: 8px; }"
    "QLabel#hintText { color: #7a90b8; font-size: 8.5pt; }"
    # Collapsible hint container
    "QWidget#collapsibleHint { background: transparent; }"
    # QSplitter handle
    "QSplitter::handle { background: #2a3050; width: 2px; }"
    "QSplitter::handle:hover { background: #3c8cff; }"
    # Field labels
    "QLabel#fieldLabel { color: #a0b4d0; font-size: 9pt; font-weight: bold; min-width: 100px; }"
    # Common widgets
    "QLabel { color: #d0d8f0; font-size: 10pt; }"
    "QScrollArea { background: transparent; border: none; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
    "QCalendarWidget { border: 1px solid #2a3050; border-radius: 6px; }"
    "QCalendarWidget QAbstractItemView { background: #1e2230; color: #d0d8f0;"
    "  selection-background-color: #3c8cff; selection-color: #fff; }"
    "QCalendarWidget QToolButton { color: #d0d8f0; background: transparent; font-weight: bold; }"
    "QCalendarWidget QMenu { background: #252840; color: #d0d8f0; }"
    "QComboBox { background: #252840; color: #d0d8f0; border: 1px solid #3a4468;"
    "  border-radius: 5px; padding: 4px 10px; font-size: 10pt; }"
    "QComboBox:focus { border-color: #3c8cff; }"
    "QComboBox::drop-down { border: none; width: 20px; }"
    "QComboBox QAbstractItemView { background: #252840; color: #d0d8f0;"
    "  selection-background-color: #3c8cff; border: 1px solid #3a4468; }"
    "QLineEdit { background: #1e2230; color: #d0d8f0; border: 1px solid #3a4468;"
    "  border-radius: 5px; padding: 5px 10px; font-size: 10pt; }"
    "QLineEdit:focus { border-color: #3c8cff; }"
    "QPlainTextEdit { background: #1e2230; color: #d0d8f0; border: 1px solid #3a4468;"
    "  border-radius: 5px; padding: 4px 8px; font-size: 10.5pt; }"
    "QPlainTextEdit:focus { border-color: #3c8cff; }"
    "QSpinBox { background: #252840; color: #d0d8f0; border: 1px solid #3a4468;"
    "  border-radius: 5px; padding: 4px 8px; font-size: 10pt; }"
    "QSpinBox:focus { border-color: #3c8cff; }"
    "QSpinBox::up-button, QSpinBox::down-button { background: #2e3550; border: none; width: 18px; }"
    # Buttons
    "QPushButton { background: #252840; color: #d0d8f0; border: 1px solid #3a4468;"
    "  border-radius: 5px; padding: 5px 14px; font-size: 9.5pt; }"
    "QPushButton:hover { background: #2e3550; border-color: #5a7aaa; }"
    "QPushButton:pressed { background: #1e2230; }"
    "QDialogButtonBox QPushButton { background: rgba(60,140,255,0.20); color: #d0d8f0;"
    "  border: 1px solid rgba(60,140,255,0.55); border-radius: 5px;"
    "  padding: 6px 22px; font-weight: bold; font-size: 10pt; }"
    "QDialogButtonBox QPushButton:hover { background: rgba(60,140,255,0.35); }"
    "QPushButton#dangerBtn { background: rgba(255,80,80,0.15); color: #ff9090;"
    "  border: 1px solid rgba(255,80,80,0.4); }"
    "QPushButton#dangerBtn:hover { background: rgba(255,80,80,0.28); }"
    "QPushButton#resetBtn { background: rgba(255,80,80,0.15); color: #ff8080;"
    "  border: 1px solid rgba(255,80,80,0.4); border-radius: 5px; padding: 4px 12px; }"
    "QPushButton#presetBtn { background: rgba(60,140,255,0.12); color: #90b8f0;"
    "  border: 1px solid rgba(60,140,255,0.30); padding: 4px 10px; border-radius: 4px; }"
    "QPushButton#presetBtn:hover { background: rgba(60,140,255,0.25); }"
    "QCheckBox { color: #d0d8f0; font-size: 10pt; spacing: 6px; }"
    "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px;"
    "  background: #252840; border: 1px solid #3a4468; }"
    "QCheckBox::indicator:checked { background: #3c8cff; border-color: #3c8cff; }"
    "QFrame#divider { background: #2a3050; max-height: 1px; }"
)

_OVERLAY_DLG_SS_TEMPLATE = _DLG_SS


def _overlay_dialog_style_bundle(tokens: dict | None = None, metrics: dict | None = None) -> dict:
    resolved_tokens = dict(get_dialog_theme_tokens())
    if tokens:
        resolved_tokens.update(tokens)
    resolved_metrics = dict(get_dialog_metric_tokens())
    if metrics:
        resolved_metrics.update(metrics)

    accent = str(resolved_tokens["accent"])
    accent_hover = str(resolved_tokens.get("accent_hover") or accent)
    accent_color = QColor(accent)
    if not accent_color.isValid():
        accent_color = QColor("#3c8cff")

    def _acc(alpha: str) -> str:
        return f"rgba({accent_color.red()},{accent_color.green()},{accent_color.blue()},{alpha})"

    return {
        "tokens": resolved_tokens,
        "metrics": resolved_metrics,
        "accent": accent,
        "accent_hover": accent_hover,
        "accent_soft_12": _acc("0.12"),
        "accent_soft_20": _acc("0.20"),
        "accent_soft_25": _acc("0.25"),
        "accent_soft_30": _acc("0.30"),
        "accent_soft_35": _acc("0.35"),
        "accent_soft_55": _acc("0.55"),
        "panel_radius": max(10, int(resolved_metrics.get("list_radius", 6)) + 4),
        "hint_radius": max(8, int(resolved_metrics.get("group_radius", 3)) + 5),
        "tab_pane_radius": max(6, int(resolved_metrics.get("tab_radius", 0)) + 6),
        "field_radius": max(5, int(resolved_metrics.get("field_radius", 0)) + 5),
        "button_radius": max(5, int(resolved_metrics.get("button_radius", 5))),
        "preset_radius": max(4, int(resolved_metrics.get("button_radius", 5)) - 1),
        "check_radius": max(3, int(resolved_metrics.get("checkbox_indicator_size", 10)) // 3),
        "menu_radius": max(6, int(resolved_metrics.get("list_radius", 6))),
        "menu_item_radius": max(4, int(resolved_metrics.get("list_item_radius", 4))),
    }


def _overlay_menu_style(tokens: dict | None = None, metrics: dict | None = None) -> str:
    bundle = _overlay_dialog_style_bundle(tokens=tokens, metrics=metrics)
    resolved_tokens = bundle["tokens"]
    accent = QColor(bundle["accent"])
    selected_bg = f"rgba({accent.red()},{accent.green()},{accent.blue()},0.32)"
    return (
        f"QMenu {{ background: {resolved_tokens['surface_alt']}; color: {resolved_tokens['text_primary']}; "
        f"border: 1px solid {resolved_tokens['border']}; border-radius: {bundle['menu_radius']}px; "
        "font-family: 'Segoe UI Emoji', 'Segoe UI Symbol', 'Segoe UI', 'Malgun Gothic', sans-serif; font-size: 13px; padding: 4px; }"
        "QMenu::item { padding: 6px 24px 6px 28px; border-radius: 4px; }"
        f"QMenu::item:selected {{ background: {selected_bg}; border-radius: {bundle['menu_item_radius']}px; }}"
        "QMenu::icon { left: 8px; }"
        f"QMenu::separator {{ height: 1px; background: {resolved_tokens.get('border_soft') or resolved_tokens['border']}; margin: 5px 8px; }}"
    )


def _apply_widget_dialog_tokens(
    css: str, tokens: dict | None = None, metrics: dict | None = None
) -> str:
    bundle = _overlay_dialog_style_bundle(tokens=tokens, metrics=metrics)
    resolved_tokens = bundle["tokens"]
    replacements = {
        "#3c8cff": bundle["accent"],
        "#90b8f0": bundle["accent_hover"],
        "rgba(60,140,255,0.12)": bundle["accent_soft_12"],
        "rgba(60,140,255,0.20)": bundle["accent_soft_20"],
        "rgba(60,140,255,0.25)": bundle["accent_soft_25"],
        "rgba(60,140,255,0.30)": bundle["accent_soft_30"],
        "rgba(60,140,255,0.35)": bundle["accent_soft_35"],
        "rgba(60,140,255,0.55)": bundle["accent_soft_55"],
        "#1a1e2e": resolved_tokens["surface_bg"],
        "#1e2230": resolved_tokens["surface_alt"],
        "#252840": resolved_tokens["surface_item"],
        "#2e3550": resolved_tokens["surface_hover"],
        "#d0d8f0": resolved_tokens["text_primary"],
        "#a0b4d0": resolved_tokens["text_secondary"],
        "#8090b0": resolved_tokens["text_muted"],
        "#6d7fa8": resolved_tokens.get("text_faint") or resolved_tokens["text_muted"],
        "#9fb4d8": resolved_tokens["text_secondary"],
        "#2a3050": resolved_tokens["border"],
        "#3a4468": resolved_tokens["border"],
        "#5a7aaa": resolved_tokens.get("border_soft") or resolved_tokens["border"],
        "#111522": resolved_tokens.get("surface_top") or resolved_tokens["surface_bg"],
        "border-radius: 10px;": f"border-radius: {bundle['panel_radius']}px;",
        "border-radius: 8px;": f"border-radius: {bundle['hint_radius']}px;",
        "border-radius: 0 6px 6px 6px;": f"border-radius: 0 {bundle['tab_pane_radius']}px {bundle['tab_pane_radius']}px {bundle['tab_pane_radius']}px;",
        "border-radius: 6px 6px 0 0;": f"border-radius: {bundle['tab_pane_radius']}px {bundle['tab_pane_radius']}px 0 0;",
        "border-radius: 6px;": f"border-radius: {bundle['tab_pane_radius']}px;",
        "border-radius: 5px;": f"border-radius: {bundle['field_radius']}px;",
        "border-radius: 4px;": f"border-radius: {bundle['preset_radius']}px;",
        "border-radius: 3px;": f"border-radius: {bundle['check_radius']}px;",
    }
    for old, new in replacements.items():
        css = css.replace(old, new)
    return css


def _build_overlay_dialog_stylesheet(
    tokens: dict | None = None, metrics: dict | None = None
) -> str:
    return _apply_widget_dialog_tokens(
        build_dialog_stylesheet() + _OVERLAY_DLG_SS_TEMPLATE, tokens=tokens, metrics=metrics
    )


_DLG_SS = _build_overlay_dialog_stylesheet()


def _fresh_dlg_ss() -> str:
    """설정 다이얼로그 열기 직전에 현재 테마 토큰으로 stylesheet를 빌드."""
    return _build_overlay_dialog_stylesheet()


def _overlay_color_button_style(
    rgba: str, tokens: dict | None = None, metrics: dict | None = None
) -> str:
    bundle = _overlay_dialog_style_bundle(tokens=tokens, metrics=metrics)
    raw = str(rgba or "").strip()
    if raw.lower().startswith("rgba("):
        css = raw
    else:
        c, a = _parse_rgba(raw)
        css = _rgba_css(c, a)
    border = bundle["tokens"]["border"]
    radius = bundle["preset_radius"]
    return f"background: {css}; border: 1px solid {border}; border-radius: {radius}px;"


def _overlay_hint_toggle_style(tokens: dict | None = None) -> str:
    bundle = _overlay_dialog_style_bundle(tokens=tokens)
    text_muted = bundle["tokens"]["text_muted"]
    text_secondary = bundle["tokens"]["text_secondary"]
    return (
        "QToolButton {"
        f" color:{text_muted}; font-size:9pt; background:transparent;"
        " border:none; text-align:left; padding:4px 2px; }"
        f"QToolButton:hover {{ color:{text_secondary}; }}"
    )


def _overlay_hint_link_style(tokens: dict | None = None) -> str:
    bundle = _overlay_dialog_style_bundle(tokens=tokens)
    link_color = bundle["tokens"].get("accent_hover", bundle["accent"])
    return f"color:{link_color};text-decoration:none;"


def _overlay_preview_card_inline_style(metrics: dict | None = None) -> str:
    resolved_metrics = dict(get_dialog_metric_tokens())
    if metrics:
        resolved_metrics.update(metrics)
    padding_y = max(12, int(resolved_metrics.get("textedit_padding_y", 8)) + 10)
    padding_x = max(10, int(resolved_metrics.get("textedit_padding_x", 10)) + 2)
    return f"padding: {padding_y}px {padding_x}px;"


def _overlay_group_label_style(tokens: dict | None = None, metrics: dict | None = None) -> str:
    bundle = _overlay_dialog_style_bundle(tokens=tokens, metrics=metrics)
    color = bundle["tokens"].get("text_faint") or bundle["tokens"]["text_muted"]
    font_pt = max(8, int(bundle["metrics"].get("subtitle_font_pt", 11)) - 3)
    return f"color:{color}; font-size:{font_pt}pt;"


# ---------------------------------------------------------------------------
# Template HTML helpers (used by all _resolve_*_template methods)
# ---------------------------------------------------------------------------

_TEMPLATE_COLOR_ALIASES = frozenset(
    {
        "text",
        "primary",
        "secondary",
        "muted",
        "faint",
        "accent",
        "info",
        "warning",
        "success",
        "danger",
    }
)
_TEMPLATE_COLOR_ALIAS_RE = _re.compile(r"color:([A-Za-z_][A-Za-z0-9_-]*)(?=[;\"'])", _re.IGNORECASE)


def _normalize_template_color_hint(raw: str) -> str:
    value = str(raw or "").strip()
    alias = value.lower()
    return alias if alias in _TEMPLATE_COLOR_ALIASES else value


def _apply_span(value: str, hints: list[str]) -> str:
    """Wrap *value* in a <span> tag built from pipe-separated style hints.

    Size hint (``size=...``): all forms are stored as sentinel markers and
    resolved proportionally at render time by ``_scale_template_html``:

        size=36         : "36 pt when base font = 24 pt" (legacy ratio mode)
        size=1.5x       : 1.5 x base font size
        size=150%       : 150% of base font size (same as 1.5x)
        size=+10        : base font size + 10 pt
        size=-4         : base font size - 4 pt
        size=base       : exactly the base font size (= size=1x = size=100%)

    Other hints:
        bold            : font-weight: bold
        italic          : font-style: italic
        color=accent / muted / warning / ... or a custom hex color
                        : semantic alias or explicit CSS color value
        lh=N / line=N / line_height=N
                        : line-height (pt values are also scaled proportionally)

    Returns the bare value string when no hints produce any styles.
    """
    styles: list[str] = []
    for h in hints:
        h = h.strip()
        if h.startswith("size="):
            raw = h[5:].strip()
            # Encode as a sentinel so _scale_template_html resolves at render time.
            # Format: font-size:<encoded>_TMPLREF_pt
            # Encodings:
            #   RATIO:<float>   ??multiply base by float  (1.5x / 150% / base)
            #   DELTA:<int>     ??add int to base          (+10 / -4)
            #   REF:<int>       ??legacy "N at ref=24pt"   (plain integer)
            if raw == "base":
                styles.append("font-size:RATIO:1.0_TMPLREF_pt")
            elif raw.endswith("x"):
                with contextlib.suppress(ValueError):
                    styles.append(f"font-size:RATIO:{float(raw[:-1])}_TMPLREF_pt")
            elif raw.endswith("%"):
                with contextlib.suppress(ValueError):
                    styles.append(f"font-size:RATIO:{float(raw[:-1]) / 100.0}_TMPLREF_pt")
            elif raw.startswith(("+", "-")) and raw[1:].lstrip(".").isdigit():
                with contextlib.suppress(ValueError):
                    styles.append(f"font-size:DELTA:{int(float(raw))}_TMPLREF_pt")
            else:
                with contextlib.suppress(ValueError):
                    styles.append(f"font-size:REF:{int(raw)}_TMPLREF_pt")
        elif h.startswith(("line=", "line_height=", "lh=")):
            raw = h.split("=", 1)[1].strip()
            if not raw:
                continue
            try:
                num = float(raw)
            except ValueError:
                styles.append(f"line-height:{raw}")
            else:
                if num <= 4:
                    # Treat as a unitless multiplier ??also scale proportionally
                    styles.append(f"line-height:RATIO:{num}_TMPLREF_lh")
                elif float(num).is_integer():
                    styles.append(f"line-height:REF:{int(num)}_TMPLREF_lh")
                else:
                    styles.append(f"line-height:REF:{num}_TMPLREF_lh")
        elif h == "bold":
            styles.append("font-weight:bold")
        elif h == "italic":
            styles.append("font-style:italic")
        elif h.startswith("color="):
            styles.append(f"color:{_normalize_template_color_hint(h[6:])}")
    if styles:
        return f'<span style="{";".join(styles)}">{value}</span>'
    return value


# Reference font size used for the legacy ``size=N`` (plain integer) form.
# "size=36" means "36 pt when the base font is this many pt".
from calendar_app.presentation.widgets.overlay_template_utils import (  # noqa: E402, F401
    _apply_align_tags,
    _empty_preview_html,
    _extract_global_lh,
    _inject_global_lh,
    _preview_base_size,
    _protect_align_tags,
    _scale_template_html,
)

# ---------------------------------------------------------------------------
# Grip frame
# ---------------------------------------------------------------------------

_RESIZE_GRIP = 22  # px corner resize zone


class _GripFrame(QFrame):
    """QFrame subclass that paints a resize-grip indicator.

    show_grip: set True while actively resizing (bright, fully opaque)
    hover_grip: set True while mouse hovers the resize zone (dim, semi-transparent)
    """

    show_grip: bool = False  # toggled by _BaseOverlayWidget during resize drag
    hover_grip: bool = False  # toggled by _BaseOverlayWidget on hover enter/leave
    grip_corner: str | None = None

    def paintEvent(self, event):
        super().paintEvent(event)
        interaction_fill = self.property("_interaction_fill_color")
        if isinstance(interaction_fill, QColor) and interaction_fill.alpha() > 0:
            p = QPainter(self)
            p.fillRect(self.rect(), interaction_fill)
            p.end()
        if not self.show_grip and not self.hover_grip:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = 215 if self.show_grip else 110
        w, h = self.width(), self.height()
        margin, arm = 7, 10
        grip_color = self.property("_grip_color")
        if not isinstance(grip_color, QColor):
            grip_color = QColor(255, 255, 255)
        frame_rect = self.rect().adjusted(3, 3, -3, -3)

        color_frame = QColor(grip_color)
        color_frame.setAlpha(210 if self.show_grip else 120)
        color_frame_pen = QPen(color_frame, 1.0 if self.show_grip else 0.9)
        color_frame_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        p.setPen(color_frame_pen)
        p.drawRoundedRect(frame_rect, 10, 10)

        def _draw_corner(corner: str, strong: bool = False):
            local_color = QColor(grip_color)
            local_color.setAlpha(245 if strong else alpha)
            color_pen = QPen(local_color, 2.2 if strong else 1.8)
            color_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

            p.setPen(color_pen)
            if corner == "top_left":
                p.drawLine(margin, margin + arm, margin, margin)
                p.drawLine(margin, margin, margin + arm, margin)
            elif corner == "top_right":
                p.drawLine(w - margin - arm, margin, w - margin, margin)
                p.drawLine(w - margin, margin, w - margin, margin + arm)
            elif corner == "bottom_left":
                p.drawLine(margin, h - margin - arm, margin, h - margin)
                p.drawLine(margin, h - margin, margin + arm, h - margin)
            elif corner == "bottom_right":
                p.drawLine(w - margin - arm, h - margin, w - margin, h - margin)
                p.drawLine(w - margin, h - margin - arm, w - margin, h - margin)

        active_corner = self.grip_corner if (self.show_grip or self.hover_grip) else None
        for corner in ("top_left", "top_right", "bottom_left", "bottom_right"):
            _draw_corner(corner, strong=(corner == active_corner))
        p.end()


# ---------------------------------------------------------------------------
# Base overlay widget
# ---------------------------------------------------------------------------


class _BaseOverlayWidget(QWidget):
    """Common base for all overlay widgets.

    Subclasses must implement:
        _settings_prefix() -> str (e.g. "overlay_clock")
        _default_font_size() -> int
        _build_face() -> QFrame (the visible face widget)
        _refresh_face() -> None (update face text/state)
        _build_context_menu(menu: QMenu) -> None (add widget-specific items)
        _apply_appearance() -> None (called after any setting change)
    """

    # Subclasses define: _STYLES = [("id", "Label"), ...]  ordered list of available styles
    _STYLES: list[tuple[str, str]] = []
    _STYLE_I18N_PREFIX: str | None = None

    # Subclasses may override these to set widget-specific default colors.
    _DEFAULT_TEXT_RGBA: str = "#fcfdfef0"
    _DEFAULT_BG_RGBA: str = "#d6101418"
    _DEFAULT_BORDER_RGBA: str = "#20ffffff"

    # Subclasses set this to the QSettings key that holds the template string,
    # e.g. "clock_template", "sw_template".  None = no template support.
    _TEMPLATE_KEY: str | None = None

    def __init__(self, owner):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        self.owner = owner
        self._drag_offset: QPoint | None = None
        self._resize_origin_global: QPoint | None = None
        self._resize_origin_size: tuple[int, int] = (0, 0)
        self._resize_origin_content_size: tuple[int, int] = (0, 0)
        self._resize_chrome_size: tuple[int, int] = (0, 0)
        self._resize_origin_pos: QPoint | None = None
        self._resize_origin_font: int = self._default_font_size()
        self._resize_corner: str | None = None
        self._resizing: bool = False
        self._interaction_locked: bool = False
        self._measuring: bool = False
        self._last_fit_size: tuple[int, int] = (0, 0)
        self._last_live_scale_apply_at: float = 0.0
        self._last_live_fit_at: float = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.face = self._build_face()
        outer.addWidget(self.face)

        self.face.installEventFilter(self)
        for child in self.face.findChildren(QWidget):
            child.installEventFilter(self)

    # -- abstract-ish interface --

    def _settings_prefix(self) -> str:
        raise NotImplementedError

    def _default_font_size(self) -> int:
        return 32

    def _build_face(self) -> QFrame:
        raise NotImplementedError

    def _refresh_face(self):
        pass

    def _build_context_menu(self, menu: QMenu):
        pass

    def _apply_appearance(self):
        raise NotImplementedError

    def _apply_base_appearance(self) -> dict:
        """Apply common styling (background, border, margins) to the face.

        Returns:
            sp (dict): The resolved style-params for this widget and style.
        """
        style = self.display_style()
        bg_rgb, bg_a = _parse_rgba(self.bg_color_rgba())
        bd_rgb, bd_a = _parse_rgba(self.border_color_rgba())
        fg_rgb, fg_a = _parse_rgba(self.text_color_rgba())

        # Determine kind (e.g. "clock" from "overlay_clock")
        kind = self._settings_prefix().replace("overlay_", "")
        sp = _style_params_for(kind, style)

        # Ensure face has an object name for stylesheet scoping
        obj_name = self.face.objectName() or f"{kind}Face"
        if not self.face.objectName():
            self.face.setObjectName(obj_name)

        face_ss = _build_face_ss(obj_name, sp, bg_rgb, bg_a, bd_rgb, bd_a, fg_rgb, fg_a)
        self.face.setStyleSheet(face_ss)

        # Apply window opacity
        self.setWindowOpacity(self.widget_opacity())

        # Apply margins from style params
        margins = sp.get("margins", [18, 10, 18, 10])
        if self.face.layout():
            self.face.layout().setContentsMargins(*margins)

        # Update dependent visual states
        self._update_grip_color()
        self._update_interaction_surface()

        return sp

    # -- settings helpers --

    def _s(self):
        return self.owner.settings

    def _pref(self):
        return self._settings_prefix()

    def _get(self, key, default=None, type_=None):
        full = f"{self._pref()}_{key}"
        if type_ is not None:
            return self._s().value(full, default, type=type_)
        return self._s().value(full, default)

    def _set(self, key, val):
        self._s().setValue(f"{self._pref()}_{key}", val)

    def _screen_bounds(self) -> tuple[int, int]:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return 1600, 900
        rect = screen.availableGeometry()
        return max(320, rect.width()), max(240, rect.height())

    def _normalized_fixed_dimension(self, key: str) -> int | None:
        raw = self._get(key, None)
        if raw in (None, "", "None"):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            self._set(key, None)
            return None
        screen_w, screen_h = self._screen_bounds()
        max_value = int(screen_w * 0.9) if key.endswith("_w") else int(screen_h * 0.85)
        if value < 40:
            value = 40
        if value > max_value:
            value = max_value
        self._set(key, value)
        return value

    def font_size(self) -> int:
        raw = self._get("font_size", self._default_font_size(), type_=int)
        clamped = max(6, min(500, int(raw or self._default_font_size())))
        if clamped != raw:
            self._set("font_size", clamped)
        return clamped

    # Ordered fallback list: first available font wins.
    # CJK-aware: Malgun Gothic / Noto Sans CJK before Western monospace fallbacks.
    _FONT_FALLBACKS = [
        "Malgun Gothic",  # Windows 한글
        "Noto Sans CJK KR",  # Linux/Android 한글
        "Apple SD Gothic Neo",  # macOS 한글
        "Consolas",
        "Courier New",
        "Courier",
        "Lucida Console",
        "monospace",
    ]

    def font_family(self) -> str:
        raw = str(self._get("font_family", "") or "")
        if raw and raw in QFontDatabase.families():
            return raw
        # Stored font unavailable ??pick the first available fallback.
        available = QFontDatabase.families()
        for name in self._FONT_FALLBACKS:
            if name in available:
                return name
        return "monospace"

    def text_color_rgba(self) -> str:
        d = self._DEFAULT_TEXT_RGBA
        return str(self._get("text_color_rgba", d) or d)

    def bg_color_rgba(self) -> str:
        d = self._DEFAULT_BG_RGBA
        return str(self._get("bg_color_rgba", d) or d)

    def border_color_rgba(self) -> str:
        d = self._DEFAULT_BORDER_RGBA
        return str(self._get("border_color_rgba", d) or d)

    def widget_opacity(self) -> float:
        """Return the window opacity (0.0 to 1.0). Default is 1.0."""
        val = self._get("widget_opacity", 100, type_=int)
        return max(0.1, min(1.0, val / 100.0))

    def _update_grip_color(self):
        text_c, text_a = _parse_rgba(self.text_color_rgba(), fallback_alpha=255)
        bg_c, bg_a = _parse_rgba(self.bg_color_rgba(), fallback_alpha=214)
        border_c, border_a = _parse_rgba(self.border_color_rgba(), fallback_alpha=32)

        weighted = [
            (text_c, max(0, text_a)),
            (border_c, max(0, border_a)),
            (bg_c, max(0, bg_a)),
        ]
        weighted.sort(key=lambda item: item[1], reverse=True)
        base_color, base_alpha = weighted[0]

        if base_alpha <= 8:
            base_color = QColor(text_c if text_a > 0 else QColor("#5aa9ff"))

        comp = QColor(255 - base_color.red(), 255 - base_color.green(), 255 - base_color.blue())
        hue = comp.hue()
        sat = max(comp.saturation(), 170)
        val = max(comp.value(), 210)
        if hue < 0:
            comp = QColor("#7fd6ff")
        else:
            comp.setHsv(hue, sat, val)

        self.face.setProperty("_grip_color", comp)
        self.face.update()

    def _update_interaction_surface(self):
        bg_c, bg_a = _parse_rgba(self.bg_color_rgba(), fallback_alpha=214)
        border_c, border_a = _parse_rgba(self.border_color_rgba(), fallback_alpha=32)
        text_c, text_a = _parse_rgba(self.text_color_rgba(), fallback_alpha=255)

        if bg_a <= 0 and border_a <= 0:
            base = QColor(text_c if text_a > 0 else border_c if border_a > 0 else bg_c)
            if not base.isValid():
                base = QColor("#7fd6ff")
            fill = QColor(base)
            fill.setAlpha(1)
            self.face.setProperty("_interaction_fill_color", fill)
        else:
            self.face.setProperty("_interaction_fill_color", QColor(0, 0, 0, 0))
        self.face.update()

    def _set_template_label(self, html: str, base_size: int | None = None) -> None:
        """Render *html* into _template_label with the widget's current fg color/font.

        Wraps the fragment in a <div> that sets color, font-family, and center-align,
        then shows _template_label.  Subclasses must have self._template_label defined.

        ``base_size`` is the widget's current font_size (pt).  When provided, any
        ``{var|size=N}`` hints in the template are scaled proportionally so that the
        text grows/shrinks together with the widget when resized.

        Global line-height
        ------------------
        The HTML fragment may contain a ``<lh N>`` marker (inserted by
        ``_extract_global_lh``) which is stripped from the content and applied
        as ``line-height`` on the outer ``<div>`` instead.  This is the only
        reliable way to control inter-line spacing in QLabel rich text.
        """
        if base_size is None:
            base_size = self.font_size()
        html, lh_css = _extract_global_lh(html, base_size)
        scaled_html = _scale_template_html(html, base_size)
        scaled_html = self._resolve_template_color_aliases(scaled_html)
        fg_c, fg_a = _parse_rgba(self.text_color_rgba())
        fg_css = _rgba_css(fg_c, fg_a)
        lh_part = f"line-height:{lh_css};" if lh_css else ""
        self._template_label.setText(
            f"<div style=\"color:{fg_css};font-family:'{self.font_family()}';"
            f'text-align:center;{lh_part}">'
            f"{scaled_html}</div>"
        )
        self._template_label.setVisible(True)

    def _create_settings_dialog(
        self,
        title: str,
        min_width: int,
        min_height: int,
        subtitle: str = "",
    ) -> tuple[QDialog, QVBoxLayout]:
        dlg = QDialog(self)
        apply_dialog_title(dlg, title)
        dlg.setMinimumWidth(min_width)
        dlg.setMinimumHeight(min_height)
        dlg.setModal(True)
        dlg.raise_()
        dlg.activateWindow()
        dlg.setStyleSheet(_fresh_dlg_ss())

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        if subtitle:
            hero = QFrame(dlg)
            hero.setObjectName("settingsHero")
            hero_lay = QVBoxLayout(hero)
            hero_lay.setContentsMargins(14, 10, 14, 10)
            hero_lay.setSpacing(3)

            title_lbl = QLabel(title, hero)
            title_lbl.setObjectName("settingsHeroTitle")
            body_lbl = QLabel(subtitle, hero)
            body_lbl.setObjectName("settingsHeroBody")
            body_lbl.setWordWrap(True)

            hero_lay.addWidget(title_lbl)
            hero_lay.addWidget(body_lbl)
            outer.addWidget(hero)

        return dlg, outer

    def _create_tabbed_settings_dialog(
        self,
        title: str,
        min_width: int = 640,
        min_height: int = 560,
    ):
        """Create a tabbed settings dialog.

        Returns (dlg, outer_layout, tab_widget).
        Callers add tab pages via tab_widget.addTab(widget, label).
        """
        from PyQt6.QtWidgets import QTabWidget as _QTabWidget

        dlg = QDialog(self)
        apply_dialog_title(dlg, title)
        dlg.setMinimumWidth(min_width)
        dlg.setMinimumHeight(min_height)
        dlg.setModal(True)
        dlg.raise_()
        dlg.activateWindow()
        dlg.setStyleSheet(_fresh_dlg_ss())

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        tabs = _QTabWidget(dlg)
        outer.addWidget(tabs, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dlg,
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        outer.addWidget(btns)

        return dlg, outer, tabs

    def _make_scroll_tab(self, tabs=None):  # noqa: ARG002
        """Create a scrollable tab page widget.  Returns (page_widget, inner_layout)."""
        from PyQt6.QtWidgets import QScrollArea as _QScrollArea

        page = QWidget()
        scroll = _QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QVBoxLayout(page)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(10)
        return scroll, inner

    def _add_section_label(self, layout, text: str):
        """Add a small uppercase section separator label to a layout."""
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        layout.addWidget(lbl)

    def _add_divider(self, layout):
        """Add a thin horizontal divider line to a layout."""
        div = QFrame()
        div.setObjectName("divider")
        div.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(div)

    def _make_hint_box(self, parent, text: str, editor=None) -> QFrame:
        """Return a styled hint/info box widget.

        If *editor* (a QPlainTextEdit) is provided, any ``{...}`` tokens in
        *text* are rendered as clickable links that insert the token at the
        editor's current cursor position when clicked.
        """
        import re as _re_hint

        box = QFrame(parent)
        box.setObjectName("hintBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)

        if editor is not None:
            # Convert {token} patterns to <a href="token"> links
            def _to_link(m: _re_hint.Match) -> str:
                raw = m.group(0)  # e.g. {time:%H:%M}
                # URL-encode minimally: replace % and : so href stays clean
                encoded = raw.replace("%", "%25").replace("&", "%26")
                return f'<a href="{encoded}" style="{_overlay_hint_link_style()}">{raw}</a>'

            html_text = (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            # Re-linkify {tokens} ??they survived escaping since they have no < >
            html_text = _re_hint.sub(r"\{[^}]+\}", _to_link, html_text)

            lbl = QLabel(html_text, box)
            lbl.setObjectName("hintText")
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setOpenExternalLinks(False)

            def _on_link(href: str) -> None:
                # Decode the token back
                token = href.replace("%25", "%").replace("%26", "&")
                cursor = editor.textCursor()
                cursor.insertText(token)
                editor.setFocus()

            lbl.linkActivated.connect(_on_link)
        else:
            lbl = QLabel(text, box)
            lbl.setObjectName("hintText")
            lbl.setWordWrap(True)

        lay.addWidget(lbl)
        return box

    def _make_collapsible_hint(self, parent, text: str, settings_key: str = "") -> QWidget:
        """Return a collapsible hint section widget.

        State (open/closed) is persisted in QSettings under *settings_key* if provided.
        Defaults to collapsed so it doesn't crowd the layout on first open.
        """
        container = QWidget(parent)
        container.setObjectName("collapsibleHint")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Toggle button (header row)
        toggle_btn = QToolButton(container)
        toggle_btn.setCheckable(True)
        toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toggle_btn.setStyleSheet(_overlay_hint_toggle_style())

        # Content frame (the hint box)
        content = self._make_hint_box(container, text)

        # Restore persisted state (default: collapsed)
        initial_open = False
        if settings_key:
            initial_open = (
                str(self._s().value(settings_key + "_hint_open", "false")).lower() == "true"
            )

        def _set_open(open_: bool):
            toggle_btn.setChecked(open_)
            toggle_btn.setText(
                f"Hint {t('widget.common.hint_label', 'Help')}  {'v' if open_ else '>'}"
            )
            content.setVisible(open_)
            if settings_key:
                self._s().setValue(settings_key + "_hint_open", "true" if open_ else "false")

        toggle_btn.clicked.connect(lambda checked: _set_open(checked))
        _set_open(initial_open)

        vlay.addWidget(toggle_btn)
        vlay.addWidget(content)
        return container

    def _build_preset_row(
        self, parent, editor: QPlainTextEdit, built_in_presets: list[tuple[str, str]]
    ) -> dict:
        """Build a compact single-row preset selector (ComboBox + action buttons).

        Returns a dict with keys: layout, combo, refresh.
        """
        built_in_presets, built_in_names = _preset_logic.normalize_built_in_presets(
            built_in_presets
        )

        combo = QComboBox(parent)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setToolTip(t("widget.preset.select_hint", "Select a preset"))

        apply_btn = QPushButton(t("widget.preset.apply", "Apply"), parent)
        save_btn = QPushButton(t("widget.preset.add", "Add"), parent)
        update_btn = QPushButton(t("widget.preset.update", "Update"), parent)
        delete_btn = QPushButton(t("widget.preset.delete", "Delete"), parent)

        for btn in (apply_btn, save_btn, update_btn, delete_btn):
            btn.setObjectName("presetBtn")
            btn.setFixedHeight(26)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(combo, 1)
        row.addWidget(apply_btn)
        row.addWidget(save_btn)
        row.addWidget(update_btn)
        row.addWidget(delete_btn)

        # --- Data helpers ---
        _KIND_USER = "user"

        def _current_kind() -> str:
            return combo.currentData(Qt.ItemDataRole.UserRole + 1) or ""

        def _current_template() -> str:
            return combo.currentData(Qt.ItemDataRole.UserRole) or ""

        def _current_name() -> str:
            return str(combo.currentData(Qt.ItemDataRole.UserRole + 2) or "").strip()

        def _sync_buttons():
            states = _preset_logic.row_button_states(
                current_kind=_current_kind(),
                item_count=combo.count(),
            )
            apply_btn.setEnabled(states["apply"])
            update_btn.setEnabled(states["update"])
            delete_btn.setEnabled(states["delete"])

        def refresh_combo(select_name: str | None = None, select_kind: str | None = None):
            combo.blockSignals(True)
            combo.clear()
            entries = _preset_logic.build_row_entries(
                built_in_presets,
                self._load_user_presets(),
            )
            _preset_ui.append_row_entries(
                combo,
                entries,
                builtin_label=t("widget.preset.kind_builtin", "Built-in"),
                user_label=t("widget.preset.kind_user", "User"),
            )

            # Restore selection
            target_idx = _preset_logic.find_selection_index(
                entries,
                select_name,
                select_kind,
                start_index=0,
                default_index=0,
            )
            combo.setCurrentIndex(target_idx)
            combo.blockSignals(False)
            _sync_buttons()

        def apply_preset():
            tmpl = _current_template()
            editor.setPlainText(tmpl)

        def save_preset():
            name = self._try_create_row_user_preset(
                parent,
                editor.toPlainText(),
                built_in_names,
            )
            if name:
                refresh_combo(name, _KIND_USER)

        def update_preset():
            if _current_kind() != _KIND_USER:
                return
            name = _current_name()
            if self._try_update_user_preset(parent, name, editor.toPlainText()):
                refresh_combo(name, _KIND_USER)

        def delete_preset():
            if _current_kind() != _KIND_USER:
                return
            if self._try_delete_row_user_preset(parent, _current_name()):
                refresh_combo()

        combo.currentIndexChanged.connect(lambda _: _sync_buttons())
        apply_btn.clicked.connect(apply_preset)
        save_btn.clicked.connect(save_preset)
        update_btn.clicked.connect(update_preset)
        delete_btn.clicked.connect(delete_preset)

        refresh_combo()
        return {"layout": row, "combo": combo, "refresh": refresh_combo}

    def _make_preview_card(self, parent) -> QLabel:
        """Return a styled preview label (RichText, centered)."""
        lbl = QLabel(parent)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setObjectName("previewCard")
        lbl.setStyleSheet(_overlay_preview_card_inline_style())
        lbl.setMinimumHeight(100)
        return lbl

    def _user_presets_key(self) -> str:
        return _preset_store._user_presets_key(self._pref())

    def _hidden_builtins_key(self) -> str:
        return _preset_store._hidden_builtins_key(self._pref())

    def _load_user_presets(self) -> list[dict[str, str]]:
        return _preset_store.load_user_presets(self._s(), self._pref())

    def _save_user_presets(self, presets: list[dict[str, str]]) -> None:
        _preset_store.save_user_presets(self._s(), self._pref(), presets)

    def _load_hidden_builtins(self) -> set[str]:
        return _preset_store.load_hidden_builtins(self._s(), self._pref())

    def _save_hidden_builtins(self, hidden: set[str]) -> None:
        _preset_store.save_hidden_builtins(self._s(), self._pref(), hidden)

    def _warn_preset(self, parent, message_key: str, fallback: str, **kwargs) -> None:
        _preset_ui.warn_preset(parent, message_key, fallback, **kwargs)

    def _warn_preset_name_exists(self, parent) -> None:
        _preset_ui.warn_preset_name_exists(parent)

    def _warn_preset_name_builtin(self, parent) -> None:
        _preset_ui.warn_preset_name_builtin(parent)

    def _prompt_preset_name(self, parent, *, initial: str = "") -> str | None:
        return _preset_ui.prompt_preset_name(parent, initial=initial)

    def _try_upsert_user_preset_entry(
        self,
        parent,
        name: str,
        template: str,
        *,
        allow_overwrite: bool,
    ) -> bool:
        saved = self._upsert_user_preset_entry(
            name,
            template,
            allow_overwrite=allow_overwrite,
        )
        if not saved:
            self._warn_preset_name_exists(parent)
            return False
        return True

    def _has_preset_name_conflict(self, name: str, built_in_names: set[str]) -> bool:
        return _preset_service.has_name_conflict(self._s(), self._pref(), name, built_in_names)

    def _require_non_empty_preset_template(self, parent, template_text: str) -> str | None:
        return _preset_ui.require_non_empty_template(parent, template_text)

    def _prompt_new_preset_payload(self, parent, editor_text: str) -> tuple[str, str] | None:
        return _preset_ui.prompt_new_preset_payload(parent, editor_text)

    def _try_create_row_user_preset(
        self,
        parent,
        editor_text: str,
        built_in_names: set[str],
    ) -> str | None:
        payload = self._prompt_new_preset_payload(parent, editor_text)
        if payload is None:
            return None
        name, template = payload
        if name in built_in_names:
            self._warn_preset_name_builtin(parent)
            return None
        if not self._try_upsert_user_preset_entry(
            parent,
            name,
            template,
            allow_overwrite=False,
        ):
            return None
        return name

    def _try_create_manager_user_preset(
        self,
        parent,
        editor_text: str,
        built_in_names: set[str],
    ) -> str | None:
        payload = self._prompt_new_preset_payload(parent, editor_text)
        if payload is None:
            return None
        name, template = payload
        if self._has_preset_name_conflict(name, built_in_names):
            self._warn_preset_name_exists(parent)
            return None
        if not self._try_upsert_user_preset_entry(
            parent,
            name,
            template,
            allow_overwrite=False,
        ):
            return None
        return name

    def _try_update_user_preset(self, parent, name: str, editor_text: str) -> bool:
        if not name:
            return False
        return self._try_upsert_user_preset_entry(
            parent,
            name,
            editor_text,
            allow_overwrite=True,
        )

    def _try_delete_row_user_preset(self, parent, name: str) -> bool:
        if not name:
            return False
        if not self._confirm_delete_preset(parent, name):
            return False
        self._remove_user_preset_entry(name)
        return True

    def _try_rename_manager_preset(
        self,
        parent,
        *,
        old_name: str,
        built_in_names: set[str],
        fallback_template: str,
    ) -> str | None:
        if not old_name:
            return None
        new_name = self._prompt_preset_name(parent, initial=old_name)
        if not new_name or new_name == old_name:
            return None
        if self._has_preset_name_conflict(new_name, built_in_names):
            self._warn_preset_name_exists(parent)
            return None
        self._apply_rename_preset_policy(
            old_name=old_name,
            new_name=new_name,
            built_in_names=built_in_names,
            fallback_template=fallback_template,
        )
        return new_name

    def _try_delete_manager_preset(
        self,
        parent,
        *,
        name: str,
        kind: str,
        built_in_names: set[str],
    ) -> bool:
        if not name:
            return False
        if not self._confirm_delete_preset(parent, name):
            return False
        self._apply_delete_preset_policy(
            name=name,
            kind=kind,
            built_in_names=built_in_names,
        )
        return True

    def _confirm_delete_preset(self, parent, name: str) -> bool:
        return _preset_ui.confirm_delete_preset(parent, name)

    def _upsert_user_preset_entry(
        self,
        name: str,
        template: str,
        *,
        allow_overwrite: bool,
    ) -> bool:
        return _preset_service.upsert_user_preset_entry(
            self._s(),
            self._pref(),
            name,
            template,
            allow_overwrite=allow_overwrite,
        )

    def _remove_user_preset_entry(self, name: str) -> None:
        _preset_service.remove_user_preset_entry(self._s(), self._pref(), name)

    def _apply_rename_preset_policy(
        self,
        *,
        old_name: str,
        new_name: str,
        built_in_names: set[str],
        fallback_template: str,
    ) -> None:
        _preset_service.apply_rename_preset_policy(
            self._s(),
            self._pref(),
            old_name=old_name,
            new_name=new_name,
            built_in_names=built_in_names,
            fallback_template=fallback_template,
        )

    def _apply_delete_preset_policy(
        self,
        *,
        name: str,
        kind: str,
        built_in_names: set[str],
    ) -> None:
        _preset_service.apply_delete_preset_policy(
            self._s(),
            self._pref(),
            name=name,
            kind=kind,
            built_in_names=built_in_names,
        )

    def _build_preset_manager(
        self, parent, editor, built_in_presets: list[tuple[str, str]]
    ) -> dict:
        wrapper = QVBoxLayout()
        wrapper.setSpacing(8)

        preset_combo = QComboBox(parent)
        preset_combo.setObjectName("presetCombo")
        preset_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        preset_combo.setToolTip(t("widget.preset.select_hint", "Select a preset"))
        preset_combo.setMinimumHeight(34)
        wrapper.addWidget(preset_combo)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        add_btn = QPushButton(t("widget.preset.add", "Save As New"), parent)
        update_btn = QPushButton(t("widget.preset.update", "Update Selected"), parent)
        for btn in (add_btn, update_btn):
            btn.setObjectName("presetBtn")
            btn.setFixedHeight(30)
            top_row.addWidget(btn)
        top_row.addStretch()
        wrapper.addLayout(top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)
        bottom_row.addStretch()
        rename_btn = QPushButton(t("widget.preset.rename", "Rename"), parent)
        delete_btn = QPushButton(t("widget.preset.delete", "Delete"), parent)
        for btn in (rename_btn, delete_btn):
            btn.setObjectName("presetBtn")
            btn.setFixedHeight(28)
            bottom_row.addWidget(btn)
        wrapper.addLayout(bottom_row)

        built_in_presets, built_in_names = _preset_logic.normalize_built_in_presets(
            built_in_presets
        )
        state = {"applying": False}

        def current_index() -> int:
            return preset_combo.currentIndex()

        def current_name() -> str:
            idx = current_index()
            return str(preset_combo.itemData(idx, Qt.ItemDataRole.UserRole + 1) or "").strip()

        def current_template() -> str:
            idx = current_index()
            return str(preset_combo.itemData(idx, Qt.ItemDataRole.UserRole + 2) or "")

        def current_kind() -> str:
            idx = current_index()
            return str(preset_combo.itemData(idx, Qt.ItemDataRole.UserRole + 3) or "")

        def _apply_selected_preset() -> None:
            idx = current_index()
            template = current_template()
            if idx < 0 or not template:
                _sync_buttons()
                return
            state["applying"] = True
            editor.setPlainText(template)
            state["applying"] = False
            _sync_buttons()

        def refresh_combo(
            select_name: str | None = None,
            select_kind: str | None = None,
            *,
            keep_editor: bool = False,
        ):
            existing_template = editor.toPlainText()
            preset_combo.blockSignals(True)
            preset_combo.clear()

            placeholder = t("widget.preset.select_hint", "Select a preset")
            _preset_ui.add_manager_placeholder(preset_combo, placeholder)

            user_preset_rows = self._load_user_presets()
            hidden_builtins = self._load_hidden_builtins()
            entries = _preset_logic.build_effective_entries(
                built_in_presets,
                user_preset_rows,
                hidden_builtins,
            )
            combo_entries = _preset_ui.append_manager_entries(preset_combo, entries)

            target_idx = 0
            if select_name:
                target_idx = _preset_logic.find_selection_index(
                    combo_entries,
                    select_name,
                    select_kind,
                    start_index=1,
                    default_index=0,
                )
            elif keep_editor:
                matched = _preset_ui.find_manager_template_index(preset_combo, existing_template)
                target_idx = matched if matched >= 0 else 0

            preset_combo.setCurrentIndex(target_idx)
            preset_combo.blockSignals(False)
            if keep_editor:
                _sync_buttons()
            else:
                _apply_selected_preset()

        def _sync_buttons():
            has_selection = current_index() > 0 and bool(current_name())
            states = _preset_logic.manager_button_states(
                has_selection=has_selection,
                editor_text=editor.toPlainText(),
                current_template=current_template(),
            )
            add_btn.setEnabled(states["add"])
            update_btn.setEnabled(states["update"])
            rename_btn.setEnabled(states["rename"])
            delete_btn.setEnabled(states["delete"])

        def add_preset():
            name = self._try_create_manager_user_preset(
                parent,
                editor.toPlainText(),
                built_in_names,
            )
            if name:
                refresh_combo(name, "user")

        def update_preset():
            name = current_name()
            if self._try_update_user_preset(parent, name, editor.toPlainText()):
                refresh_combo(name, "user", keep_editor=True)

        def rename_preset():
            new_name = self._try_rename_manager_preset(
                parent,
                old_name=current_name(),
                built_in_names=built_in_names,
                fallback_template=editor.toPlainText(),
            )
            if new_name:
                refresh_combo(new_name, "user", keep_editor=True)

        def delete_preset():
            if self._try_delete_manager_preset(
                parent,
                name=current_name(),
                kind=current_kind(),
                built_in_names=built_in_names,
            ):
                refresh_combo(keep_editor=True)

        preset_combo.currentIndexChanged.connect(lambda *_args: _apply_selected_preset())
        editor.textChanged.connect(lambda: None if state["applying"] else _sync_buttons())
        add_btn.clicked.connect(add_preset)
        update_btn.clicked.connect(update_preset)
        rename_btn.clicked.connect(rename_preset)
        delete_btn.clicked.connect(delete_preset)

        def original_template() -> str | None:
            """Return the *original* (unmodified) template for the selected preset.

            For builtin presets (even if the user has overridden them) this is
            the value from the built_in_presets list passed to this function.
            For pure user-only presets it is the saved user template (same as
            what the combo currently shows).  Returns None when nothing is
            selected (placeholder row).
            """
            name = current_name()
            if not name:
                return None
            # Look up in built_in_presets first ??gives the *original* value even
            # when the user has overridden it.
            for label, tmpl in built_in_presets:
                if label == name:
                    return tmpl
            # Pure user preset ??return whatever is stored.
            return current_template()

        refresh_combo(keep_editor=True)
        return {
            "layout": wrapper,
            "combo": preset_combo,
            "refresh": refresh_combo,
            "sync": _sync_buttons,
            "original_template": original_template,
        }

    def _make_labeled_row(self, label_text, field):
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setObjectName("fieldLabel")
        row.addWidget(lbl)
        row.addWidget(field, 1)
        return row

    def _make_rgba_color_button(self, initial_rgba: str):
        """Return a QPushButton that opens an RGBA color picker."""
        btn = QPushButton()
        btn.setObjectName("colorBtn")
        btn.setFixedSize(80, 24)

        def _update(rgba: str):
            btn.setProperty("_rgba", rgba)
            btn.setStyleSheet(_overlay_color_button_style(rgba))

        def _pick():
            cur = str(btn.property("_rgba"))
            new_rgba = _pick_rgba_color(self, t("widget.color.pick", "색상 선택"), cur)
            if new_rgba:
                _update(new_rgba)

        _update(initial_rgba)
        btn.clicked.connect(_pick)
        return btn

    def _make_font_combo(self, initial_family: str):
        """Return a QFontComboBox initialized with the current family."""
        combo = QFontComboBox()
        combo.setCurrentFont(QFont(initial_family))
        return combo

    def _make_font_size_spin(self, initial_size: int):
        """Return a QSpinBox for font size."""
        spin = QSpinBox()
        spin.setRange(6, 500)
        spin.setValue(initial_size)
        spin.setSuffix(" pt")
        return spin

    def _build_field_widget(self, f: dict) -> QWidget:
        """Helper to create a widget based on field definition."""
        ftype = f.get("type", "text")
        key = f.get("key")
        val = self._get(key, f.get("default"))

        if ftype == "text":
            w = QLineEdit(str(val))
            if "placeholder" in f:
                w.setPlaceholderText(f["placeholder"])
            return w
        elif ftype == "combo":
            w = QComboBox()
            for label, data in f.get("options", []):
                w.addItem(label, data)
            idx = w.findData(val)
            if idx >= 0:
                w.setCurrentIndex(idx)
            return w
        elif ftype == "int_combo":
            w = QComboBox()
            for v in f.get("options", []):
                w.addItem(str(v), v)
            idx = w.findData(val)
            if idx >= 0:
                w.setCurrentIndex(idx)
            return w
        elif ftype == "bool":
            w = QCheckBox()
            w.setChecked(bool(val))
            return w
        elif ftype == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            # Use a slightly larger font for better visibility
            font = w.font()
            font.setPointSize(10)
            w.setFont(font)
            dv = QDate.fromString(str(val), "yyyy-MM-dd")
            w.setDate(dv if dv.isValid() else QDate.currentDate())
            return w
        elif ftype == "time":
            w = QTimeEdit()
            font = w.font()
            font.setPointSize(10)
            w.setFont(font)
            tv = QTime.fromString(str(val), "HH:mm")
            w.setTime(tv if tv.isValid() else QTime.currentTime())
            return w
        return QWidget()

    def _get_field_value(self, w: QWidget):
        """Helper to extract value from a field widget."""
        if isinstance(w, QLineEdit):
            return w.text().strip()
        elif isinstance(w, QComboBox):
            return w.currentData()
        elif isinstance(w, QCheckBox):
            return w.isChecked()
        elif isinstance(w, QDateEdit):
            return w.date().toString("yyyy-MM-dd")
        elif isinstance(w, QTimeEdit):
            return w.time().toString("HH:mm")
        return None

    def _open_standard_settings_dialog(
        self,
        title: str,
        extra_fields: list[dict] = None,
        has_template: bool = False,
        default_template: str = "",
        template_hint: str = "",
        preview_render_fn=None,
        quick_insert_groups: list[tuple[str, list[tuple[str, str]]]] = None,
        min_width: int = 700,
        min_height: int = 560,
        extra_basic_setup_fn: callable = None,
    ):
        """Generic settings dialog with Style, Appearance, and optional Advanced tabs."""
        dlg, outer, tabs = self._create_tabbed_settings_dialog(title, min_width, min_height)

        # -- Page 1: Basic --
        basic_scroll, basic = self._make_scroll_tab()
        tabs.addTab(basic_scroll, t("widget.common.tab_basic", "Basic"))

        self._add_section_label(basic, t("widget.common.section_display", "Display"))
        style_combo = self._make_style_combo()
        basic.addLayout(
            self._make_labeled_row(t("widget.common.style", "Display style:"), style_combo)
        )

        self._active_settings_widgets = {}
        for f in extra_fields or []:
            w = self._build_field_widget(f)
            self._active_settings_widgets[f["key"]] = w
            basic.addLayout(self._make_labeled_row(f["label"], w))

        if extra_basic_setup_fn:
            extra_basic_setup_fn(basic, dlg)

        basic.addStretch()

        # -- Page 2: Appearance --
        appear_scroll, appear = self._make_scroll_tab()
        tabs.addTab(appear_scroll, t("widget.common.tab_appearance", "Appearance"))

        self._add_section_label(appear, t("widget.common.section_colors", "Colors"))
        bg_btn = self._make_rgba_color_button(self.bg_color_rgba())
        appear.addLayout(self._make_labeled_row(t("widget.common.bg_color", "Background:"), bg_btn))
        bd_btn = self._make_rgba_color_button(self.border_color_rgba())
        appear.addLayout(self._make_labeled_row(t("widget.common.border_color", "Border:"), bd_btn))
        fg_btn = self._make_rgba_color_button(self.text_color_rgba())
        appear.addLayout(self._make_labeled_row(t("widget.common.text_color", "Text:"), fg_btn))

        self._add_divider(appear)
        self._add_section_label(appear, t("widget.common.section_transparency", "TRANSPARENCY"))

        # ── 배경 불투명도 ──
        _, _cur_bg_alpha = _parse_rgba(self.bg_color_rgba(), fallback_alpha=214)
        _bg_pct = int(round(_cur_bg_alpha * 100 / 255))
        bg_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        bg_alpha_slider.setRange(0, 100)
        bg_alpha_slider.setValue(_bg_pct)
        bg_alpha_val_lbl = QLabel(f"{_bg_pct}%")
        bg_alpha_val_lbl.setMinimumWidth(35)
        bg_alpha_slider.valueChanged.connect(lambda v: bg_alpha_val_lbl.setText(f"{v}%"))
        _bg_row = self._make_labeled_row(t("widget.common.bg_opacity", "배경:"), bg_alpha_slider)
        _bg_row.addWidget(bg_alpha_val_lbl)
        appear.addLayout(_bg_row)

        # ── 테두리 불투명도 ──
        _, _cur_bd_alpha = _parse_rgba(self.border_color_rgba(), fallback_alpha=32)
        _bd_pct = int(round(_cur_bd_alpha * 100 / 255))
        bd_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        bd_alpha_slider.setRange(0, 100)
        bd_alpha_slider.setValue(_bd_pct)
        bd_alpha_val_lbl = QLabel(f"{_bd_pct}%")
        bd_alpha_val_lbl.setMinimumWidth(35)
        bd_alpha_slider.valueChanged.connect(lambda v: bd_alpha_val_lbl.setText(f"{v}%"))
        _bd_row = self._make_labeled_row(
            t("widget.common.border_opacity", "테두리:"), bd_alpha_slider
        )
        _bd_row.addWidget(bd_alpha_val_lbl)
        appear.addLayout(_bd_row)

        # ── 글씨 불투명도 ──
        _, _cur_txt_alpha = _parse_rgba(self.text_color_rgba(), fallback_alpha=255)
        _txt_pct = int(round(_cur_txt_alpha * 100 / 255))
        txt_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        txt_alpha_slider.setRange(0, 100)
        txt_alpha_slider.setValue(_txt_pct)
        txt_alpha_val_lbl = QLabel(f"{_txt_pct}%")
        txt_alpha_val_lbl.setMinimumWidth(35)
        txt_alpha_slider.valueChanged.connect(lambda v: txt_alpha_val_lbl.setText(f"{v}%"))
        _txt_row = self._make_labeled_row(
            t("widget.common.text_opacity", "글씨:"), txt_alpha_slider
        )
        _txt_row.addWidget(txt_alpha_val_lbl)
        appear.addLayout(_txt_row)

        # (Overall window opacity — hidden from main tab; kept for context-menu compat)
        opacity_slider = QSlider(Qt.Orientation.Horizontal)
        opacity_slider.setRange(10, 100)
        opacity_slider.setValue(int(self.widget_opacity() * 100))
        opacity_slider.setVisible(False)  # not shown; value preserved on accept

        self._add_divider(appear)
        self._add_section_label(appear, t("widget.common.section_font", "FONT"))
        font_combo = self._make_font_combo(self.font_family())
        appear.addLayout(
            self._make_labeled_row(t("widget.common.font_family", "Family:"), font_combo)
        )
        size_spin = self._make_font_size_spin(self.font_size())
        appear.addLayout(self._make_labeled_row(t("widget.common.font_size", "Size:"), size_spin))
        appear.addStretch()

        # -- Page 3: Advanced (Template) --
        template_editor = None
        if has_template:
            template_result = self._build_advanced_template_tab(
                tabs,
                dlg,
                current_template=self._get(self._TEMPLATE_KEY or "template", default_template),
                default_template=default_template,
                presets=_get_widget_presets(
                    self._settings_prefix().replace("overlay_", ""), t, default_template
                ),
                placeholder=default_template,
                hint_text=template_hint,
                render_preview=preview_render_fn,
                quick_insert_groups=quick_insert_groups,
                refresh_signals=[
                    style_combo.currentIndexChanged,
                    fg_btn.clicked,
                    bg_btn.clicked,
                    *[
                        w.currentIndexChanged
                        for w in self._active_settings_widgets.values()
                        if hasattr(w, "currentIndexChanged")
                    ],
                    *[
                        w.textChanged
                        for w in self._active_settings_widgets.values()
                        if hasattr(w, "textChanged")
                    ],
                    *[
                        w.stateChanged
                        for w in self._active_settings_widgets.values()
                        if hasattr(w, "stateChanged")
                    ],
                    *[
                        w.dateChanged
                        for w in self._active_settings_widgets.values()
                        if hasattr(w, "dateChanged")
                    ],
                    *[
                        w.timeChanged
                        for w in self._active_settings_widgets.values()
                        if hasattr(w, "timeChanged")
                    ],
                ],
            )
            template_editor = template_result["editor"]

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Commit Style
            self._set("display_style", style_combo.currentData())

            # Commit Appearance — merge alpha sliders into rgba values
            def _merge_alpha(rgba_str: str, new_alpha: int, fallback_alpha: int) -> str:
                c, _ = _parse_rgba(rgba_str, fallback_alpha=fallback_alpha)
                return _to_rgba_str(c, new_alpha)

            self._set(
                "bg_color_rgba",
                _merge_alpha(
                    str(bg_btn.property("_rgba")),
                    int(round(bg_alpha_slider.value() * 255 / 100)),
                    214,
                ),
            )
            self._set(
                "border_color_rgba",
                _merge_alpha(
                    str(bd_btn.property("_rgba")),
                    int(round(bd_alpha_slider.value() * 255 / 100)),
                    32,
                ),
            )
            self._set(
                "text_color_rgba",
                _merge_alpha(
                    str(fg_btn.property("_rgba")),
                    int(round(txt_alpha_slider.value() * 255 / 100)),
                    255,
                ),
            )
            self._set("font_family", font_combo.currentFont().family())
            self._set("font_size", size_spin.value())
            self._set("widget_opacity", opacity_slider.value())

            # Commit extra fields
            for key, w in self._active_settings_widgets.items():
                self._set(key, self._get_field_value(w))

            # Commit Template
            if template_editor:
                self._set(self._TEMPLATE_KEY or "template", template_editor.toPlainText().strip())

            # Apply
            self._apply_and_resize(refit=True)
            self._refresh_face()
            return True
        return False

    def _style_items(self) -> list[tuple[str, str]]:
        if not self._STYLE_I18N_PREFIX:
            return list(self._STYLES)
        return [
            (style_id, t(f"{self._STYLE_I18N_PREFIX}.style.{style_id}", fallback))
            for style_id, fallback in self._STYLES
        ]

    def _make_style_combo(self, parent=None):
        from PyQt6.QtWidgets import QComboBox as _QComboBox

        combo = _QComboBox(parent)
        current = self.display_style()
        selected_index = 0
        for index, (style_id, style_label) in enumerate(self._style_items()):
            combo.addItem(style_label, style_id)
            if style_id == current:
                selected_index = index
        combo.setCurrentIndex(selected_index)
        return combo

    def _wrap_preview_html(
        self, html: str, align: str = "center", preview_size: QSize | None = None
    ) -> str:
        preview_pt = _preview_base_size(preview_size or QSize(320, 240))
        scaled = _scale_template_html(html, preview_pt)
        scaled = self._resolve_template_color_aliases(scaled)
        fg_c, fg_a = _parse_rgba(self.text_color_rgba())
        fg_css = _rgba_css(fg_c, fg_a)
        return (
            f"<div style=\"color:{fg_css};font-family:'{self.font_family()}';"
            f"font-size:{preview_pt}pt;text-align:{align};"
            f'max-width:100%;max-height:100%;overflow:hidden;">{scaled}</div>'
        )

    def _template_color_alias_map(self) -> dict[str, str]:
        tokens = dict(get_ui_tokens(settings=self._s()))
        fg_c, fg_a = _parse_rgba(self.text_color_rgba(), fallback_alpha=255)
        current_text = _rgba_css(fg_c, fg_a)
        text_primary = str(tokens.get("text_primary", current_text))
        text_secondary = str(tokens.get("text_secondary", text_primary))
        text_muted = str(tokens.get("text_muted", text_secondary))
        return {
            "text": current_text,
            "primary": current_text,
            "secondary": text_secondary,
            "muted": text_muted,
            "faint": str(tokens.get("text_faint", text_muted)),
            "accent": str(tokens.get("accent", text_primary)),
            "info": str(tokens.get("info_hex", tokens.get("accent", text_primary))),
            "warning": str(tokens.get("warning_hex", text_primary)),
            "success": str(tokens.get("success_hex", text_primary)),
            "danger": str(tokens.get("danger_hex", text_primary)),
        }

    def _resolve_template_color_aliases(self, html: str) -> str:
        alias_map = self._template_color_alias_map()

        def _replace(match: _re.Match) -> str:
            alias = match.group(1).lower()
            resolved = alias_map.get(alias)
            return f"color:{resolved}" if resolved else match.group(0)

        return _TEMPLATE_COLOR_ALIAS_RE.sub(_replace, html)

    def _compose_template_grammar_hint(self, hint_text: str) -> str:
        common_hint = "\n".join(
            [
                t("widget.common.grammar_intro", "Grammar"),
                t("widget.common.grammar_token", _GRAMMAR_TOKEN_FALLBACK),
                t("widget.common.grammar_plain_text", _GRAMMAR_PLAIN_FALLBACK),
                t("widget.common.grammar_size", "Size formats: 36 / 1.5x / 150% / +8 / -4 / base"),
                t(
                    "widget.common.grammar_line_height",
                    "Line height: {lh=2.0} / {line=1.4} / {line_height=40pt}",
                ),
                t(
                    "widget.common.grammar_newline",
                    "New line: use Enter or \\n inside the template",
                ),
                t(
                    "widget.common.grammar_align",
                    "Line alignment: {align=left} / {align=center} / {align=right}",
                ),
                t(
                    "widget.common.grammar_conditional",
                    "Conditional block: {if task_count > 0}...{else}...{/if}",
                ),
            ]
        )
        specific = str(hint_text or "").strip()
        if not specific:
            return common_hint
        return f"{common_hint}\n\n{specific}"

    def _build_advanced_template_tab(
        self,
        tabs,
        dialog,
        *,
        current_template: str,
        default_template: str,
        presets: list,
        placeholder: str,
        hint_text: str,
        render_preview,
        render_meta=None,
        refresh_signals: list | None = None,
        reset_label: str | None = None,
        clear_label: str | None = None,
        tab_title: str | None = None,
        quick_insert_groups: list | None = None,
    ) -> dict:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QTabWidget

        tab_page = QWidget()
        tab_outer = QVBoxLayout(tab_page)
        tab_outer.setContentsMargins(12, 12, 12, 10)
        tab_outer.setSpacing(8)
        tabs.addTab(tab_page, tab_title or t("widget.common.tab_advanced", "Advanced"))

        self._add_section_label(tab_outer, t("widget.common.section_presets", "PRESETS"))

        editor = QPlainTextEdit(tab_page)
        editor.setPlaceholderText(placeholder)
        editor.setPlainText(current_template)

        preset_manager = self._build_preset_manager(tab_page, editor, presets)
        tab_outer.addLayout(preset_manager["layout"])

        self._add_divider(tab_outer)

        splitter = QSplitter(Qt.Orientation.Horizontal, tab_page)
        splitter.setChildrenCollapsible(False)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        editor_wrap = QWidget(splitter)
        editor_wrap_lay = QVBoxLayout(editor_wrap)
        editor_wrap_lay.setContentsMargins(0, 0, 4, 0)
        editor_wrap_lay.setSpacing(4)
        editor_cap = QLabel(t("widget.common.section_template", "TEMPLATE"), editor_wrap)
        editor_cap.setObjectName("previewCaption")
        editor_wrap_lay.addWidget(editor_cap)
        editor.setParent(editor_wrap)
        editor.setMinimumHeight(320)
        editor_wrap_lay.addWidget(editor, 1)
        splitter.addWidget(editor_wrap)

        preview_wrap = QWidget(splitter)
        preview_wrap_lay = QVBoxLayout(preview_wrap)
        preview_wrap_lay.setContentsMargins(4, 0, 0, 0)
        preview_wrap_lay.setSpacing(4)
        preview_cap = QLabel(t("widget.common.preview_area", "PREVIEW"), preview_wrap)
        preview_cap.setObjectName("previewCaption")
        preview_wrap_lay.addWidget(preview_cap)

        preview_tabs = QTabWidget(preview_wrap)
        preview_tabs.setObjectName("previewTabs")

        preview_page = QWidget(preview_tabs)
        preview_page_lay = QVBoxLayout(preview_page)
        preview_page_lay.setContentsMargins(0, 0, 0, 0)
        preview_page_lay.setSpacing(6)
        preview_lbl = self._make_preview_card(preview_page)
        preview_lbl.setMinimumHeight(320)
        preview_page_lay.addWidget(preview_lbl, 1)
        preview_meta = QLabel(preview_page)
        preview_meta.setObjectName("previewMeta")
        preview_page_lay.addWidget(preview_meta)
        preview_tabs.addTab(preview_page, t("widget.common.preview_caption", "Preview"))

        grammar_page = QWidget(preview_tabs)
        grammar_page_lay = QVBoxLayout(grammar_page)
        grammar_page_lay.setContentsMargins(0, 0, 0, 0)
        grammar_page_lay.setSpacing(8)

        grammar_scroll = QScrollArea(grammar_page)
        grammar_scroll.setWidgetResizable(True)
        grammar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        grammar_inner = QWidget(grammar_scroll)
        grammar_inner_lay = QVBoxLayout(grammar_inner)
        grammar_inner_lay.setContentsMargins(0, 0, 0, 0)
        grammar_inner_lay.setSpacing(8)

        grammar_hint = self._make_hint_box(
            grammar_inner,
            self._compose_template_grammar_hint(hint_text),
            editor=editor,
        )
        grammar_inner_lay.addWidget(grammar_hint)

        if quick_insert_groups:
            self._add_section_label(
                grammar_inner_lay, t("widget.common.quick_insert", "Quick Insert")
            )

            def _insert(snippet: str):
                cursor = editor.textCursor()
                cursor.insertText(snippet)
                editor.setFocus()

            for group_name, vars_list in quick_insert_groups:
                grp_wrap = QWidget(grammar_inner)
                grp_lay = QVBoxLayout(grp_wrap)
                grp_lay.setContentsMargins(0, 2, 0, 0)
                grp_lay.setSpacing(4)

                grp_lbl = QLabel(group_name, grp_wrap)
                grp_lbl.setStyleSheet(_overlay_group_label_style())
                grp_lay.addWidget(grp_lbl)

                chip_wrap = QWidget(grp_wrap)
                chip_flow = _FlowLayout(chip_wrap, h_spacing=4, v_spacing=4)
                chip_wrap.setLayout(chip_flow)
                for snippet, label in vars_list:
                    btn = QPushButton(label, chip_wrap)
                    btn.setObjectName("presetBtn")
                    btn.setToolTip(snippet)
                    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                    btn.clicked.connect(lambda _, s=snippet: _insert(s))
                    chip_flow.addWidget(btn)
                grp_lay.addWidget(chip_wrap)
                grammar_inner_lay.addWidget(grp_wrap)

        grammar_inner_lay.addStretch()
        grammar_scroll.setWidget(grammar_inner)
        grammar_page_lay.addWidget(grammar_scroll, 1)
        preview_tabs.addTab(grammar_page, t("widget.common.grammar_hint_tab", "Grammar Help"))

        preview_wrap_lay.addWidget(preview_tabs, 1)
        splitter.addWidget(preview_wrap)

        splitter.setSizes([560, 500])
        tab_outer.addWidget(splitter, 1)

        self._add_divider(tab_outer)
        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        _clear_label = clear_label or t("widget.common.clear_template", "Clear")
        _reset_label = reset_label or t("widget.common.reset_template", "Reset Template")

        _preset_combo = preset_manager["combo"]

        def _reset_combo_selection():
            """After clear, no preset matches the editor text, so deselect."""
            _preset_combo.blockSignals(True)
            _preset_combo.setCurrentIndex(0)
            _preset_combo.blockSignals(False)
            preset_manager["sync"]()
            reset_btn.setEnabled(bool(default_template))

        def _do_reset():
            """Restore the original template for the selected preset, or fall
            back to the widget-level default when no preset is selected."""
            orig = preset_manager["original_template"]()
            if orig is not None:
                # A preset is selected: restore its unmodified original value.
                editor.setPlainText(orig)
                # Re-sync buttons; combo selection stays on the same preset.
                preset_manager["sync"]()
            else:
                # No preset selected: fall back to the widget default template.
                editor.setPlainText(default_template)
                _reset_combo_selection()

        def _sync_reset_btn():
            has_preset = _preset_combo.currentIndex() > 0
            reset_btn.setEnabled(has_preset or bool(default_template))

        _preset_combo.currentIndexChanged.connect(lambda _: _sync_reset_btn())

        clear_btn = QPushButton(_clear_label, tab_page)
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(lambda: (editor.setPlainText(""), _reset_combo_selection()))
        action_row.addWidget(clear_btn)
        action_row.addStretch()

        reset_btn = QPushButton(_reset_label, tab_page)
        reset_btn.setObjectName("resetBtn")
        reset_btn.clicked.connect(_do_reset)
        _sync_reset_btn()
        action_row.addWidget(reset_btn)

        tab_outer.addLayout(action_row)

        preview_timer = QTimer(dialog)
        preview_timer.setSingleShot(True)
        preview_timer.setInterval(250)

        def _update_preview():
            template = editor.toPlainText().strip()
            if not template:
                preview_lbl.setText(
                    self._wrap_preview_html(
                        _empty_preview_html(
                            t(
                                "widget.common.preview_empty_hint",
                                "The preview appears after you enter a template.",
                            )
                        ),
                        preview_size=preview_lbl.size(),
                    )
                )
                preview_meta.setText("")
                return
            html = render_preview(template)
            preview_lbl.setText(self._wrap_preview_html(html, preview_size=preview_lbl.size()))
            meta = render_meta() if callable(render_meta) else ""
            preview_meta.setText(meta or "")

        editor.textChanged.connect(lambda: preview_timer.start())
        for signal in refresh_signals or []:
            signal.connect(lambda *_args: preview_timer.start())
        preview_timer.timeout.connect(_update_preview)
        preview_lbl.resizeEvent = lambda event, _orig=preview_lbl.resizeEvent: (
            _orig(event),
            preview_timer.start(),
        )[-1]

        if current_template:
            tabs.setCurrentWidget(tab_page)
        _update_preview()

        return {
            "tab": tab_page,
            "layout": tab_outer,
            "editor": editor,
            "preview_label": preview_lbl,
            "preview_meta": preview_meta,
            "preview_tabs": preview_tabs,
            "preview_timer": preview_timer,
            "update_preview": _update_preview,
        }

    def _widget_template(self) -> str:
        """Return the stored template string for this widget (empty = basic mode).

        Requires _TEMPLATE_KEY to be set on the subclass.
        """
        if self._TEMPLATE_KEY is None:
            return ""
        default = getattr(self, "_DEFAULT_TEMPLATE", "")
        val = self._get(self._TEMPLATE_KEY, default)
        return str(val if val not in (None, "") else default)

    def _is_template_mode(self) -> bool:
        """Return True when a non-empty template string is stored."""
        return bool(self._widget_template().strip())

    # -- shared conditional expression engine --

    _RE_COND_PARSE = _re.compile(r"^(\w+)\s*(==|!=|<=|>=|<|>)\s*(.+)$")
    _RE_DURATION = _re.compile(r"^(\d+(?:\.\d+)?)(h|m|s)$")
    _RE_COND_BLOCK = _re.compile(
        r"\{if\s+([^}]+)\}"  # {if condition}
        r"(.*?)"  # true branch
        r"(?:\{else\}(.*?))?"  # optional {else} branch
        r"\{/if\}",
        _re.DOTALL,
    )

    @staticmethod
    def _eval_condition(cond: str, ctx: dict) -> bool:
        """Evaluate a simple condition: 'var op rhs'.

        Operators: == != < > <= >=
        RHS supports integers, floats, duration literals (1h / 30m / 90s),
        and plain strings.  LHS is looked up in *ctx*.
        """
        cond = cond.strip()
        m = _BaseOverlayWidget._RE_COND_PARSE.match(cond)
        if not m:
            return False
        var_name, op, rhs_raw = m.group(1), m.group(2), m.group(3).strip()

        lhs = ctx.get(var_name)
        if lhs is None:
            return False

        dur_m = _BaseOverlayWidget._RE_DURATION.match(rhs_raw.lower())
        if dur_m:
            val = float(dur_m.group(1))
            unit = dur_m.group(2)
            rhs: float | str = val * {"h": 3600, "m": 60, "s": 1}[unit]
            if isinstance(lhs, str) and ":" in lhs and lhs not in ("--:--:--", ""):
                parts = lhs.split(":")
                try:
                    secs = sum(
                        int(p) * f for p, f in zip(reversed(parts), [1, 60, 3600], strict=False)
                    )
                    lhs = float(secs)
                except (ValueError, TypeError):
                    return False
            elif isinstance(lhs, str):
                return False
        else:
            try:
                rhs = float(rhs_raw)
                lhs = float(lhs) if not isinstance(lhs, (int, float)) else lhs
            except (ValueError, TypeError):
                rhs = rhs_raw  # string comparison

        try:
            if op == "==":
                return lhs == rhs
            if op == "!=":
                return lhs != rhs
            if op == "<":
                return float(lhs) < float(rhs)  # type: ignore[arg-type]
            if op == ">":
                return float(lhs) > float(rhs)  # type: ignore[arg-type]
            if op == "<=":
                return float(lhs) <= float(rhs)  # type: ignore[arg-type]
            if op == ">=":
                return float(lhs) >= float(rhs)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            pass
        return False

    @staticmethod
    def _process_conditionals(text: str, ctx: dict) -> str:
        """Replace {if cond}...{else}...{/if} blocks using *ctx* for evaluation.

        {else} is optional.  Nesting is not supported.
        """

        def _replace(m: _re.Match) -> str:
            cond = m.group(1).strip()
            true_branch = m.group(2) or ""
            false_branch = m.group(3) or ""
            if _BaseOverlayWidget._eval_condition(cond, ctx):
                return true_branch
            return false_branch

        return _BaseOverlayWidget._RE_COND_BLOCK.sub(_replace, text)

    def always_on_top(self) -> bool:
        return self._get("always_on_top", True, type_=bool)

    def display_style(self) -> str:
        """Return current display style id (falls back to first defined style)."""
        style_items = self._style_items()
        default = style_items[0][0] if style_items else "default"
        return str(self._get("display_style", default) or default)

    def _set_display_style(self, style_id: str):
        self._set("display_style", style_id)
        self._apply_and_resize(refit=True)

    def _update_always_on_top(self, value: bool):
        self._set("always_on_top", value)
        flags = self.windowFlags()
        if value:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint

        was_visible = self.isVisible()
        pos = self.pos()
        self.setWindowFlags(flags)
        self.move(pos)
        if was_visible:
            self.show()

    # -- position helpers --

    def save_position(self):
        pos = self.pos()
        self._set("pos_x", pos.x())
        self._set("pos_y", pos.y())

    def restore_position(self, default_offset: QPoint):
        px = self._get("pos_x")
        py = self._get("pos_y")
        if px is None or py is None:
            target = self.owner.frameGeometry().topRight() + default_offset
            self.move(target)
        else:
            self.move(int(px), int(py))

    def reset_position(self, default_offset: QPoint):
        target = self.owner.frameGeometry().topRight() + default_offset
        self.move(target)
        self.save_position()

    def center_on_owner(self):
        owner_rect = self.owner.frameGeometry()
        target_x = owner_rect.x() + max(0, (owner_rect.width() - self.width()) // 2)
        target_y = owner_rect.y() + max(0, (owner_rect.height() - self.height()) // 2)
        self.move(target_x, target_y)
        self.save_position()

    # -- enabled/visible --

    def is_enabled(self) -> bool:
        return self._get("enabled", False, type_=bool)

    def _show_with_correct_size(self):
        """Show widget and enforce the correct size.

        In fixed-size mode Qt may reset the window geometry while the widget
        is hidden, so we always re-apply the stored dimensions after show().
        In content-fit mode adjustSize() is used as usual.
        """
        self.show()
        fw = self._normalized_fixed_dimension("fixed_w")
        fh = self._normalized_fixed_dimension("fixed_h")
        if fw is not None and fh is not None:
            # Re-apply appearance after show() so Qt's pending layout flush
            # does not override the font/size that was computed while hidden.
            self._apply_appearance()
            self._update_grip_color()
            self._update_interaction_surface()
            self._release_layout_constraints()
            self.resize(int(fw), int(fh))
        else:
            self.adjustSize()
        self.raise_()

    def set_enabled(self, val: bool):
        self._set("enabled", val)
        if val:
            self._show_with_correct_size()
        else:
            self.hide()
        sync = getattr(self, "_overlay_manager_sync", None)
        if callable(sync):
            sync()

    def set_interaction_locked(self, locked: bool):
        """고정 모드 시 드래그/리사이즈 비활성화."""
        self._interaction_locked = locked
        if locked:
            self._drag_offset = None
            self._resize_origin_global = None
            self.unsetCursor()

    # -- resize zone --

    def _resize_corner_at(self, local_pos: QPoint) -> str | None:
        right = self.face.width() - _RESIZE_GRIP
        bottom = self.face.height() - _RESIZE_GRIP
        left_hit = local_pos.x() <= _RESIZE_GRIP
        right_hit = local_pos.x() >= right
        top_hit = local_pos.y() <= _RESIZE_GRIP
        bottom_hit = local_pos.y() >= bottom
        if top_hit and left_hit:
            return "top_left"
        if top_hit and right_hit:
            return "top_right"
        if bottom_hit and left_hit:
            return "bottom_left"
        if bottom_hit and right_hit:
            return "bottom_right"
        return None

    def _update_hover_cursor(self, local_pos: QPoint):
        corner = self._resize_corner_at(local_pos)
        if corner in {"top_left", "bottom_right"}:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif corner in {"top_right", "bottom_left"}:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        if not self.face.hover_grip or self.face.grip_corner != corner:
            self.face.hover_grip = True
            self.face.grip_corner = corner
            self.face.update()

    def _release_layout_constraints(self):
        """Remove all minimum-size constraints from face, its layout, and all descendants."""
        self.face.setMinimumSize(0, 0)
        lay = self.face.layout()
        if lay:
            lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        for child in self.face.findChildren(QWidget):
            child.setMinimumSize(0, 0)
            child_lay = child.layout() if hasattr(child, "layout") else None
            if child_lay:
                child_lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        outer_lay = self.layout()
        if outer_lay:
            outer_lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def _apply_and_resize(self, refit: bool = False):
        """Apply stored appearance (font, colors) and enforce the correct window size.

        Pass refit=True when the font family/size or layout has changed in a
        way that requires the font to be re-fitted to the fixed box (e.g. after
        the user picks a new font from the font dialog).  On normal startup
        the stored font_size is already correct, so no re-fitting is needed.
        """
        fw = self._normalized_fixed_dimension("fixed_w")
        fh = self._normalized_fixed_dimension("fixed_h")
        if refit and fw is not None and fh is not None:
            self._fit_font_to_size(int(fw), int(fh))
        else:
            self._apply_appearance()
            self._update_grip_color()
            self._update_interaction_surface()
            self._force_resize()

    def _force_resize(self):
        """Flush layout and resize the outer window to fit content (unless fixed-size mode)."""
        if not hasattr(self, "face"):
            return
        if self._measuring:
            return
        fw = self._normalized_fixed_dimension("fixed_w")
        fh = self._normalized_fixed_dimension("fixed_h")
        if fw is not None and fh is not None:
            self._release_layout_constraints()
            self.resize(int(fw), int(fh))
            return
        self.setMaximumSize(16777215, 16777215)
        self.setMinimumSize(0, 0)
        lay = self.face.layout()
        if lay:
            lay.invalidate()
            lay.activate()
        self.face.updateGeometry()
        self.updateGeometry()
        if self.isVisible():
            self.adjustSize()

    def _content_space_for_widget_size(self, target_w: int, target_h: int) -> tuple[int, int]:
        """Estimate how much inner space is actually available for widget content."""
        chrome_w, chrome_h = self._resize_chrome_size
        content_w = max(1, int(target_w) - max(0, chrome_w))
        content_h = max(1, int(target_h) - max(0, chrome_h))
        return content_w, content_h

    def _capture_resize_content_metrics(self) -> None:
        """Capture the current non-content chrome so live scaling can use inner space."""
        face_rect = self.face.contentsRect() if hasattr(self, "face") else QRect()
        face_size = self.face.size() if hasattr(self, "face") else QSize()
        layout = self.face.layout() if hasattr(self, "face") else None
        margins = layout.contentsMargins() if layout else None

        layout_w = 0 if margins is None else margins.left() + margins.right()
        layout_h = 0 if margins is None else margins.top() + margins.bottom()
        face_chrome_w = max(0, face_size.width() - face_rect.width()) + layout_w
        face_chrome_h = max(0, face_size.height() - face_rect.height()) + layout_h

        outer_w = max(0, self.width() - face_size.width())
        outer_h = max(0, self.height() - face_size.height())
        chrome_w = face_chrome_w + outer_w
        chrome_h = face_chrome_h + outer_h

        self._resize_chrome_size = (chrome_w, chrome_h)
        self._resize_origin_content_size = self._content_space_for_widget_size(
            self.width(), self.height()
        )

    def _natural_box_scale(self, target_w: int, target_h: int) -> float:
        """Return a resize scale derived from the actual content area, not outer box size."""
        ow, oh = self._resize_origin_content_size
        if ow <= 0 or oh <= 0:
            return 1.0

        content_w, content_h = self._content_space_for_widget_size(target_w, target_h)
        scale_w = content_w / max(1, ow)
        scale_h = content_h / max(1, oh)
        min_scale = min(scale_w, scale_h)
        area_scale = (max(0.01, scale_w) * max(0.01, scale_h)) ** 0.5

        # Push text scaling harder than the box itself so resize feels dramatic.
        # A small area component keeps diagonal drags from looking lopsided.
        blended = (min_scale * 0.94) + (area_scale * 0.06)
        if blended >= 1.0:
            eased = 1.0 + ((blended - 1.0) * 1.35)
        else:
            eased = 1.0 - ((1.0 - blended) * 1.3)
        return max(0.25, min(4.0, eased))

    def _scale_font_with_box(self, target_w: int, target_h: int, *, live: bool = False):
        """Fit the font directly to the current content space of the widget box."""
        if live:
            self._release_layout_constraints()
            self.resize(int(target_w), int(target_h))
            now = time.monotonic()
            if (now - self._last_live_fit_at) >= (1.0 / 60.0):
                self._last_live_fit_at = now
                self._fit_font_to_size(target_w, target_h, live=True)
            return
        self._fit_font_to_size(target_w, target_h)

    def _anchor_point_for_corner(self, corner: str, pos: QPoint, size: tuple[int, int]) -> QPoint:
        """Return the opposite-corner anchor point for a resize operation."""
        w, h = size
        if corner == "bottom_right":
            return QPoint(pos.x(), pos.y())
        if corner == "bottom_left":
            return QPoint(pos.x() + w, pos.y())
        if corner == "top_right":
            return QPoint(pos.x(), pos.y() + h)
        return QPoint(pos.x() + w, pos.y() + h)

    def _position_from_anchor(self, corner: str, anchor: QPoint, size: tuple[int, int]) -> QPoint:
        """Reconstruct top-left position while keeping the opposite corner fixed."""
        w, h = size
        if corner == "bottom_right":
            return QPoint(anchor.x(), anchor.y())
        if corner == "bottom_left":
            return QPoint(anchor.x() - w, anchor.y())
        if corner == "top_right":
            return QPoint(anchor.x(), anchor.y() - h)
        return QPoint(anchor.x() - w, anchor.y() - h)

    def _fit_font_to_size(self, target_w: int, target_h: int, *, live: bool = False):
        """Binary-search the largest font size that fits within target_w x target_h."""
        lay = self.face.layout()
        if lay is None:
            return

        self._release_layout_constraints()

        # Clamp target to reasonable min so tiny drags don't produce size=6.
        target_w = max(target_w, 60)
        target_h = max(target_h, 20)
        content_w, content_h = self._content_space_for_widget_size(target_w, target_h)

        def _needed(size: int) -> QSize:
            """Apply font size and return the measured face size."""
            self._set("font_size", size)
            saved_fw = self._get("fixed_w", None)
            saved_fh = self._get("fixed_h", None)
            self._set("fixed_w", None)
            self._set("fixed_h", None)
            try:
                self._apply_appearance()
                # Force layout to recalculate so contentsMargins / spacing are current.
                lay.invalidate()
                lay.activate()
            except Exception:
                pass
            finally:
                self._set("fixed_w", saved_fw)
                self._set("fixed_h", saved_fh)
            return _measure_face_size_precise(self.face, content_w)

        self._measuring = True
        try:
            lo = 6
            hi = max(64, self.font_size(), self._resize_origin_font, self._default_font_size())
            while hi < 100000:
                needed = _needed(hi)
                if needed.width() > content_w or needed.height() > content_h:
                    break
                lo = hi
                hi *= 2
            best = lo
            while lo <= hi:
                mid = (lo + hi) // 2
                needed = _needed(mid)
                if needed.width() <= content_w and needed.height() <= content_h:
                    best = mid
                    lo = mid + 1  # noqa: SIM113
                else:
                    hi = mid - 1  # noqa: SIM113
        finally:
            self._measuring = False

        self._set("font_size", best)
        try:
            self._apply_appearance()
            self._update_grip_color()
            self._update_interaction_surface()
            if live:
                self._release_layout_constraints()
                self.resize(int(target_w), int(target_h))
            else:
                self._force_resize()
        except Exception:
            pass

    # -- event filter (drag + resize + context menu) --

    def _is_face_descendant(self, widget) -> bool:
        if not hasattr(self, "face"):
            return False
        w = widget
        while w is not None:
            if w is self.face:
                return True
            w = w.parent()
        return False

    def eventFilter(self, watched, event):
        if not self._is_face_descendant(watched):
            return super().eventFilter(watched, event)

        etype = event.type()

        if etype == QEvent.Type.MouseButtonPress:
            btn = event.button()
            if self._interaction_locked:
                if btn == Qt.MouseButton.RightButton:
                    self._show_context_menu(event.globalPosition().toPoint())
                    event.accept()
                    return True
                return False  # 드래그/리사이즈 차단, 자식 위젯에 전달
            if btn == Qt.MouseButton.LeftButton:
                local = self.face.mapFromGlobal(event.globalPosition().toPoint())
                corner = self._resize_corner_at(local)
                if corner:
                    self._resize_origin_global = event.globalPosition().toPoint()
                    self._resize_origin_size = (self.width(), self.height())
                    self._capture_resize_content_metrics()
                    self._resize_origin_pos = self.pos()
                    self._resize_origin_font = self.font_size()
                    self._resize_corner = corner
                    self._resizing = True
                    self._last_fit_size = (0, 0)
                    self._last_live_scale_apply_at = 0.0
                    self._last_live_fit_at = 0.0
                    self._release_layout_constraints()
                    self._update_hover_cursor(local)
                    self.face.show_grip = True
                    self.face.grip_corner = corner
                    self.face.update()
                else:
                    self._drag_offset = (
                        event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    )
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return True
            if btn == Qt.MouseButton.RightButton:
                self._show_context_menu(event.globalPosition().toPoint())
                event.accept()
                return True

        if etype == QEvent.Type.MouseMove:
            local = self.face.mapFromGlobal(event.globalPosition().toPoint())

            if self._resize_origin_global is not None and not (
                event.buttons() & Qt.MouseButton.LeftButton
            ):
                self._resize_origin_global = None
                self._resize_origin_pos = None
                self._resize_corner = None
                self._resizing = False
                self.face.show_grip = False
                self.face.update()
                self._refresh_face()
                self._update_hover_cursor(local)
                event.accept()
                return True
            if self._drag_offset is not None and not (event.buttons() & Qt.MouseButton.LeftButton):
                self._drag_offset = None
                self._update_hover_cursor(local)
                event.accept()
                return True

            if (
                self._resize_origin_global is not None
                and event.buttons() & Qt.MouseButton.LeftButton
            ):
                delta = event.globalPosition().toPoint() - self._resize_origin_global
                ow, oh = self._resize_origin_size
                origin_pos = self._resize_origin_pos or self.pos()
                corner = self._resize_corner or "bottom_right"
                if corner == "bottom_right":
                    new_x = origin_pos.x()
                    new_y = origin_pos.y()
                    new_w = max(80, int(ow + delta.x()))
                    new_h = max(40, int(oh + delta.y()))
                elif corner == "bottom_left":
                    new_w = max(80, int(ow - delta.x()))
                    new_h = max(40, int(oh + delta.y()))
                    new_x = int(origin_pos.x() + (ow - new_w))
                    new_y = origin_pos.y()
                elif corner == "top_right":
                    new_w = max(80, int(ow + delta.x()))
                    new_h = max(40, int(oh - delta.y()))
                    new_x = origin_pos.x()
                    new_y = int(origin_pos.y() + (oh - new_h))
                else:
                    new_w = max(80, int(ow - delta.x()))
                    new_h = max(40, int(oh - delta.y()))
                    new_x = int(origin_pos.x() + (ow - new_w))
                    new_y = int(origin_pos.y() + (oh - new_h))
                self._set("fixed_w", new_w)
                self._set("fixed_h", new_h)
                self.move(new_x, new_y)
                self._scale_font_with_box(new_w, new_h, live=True)
                event.accept()
                return True
            if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                event.accept()
                return True

            self._update_hover_cursor(local)

        if etype == QEvent.Type.Enter:
            self.face.hover_grip = True
            self.face.grip_corner = None
            self.face.update()

        if etype == QEvent.Type.MouseButtonRelease:
            if self._resize_origin_global is not None:
                final_w = int(self._get("fixed_w", self.width()) or self.width())
                final_h = int(self._get("fixed_h", self.height()) or self.height())
                corner = self._resize_corner or "bottom_right"
                origin_pos = self._resize_origin_pos or self.pos()
                anchor = self._anchor_point_for_corner(corner, origin_pos, self._resize_origin_size)
                self._resize_origin_global = None
                self._resize_origin_pos = None
                self._resize_corner = None
                self._resizing = False
                self.face.show_grip = False
                self.face.update()
                self._apply_appearance()
                self._refresh_face()  # tick???????占쎈Ŧ????????????????影?占쏀맮?耀붾굝????????硫멸킐??????????????????耀붾굝?????????? ????????占쎄뭐???饔낅떽???????
                self._release_layout_constraints()
                self._fit_font_to_size(final_w, final_h)
                self.move(self._position_from_anchor(corner, anchor, (final_w, final_h)))
                self.save_position()
                local = self.face.mapFromGlobal(event.globalPosition().toPoint())
                self._update_hover_cursor(local)
                event.accept()
                return True
            if self._drag_offset is not None:
                self._drag_offset = None
                self.save_position()
                local = self.face.mapFromGlobal(event.globalPosition().toPoint())
                self._update_hover_cursor(local)
            event.accept()
            return True

        if etype == QEvent.Type.Leave:
            self.unsetCursor()
            if self.face.hover_grip:
                self.face.hover_grip = False
                self.face.grip_corner = None
                self.face.update()
            return False

        if etype == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            return self._on_double_click()

        return super().eventFilter(watched, event)

    def _on_double_click(self) -> bool:
        return False

    # -- context menu --

    def _show_context_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())

        self._build_context_menu(menu)

        if len(self._STYLES) > 1:
            menu.addSeparator()
            style_menu = menu.addMenu(t("widget.menu.display_style", "Display Style"))
            style_menu.setIcon(_ic(ICON.DISPLAY_STYLE))
            style_menu.setStyleSheet(self._menu_style())
            cur = self.display_style()
            for sid, slabel in self._style_items():
                act = style_menu.addAction(slabel, lambda *_, s=sid: self._set_display_style(s))
                act.setCheckable(True)
                act.setChecked(sid == cur)

        menu.addSeparator()
        app_menu = menu.addMenu(t("widget.menu.appearance", "Appearance"))
        app_menu.setIcon(_ic(ICON.APPEARANCE))
        app_menu.setStyleSheet(self._menu_style())
        self._add_appearance_actions(app_menu)

        menu.addSeparator()
        aot = menu.addAction(
            t("widget.menu.always_on_top", "Always on top"), lambda: self._toggle_always_on_top()
        )
        aot.setIcon(_ic(ICON.ALWAYS_ON_TOP))
        aot.setCheckable(True)
        aot.setChecked(self.always_on_top())

        act_pos = menu.addAction(
            t("widget.menu.reset_position", "Reset position"), self._action_reset_position
        )
        act_pos.setIcon(_ic(ICON.RESET_POS))
        act_size = menu.addAction(
            t("widget.menu.reset_size", "Optimize size"), self._action_reset_size
        )
        act_size.setIcon(_ic(ICON.RESET_SIZE))
        menu.addSeparator()
        act_hide = menu.addAction(t("widget.menu.hide", "Hide"), lambda: self.set_enabled(False))
        act_hide.setIcon(_ic(ICON.HIDE))

        _remove_cb = getattr(self, "_overlay_manager_remove", None)
        if callable(_remove_cb):
            act_del = menu.addAction(
                t("widget.menu.delete", "Delete..."),
                _remove_cb,
            )
            act_del.setIcon(_ic(ICON.DELETE))

        menu.exec(global_pos)

    def _add_appearance_actions(self, menu: QMenu):
        act_font = menu.addAction(t("widget.menu.font", "Font..."), self._action_font)
        act_font.setIcon(_ic(ICON.FONT))
        menu.addSeparator()

        act_tc = menu.addAction(
            t("widget.menu.text_color", "Text color..."), self._action_text_color
        )
        act_tc.setIcon(_ic(ICON.TEXT_COLOR))
        act_bc = menu.addAction(
            t("widget.menu.background_color", "Background color..."), self._action_bg_color
        )
        act_bc.setIcon(_ic(ICON.COLOR_PICKER))
        act_brc = menu.addAction(
            t("widget.menu.border_color", "Border color..."), self._action_border_color
        )
        act_brc.setIcon(_ic(ICON.COLOR_PICKER))

        menu.addSeparator()
        act_op = menu.addAction(
            t("widget.menu.opacity_settings", "Opacity..."), self._action_open_opacity_dialog
        )
        act_op.setIcon(_ic(ICON.OPACITY))

        menu.addSeparator()
        act_rc = menu.addAction(
            t("widget.menu.reset_colors", "Reset colors"), self._action_reset_colors
        )
        act_rc.setIcon(_ic(ICON.REFRESH))

    def _action_font(self):
        dlg = _FontPickerDialog(self.font_family(), self.font_size(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            family, size = dlg.result_font()
            self._set("font_family", family)
            self._set("font_size", size)
            self._apply_and_resize()

    def _action_text_color(self):
        result = _pick_rgba_color(
            self, t("widget.color.text", "Text Color"), self.text_color_rgba()
        )
        if result:
            self._set("text_color_rgba", result)
            self._apply_and_resize()

    def _action_bg_color(self):
        result = _pick_rgba_color(
            self, t("widget.color.background", "Background Color"), self.bg_color_rgba()
        )
        if result:
            self._set("bg_color_rgba", result)
            self._apply_and_resize()

    def _action_border_color(self):
        result = _pick_rgba_color(
            self, t("widget.color.border", "Border Color"), self.border_color_rgba()
        )
        if result:
            self._set("border_color_rgba", result)
            self._apply_and_resize()

    def _action_open_opacity_dialog(self):
        from PyQt6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QLabel,
            QSlider,
            QVBoxLayout,
        )

        dlg = QDialog(self)
        apply_dialog_title(dlg, t("widget.menu.opacity_settings", "Opacity"))
        dlg.setModal(False)
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet(_fresh_dlg_ss())

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        def _make_row(label_text: str, initial: int, callback, range_max: int = 255):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(100)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, range_max)
            slider.setValue(initial)
            val_lbl = QLabel(str(initial))
            val_lbl.setMinimumWidth(28)
            slider.valueChanged.connect(lambda v: (val_lbl.setText(str(v)), callback(v)))
            row.addWidget(lbl)
            row.addWidget(slider, 1)
            row.addWidget(val_lbl)
            layout.addLayout(row)

        _, cur_txt_alpha = _parse_rgba(self.text_color_rgba(), fallback_alpha=255)
        _, cur_bg_alpha = _parse_rgba(self.bg_color_rgba(), fallback_alpha=214)
        _, cur_bd_alpha = _parse_rgba(self.border_color_rgba(), fallback_alpha=32)
        cur_widget_opacity = int(self.widget_opacity() * 100)

        _make_row(
            t("widget.menu.overall_opacity", "Overall Opacity"),
            cur_widget_opacity,
            self._action_widget_opacity,
            range_max=100,
        )
        _make_row(
            t("widget.menu.text_opacity", "Text Opacity"), cur_txt_alpha, self._action_text_alpha
        )
        _make_row(
            t("widget.menu.background_opacity", "Background Opacity"),
            cur_bg_alpha,
            self._action_bg_alpha,
        )
        _make_row(
            t("widget.menu.border_opacity", "Border Opacity"),
            cur_bd_alpha,
            self._action_border_alpha,
        )

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.accept)
        layout.addWidget(btns)

        dlg.exec()

    def _action_widget_opacity(self, opacity_100: int):
        self._set("widget_opacity", opacity_100)
        self.setWindowOpacity(max(0.1, min(1.0, opacity_100 / 100.0)))

    def _action_text_alpha(self, alpha: int):
        c, _ = _parse_rgba(self.text_color_rgba())
        self._set("text_color_rgba", _to_rgba_str(c, alpha))
        self._apply_and_resize()

    def _action_bg_alpha(self, alpha: int):
        c, _ = _parse_rgba(self.bg_color_rgba())
        self._set("bg_color_rgba", _to_rgba_str(c, alpha))
        self._apply_and_resize()

    def _action_border_alpha(self, alpha: int):
        c, _ = _parse_rgba(self.border_color_rgba())
        self._set("border_color_rgba", _to_rgba_str(c, alpha))
        self._apply_and_resize()

    def _action_reset_colors(self):
        self._set("text_color_rgba", self._DEFAULT_TEXT_RGBA)
        self._set("bg_color_rgba", self._DEFAULT_BG_RGBA)
        self._set("border_color_rgba", self._DEFAULT_BORDER_RGBA)
        self._apply_and_resize()

    def _toggle_always_on_top(self):
        self._update_always_on_top(not self.always_on_top())

    def _action_reset_position(self):
        raise NotImplementedError

    def _action_reset_size(self):
        """Clear fixed-size constraint and return to content-fit mode."""
        self._set("fixed_w", None)
        self._set("fixed_h", None)
        self._release_layout_constraints()
        self._force_resize()

    def _menu_style(self) -> str:
        return _overlay_menu_style()

    # -- appearance helpers --

    def _face_stylesheet(self, obj_name: str, radius: int = 12, border_width: int = 1) -> str:
        bg_c, bg_a = _parse_rgba(self.bg_color_rgba())
        bd_c, bd_a = _parse_rgba(self.border_color_rgba())
        return (
            f"QFrame#{obj_name} {{"
            f"  background-color: {_rgba_css(bg_c, bg_a)};"
            f"  border: {border_width}px solid {_rgba_css(bd_c, bd_a)};"
            f"  border-radius: {radius}px;"
            f"}}"
        )

    def _make_font(self, size: int | None = None, bold: bool = True) -> QFont:
        f = QFont(self.font_family(), size if size is not None else self.font_size())
        f.setBold(bold)
        f.setStyleHint(QFont.StyleHint.Monospace)
        return f

    def _text_color_str(self) -> str:
        c, a = _parse_rgba(self.text_color_rgba())
        return _rgba_css(c, a)

    def _secondary_color_str(self, alpha_offset: int = -40) -> str:
        c, a = _parse_rgba(self.text_color_rgba())
        return _rgba_css(c, max(0, a + alpha_offset))
