# -*- coding: utf-8 -*-
"""Daily briefing dialog with configurable visibility and reminder rules."""

import logging
import re

from PyQt6.QtCore import QDate, QEvent, QLocale, QSettings, QSize, Qt, QTime, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import db_repository_unified as repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se

logger = logging.getLogger(__name__)

_SETTINGS_KEY_LAST_SHOWN = "daily_summary_last_shown"
_SETTINGS_KEY_TIME = "daily_summary_time"
_SETTINGS_KEY_SCHEDULE_MODE = "daily_summary_schedule_visibility"
_SETTINGS_KEY_ROUTINE_MODE = "daily_summary_routine_visibility"
_SETTINGS_KEY_STARTUP_ENABLED = "daily_summary_startup_enabled"
_SETTINGS_KEY_DAILY_ENABLED = "daily_summary_daily_enabled"
_SETTINGS_KEY_HIDE_WEEKENDS = "daily_summary_hide_weekends"
_DEFAULT_TIME = "08:00"
_MODE_ALWAYS = "always"
_MODE_WHEN_AVAILABLE = "when_available"
_MODE_HIDDEN = "hidden"
_VALID_VISIBILITY_MODES = {_MODE_ALWAYS, _MODE_WHEN_AVAILABLE, _MODE_HIDDEN}


def _setting_bool(settings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _visibility_mode(settings, key: str) -> str:
    value = str(settings.value(key, _MODE_ALWAYS) or _MODE_ALWAYS)
    return value if value in _VALID_VISIBILITY_MODES else _MODE_ALWAYS


def _icon_hex(value, fallback: str = "#6b7688") -> str:
    """Normalize theme CSS colors to the #RRGGBB format qtawesome requires."""
    text = str(value or "").strip()
    if text.startswith("#"):
        color = QColor(text)
        return color.name(QColor.NameFormat.HexRgb) if color.isValid() else fallback
    match = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text, re.IGNORECASE)
    if match:
        return QColor(*(max(0, min(255, int(part))) for part in match.groups())).name(
            QColor.NameFormat.HexRgb
        )
    color = QColor(text)
    return color.name(QColor.NameFormat.HexRgb) if color.isValid() else fallback


class _ToggleSwitch(QCheckBox):
    """Keyboard-accessible compact switch rendered consistently across Windows themes."""

    def __init__(self, accent: str, text_primary: str, parent=None):
        super().__init__(parent)
        self._accent = QColor(accent)
        primary = QColor(text_primary)
        self._off = QColor("#c7cfda") if primary.lightness() < 128 else QColor("#545d69")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self):
        return QSize(44, 24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self.rect().adjusted(1, 2, -1, -2)
        track_color = QColor(self._accent if self.isChecked() else self._off)
        if self.underMouse():
            track_color = track_color.lighter(108)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 10, 10)

        knob_size = 16
        knob_x = self.width() - knob_size - 4 if self.isChecked() else 4
        knob_y = (self.height() - knob_size) // 2
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(knob_x, knob_y, knob_size, knob_size)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._accent, 1))
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 11, 11)


def _today_str() -> str:
    return QDate.currentDate().toString("yyyy-MM-dd")


