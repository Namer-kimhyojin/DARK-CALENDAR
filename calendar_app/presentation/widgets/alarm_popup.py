# -*- coding: utf-8 -*-
"""Alarm popup window shown when a task alarm fires."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
import re
import winsound

from PyQt6.QtCore import QDate, QLocale, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_metric_tokens
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.ui_tokens import get_ui_tokens

# ── Design constants ──────────────────────────────────────────────────────────
_W_BASE = 440  # logical pixels at 96 DPI — scaled at runtime via _popup_width()
_H = 180
_RADIUS = 12
_ACCENT = QColor(60, 140, 255)  # blue — default (task)
_ACCENT_WARN = QColor(255, 140, 60)  # orange — soon / overdue
_ACCENT_OK = QColor(46, 204, 113)  # green — confirmed
_ACCENT_ERROR = QColor(231, 76, 60)  # red — error/issue

_MIN_TEXT_PT = 11
_BLACK = QColor(0, 0, 0)
_WHITE = QColor(255, 255, 255)
_DEFAULT_CARD_BG = QColor(22, 22, 27)
_DEFAULT_BORDER = QColor(68, 68, 68)
_CSS_RGBA_FUNC = "rgb" + "a"

_SNOOZE_OPTIONS = [5, 10, 30, 60]  # minutes
_SNOOZE_DEFAULT_MINUTES = 5


def _popup_width() -> int:
    """DPI-aware popup width — scales _W_BASE by screen logical DPI."""
    try:
        screen = QApplication.primaryScreen()
        if screen:
            dpi_scale = screen.logicalDotsPerInch() / 96.0
            return int(max(340, min(640, _W_BASE * dpi_scale)))
    except Exception:
        pass
    return _W_BASE


_RGBA_COLOR_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)", re.IGNORECASE
)


def _parse_css_color(value: object, fallback: object) -> QColor:
    raw = str(value or "").strip()
    if raw:
        match = _RGBA_COLOR_RE.fullmatch(raw)
        if match:
            r, g, b, alpha_raw = match.groups()
            alpha = 255
            if alpha_raw is not None:
                alpha_float = float(alpha_raw)
                alpha = (
                    int(round(alpha_float * 255.0))
                    if alpha_float <= 1.0
                    else int(round(alpha_float))
                )
            return QColor(
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
                max(0, min(255, alpha)),
            )
        color = QColor(raw)
        if color.isValid():
            return color

    fallback_color = (
        QColor(fallback) if isinstance(fallback, QColor) else QColor(str(fallback or "black"))
    )
    if not fallback_color.isValid():
        fallback_color = QColor(_BLACK)
    return fallback_color


def _opaque_css_color(value: object, fallback: object) -> str:
    color = _parse_css_color(value, fallback)
    color.setAlpha(255)
    return color.name(QColor.NameFormat.HexRgb)


def _composite_opaque_css_color(value: object, fallback: object) -> str:
    color = _parse_css_color(value, fallback)
    if color.alpha() >= 255:
        color.setAlpha(255)
        return color.name(QColor.NameFormat.HexRgb)

    base = _parse_css_color(fallback, _BLACK)
    alpha = color.alpha() / 255.0
    inv = 1.0 - alpha
    blended = QColor(
        int(round(color.red() * alpha + base.red() * inv)),
        int(round(color.green() * alpha + base.green() * inv)),
        int(round(color.blue() * alpha + base.blue() * inv)),
        255,
    )
    return blended.name(QColor.NameFormat.HexRgb)


def _get_contrast_text_color(bg_color: QColor) -> str:
    """Return black or white text depending on background luminance."""
    # Standard luminance calculation: 0.299*R + 0.587*G + 0.114*B
    luminance = (
        0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()
    ) / 255.0
    return (
        _BLACK.name(QColor.NameFormat.HexRgb)
        if luminance > 0.6
        else _WHITE.name(QColor.NameFormat.HexRgb)
    )


def _alarm_popup_style_bundle(tokens=None, metrics=None, settings=None) -> dict:
    resolved_tokens = dict(get_ui_tokens(settings=settings, opacity_factor=1.0))
    if tokens:
        resolved_tokens.update(tokens)
    resolved_metrics = dict(get_dialog_metric_tokens(settings=settings))
    if metrics:
        resolved_metrics.update(metrics)

    accent = QColor(str(resolved_tokens["accent"]))
    if not accent.isValid():
        accent = QColor(_ACCENT)
    accent_hover = QColor(
        str(resolved_tokens.get("accent_hover") or accent.name(QColor.NameFormat.HexRgb))
    )
    if not accent_hover.isValid():
        accent_hover = QColor(accent).lighter(112)
    accent_pressed = QColor(accent)
    accent_pressed = accent_pressed.darker(118)

    success = QColor(str(resolved_tokens["success_hex"]))
    warning = QColor(str(resolved_tokens["warning_hex"]))
    danger = QColor(str(resolved_tokens["danger_hex"]))

    card_radius = max(_RADIUS, int(resolved_metrics.get("button_radius", 5)) + 7)
    button_radius = max(6, int(resolved_metrics.get("button_radius", 5)) + 1)
    menu_radius = max(6, int(resolved_metrics.get("list_radius", 6)))
    menu_item_radius = max(4, int(resolved_metrics.get("list_item_radius", 4)))
    text_pt = max(_MIN_TEXT_PT, int(resolved_metrics.get("subtitle_font_pt", _MIN_TEXT_PT)))
    card_bg = _opaque_css_color(resolved_tokens.get("bg_main"), _DEFAULT_CARD_BG)
    card_surface = _opaque_css_color(resolved_tokens.get("bg_alt"), card_bg)
    card_hover = _composite_opaque_css_color(
        resolved_tokens.get("bg_item_hover") or resolved_tokens.get("bg_hover"),
        card_surface,
    )

    # 대비색 계산
    text_on_accent = _get_contrast_text_color(accent)

    # 테두리 가시성 보강: 너무 흐릿한 경우(알파값이 낮은 경우) 보정
    raw_border = resolved_tokens["border"]
    border_color = _parse_css_color(raw_border, _DEFAULT_BORDER)
    if border_color.alpha() < 60:
        # 가시성이 너무 낮으면 조금 더 진하게 (검정 배경 대비 가이드)
        border_color.setAlpha(80)
    card_border = (
        f"{_CSS_RGBA_FUNC}({border_color.red()}, {border_color.green()}, "
        f"{border_color.blue()}, {border_color.alpha() / 255.0})"
    )

    return {
        "tokens": resolved_tokens,
        "metrics": resolved_metrics,
        "card_bg_source": str(resolved_tokens.get("bg_main") or ""),
        "card_surface_source": str(resolved_tokens.get("bg_alt") or ""),
        "card_radius": card_radius,
        "button_radius": button_radius,
        "menu_radius": menu_radius,
        "menu_item_radius": menu_item_radius,
        "text_pt": text_pt,
        "title_pt": max(13, int(resolved_metrics.get("title_font_pt", 15)) - 2),
        "card_bg": card_bg,
        "card_border": card_border,
        "card_surface": card_surface,
        "card_hover": card_hover,
        "text_primary": resolved_tokens["text_primary"],
        "text_secondary": resolved_tokens["text_secondary"],
        "text_muted": resolved_tokens["text_muted"],
        "text_on_accent": text_on_accent,
        "accent": accent,
        "accent_hover": accent_hover,
        "accent_pressed": accent_pressed,
        "accent_warn": warning if warning.isValid() else QColor(_ACCENT_WARN),
        "accent_ok": success if success.isValid() else QColor(_ACCENT_OK),
        "accent_error": danger if danger.isValid() else QColor(_ACCENT_ERROR),
    }


def _build_alarm_popup_menu_stylesheet(bundle: dict) -> str:
    return f"""