class DailySummaryDialog(QDialog):
    """Shows today's briefing in a frameless modal with an expandable settings pane."""

    COMPACT_SIZE = (560, 500)
    EXPANDED_SIZE = (960, 500)

    def __init__(self, parent=None, theme_color=None, *, show_settings: bool = False):
        super().__init__(parent)
        self._theme_color = theme_color
        self._dialog_settings = getattr(parent, "settings", None) or QSettings(
            "kimhyojin", "Dark Calendar"
        )
        self._drag_origin = None
        self._settings_open = False
        self._settings_overlay_mode = False
        self._visibility_buttons: dict[str, dict[str, QPushButton]] = {}
        apply_dialog_title(self, t("dialog.daily.title", "오늘의 일정 & 마감 업무"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setSizeGripEnabled(False)
        self._ui_tokens = get_dialog_theme_tokens(
            theme_color=self._theme_color,
            settings=self._dialog_settings,
        )
        self._build_ui()
        self.resize(*self.COMPACT_SIZE)
        self.setMinimumSize(*self.COMPACT_SIZE)
        self.setAccessibleName(t("dialog.daily.briefing_title", "오늘의 브리핑"))
        self.setAccessibleDescription(
            t(
                "dialog.daily.briefing_description",
                "오늘의 일정과 마감 업무를 확인하고 자동 표시 방식을 설정합니다.",
            )
        )
        if show_settings:
            self._set_settings_open(True)

    def _build_ui(self):
        tokens = self._ui_tokens
        accent = tokens.get("accent", "#4da6ff")
        accent_text = tokens.get("accent_text", "#ffffff")
        accent_display = tokens.get("tab_text_active", accent)
        surface_bg = tokens.get("floating_bg", tokens.get("surface_bg", "#ffffff"))
        surface_item = tokens.get("surface_item", "#f4f7fb")
        surface_hover = tokens.get("surface_hover", "#edf3fb")
        text_primary = tokens.get("text_primary", "#172033")
        text_secondary = tokens.get("text_secondary", "#526078")
        text_muted = tokens.get("text_muted", "#7b879b")
        border = tokens.get("border", "rgba(23,32,51,0.16)")
        border_soft = tokens.get("border_soft", "rgba(23,32,51,0.10)")
        accent_soft = tokens.get("accent_soft") or "rgba(77,166,255,0.10)"

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        self.container = QFrame()
        self.container.setObjectName("dailySummaryShell")
        shell_layout = QHBoxLayout(self.container)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self._shell_layout = shell_layout

        self.summary_panel = QWidget()
        self.summary_panel.setObjectName("dailySummaryPanel")
        summary_layout = QVBoxLayout(self.summary_panel)
        summary_layout.setContentsMargins(26, 22, 26, 20)
        summary_layout.setSpacing(0)
        self._build_summary_header(summary_layout, text_primary, text_secondary, text_muted, accent_display)

        self.summary_scroll = QScrollArea()
        self.summary_scroll.setObjectName("dailySummaryContent")
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.summary_scroll.setAccessibleName(t("dialog.daily.title", "오늘의 일정 & 마감 업무"))
        content = QWidget()
        content.setObjectName("dailySummaryScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 12, 4, 0)
        content_layout.setSpacing(18)
        self.summary_scroll.setWidget(content)
        summary_layout.addWidget(self.summary_scroll, 1)

        today = _today_str()
        self.schedule_items = self._load_schedule(today)
        self.routine_items = self._load_due_routines(today)
        self.has_content = bool(self.schedule_items) or bool(self.routine_items)

        self.schedule_section = self._build_schedule_section(
            self.schedule_items, text_primary, text_secondary, text_muted, accent_display
        )
        self.routine_section = self._build_routine_section(
            self.routine_items, text_primary, text_secondary, text_muted, accent_display
        )
        content_layout.addWidget(self.schedule_section)
        content_layout.addWidget(self.routine_section)
        content_layout.addStretch(1)

        self._build_summary_footer(summary_layout, text_secondary, text_muted)
        shell_layout.addWidget(self.summary_panel, 1)

        self.panel_divider = QFrame()
        self.panel_divider.setObjectName("dailySummaryPanelDivider")
        self.panel_divider.setFixedWidth(1)
        self.panel_divider.hide()
        shell_layout.addWidget(self.panel_divider)

        self.settings_panel = self._build_settings_panel(text_primary, text_secondary, text_muted)
        self.settings_panel.setObjectName("dailySummarySettingsPanel")
        self.settings_panel.hide()
        shell_layout.addWidget(self.settings_panel)
        root.addWidget(self.container)

        self.setStyleSheet(
            f"""
            QDialog {{
                background: transparent;
                font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
            QFrame#dailySummaryShell {{
                background-color: {surface_bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QWidget#dailySummaryPanel, QWidget#dailySummarySettingsPanel,
            QWidget#dailySummaryScrollContent, QScrollArea#dailySummaryContent {{
                background: transparent;
                border: none;
            }}
            QFrame#dailySummaryPanelDivider {{ background-color: {border_soft}; border: none; }}
            QLabel {{ background: transparent; border: none; color: {text_secondary}; }}
            QLabel[role="title"] {{ color: {text_primary}; font-size: 24px; font-weight: 750; }}
            QLabel[role="date"] {{ color: {text_muted}; font-size: 13px; font-weight: 600; }}
            QLabel[role="sectionTitle"] {{ color: {text_primary}; font-size: 14px; font-weight: 700; }}
            QLabel[role="sectionCount"] {{ color: {text_muted}; font-size: 12px; font-weight: 600; }}
            QLabel[role="helper"] {{ color: {text_muted}; font-size: 12px; font-weight: 500; }}
            QFrame#dailySummaryItem {{
                background-color: {accent_soft};
                border: 1px solid {border_soft};
                border-radius: 10px;
            }}
            QLabel#dailySummaryBadge {{
                color: {accent_display}; background-color: {accent_soft};
                border: none; border-radius: 7px; padding: 4px 8px;
                font-size: 12px; font-weight: 700;
            }}
            QFrame#dailySummaryStatChip {{
                background-color: {accent_soft}; border: 1px solid {border_soft};
                border-radius: 9px;
            }}
            QPushButton, QToolButton {{
                min-height: 36px; border-radius: 9px; padding: 4px 12px;
                color: {text_secondary}; background-color: transparent;
                border: 1px solid transparent; font-size: 13px; font-weight: 650;
            }}
            QPushButton:hover, QToolButton:hover {{ background-color: {surface_hover}; color: {text_primary}; }}
            QPushButton#primary_btn {{
                min-width: 94px; min-height: 40px; background-color: {accent};
                color: {accent_text}; border: 1px solid {accent}; font-weight: 750;
            }}
            QPushButton#ghost_btn {{ border: 1px solid {border}; background-color: transparent; }}
            QPushButton[segment="true"] {{
                min-height: 32px; padding: 2px 9px; border-radius: 7px;
                border: 1px solid {border}; background-color: {surface_item};
            }}
            QPushButton[segment="true"]:checked {{
                background-color: {accent}; color: {accent_text}; border-color: {accent};
            }}
            QCheckBox {{ color: {text_secondary}; spacing: 10px; font-size: 13px; font-weight: 600; }}
            QTimeEdit {{ min-height: 34px; max-height: 34px; min-width: 92px; padding: 0 8px;
                color: {text_primary}; background-color: {surface_item};
                border: 1px solid {border}; border-radius: 8px; }}
            QScrollArea#dailySummaryContent QScrollBar:vertical {{ width: 9px; margin: 4px 0; }}
            """
        )
        self._apply_visibility_preferences()

    def _build_summary_header(self, layout, text_primary, text_secondary, text_muted, accent):
        header = QWidget()
        header.setObjectName("dailySummaryDragHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel(t("dialog.daily.briefing_title", "오늘의 브리핑"))
        title.setProperty("role", "title")
        today = QDate.currentDate()
        weekday = QLocale().dayName(today.dayOfWeek(), QLocale.FormatType.ShortFormat)
        date_label = QLabel(f"{today.toString('yyyy-MM-dd')} ({weekday})")
        date_label.setProperty("role", "date")
        title_col.addWidget(title)
        title_col.addWidget(date_label)
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)

        self.settings_btn = QToolButton()
        self.settings_btn.setText(t("dialog.daily.visibility_settings", "노출 설정"))
        self.settings_btn.setIcon(_ic(ICON.SETTINGS, color=_icon_hex(text_secondary)))
        self.settings_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_btn.setAccessibleName(self.settings_btn.text())
        self.settings_btn.clicked.connect(lambda: self._set_settings_open(True))
        header_layout.addWidget(self.settings_btn)

        close_btn = self._icon_button(
            ICON.CLOSE,
            t("common.close", "닫기"),
            text_muted,
        )
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        self._drag_targets = [header, title, date_label]
        for target in self._drag_targets:
            target.installEventFilter(self)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 14, 0, 0)
        stats_row.setSpacing(8)
        stats_row.addStretch(1)
        self.schedule_stat_value = QLabel("0")
        self.routine_stat_value = QLabel("0")
        stats_row.addWidget(
            self._build_stat_chip(
                ICON.CALENDAR,
                t("dialog.daily.schedule_short", "일정"),
                self.schedule_stat_value,
                accent,
                text_secondary,
            )
        )
        stats_row.addWidget(
            self._build_stat_chip(
                ICON.CHECKLIST,
                t("dialog.daily.routine_short", "마감"),
                self.routine_stat_value,
                text_muted,
                text_secondary,
            )
        )
        layout.addLayout(stats_row)

    def _build_stat_chip(self, icon_key, label_text, value_label, icon_color, text_color):
        chip = QFrame()
        chip.setObjectName("dailySummaryStatChip")
        row = QHBoxLayout(chip)
        row.setContentsMargins(11, 7, 11, 7)
        row.setSpacing(7)
        icon_label = QLabel()
        icon_label.setPixmap(_ic(icon_key, color=_icon_hex(icon_color)).pixmap(17, 17))
        label = QLabel(label_text)
        label.setStyleSheet(f"color:{text_color}; font-size:12px; font-weight:650;")
        value_label.setStyleSheet(f"color:{icon_color}; font-size:17px; font-weight:800;")
        row.addWidget(icon_label)
        row.addWidget(label)
        row.addWidget(value_label)
        return chip

    def _section_header(self, icon_key, title_text, count_text, icon_color):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(_ic(icon_key, color=_icon_hex(icon_color)).pixmap(19, 19))
        title = QLabel(_se(title_text))
        title.setProperty("role", "sectionTitle")
        count = QLabel(count_text)
        count.setProperty("role", "sectionCount")
        row.addWidget(icon_label)
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(count)
        return row

    def _build_schedule_section(self, items, text_primary, text_secondary, text_muted, accent):
        section = QWidget()
        section.setObjectName("dailyScheduleSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        layout.addLayout(
            self._section_header(
                ICON.CALENDAR,
                t("dialog.daily.schedule_section", "오늘의 일정"),
                t("dialog.daily.schedule_count", "{count}건", count=len(items)),
                accent,
            )
        )
        self.schedule_stat_value.setText(str(len(items)))
        if not items:
            layout.addWidget(self._empty_item(t("dialog.daily.no_schedule", "오늘 예정된 일정이 없습니다.")))
            return section
        for item in items:
            item_text = str(item).lstrip("• ").strip()
            is_all_day = item_text.endswith("[종일]")
            if is_all_day:
                item_text = item_text[: -len("[종일]")].strip()
            frame = QFrame()
            frame.setObjectName("dailySummaryItem")
            row = QHBoxLayout(frame)
            row.setContentsMargins(12, 10, 12, 10)
            row.setSpacing(9)
            if is_all_day:
                badge = QLabel(t("dialog.daily.all_day", "종일"))
                badge.setObjectName("dailySummaryBadge")
                row.addWidget(badge)
            label = QLabel(item_text)
            label.setWordWrap(True)
            label.setStyleSheet(f"color:{text_primary}; font-size:13px; font-weight:650;")
            row.addWidget(label, 1)
            layout.addWidget(frame)
        return section

    def _build_routine_section(self, items, text_primary, text_secondary, text_muted, accent):
        section = QWidget()
        section.setObjectName("dailyRoutineSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        layout.addLayout(
            self._section_header(
                ICON.CHECKLIST,
                t("dialog.daily.routine_section", "오늘 마감 업무"),
                t("dialog.daily.routine_count", "{count}건", count=len(items)),
                text_muted,
            )
        )
        self.routine_stat_value.setText(str(len(items)))
        if not items:
            layout.addWidget(self._empty_item(t("dialog.daily.no_routines", "오늘 마감인 업무가 없습니다.")))
            return section
        for name, pct_text, tags_text in items:
            frame = QFrame()
            frame.setObjectName("dailySummaryItem")
            row = QHBoxLayout(frame)
            row.setContentsMargins(12, 10, 12, 10)
            row.setSpacing(8)
            text = name + (f"  {pct_text}" if pct_text else "")
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(f"color:{text_primary}; font-size:13px; font-weight:650;")
            row.addWidget(label, 1)
            if tags_text:
                tag = QLabel(tags_text)
                tag.setObjectName("dailySummaryBadge")
                tag.setMaximumWidth(150)
                tag.setWordWrap(True)
                tag.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
                row.addWidget(tag)
            layout.addWidget(frame)
        return section

    def _empty_item(self, text):
        frame = QFrame()
        frame.setObjectName("dailySummaryItem")
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 9, 12, 9)
        label = QLabel(text.strip())
        label.setProperty("role", "helper")
        label.setWordWrap(True)
        row.addWidget(label)
        return frame

    def _build_summary_footer(self, layout, text_secondary, text_muted):
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background:{self._ui_tokens.get('border_soft', 'rgba(0,0,0,0.10)')}; max-height:1px;")
        layout.addWidget(divider)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 14, 0, 0)
        footer.setSpacing(8)
        self.disable_auto_btn = QPushButton(t("dialog.daily.disable_auto", "다시 알리지 않기"))
        self.disable_auto_btn.setIcon(_ic(ICON.ALARM, color=_icon_hex(text_muted)))
        self.disable_auto_btn.setAutoDefault(False)
        self.disable_auto_btn.setAccessibleDescription(
            t("dialog.daily.disable_auto_help", "앱 시작 및 매일 자동 표시를 모두 끕니다.")
        )
        self.disable_auto_btn.clicked.connect(self._disable_automatic_display)
        footer.addWidget(self.disable_auto_btn)
        footer.addStretch(1)
        self.ok_btn = QPushButton(t("btn.confirm", "확인"))
        self.ok_btn.setObjectName("primary_btn")
        self.ok_btn.setProperty("dialogFooter", True)
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)
        footer.addWidget(self.ok_btn)
        layout.addLayout(footer)

    def _build_settings_panel(self, text_primary, text_secondary, text_muted):
        panel = QWidget()
        panel.setMinimumWidth(390)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel(t("dialog.daily.settings_title", "노출 설정"))
        title.setProperty("role", "title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        close_btn = self._icon_button(ICON.CLOSE, t("common.close", "닫기"), text_muted)
        close_btn.clicked.connect(lambda: self._set_settings_open(False))
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        helper = QLabel(
            t("dialog.daily.settings_help", "보여줄 내용과 자동 표시 시점을 정합니다.")
        )
        helper.setProperty("role", "helper")
        helper.setWordWrap(True)
        layout.addWidget(helper)
        layout.addSpacing(4)

        layout.addLayout(
            self._build_visibility_row(
                "schedule",
                t("dialog.daily.schedule_section", "오늘의 일정"),
                t("dialog.daily.when_schedule", "일정 있을 때"),
            )
        )
        layout.addLayout(
            self._build_visibility_row(
                "routine",
                t("dialog.daily.routine_section", "오늘 마감 업무"),
                t("dialog.daily.when_routine", "업무 있을 때"),
            )
        )

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background:{self._ui_tokens.get('border_soft', 'rgba(0,0,0,0.10)')}; max-height:1px;")
        layout.addWidget(divider)
        layout.addSpacing(4)

        self.startup_toggle = self._switch(t("dialog.daily.startup_auto", "앱 시작 시 자동 표시"))
        layout.addLayout(self._labeled_control_row(self.startup_toggle.accessibleName(), self.startup_toggle))

        self.daily_toggle = self._switch(t("dialog.daily.daily_reminder", "매일 다시 알림"))
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setAccessibleName(t("dialog.daily.reminder_time", "알림 시간"))
        reminder_controls = QHBoxLayout()
        reminder_controls.setSpacing(8)
        reminder_controls.addWidget(self.time_edit)
        reminder_controls.addWidget(self.daily_toggle)
        reminder_widget = QWidget()
        reminder_widget.setLayout(reminder_controls)
        layout.addLayout(
            self._labeled_control_row(t("dialog.daily.daily_reminder", "매일 다시 알림"), reminder_widget)
        )
        self.daily_toggle.toggled.connect(self.time_edit.setEnabled)

        self.weekend_checkbox = QCheckBox(
            t("dialog.daily.hide_weekends", "주말에는 표시하지 않기")
        )
        self.weekend_checkbox.setAccessibleName(self.weekend_checkbox.text())
        layout.addWidget(self.weekend_checkbox)
        weekend_help = QLabel(
            t("dialog.daily.hide_weekends_help", "토요일과 일요일에는 브리핑을 자동으로 열지 않습니다.")
        )
        weekend_help.setProperty("role", "helper")
        weekend_help.setWordWrap(True)
        layout.addWidget(weekend_help)
        layout.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton(t("btn.cancel", "취소"))
        cancel.setObjectName("ghost_btn")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self._cancel_settings)
        save = QPushButton(t("btn.save", "저장"))
        save.setObjectName("primary_btn")
        save.setAutoDefault(False)
        save.clicked.connect(self._save_settings)
        self.settings_cancel_btn = cancel
        self.settings_save_btn = save
        footer.addWidget(cancel)
        footer.addWidget(save)
        layout.addLayout(footer)
        self._load_settings_controls()
        return panel

    def _build_visibility_row(self, section_key, label_text, when_text):
        row = QHBoxLayout()
        row.setSpacing(10)
        label = QLabel(_se(label_text))
        label.setProperty("role", "sectionTitle")
        label.setMinimumWidth(105)
        row.addWidget(label)
        group = QButtonGroup(self)
        group.setExclusive(True)
        buttons = {}
        for mode, text in (
            (_MODE_ALWAYS, t("dialog.daily.visibility_always", "항상")),
            (_MODE_WHEN_AVAILABLE, when_text),
            (_MODE_HIDDEN, t("dialog.daily.visibility_hidden", "숨김")),
        ):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.setAutoDefault(False)
            button.setAccessibleName(f"{_se(label_text)}: {text}")
            group.addButton(button)
            row.addWidget(button, 1)
            buttons[mode] = button
        self._visibility_buttons[section_key] = buttons
        return row

    def _labeled_control_row(self, label_text, control):
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setProperty("role", "sectionTitle")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(control)
        return row

    def _switch(self, accessible_name):
        switch = _ToggleSwitch(
            self._ui_tokens.get("accent", "#4da6ff"),
            self._ui_tokens.get("text_primary", "#172033"),
        )
        switch.setObjectName("dailySwitch")
        switch.setAccessibleName(accessible_name)
        return switch

    def _icon_button(self, icon_key, accessible_name, color):
        button = QToolButton()
        button.setIcon(_ic(icon_key, color=_icon_hex(color)))
        button.setAccessibleName(accessible_name)
        button.setToolTip(accessible_name)
        button.setFixedSize(38, 38)
        return button

    def _selected_visibility_mode(self, section_key):
        for mode, button in self._visibility_buttons[section_key].items():
            if button.isChecked():
                return mode
        return _MODE_ALWAYS

    def _load_settings_controls(self):
        schedule_mode = _visibility_mode(self._dialog_settings, _SETTINGS_KEY_SCHEDULE_MODE)
        routine_mode = _visibility_mode(self._dialog_settings, _SETTINGS_KEY_ROUTINE_MODE)
        self._visibility_buttons["schedule"][schedule_mode].setChecked(True)
        self._visibility_buttons["routine"][routine_mode].setChecked(True)
        self.startup_toggle.setChecked(
            _setting_bool(self._dialog_settings, _SETTINGS_KEY_STARTUP_ENABLED, True)
        )
        daily_enabled = _setting_bool(self._dialog_settings, _SETTINGS_KEY_DAILY_ENABLED, True)
        self.daily_toggle.setChecked(daily_enabled)
        self.time_edit.setEnabled(daily_enabled)
        time_value = str(self._dialog_settings.value(_SETTINGS_KEY_TIME, _DEFAULT_TIME))
        parsed_time = QTime.fromString(time_value, "HH:mm")
        self.time_edit.setTime(parsed_time if parsed_time.isValid() else QTime(8, 0))
        self.weekend_checkbox.setChecked(
            _setting_bool(self._dialog_settings, _SETTINGS_KEY_HIDE_WEEKENDS, False)
        )

    def _save_settings(self):
        self._dialog_settings.setValue(
            _SETTINGS_KEY_SCHEDULE_MODE, self._selected_visibility_mode("schedule")
        )
        self._dialog_settings.setValue(
            _SETTINGS_KEY_ROUTINE_MODE, self._selected_visibility_mode("routine")
        )
        self._dialog_settings.setValue(_SETTINGS_KEY_STARTUP_ENABLED, self.startup_toggle.isChecked())
        self._dialog_settings.setValue(_SETTINGS_KEY_DAILY_ENABLED, self.daily_toggle.isChecked())
        self._dialog_settings.setValue(
            _SETTINGS_KEY_TIME, self.time_edit.time().toString("HH:mm")
        )
        self._dialog_settings.setValue(
            _SETTINGS_KEY_HIDE_WEEKENDS, self.weekend_checkbox.isChecked()
        )
        self._dialog_settings.sync()
        self._apply_visibility_preferences()
        if not self.has_visible_sections:
            self._settings_open = False
            self.accept()
            return
        self._set_settings_open(False)

    def _cancel_settings(self):
        self._load_settings_controls()
        self._set_settings_open(False)

    def _disable_automatic_display(self):
        self._dialog_settings.setValue(_SETTINGS_KEY_STARTUP_ENABLED, False)
        self._dialog_settings.setValue(_SETTINGS_KEY_DAILY_ENABLED, False)
        self._dialog_settings.sync()
        self.accept()

    def _apply_visibility_preferences(self):
        schedule_mode = _visibility_mode(self._dialog_settings, _SETTINGS_KEY_SCHEDULE_MODE)
        routine_mode = _visibility_mode(self._dialog_settings, _SETTINGS_KEY_ROUTINE_MODE)
        show_schedule = schedule_mode == _MODE_ALWAYS or (
            schedule_mode == _MODE_WHEN_AVAILABLE and bool(self.schedule_items)
        )
        show_routine = routine_mode == _MODE_ALWAYS or (
            routine_mode == _MODE_WHEN_AVAILABLE and bool(self.routine_items)
        )
        self.schedule_section.setVisible(show_schedule)
        self.routine_section.setVisible(show_routine)
        self.has_visible_sections = show_schedule or show_routine

    def _set_settings_open(self, open_settings: bool):
        if self._settings_open == open_settings:
            return
        self._settings_open = open_settings
        if open_settings:
            self._load_settings_controls()
            screen = self.screen()
            available_width = screen.availableGeometry().width() if screen is not None else 1920
            self._settings_overlay_mode = available_width < self.EXPANDED_SIZE[0] + 48
            self.settings_panel.show()
            if self._settings_overlay_mode:
                self.summary_panel.hide()
                self.panel_divider.hide()
                target_width = self.COMPACT_SIZE[0]
            else:
                self.summary_panel.show()
                self.panel_divider.show()
                target_width = self.EXPANDED_SIZE[0]
            self._resize_preserving_screen(target_width, self.EXPANDED_SIZE[1])
            self.settings_save_btn.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.summary_panel.show()
            self.settings_panel.hide()
            self.panel_divider.hide()
            self._settings_overlay_mode = False
            self._resize_preserving_screen(*self.COMPACT_SIZE)
            self.settings_btn.setFocus(Qt.FocusReason.OtherFocusReason)

    def _resize_preserving_screen(self, width, height):
        old_top_left = self.frameGeometry().topLeft()
        self.setMinimumSize(0, 0)
        self._shell_layout.invalidate()
        self._shell_layout.activate()
        if self.layout() is not None:
            self.layout().invalidate()
            self.layout().activate()
        self.resize(width, height)
        self.setMinimumSize(width, height)
        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        x = min(max(old_top_left.x(), available.left()), available.right() - width + 1)
        y = min(max(old_top_left.y(), available.top()), available.bottom() - height + 1)
        self.move(x, y)

    def eventFilter(self, watched, event):
        if watched in getattr(self, "_drag_targets", ()):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if (
                event.type() == QEvent.Type.MouseMove
                and self._drag_origin is not None
                and event.buttons() & Qt.MouseButton.LeftButton
            ):
                self.move(event.globalPosition().toPoint() - self._drag_origin)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_origin = None
        return super().eventFilter(watched, event)

    def _load_schedule(self, today: str) -> list:
        try:
            rows = repo.get_schedule_tasks_overlapping_range_with_progress(today, today)
        except Exception:
            logger.exception("DailySummary: failed to load schedule")
            return []
        items = []
        for row in rows:
            name = row.get("name", "")
            deadline = str(row.get("deadline") or "")
            time_part = deadline[11:16] if len(deadline) > 10 else ""
            end = str(row.get("end_date") or "")
            end_time = end[11:16] if len(end) > 10 else ""
            is_all_day = bool(row.get("all_day"))
            if is_all_day:
                items.append(f"• {name}  [종일]")
            elif time_part:
                suffix = f" ~ {end_time}" if end_time else ""
                items.append(f"• {name}  {time_part}{suffix}")
            else:
                items.append(f"• {name}")
        return items

    def _load_due_routines(self, today: str) -> list:
        try:
            rows = repo.get_tasks_by_type_with_progress("routine")
        except Exception:
            logger.exception("DailySummary: failed to load routines")
            return []
        result = []
        for row in rows:
            status = str(row.get("status") or "").lower()
            if status in ("done", "completed") or row.get("is_completed"):
                continue
            target = str(row.get("target_date") or "")[:10]
            deadline = str(row.get("deadline") or "")[:10]
            due = target or deadline
            if due and due > today:
                continue
            prog = row.get("progress") or {}
            total = prog.get("total") or row.get("checklist_total", 0) or 0
            comp = prog.get("completed") or row.get("checklist_completed", 0) or 0
            pct_text = f"({comp}/{total})" if total > 0 else ""
            tags_raw = row.get("tags") or ""
            tag_list = [tg.strip() for tg in tags_raw.split(",") if tg.strip()]
            tags_text = " · ".join(tag_list) if tag_list else ""
            result.append((row.get("name", ""), pct_text, tags_text))
        return result


# ── Public API ────────────────────────────────────────────────────────────────


def maybe_show_daily_summary(app, trigger: str = "startup") -> None:
    """Show the briefing when the selected automatic-display rule allows it."""
    settings = getattr(app, "settings", None)
    if settings is None:
        return

    if trigger == "startup" and not _setting_bool(
        settings, _SETTINGS_KEY_STARTUP_ENABLED, True
    ):
        return
    if trigger == "daily" and not _setting_bool(settings, _SETTINGS_KEY_DAILY_ENABLED, True):
        return
    if _setting_bool(
        settings, _SETTINGS_KEY_HIDE_WEEKENDS, False
    ) and QDate.currentDate().dayOfWeek() in (6, 7):
        return

    today = _today_str()
    last_shown = settings.value(_SETTINGS_KEY_LAST_SHOWN, "")
    if last_shown == today:
        return

    try:
        dlg = DailySummaryDialog(parent=app)
        if not dlg.has_content or not dlg.has_visible_sections:
            dlg.deleteLater()
            return
        settings.setValue(_SETTINGS_KEY_LAST_SHOWN, today)
        dlg.exec()
    except Exception:
        logger.exception("DailySummary: dialog failed")


def schedule_daily_summary_timer(app) -> QTimer | None:
    """Set up a QTimer to fire at the configured time each day."""
    from PyQt6.QtCore import QTime as _QTime

    settings = getattr(app, "settings", None)
    if settings is None:
        return None

    timer = QTimer(app)
    timer.setSingleShot(False)

    def _fire():
        if not _setting_bool(settings, _SETTINGS_KEY_DAILY_ENABLED, True):
            return
        time_str = str(settings.value(_SETTINGS_KEY_TIME, _DEFAULT_TIME))
        try:
            hh, mm = [int(x) for x in time_str.split(":")]
        except (TypeError, ValueError):
            hh, mm = 8, 0
        now = _QTime.currentTime()
        target = _QTime(hh, mm)
        if abs(now.secsTo(target)) <= 65:
            maybe_show_daily_summary(app, trigger="daily")

    timer.timeout.connect(_fire)
    timer.start(60_000)
    return timer