QMenu {{
    /* background-color: {bundle.get("card_surface_source", "")}; */
    background-color: {bundle["card_surface"]};
    border: 1px solid {bundle["card_border"]};
    border-radius: {bundle["menu_radius"]}px;
    padding: 4px;
    font-family: 'Segoe UI Emoji', 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: {bundle["text_pt"]}pt;
    color: {bundle["text_primary"]};
}}
QMenu::item {{
    background-color: transparent;
    padding: 6px 20px 6px 12px;
    border-radius: {bundle["menu_item_radius"]}px;
}}
QMenu::item:selected {{
    background-color: {bundle["card_hover"]};
}}
"""


def _build_alarm_popup_stylesheet(bundle: dict) -> str:
    return f"""
QWidget#AlarmPopupRoot {{
    background: transparent;
}}
QFrame#AlarmCard {{
    /* background: {bundle.get("card_bg_source", "")}; */
    background: {bundle["card_bg"]};
    border: 1px solid {bundle["card_border"]};
    border-radius: {bundle["card_radius"]}px;
}}
QWidget#AlarmContent {{
    background: transparent;
}}
QLabel#AlarmIcon {{
    color: {bundle["accent"].name(QColor.NameFormat.HexRgb)};
    font-size: 16px;
    background: transparent;
}}
QLabel#TaskTitle {{
    color: {bundle["text_primary"]};
    font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: {bundle["title_pt"]}pt;
    font-weight: bold;
    background: transparent;
}}
QLabel#TimeLabel {{
    color: {bundle["text_secondary"]};
    font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: {bundle["text_pt"]}pt;
    background: transparent;
}}
QLabel#LocationLabel {{
    color: {bundle["text_muted"]};
    font-family: 'Segoe UI Emoji', 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: {bundle["text_pt"]}pt;
    background: transparent;
}}
QPushButton#ConfirmBtn {{
    background: {bundle["accent"].name(QColor.NameFormat.HexRgb)};
    color: {bundle["text_on_accent"]};
    border: none;
    border-radius: {bundle["button_radius"]}px;
    font-family: 'Segoe UI Emoji', 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: 12pt;
    font-weight: bold;
    padding: 0px 16px;
    min-height: 32px;
    min-width: 80px;
}}
QPushButton#ConfirmBtn:hover {{
    background: {bundle["accent_hover"].name(QColor.NameFormat.HexRgb)};
}}
QPushButton#ConfirmBtn:pressed {{
    background: {bundle["accent_pressed"].name(QColor.NameFormat.HexRgb)};
}}
QToolButton#SnoozeBtn {{
    background: {bundle["card_surface"]};
    color: {bundle["text_primary"]};
    border: 1.5px solid {bundle["card_border"]};
    border-radius: {bundle["button_radius"]}px;
    font-family: 'Segoe UI Emoji', 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: {bundle["text_pt"]}pt;
    padding: 0px 12px;
    min-height: 32px;
    min-width: 80px;
}}
QToolButton#SnoozeBtn:hover {{
    background: {bundle["card_hover"]};
    color: {bundle["text_primary"]};
    border-color: {bundle["accent"].name(QColor.NameFormat.HexRgb)};
}}
QToolButton#SnoozeBtn::menu-indicator {{
    image: none;
    width: 0px;
}}
QPushButton#DoneBtn {{
    background: transparent;
    color: {bundle["accent_ok"].name(QColor.NameFormat.HexRgb)};
    border: 1.5px solid {bundle["accent_ok"].name(QColor.NameFormat.HexRgb)};
    border-radius: {bundle["button_radius"]}px;
    font-family: 'Segoe UI Emoji', 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: 11pt;
    font-weight: bold;
    padding: 0px 12px;
    min-height: 32px;
    min-width: 60px;
}}
QPushButton#DoneBtn:hover {{
    background: {bundle["accent_ok"].name(QColor.NameFormat.HexRgb)};
    color: {_get_contrast_text_color(bundle["accent_ok"])};
}}
QPushButton#CloseBtn {{
    background: transparent;
    color: {bundle["text_muted"]};
    border: none;
    font-size: 14px;
    min-width: 20px;
    min-height: 20px;
    max-width: 20px;
    max-height: 20px;
    border-radius: {bundle["card_radius"] - 2}px;
    padding: 0;
}}
QPushButton#CloseBtn:hover {{
    background: {bundle["card_hover"]};
    color: {bundle["text_secondary"]};
}}
{_build_alarm_popup_menu_stylesheet(bundle)}
"""


def _alarm_time_label_style(state: str, bundle: dict) -> str:
    color = bundle["text_secondary"]
    if state == "warning":
        color = bundle["accent_warn"].name(QColor.NameFormat.HexRgb)
    elif state == "danger":
        color = bundle["accent_error"].name(QColor.NameFormat.HexRgb)
    return (
        f"color: {color}; font-size: {bundle['text_pt']}pt; background: transparent;"
        "font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;"
    )


class AlarmPopupWindow(QWidget):
    """Frameless alarm popup shown when a task alarm fires.

    Signals
    -------
    confirmed(task_id)  — user dismissed / confirmed the alarm
    snoozed(task_id, minutes)  — user chose to snooze
    completed(task_id) — user marked task as done
    """

    confirmed = pyqtSignal(int)
    snoozed = pyqtSignal(int, int)
    completed = pyqtSignal(int)

    def __init__(
        self,
        task: dict,
        deadline_dt: datetime,
        on_open_task: Callable[[int], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowOpacity(1.0)
        self.setObjectName("AlarmPopupRoot")
        self._style_bundle = _alarm_popup_style_bundle(settings=getattr(parent, "settings", None))
        self._menu_stylesheet = _build_alarm_popup_menu_stylesheet(self._style_bundle)
        self.setStyleSheet(_build_alarm_popup_stylesheet(self._style_bundle))

        self._task = task
        self._task_id: int = task.get("id", -1)
        self._deadline_dt = deadline_dt
        self._on_open_task = on_open_task

        # Determine accent colour from deadline proximity
        self._accent = self._pick_accent()

        _settings = QSettings("kimhyojin", "Dark Calendar")
        self._default_snooze = int(_settings.value("alarm/default_snooze", _SNOOZE_DEFAULT_MINUTES))

        self._build_ui()
        self.setFixedWidth(_popup_width())
        self.adjustSize()
        self._position_on_screen()

        # Live clock — updates "time remaining" label every 30 s
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(30_000)
        self._tick_timer.timeout.connect(self._refresh_time_label)
        self._tick_timer.start()

        # Auto-snooze timer — duration from user settings
        self._auto_snooze_timer = QTimer(self)
        self._auto_snooze_timer.setSingleShot(True)
        self._auto_snooze_timer.setInterval(self._default_snooze * 60 * 1000)
        self._auto_snooze_timer.timeout.connect(lambda: self._on_snooze(self._default_snooze))
        self._auto_snooze_timer.start()

        # Play notification sound
        self._play_notification_sound()

    def _play_notification_sound(self) -> None:
        """Play the Windows notification sound without Qt Multimedia/FFmpeg."""
        with suppress(Exception):
            winsound.PlaySound(
                "SystemNotification",
                winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Card frame
        card = QFrame(self)
        card.setObjectName("AlarmCard")
        root_layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Colour accent bar (drawn via paintEvent on an inner widget)
        self._accent_bar = _AccentBar(self._accent, self._style_bundle["card_radius"], card)
        card_layout.addWidget(self._accent_bar)

        # Content area
        content = QWidget(card)
        content.setObjectName("AlarmContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 10, 12, 14)
        content_layout.setSpacing(4)

        # Header row: bell + title + close
        header = QHBoxLayout()
        header.setSpacing(6)

        _bell_icon_key = ICON.WARNING if self._task.get("type") == "sync_issue" else ICON.ALARM
        bell = QLabel(content)
        bell.setObjectName("AlarmIcon")
        bell.setPixmap(_ic(_bell_icon_key).pixmap(16, 16))
        bell.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header.addWidget(bell)

        title_text = self._task.get("name") or t("alarm_popup.task", "작업")
        self._title_label = QLabel(title_text, content)
        self._title_label.setObjectName("TaskTitle")
        self._title_label.setWordWrap(True)
        self._title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self._title_label, 1)

        close_btn = QPushButton("", content)
        close_btn.setIcon(_ic(ICON.CLOSE))
        close_btn.setObjectName("CloseBtn")
        # X dismisses with default snooze rather than confirming,
        # so the alarm can re-fire.  Use _on_confirm only for the 확인 button.
        close_btn.clicked.connect(lambda: self._on_snooze(self._default_snooze))
        close_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(close_btn)

        content_layout.addLayout(header)

        # Time remaining
        self._time_label = QLabel(content)
        self._time_label.setObjectName("TimeLabel")
        self._refresh_time_label()
        content_layout.addWidget(self._time_label)

        # Location (if present)
        location = str(self._task.get("location") or "").strip()
        if location:
            loc_label = QLabel(location, content)
            loc_label.setObjectName("LocationLabel")
            loc_label.setWordWrap(True)
            content_layout.addWidget(loc_label)

        content_layout.addSpacing(6)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 0, 0, 0)

        if self._task.get("type") == "sync_issue":
            # View Issues button
            view_issues_btn = QPushButton(t("alarm_popup.view_issues", "문제 보기"))
            view_issues_btn.setObjectName("ConfirmBtn")  # Reuse accent styling
            view_issues_btn.clicked.connect(self._on_open_task)

            # Close button
            close_btn = QPushButton(t("common.close", "닫기"))
            close_btn.setObjectName("DoneBtn")  # Reuse secondary styling
            close_btn.clicked.connect(self.close)

            btn_row.addWidget(view_issues_btn)
            btn_row.addStretch()
            btn_row.addWidget(close_btn)
        else:
            # Snooze button (with drop-up menu)
            self._snooze_btn = QToolButton()
            self._snooze_btn.setObjectName("SnoozeBtn")
            self._snooze_btn.setText(t("alarm_popup.snooze_btn", "스누즈"))
            self._snooze_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

            # Create menu WITHOUT parent to avoid inheriting transparency/translucency
            snooze_menu = QMenu()
            snooze_menu.setWindowOpacity(1.0)
            snooze_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            snooze_menu.setStyleSheet(self._menu_stylesheet)

            for mins in _SNOOZE_OPTIONS:
                label = (
                    t("alarm_popup.snooze_min", "{mins}분 후").replace("{mins}", str(mins))
                    if mins < 60
                    else t("alarm_popup.snooze_1h", "1시간 후")
                )
                snooze_menu.addAction(label, lambda m=mins: self._on_snooze(m))
            self._snooze_btn.setMenu(snooze_menu)

            # Done button
            done_btn = QPushButton(t("alarm_popup.done_btn", "완료"))
            done_btn.setObjectName("DoneBtn")
            done_btn.clicked.connect(self._on_done)

            # Confirm button
            confirm_btn = QPushButton(t("alarm_popup.confirm_btn", "확인"))
            confirm_btn.setObjectName("ConfirmBtn")
            confirm_btn.clicked.connect(self._on_confirm)

            # Add to row
            btn_row.addWidget(self._snooze_btn)
            btn_row.addWidget(done_btn)
            btn_row.addStretch()
            btn_row.addWidget(confirm_btn)

        content_layout.addLayout(btn_row)
        card_layout.addWidget(content)

    def _pick_accent(self) -> QColor:
        if self._task.get("type") == "sync_issue":
            return QColor(self._style_bundle["accent_error"])
        now = datetime.now()
        delta_secs = (self._deadline_dt - now).total_seconds()
        if delta_secs < 0:
            return QColor(self._style_bundle["accent_warn"])
        if delta_secs < 15 * 60:
            return QColor(self._style_bundle["accent_warn"])
        return QColor(self._style_bundle["accent"])

    def _refresh_time_label(self) -> None:
        now = datetime.now()
        delta = self._deadline_dt - now
        total_mins = int(delta.total_seconds() / 60)
        loc = QLocale()
        if total_mins > 0:
            state = "default"
            if total_mins < 60:
                text = t("alarm_popup.time_remaining", "{mins}분 후").replace(
                    "{mins}", str(total_mins)
                )
            elif total_mins < 1440:
                hours = total_mins // 60
                mins = total_mins % 60
                if mins:
                    text = (
                        t("alarm_popup.time_remaining_hm", "{h}시간 {m}분 후")
                        .replace("{h}", str(hours))
                        .replace("{m}", str(mins))
                    )
                else:
                    text = t("alarm_popup.time_remaining_h", "{h}시간 후").replace(
                        "{h}", str(hours)
                    )
            else:
                deadline_qdate = QDate(
                    self._deadline_dt.year, self._deadline_dt.month, self._deadline_dt.day
                )
                date_str = loc.toString(
                    deadline_qdate, loc.dateFormat(QLocale.FormatType.ShortFormat)
                )
                time_str = self._deadline_dt.strftime("%H:%M")
                text = f"{date_str} {time_str}"
        elif total_mins == 0:
            text = t("alarm_popup.time_now", "지금")
            state = "warning"
        else:
            abs_mins = abs(total_mins)
            state = "danger"
            if abs_mins < 60:
                text = t("alarm_popup.time_past", "{mins}분 지남").replace("{mins}", str(abs_mins))
            else:
                hours = abs_mins // 60
                text = t("alarm_popup.time_past_h", "{h}시간 지남").replace("{h}", str(hours))
        self._time_label.setText(text)
        self._time_label.setStyleSheet(_alarm_time_label_style(state, self._style_bundle))

    def _position_on_screen(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 16
            y = geo.bottom() - self.height() - 16
            self.move(x, y)

    def _on_confirm(self) -> None:
        self._tick_timer.stop()
        if hasattr(self, "_auto_snooze_timer"):
            self._auto_snooze_timer.stop()
        self.confirmed.emit(self._task_id)
        self.close()

    def _on_snooze(self, minutes: int) -> None:
        self._tick_timer.stop()
        if hasattr(self, "_auto_snooze_timer"):
            self._auto_snooze_timer.stop()
        self.snoozed.emit(self._task_id, minutes)
        self.close()

    def _on_done(self) -> None:
        self._tick_timer.stop()
        if hasattr(self, "_auto_snooze_timer"):
            self._auto_snooze_timer.stop()
        self.completed.emit(self._task_id)
        self.close()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_drag_start"):
            self.move(event.globalPosition().toPoint() - self._drag_start)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_drag_start"):
            del self._drag_start


class _AccentBar(QWidget):
    def __init__(self, color: QColor, radius: int, parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self._radius = radius
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        r = self._radius
        path.moveTo(r, 0)
        path.arcTo(0, 0, r * 2, r * 2, 90, 90)
        path.lineTo(0, self.height())
        path.lineTo(self.width(), self.height())
        path.arcTo(self.width() - r * 2, 0, r * 2, r * 2, 0, 90)
        path.closeSubpath()
        p.fillPath(path, self._color)
