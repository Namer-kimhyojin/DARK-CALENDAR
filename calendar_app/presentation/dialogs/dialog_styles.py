import re

from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QCalendarWidget, QDateEdit, QDialog, QHeaderView, QTableView

from calendar_app.shared.color_utils import (
    parse_css_alpha_to_unit,
    parse_hex_color,
    shift_rgb,
)
from calendar_app.shared.theme_snapshot import (
    DIALOG_METRIC_BOUNDS as SHARED_DIALOG_METRIC_BOUNDS,
)
from calendar_app.shared.theme_snapshot import (
    DIALOG_METRIC_DEFAULTS as SHARED_DIALOG_METRIC_DEFAULTS,
)
from calendar_app.shared.theme_snapshot import (
    build_dialog_base_tokens,
    get_color_token_overrides,
    get_metric_token_overrides,
    normalize_color_token,
    normalize_metric_token_value,
    set_color_token_overrides,
    set_metric_token_overrides,
)
from calendar_app.shared.theme_snapshot import (
    build_dialog_metric_tokens as build_shared_dialog_metric_tokens,
)
from calendar_app.shared.ui_tokens import get_shared_qss, get_ui_tokens

FIXED_DIALOG_STYLE = """
    QDialog {
        background-color: #16161b;
        color: #e1e1e6;
        font-family: 'Segoe UI Emoji', 'Segoe UI', 'Inter', 'Malgun Gothic', sans-serif;
        font-size: 14px;
    }
    QWidget {
        color: #e1e1e6;
    }
    QTabWidget {
        background-color: #13131a;
    }
    QTabBar {
        background-color: #13131a;
    }
    QTabWidget::pane {
        border: 1px solid #2a2a33;
        background: #111116;
        top: -1px;
        border-radius: 0 0 10px 10px;
    }
    QTabBar::tab {
        background: #1c1c23;
        color: #9a9aaa;
        padding: 8px 22px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        border-bottom-left-radius: 0px;
        border-bottom-right-radius: 0px;
        min-width: 80px;
        font-size: 14px;
        font-weight: 600;
        margin-right: 3px;
        border: 1px solid #28282f;
        border-bottom: none;
    }
    QTabBar::tab:hover {
        background: #22222a;
        color: #d0d0da;
    }
    QTabBar::tab:selected {
        background: #111116;
        color: #4da6ff;
        border: 1px solid #35353f;
        border-top: 2px solid #4da6ff;
        border-bottom: 1px solid #111116;
        margin-bottom: -1px;
    }
    QLabel[role="dialogTitle"], QLabel#dialogTitle, QLabel#dialog_title {
        color: #e1e1e6;
        font-size: 16px;
        font-weight: 700;
    }
    QLabel[role="dialogSubtitle"], QLabel#dialogSubtitle, QLabel#dialog_subtitle {
        color: #9aa0ad;
        font-size: 12px;
        font-weight: 500;
    }
    QLabel {
        color: #9aa0ad;
        font-weight: 600;
        font-size: 13px;
        margin-top: 2px;
        margin-bottom: 2px;
    }
    QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {
        background-color: #111116;
        color: #e8e8f0;
        border: 1px solid #2e2e38;
        border-radius: 7px;
        padding: 4px 10px;
        font-size: 14px;
        min-height: 34px;
        max-height: 34px;
        selection-background-color: rgba(77, 166, 255, 0.25);
    }
    QTextEdit, QPlainTextEdit {
        background-color: #111116;
        color: #e8e8f0;
        border: 1px solid #2e2e38;
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 14px;
        selection-background-color: rgba(77, 166, 255, 0.25);
    }
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
    QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
        border: 1px solid #4da6ff;
        background-color: #111116; /* FOCUS_MATCH */
    }
    QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTimeEdit:hover, QSpinBox:hover {
        border-color: #3d3d4a;
    }
    QLineEdit::placeholder {
        color: #555562;
    }
    QComboBox::drop-down {
        border: none;
        width: 28px;
    }
    QComboBox QAbstractItemView {
        background-color: #111116;
        border: 1px solid #2e2e38;
        selection-background-color: rgba(77, 166, 255, 0.25);
        color: #e8e8f0;
        outline: none;
    }
    QComboBox::down-arrow {
        width: 12px;
        height: 12px;
    }
    QPushButton {
        background-color: #1e1e26;
        color: #c8ccd4;
        font-family: 'Segoe UI Emoji', 'Segoe UI', 'Inter', 'Malgun Gothic', sans-serif;
        font-weight: 600;
        padding: 4px 16px;
        border-radius: 8px;
        font-size: 14px;
        min-height: 34px;
        max-height: 34px;
        border: 1px solid #32323c;
    }
    QPushButton:hover {
        background-color: #26262f;
        border-color: #44444f;
        color: #ffffff;
    }
    QPushButton:pressed {
        background-color: #18181f;
    }
    QPushButton[default="true"], QPushButton:default {
        background-color: rgba(77, 166, 255, 0.10);
        border-color: rgba(77, 166, 255, 0.55);
        color: #4da6ff;
        font-weight: 700;
    }
    QPushButton[default="true"]:hover, QPushButton:default:hover {
        background-color: rgba(77, 166, 255, 0.18);
        border-color: #4da6ff;
        color: #ffffff;
    }
    QPushButton#primary_btn {
        background-color: rgba(77, 166, 255, 0.10);
        border-color: rgba(77, 166, 255, 0.55);
        color: #4da6ff;
        font-weight: 700;
    }
    QPushButton#primary_btn:hover {
        background-color: rgba(77, 166, 255, 0.18);
        border-color: #4da6ff;
        color: #ffffff;
    }
    QPushButton#success_btn {
        background-color: rgba(53, 182, 106, 0.14);
        border-color: rgba(53, 182, 106, 0.42);
        color: #35b66a;
        font-weight: 700;
    }
    QPushButton#success_btn:hover {
        background-color: rgba(53, 182, 106, 0.22);
        border-color: #35b66a;
        color: #ffffff;
    }
    QPushButton#ghost_btn {
        background-color: #18181f;
        color: #9aa0ad;
        border: 1px solid #2e2e38;
    }
    QPushButton#ghost_btn:hover {
        background-color: #22222a;
        color: #e0e0e8;
        border-color: #42424e;
    }
    QPushButton#danger_btn {
        background-color: transparent;
        color: #d25a66;
        border: 1px solid rgba(210, 90, 102, 0.35);
        font-weight: 600;
    }
    QPushButton#danger_btn:hover {
        background-color: rgba(210, 90, 102, 0.12);
        color: #e87080;
        border: 1px solid rgba(210, 90, 102, 0.65);
    }
    QListWidget, QTableView, QTableWidget {
        background: #111116;
        color: #e1e1e6;
        border: 1px solid #2a2a33;
        border-radius: 8px;
        padding: 4px;
        gridline-color: #222229;
        outline: none;
    }
    QListWidget::item {
        padding: 9px 10px;
        border-radius: 5px;
        margin-bottom: 1px;
    }
    QListWidget::item:hover {
        background-color: rgba(255, 255, 255, 0.04);
    }
    QListWidget::item:selected {
        background-color: rgba(77, 166, 255, 0.12);
        border: 1px solid rgba(77, 166, 255, 0.25);
        color: #6db8ff;
        font-weight: 700;
    }
    QHeaderView::section {
        background-color: #1e1e26;
        color: #7a7a8a;
        padding: 9px 10px;
        border: none;
        border-bottom: 1px solid #2a2a33;
        font-weight: 700;
        font-size: 13px;
    }
    QCheckBox, QRadioButton {
        color: #c8ccd4;
        font-size: 14px;
        spacing: 9px;
        font-weight: 500;
        min-height: 26px;
    }
    QCheckBox::indicator {
        width: 17px;
        height: 17px;
        border: 1.5px solid #3a3a46;
        background: #18181f;
        border-radius: 4px;
    }
    QCheckBox::indicator:hover {
        border-color: #4da6ff;
        background: #1e1e28;
    }
    QCheckBox::indicator:checked {
        background-color: #4da6ff;
        border-color: #4da6ff;
        image: none;
    }
    QRadioButton::indicator {
        width: 17px;
        height: 17px;
        border: 1.5px solid #3a3a46;
        background: #18181f;
        border-radius: 9px;
    }
    QRadioButton::indicator:hover {
        border-color: #4da6ff;
        background: #1e1e28;
    }
    QRadioButton::indicator:checked {
        background-color: #4da6ff;
        border-color: #4da6ff;
        image: none;
    }
    QGroupBox {
        border: 1px solid #252530;
        border-radius: 9px;
        margin-top: 18px;
        padding-top: 22px;
        padding-bottom: 6px;
        font-size: 13px;
        font-weight: 700;
        color: #c0c4cc;
        background-color: #13131a;
    }
    QGroupBox::title {
        subcontrol-origin: border;
        subcontrol-position: top left;
        left: 14px;
        top: -10px;
        padding: 1px 9px;
        background-color: #13131a;
        color: #5aabf0;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    QScrollArea {
        border: none;
        background-color: transparent;
    }
    QScrollBar:vertical {
        border: none;
        background: #0e0e13;
        width: 8px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #32323c;
        min-height: 24px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover {
        background: #48484f;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        border: none;
        background: #0e0e13;
        height: 8px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background: #32323c;
        min-width: 24px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #48484f;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #2e2e38;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #4a4a58;
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        background: #4da6ff;
    }
    QToolButton {
        background: #1e1e26;
        border: 1px solid #32323c;
        border-radius: 6px;
        padding: 4px 6px;
        color: #c8ccd4;
        font-size: 13px;
    }
    QToolButton:hover {
        background: #26262f;
        border-color: #44444f;
        color: #ffffff;
    }
    QCalendarWidget QWidget {
        alternate-background-color: #111116;
    }
    QCalendarWidget QWidget#qt_calendar_navigationbar {
        background-color: #1c1c23;
        border-bottom: 1px solid #2a2a33;
        min-height: 34px;
        padding: 0 4px;
    }
    QCalendarWidget QToolButton {
        color: #e1e1e6;
        font-weight: 600;
        background-color: transparent;
        border: none;
        border-radius: 5px;
        margin: 0px;
        padding: 0px;
        min-width: 24px;
        min-height: 24px;
        qproperty-iconSize: 16px 16px;
    }
    QCalendarWidget QToolButton:hover {
        background-color: #26262f;
    }
    QCalendarWidget QAbstractItemView {
        background-color: #111116;
        color: #e1e1e6;
        selection-background-color: rgba(77, 166, 255, 0.20);
        selection-color: #ffffff;
        outline: none;
    }
    QCalendarWidget QSpinBox#qt_calendar_yearedit {
        background: #111116;
        color: #e1e1e6;
        border: 1px solid #2e2e38;
        selection-background-color: rgba(77, 166, 255, 0.20);
    }
    QCalendarWidget QMenu#qt_calendar_monthmenu {
        background-color: #1c1c23;
        color: #e1e1e6;
        border: 1px solid #2a2a33;
    }
    QCalendarWidget QTableView {
        background-color: #111116;
        alternate-background-color: #111116;
        outline: 0;
        gridline-color: transparent;
    }
    /* ── Inline field validation ─────────────────────────────────── */
    QLineEdit[state="error"], QTextEdit[state="error"], QComboBox[state="error"] {
        border: 1px solid #e05555;
        background-color: rgba(224, 85, 85, 0.06);
    }
    QLineEdit[state="error"]:focus, QTextEdit[state="error"]:focus {
        border: 1px solid #ff6b6b;
        background-color: rgba(224, 85, 85, 0.08);
    }
    QLineEdit[state="success"], QTextEdit[state="success"] {
        border: 1px solid #35b66a;
    }
    QLabel[role="field_error"] {
        color: #e05555;
        font-size: 11px;
        font-weight: 500;
        margin-top: 0px;
        margin-bottom: 2px;
    }
    QLabel[role="field_hint"] {
        color: #5a6270;
        font-size: 11px;
        font-weight: 400;
        margin-top: 0px;
        margin-bottom: 2px;
    }
    /* ── Collapsible section toggle ───────────────────────────────── */
    QPushButton#collapsible_toggle {
        background: transparent;
        border: none;
        color: #6a7888;
        font-weight: 600;
        font-size: 12px;
        text-align: left;
        padding: 3px 0px;
        min-height: 24px;
        max-height: 24px;
    }
    QPushButton#collapsible_toggle:hover {
        color: #b0bac8;
    }
    QPushButton#collapsible_toggle[expanded="true"] {
        color: #8ab4d4;
    }
"""

_DIALOG_BASE_MARKER = "/* DC_DIALOG_BASE */"
_DIALOG_TOKEN_OVERRIDE_PREFIX = "dialog_token."
_RGBA_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)

# Editable color tokens exposed by the dialog token editor.
DIALOG_TOKEN_EDITABLE_KEYS = (
    "accent",
    "text_primary",
    "text_secondary",
    "text_muted",
    "text_faint",
    "placeholder_text",
    "surface_bg",
    "surface_alt",
    "surface_item",
    "surface_hover",
    "surface_top",
    "title_bg",
    "title_text",
    "title_subtext",
    "tab_strip_bg",
    "tab_idle_bg",
    "tab_active_bg",
    "tab_text",
    "tab_text_hover",
    "tab_text_active",
    "border",
    "border_soft",
    "list_selected_bg",
    "list_selected_border",
    "list_selected_text",
    "list_hover_bg",
    "table_header_bg",
    "table_header_text",
    "check_indicator_bg",
    "check_indicator_border",
    "check_checked_bg",
    "check_checked_border",
    "button_base_bg",
    "button_base_text",
    "button_base_border",
    "button_base_hover_bg",
    "button_base_hover_text",
    "button_base_hover_border",
    "button_pressed_bg",
    "button_pressed_text",
    "button_pressed_border",
    "button_disabled_bg",
    "button_disabled_text",
    "button_disabled_border",
    "button_primary_bg",
    "button_primary_text",
    "button_primary_border",
    "button_primary_hover_bg",
    "button_primary_hover_text",
    "button_primary_hover_border",
    "button_ghost_bg",
    "button_ghost_text",
    "button_ghost_border",
    "button_ghost_hover_bg",
    "button_ghost_hover_text",
    "button_ghost_hover_border",
    "button_success_bg",
    "button_success_text",
    "button_success_border",
    "button_success_hover_bg",
    "button_success_hover_text",
    "button_success_hover_border",
    "button_danger_bg",
    "button_danger_text",
    "button_danger_border",
    "button_danger_hover_bg",
    "button_danger_hover_text",
    "button_danger_hover_border",
    "toolbutton_bg",
    "toolbutton_text",
    "toolbutton_border",
    "toolbutton_hover_bg",
    "toolbutton_hover_text",
    "toolbutton_hover_border",
    "toolbutton_pressed_bg",
    "toolbutton_pressed_text",
    "toolbutton_pressed_border",
    "toolbutton_disabled_bg",
    "toolbutton_disabled_text",
    "toolbutton_disabled_border",
)

# Standard dialog size presets — use with apply_common_dialog_style(size=DIALOG_SIZES["..."])
DIALOG_SIZES: dict[str, tuple[int, int]] = {
    "settings_large": (1020, 680),  # gcal_settings, 다중 탭 설정
    "settings_medium": (900, 620),  # pomodoro, away, label
    "editor": (620, 680),  # task_dialog, directive_dialog, checklist
    "picker": (700, 560),  # panel_color_picker
    "report": (620, 620),  # eod_report
    "small": (400, 300),  # recurring_event, 단순 확인 다이얼로그
}

# Editable metric tokens exposed by the dialog token editor.
DIALOG_METRIC_DEFAULTS = dict(SHARED_DIALOG_METRIC_DEFAULTS)
DIALOG_METRIC_BOUNDS = dict(SHARED_DIALOG_METRIC_BOUNDS)


def _rgba(color: QColor, alpha_0_to_1: float) -> str:
    alpha = max(0.0, min(1.0, float(alpha_0_to_1)))
    alpha_i = int(round(alpha * 255))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_i})"


def _format_rgba(r: int, g: int, b: int, alpha_0_to_1: float) -> str:
    alpha = max(0.0, min(1.0, float(alpha_0_to_1)))
    alpha_i = int(round(alpha * 255))
    return f"rgba({r}, {g}, {b}, {alpha_i})"


_parse_css_alpha_to_unit = parse_css_alpha_to_unit
_shift_rgb = shift_rgb


def _normalize_token_color(value: str | None) -> str | None:
    return normalize_color_token(value)


def get_dialog_token_overrides(settings: QSettings | None = None) -> dict:
    return get_color_token_overrides(
        DIALOG_TOKEN_EDITABLE_KEYS,
        prefix=_DIALOG_TOKEN_OVERRIDE_PREFIX,
        settings=settings,
    )


def set_dialog_token_overrides(overrides: dict | None, settings: QSettings | None = None):
    set_color_token_overrides(
        DIALOG_TOKEN_EDITABLE_KEYS,
        overrides,
        prefix=_DIALOG_TOKEN_OVERRIDE_PREFIX,
        settings=settings,
    )


def clear_dialog_token_overrides(settings: QSettings | None = None):
    set_dialog_token_overrides({}, settings=settings)


def _normalize_metric_value(key: str, value) -> int | None:
    return normalize_metric_token_value(
        key,
        value,
        defaults=DIALOG_METRIC_DEFAULTS,
        bounds=DIALOG_METRIC_BOUNDS,
    )


def get_dialog_metric_overrides(settings: QSettings | None = None) -> dict:
    return get_metric_token_overrides(
        DIALOG_METRIC_DEFAULTS,
        DIALOG_METRIC_BOUNDS,
        prefix=f"{_DIALOG_TOKEN_OVERRIDE_PREFIX}metric.",
        settings=settings,
    )


def set_dialog_metric_overrides(overrides: dict | None, settings: QSettings | None = None):
    set_metric_token_overrides(
        DIALOG_METRIC_DEFAULTS,
        DIALOG_METRIC_BOUNDS,
        overrides,
        prefix=f"{_DIALOG_TOKEN_OVERRIDE_PREFIX}metric.",
        settings=settings,
    )


def clear_dialog_metric_overrides(settings: QSettings | None = None):
    set_dialog_metric_overrides({}, settings=settings)


def get_dialog_metric_tokens(
    apply_overrides: bool = True, settings: QSettings | None = None
) -> dict:
    return build_shared_dialog_metric_tokens(settings=settings, apply_overrides=apply_overrides)


def _build_dialog_metric_override_styles(metrics: dict) -> str:
    m = {**DIALOG_METRIC_DEFAULTS, **(metrics or {})}
    return f"""
/* DC_DIALOG_METRIC_OVERRIDES */
QDialog {{
    font-size: {m["base_font_pt"]}px;
}}
QLabel[role="dialogTitle"], QLabel#dialogTitle, QLabel#dialog_title {{
    font-size: {m["title_font_pt"]}px;
}}
QLabel[role="dialogSubtitle"], QLabel#dialogSubtitle, QLabel#dialog_subtitle {{
    font-size: {m["subtitle_font_pt"]}px;
}}
QTabBar::tab {{
    padding: {m["tab_padding_y"]}px {m["tab_padding_x"]}px;
    min-width: {m["tab_min_width"]}px;
    border-top-left-radius: {m["tab_radius"]}px;
    border-top-right-radius: {m["tab_radius"]}px;
    margin-right: {m["tab_gap"]}px;
}}
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
    min-height: {m["field_height"]}px;
    max-height: {m["field_height"]}px;
    padding: {m["field_padding_y"]}px {m["field_padding_x"]}px;
    border-radius: {m["field_radius"]}px;
}}
QTextEdit, QPlainTextEdit {{
    padding: {m["textedit_padding_y"]}px {m["textedit_padding_x"]}px;
    border-radius: {m["textedit_radius"]}px;
}}
QPushButton {{
    min-height: {m["button_height"]}px;
    max-height: {m["button_height"]}px;
    min-width: {m["button_min_width"]}px;
    padding: {m["button_padding_y"]}px {m["button_padding_x"]}px;
    border-radius: {m["button_radius"]}px;
}}
QListWidget, QTableView, QTableWidget {{
    border-radius: {m["list_radius"]}px;
    padding: {m["list_padding"]}px;
}}
QListWidget::item {{
    padding: {m["list_item_padding_y"]}px {m["list_item_padding_x"]}px;
    border-radius: {m["list_item_radius"]}px;
    margin-bottom: {m["list_item_margin_bottom"]}px;
}}
QCheckBox {{
    spacing: {m["checkbox_spacing"]}px;
}}
QRadioButton {{
    spacing: {m["radio_spacing"]}px;
}}
QGroupBox {{
    border-radius: {m["group_radius"]}px;
    margin-top: {m["group_margin_top"]}px;
}}
QCheckBox::indicator {{
    width: {m["checkbox_indicator_size"]}px;
    height: {m["checkbox_indicator_size"]}px;
}}
QRadioButton::indicator {{
    width: {m["radio_indicator_size"]}px;
    height: {m["radio_indicator_size"]}px;
}}
QToolButton {{
    min-height: {m["toolbutton_height"]}px;
    max-height: {m["toolbutton_height"]}px;
    min-width: {m["toolbutton_min_width"]}px;
    padding: {m["toolbutton_padding_y"]}px {m["toolbutton_padding_x"]}px;
    border-radius: {m["toolbutton_radius"]}px;
}}
"""


def _apply_dialog_token_overrides(tokens: dict) -> dict:
    merged = dict(tokens or {})
    overrides = get_dialog_token_overrides()
    if not overrides:
        return merged

    merged.update(overrides)
    accent = parse_hex_color(merged.get("accent", "#4da6ff"), "#4da6ff")
    accent_hex = accent.name(QColor.NameFormat.HexRgb)
    if "accent_hover" not in overrides:
        merged["accent_hover"] = _shift_rgb(accent, 22).name(QColor.NameFormat.HexRgb)
    if "accent_soft_bg" not in overrides:
        merged["accent_soft_bg"] = _rgba(accent, 0.16)
    if "accent_soft_border" not in overrides:
        merged["accent_soft_border"] = _rgba(accent, 0.42)
    if "tab_text_active" not in overrides:
        merged["tab_text_active"] = accent_hex
    if "check_checked_bg" not in overrides:
        merged["check_checked_bg"] = accent_hex
    if "check_checked_border" not in overrides:
        merged["check_checked_border"] = accent_hex
    if "list_selected_bg" not in overrides:
        merged["list_selected_bg"] = _rgba(accent, 0.12)
    if "list_selected_border" not in overrides:
        merged["list_selected_border"] = _rgba(accent, 0.25)
    if "list_selected_text" not in overrides:
        merged["list_selected_text"] = _shift_rgb(accent, 32).name(QColor.NameFormat.HexRgb)
    if "list_hover_bg" not in overrides:
        merged["list_hover_bg"] = _rgba(accent, 0.06)
    if "button_primary_bg" not in overrides:
        merged["button_primary_bg"] = _rgba(accent, 0.10)
    if "button_primary_text" not in overrides:
        merged["button_primary_text"] = accent_hex
    if "button_primary_border" not in overrides:
        merged["button_primary_border"] = _rgba(accent, 0.55)
    if "button_primary_hover_bg" not in overrides:
        merged["button_primary_hover_bg"] = _rgba(accent, 0.18)
    if "button_primary_hover_border" not in overrides:
        merged["button_primary_hover_border"] = accent_hex
    return merged


def _build_dialog_token_override_styles(tokens: dict) -> str:
    accent = parse_hex_color(tokens.get("accent", "#4da6ff"), "#4da6ff")
    accent_hex = accent.name(QColor.NameFormat.HexRgb)
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")

    text_primary = tokens.get("text_primary", "#e1e1e6")
    text_secondary = tokens.get("text_secondary", "#c8ccd4")
    text_muted = tokens.get("text_muted", "#9aa0ad")
    title_text = tokens.get("title_text", text_primary)
    title_subtext = tokens.get("title_subtext", text_muted)
    placeholder = tokens.get("placeholder_text", tokens.get("text_faint", "#7a7a8a"))

    surface_bg = tokens.get("surface_bg", "#16161b")
    surface_alt = tokens.get("surface_alt", "#1c1c23")
    surface_item = tokens.get("surface_item", "#111116")
    surface_hover = tokens.get("surface_hover", "#18181f")
    surface_top = tokens.get("surface_top", "#13131a")

    tab_strip_bg = tokens.get("tab_strip_bg", surface_top)
    tab_idle_bg = tokens.get("tab_idle_bg", surface_alt)
    tab_active_bg = tokens.get("tab_active_bg", surface_item)
    tab_text = tokens.get("tab_text", text_muted)
    tab_text_hover = tokens.get("tab_text_hover", text_secondary)
    tab_text_active = tokens.get("tab_text_active", accent_hex)

    button_base_bg = tokens.get("button_base_bg", surface_item)
    button_base_text = tokens.get("button_base_text", text_secondary)
    button_base_border = tokens.get("button_base_border", border)
    button_base_hover_bg = tokens.get("button_base_hover_bg", surface_hover)
    button_base_hover_text = tokens.get("button_base_hover_text", text_primary)
    button_base_hover_border = tokens.get("button_base_hover_border", border)
    button_pressed_bg = tokens.get("button_pressed_bg", surface_top)
    button_pressed_text = tokens.get("button_pressed_text", button_base_hover_text)
    button_pressed_border = tokens.get("button_pressed_border", button_base_hover_border)
    button_disabled_bg = tokens.get("button_disabled_bg", surface_alt)
    button_disabled_text = tokens.get("button_disabled_text", tokens.get("text_faint", "#7a7a8a"))
    button_disabled_border = tokens.get("button_disabled_border", border_soft)

    button_primary_bg = tokens.get("button_primary_bg", _rgba(accent, 0.10))
    button_primary_text = tokens.get("button_primary_text", accent_hex)
    button_primary_border = tokens.get("button_primary_border", _rgba(accent, 0.55))
    button_primary_hover_bg = tokens.get("button_primary_hover_bg", _rgba(accent, 0.18))
    button_primary_hover_text = tokens.get("button_primary_hover_text", text_primary)
    button_primary_hover_border = tokens.get("button_primary_hover_border", accent_hex)

    button_ghost_bg = tokens.get("button_ghost_bg", surface_bg)
    button_ghost_text = tokens.get("button_ghost_text", text_muted)
    button_ghost_border = tokens.get("button_ghost_border", border_soft)
    button_ghost_hover_bg = tokens.get("button_ghost_hover_bg", surface_hover)
    button_ghost_hover_text = tokens.get("button_ghost_hover_text", text_primary)
    button_ghost_hover_border = tokens.get("button_ghost_hover_border", border)

    button_success_bg = tokens.get("button_success_bg", _rgba(accent, 0.10))
    button_success_text = tokens.get("button_success_text", accent_hex)
    button_success_border = tokens.get("button_success_border", _rgba(accent, 0.55))
    button_success_hover_bg = tokens.get("button_success_hover_bg", _rgba(accent, 0.18))
    button_success_hover_text = tokens.get("button_success_hover_text", text_primary)
    button_success_hover_border = tokens.get("button_success_hover_border", accent_hex)

    button_danger_bg = tokens.get("button_danger_bg", "transparent")
    button_danger_text = tokens.get("button_danger_text", tokens.get("danger_hex", "#d25a66"))
    button_danger_border = tokens.get(
        "button_danger_border", _rgba(QColor(button_danger_text), 0.35)
    )
    button_danger_hover_bg = tokens.get(
        "button_danger_hover_bg", _rgba(QColor(button_danger_text), 0.12)
    )
    button_danger_hover_text = tokens.get("button_danger_hover_text", button_danger_text)
    button_danger_hover_border = tokens.get(
        "button_danger_hover_border", _rgba(QColor(button_danger_text), 0.65)
    )

    check_indicator_bg = tokens.get("check_indicator_bg", surface_hover)
    check_indicator_border = tokens.get("check_indicator_border", "rgba(255,255,255,0.22)")
    check_checked_bg = tokens.get("check_checked_bg", accent_hex)
    check_checked_border = tokens.get("check_checked_border", accent_hex)

    list_selected_bg = tokens.get("list_selected_bg", _rgba(accent, 0.12))
    list_selected_border = tokens.get("list_selected_border", _rgba(accent, 0.25))
    list_selected_text = tokens.get(
        "list_selected_text", _shift_rgb(accent, 32).name(QColor.NameFormat.HexRgb)
    )
    list_hover_bg = tokens.get("list_hover_bg", _rgba(accent, 0.06))
    table_header_bg = tokens.get("table_header_bg", surface_alt)
    table_header_text = tokens.get("table_header_text", tokens.get("text_faint", "#7a7a8a"))

    toolbutton_bg = tokens.get("toolbutton_bg", surface_item)
    toolbutton_text = tokens.get("toolbutton_text", text_secondary)
    toolbutton_border = tokens.get("toolbutton_border", border)
    toolbutton_hover_bg = tokens.get("toolbutton_hover_bg", surface_hover)
    toolbutton_hover_text = tokens.get("toolbutton_hover_text", text_primary)
    toolbutton_hover_border = tokens.get("toolbutton_hover_border", border)
    toolbutton_pressed_bg = tokens.get("toolbutton_pressed_bg", surface_top)
    toolbutton_pressed_text = tokens.get("toolbutton_pressed_text", text_primary)
    toolbutton_pressed_border = tokens.get("toolbutton_pressed_border", border)
    toolbutton_disabled_bg = tokens.get("toolbutton_disabled_bg", surface_alt)
    toolbutton_disabled_text = tokens.get(
        "toolbutton_disabled_text", tokens.get("text_faint", "#7a7a8a")
    )
    toolbutton_disabled_border = tokens.get("toolbutton_disabled_border", border_soft)

    return f"""
/* DC_DIALOG_TOKEN_OVERRIDES */
QDialog {{
    background-color: {surface_bg};
    color: {text_primary};
}}
QWidget {{
    color: {text_primary};
}}
QWidget[role="dialogTitleBar"], QFrame[role="dialogTitleBar"] {{
    background-color: {tokens.get("title_bg", surface_top)};
    border-bottom: 1px solid {border_soft};
}}
QTabWidget, QTabBar {{
    background-color: {tab_strip_bg};
}}
QTabWidget::pane {{
    border: 1px solid {border};
    background: {tab_active_bg};
}}
QTabBar::tab {{
    background: {tab_idle_bg};
    color: {tab_text};
    border: 1px solid {border_soft};
    border-bottom: none;
}}
QTabBar::tab:hover {{
    background: {surface_hover};
    color: {tab_text_hover};
}}
QTabBar::tab:selected {{
    background: {tab_active_bg};
    color: {tab_text_active};
    border: 1px solid {border};
    border-top: 2px solid {accent_hex};
    border-bottom: 1px solid {tab_active_bg};
    margin-bottom: -1px;
}}
QLabel[role="dialogTitle"], QLabel#dialogTitle, QLabel#dialog_title {{
    color: {title_text};
}}
QLabel[role="dialogSubtitle"], QLabel#dialogSubtitle, QLabel#dialog_subtitle {{
    color: {title_subtext};
}}
QLabel {{
    color: {text_muted};
}}
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {surface_item};
    color: {text_primary};
    border: 1px solid {border_soft};
}}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTimeEdit:hover, QSpinBox:hover {{
    border-color: {border};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {accent_hex};
}}
QLineEdit::placeholder {{
    color: {placeholder};
}}
QPushButton {{
    background-color: {button_base_bg};
    color: {button_base_text};
    border: 1px solid {button_base_border};
}}
QPushButton:hover {{
    background-color: {button_base_hover_bg};
    color: {button_base_hover_text};
    border-color: {button_base_hover_border};
}}
QPushButton:pressed {{
    background-color: {button_pressed_bg};
    color: {button_pressed_text};
    border-color: {button_pressed_border};
}}
QPushButton:disabled {{
    background-color: {button_disabled_bg};
    color: {button_disabled_text};
    border-color: {button_disabled_border};
}}
QPushButton[default="true"], QPushButton:default,
QPushButton#primary_btn {{
    background-color: {button_primary_bg};
    border-color: {button_primary_border};
    color: {button_primary_text};
}}
QPushButton[default="true"]:hover, QPushButton:default:hover,
QPushButton#primary_btn:hover {{
    background-color: {button_primary_hover_bg};
    border-color: {button_primary_hover_border};
    color: {button_primary_hover_text};
}}
QPushButton#ghost_btn {{
    background-color: {button_ghost_bg};
    color: {button_ghost_text};
    border: 1px solid {button_ghost_border};
}}
QPushButton#ghost_btn:hover {{
    background-color: {button_ghost_hover_bg};
    color: {button_ghost_hover_text};
    border-color: {button_ghost_hover_border};
}}
QPushButton#success_btn {{
    background-color: {button_success_bg};
    color: {button_success_text};
    border: 1px solid {button_success_border};
}}
QPushButton#success_btn:hover {{
    background-color: {button_success_hover_bg};
    color: {button_success_hover_text};
    border-color: {button_success_hover_border};
}}
QPushButton#danger_btn {{
    background-color: {button_danger_bg};
    color: {button_danger_text};
    border: 1px solid {button_danger_border};
}}
QPushButton#danger_btn:hover {{
    background-color: {button_danger_hover_bg};
    color: {button_danger_hover_text};
    border-color: {button_danger_hover_border};
}}
QCheckBox, QRadioButton {{
    color: {text_secondary};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    background: {check_indicator_bg};
    border: 1.5px solid {check_indicator_border};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent_hex};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {check_checked_bg};
    border-color: {check_checked_border};
}}
QGroupBox {{
    border: 1px solid {border_soft};
    background-color: {surface_top};
    color: {text_secondary};
}}
QGroupBox::title {{
    background-color: {surface_top};
    color: {accent_hex};
}}
QListWidget, QTableView, QTableWidget {{
    background: {surface_item};
    color: {text_primary};
    border: 1px solid {border_soft};
    gridline-color: {border_soft};
}}
QListWidget::item:hover {{
    background-color: {list_hover_bg};
}}
QListWidget::item:selected,
QTableView::item:selected,
QTableWidget::item:selected {{
    background-color: {list_selected_bg};
    color: {list_selected_text};
    border: 1px solid {list_selected_border};
}}
QAbstractItemView {{
    selection-background-color: {list_selected_bg};
    selection-color: {list_selected_text};
}}
QHeaderView::section {{
    background-color: {table_header_bg};
    color: {table_header_text};
    border-bottom: 1px solid {border_soft};
}}
QToolButton {{
    background: {toolbutton_bg};
    border: 1px solid {toolbutton_border};
    color: {toolbutton_text};
}}
QToolButton:hover {{
    background: {toolbutton_hover_bg};
    border-color: {toolbutton_hover_border};
    color: {toolbutton_hover_text};
}}
QToolButton:pressed {{
    background: {toolbutton_pressed_bg};
    border-color: {toolbutton_pressed_border};
    color: {toolbutton_pressed_text};
}}
QToolButton:disabled {{
    background: {toolbutton_disabled_bg};
    border-color: {toolbutton_disabled_border};
    color: {toolbutton_disabled_text};
}}
"""


def _resolve_dialog_theme(
    theme_color: str | None,
    text_theme: str | None,
    panel_base_color: str | None,
    settings: QSettings | None = None,
) -> tuple[str, str, str]:
    if theme_color and text_theme and panel_base_color:
        return str(theme_color), str(text_theme), str(panel_base_color)

    cfg = settings or QSettings("kimhyojin", "Dark Calendar")
    resolved_theme = str(theme_color or cfg.value("theme_color", "#4da6ff"))
    resolved_text_theme = str(text_theme or cfg.value("text_theme", "dark"))
    resolved_panel_base = str(panel_base_color or cfg.value("panel_base_color", "#1c1c1c"))
    return resolved_theme, resolved_text_theme, resolved_panel_base


def get_dialog_theme_tokens(
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    apply_overrides: bool = True,
    settings: QSettings | None = None,
) -> dict:
    """Return reusable dialog color tokens based on current app theme settings."""
    theme_color, text_theme, panel_base_color = _resolve_dialog_theme(
        theme_color,
        text_theme,
        panel_base_color,
        settings=settings,
    )

    tokens = build_dialog_base_tokens(
        settings=settings,
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
    )
    if apply_overrides:
        return _apply_dialog_token_overrides(tokens)
    return tokens


def build_dialog_stylesheet(
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    palette: dict = None,
) -> str:
    """Return dialog stylesheet aligned with current UI theme settings."""
    theme_color, text_theme, panel_base_color = _resolve_dialog_theme(
        theme_color,
        text_theme,
        panel_base_color,
    )

    tokens = get_dialog_theme_tokens(
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
        apply_overrides=True,
    )
    accent = parse_hex_color(tokens.get("accent", theme_color), "#4da6ff")
    accent_hex = accent.name(QColor.NameFormat.HexRgb)
    panel_palette = {
        "surface_bg": tokens.get("surface_bg", "#16161b"),
        "toolbar_bg": tokens.get("surface_alt", "#1c1c23"),
        "item_bg": tokens.get("surface_item", "#1e1e26"),
        "surface_hover_bg": tokens.get("surface_hover", "#18181f"),
        "topbar_bg": tokens.get("surface_top", "#13131a"),
    }

    text_primary = str(tokens.get("text_primary", "#e1e1e6"))
    text_secondary = str(tokens.get("text_secondary", "#c8ccd4"))
    text_muted = str(tokens.get("text_muted", "#9aa0ad"))
    text_faint = str(tokens.get("text_faint", "#7a7a8a"))

    if isinstance(palette, dict):
        text_primary = str(palette.get("text_primary", text_primary))
        text_secondary = str(palette.get("text_secondary", text_secondary))
        text_muted = str(palette.get("text_muted", text_muted))
        text_faint = str(palette.get("text_faint", text_faint))

    style = FIXED_DIALOG_STYLE
    style = style.replace("#4da6ff", accent_hex)
    style = style.replace("rgba(77, 166, 255, 0.10)", _rgba(accent, 0.10))
    style = style.replace("rgba(77, 166, 255, 0.12)", _rgba(accent, 0.12))
    style = style.replace("rgba(77, 166, 255, 0.18)", _rgba(accent, 0.18))
    style = style.replace("rgba(77, 166, 255, 0.20)", _rgba(accent, 0.20))
    style = style.replace("rgba(77, 166, 255, 0.25)", _rgba(accent, 0.25))
    style = style.replace("rgba(77, 166, 255, 0.35)", _rgba(accent, 0.35))
    style = style.replace("rgba(77, 166, 255, 0.55)", _rgba(accent, 0.55))
    style = style.replace("rgba(77, 166, 255, 0.65)", _rgba(accent, 0.65))

    style = style.replace("#e1e1e6", text_primary)
    style = style.replace("#c8ccd4", text_secondary)
    style = style.replace("#9aa0ad", text_muted)
    style = style.replace("#7a7a8a", text_faint)
    style = style.replace("#9a9aaa", text_muted)
    style = style.replace("#d0d0da", text_secondary)
    style = style.replace("#e8e8f0", text_primary)
    style = style.replace("#c0c4cc", text_secondary)
    style = style.replace("#555562", text_faint)  # TEST

    style = style.replace("#16161b", panel_palette.get("surface_bg", "#16161b"))
    style = style.replace("#1c1c23", panel_palette.get("toolbar_bg", "#1c1c23"))
    style = style.replace("#1e1e26", panel_palette.get("item_bg", "#1e1e26"))
    style = style.replace("#18181f", panel_palette.get("surface_hover_bg", "#18181f"))
    style = style.replace("#13131a", panel_palette.get("topbar_bg", "#13131a"))
    # Input background tokens
    input_focused_bg = tokens.get("input_bg", "#111116")
    style = style.replace("#111116", input_focused_bg)
    style = style.replace("#0e0e13", panel_palette.get("topbar_bg", "#0e0e13"))
    style = style.replace("#13131a", panel_palette.get("topbar_bg", "#13131a"))
    style = style.replace("#5aabf0", accent_hex)

    # danger_btn 색상을 danger_hex 토큰에 맞게 교체
    danger_hex = tokens.get("danger_hex", "#d25a66")
    danger_qc = parse_hex_color(danger_hex, "#d25a66")
    dr, dg, db = danger_qc.red(), danger_qc.green(), danger_qc.blue()
    style = style.replace("#d25a66", danger_hex)
    style = style.replace("rgba(210, 90, 102, 0.35)", f"rgba({dr},{dg},{db},0.35)")
    style = style.replace("rgba(210, 90, 102, 0.12)", f"rgba({dr},{dg},{db},0.12)")
    style = style.replace("rgba(210, 90, 102, 0.65)", f"rgba({dr},{dg},{db},0.65)")

    # success_btn 색상을 success_hex 토큰에 맞게 교체
    success_hex = tokens.get("success_hex", "#35b66a")
    success_qc = parse_hex_color(success_hex, "#35b66a")
    sr, sg, sb = success_qc.red(), success_qc.green(), success_qc.blue()
    style = style.replace("#35b66a", success_hex)
    style = style.replace("rgba(53, 182, 106, 0.14)", f"rgba({sr},{sg},{sb},0.14)")
    style = style.replace("rgba(53, 182, 106, 0.22)", f"rgba({sr},{sg},{sb},0.22)")
    style = style.replace("rgba(53, 182, 106, 0.42)", f"rgba({sr},{sg},{sb},0.42)")

    override_style = _build_dialog_token_override_styles(tokens)
    metric_style = _build_dialog_metric_override_styles(
        get_dialog_metric_tokens(apply_overrides=True)
    )
    return f"{_DIALOG_BASE_MARKER}\n{style}\n{override_style}\n{metric_style}"


def build_dialog_preview_stylesheet(
    token_overrides: dict | None = None,
    metric_overrides: dict | None = None,
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
) -> str:
    base = build_dialog_stylesheet(
        theme_color=theme_color or "#4da6ff",
        text_theme=text_theme or "dark",
        panel_base_color=panel_base_color or "#1c1c1c",
    )

    tokens = get_dialog_theme_tokens(
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
        apply_overrides=True,
    )
    metrics = get_dialog_metric_tokens(apply_overrides=True)

    if isinstance(token_overrides, dict):
        for key, value in token_overrides.items():
            if key not in DIALOG_TOKEN_EDITABLE_KEYS:
                continue
            normalized = _normalize_token_color(value)
            if normalized:
                tokens[key] = normalized

    if isinstance(metric_overrides, dict):
        for key, value in metric_overrides.items():
            normalized = _normalize_metric_value(key, value)
            if normalized is not None:
                metrics[key] = normalized

    return (
        f"{base}\n"
        f"{_build_dialog_token_override_styles(tokens)}\n"
        f"{_build_dialog_metric_override_styles(metrics)}"
    )


COMMON_DIALOG_STYLE = FIXED_DIALOG_STYLE


def apply_common_dialog_style(
    dialog: QDialog,
    minimum_width=None,
    size=None,
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    extra_stylesheet: str | None = None,
    keep_existing_stylesheet: bool = True,
):
    """Apply the shared dialog theme while preserving optional custom styles."""
    base = build_dialog_stylesheet(
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
    )
    current = dialog.styleSheet() if keep_existing_stylesheet else ""
    shared_tokens = get_ui_tokens(
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
        opacity_factor=1.0,
    )
    parts = [get_shared_qss(shared_tokens), base]

    if current and current.strip():
        if _DIALOG_BASE_MARKER in current:
            parts = [current]
        else:
            parts.append(current)

    if extra_stylesheet and str(extra_stylesheet).strip():
        parts.append(str(extra_stylesheet))

    dialog.setStyleSheet("\n".join(parts))
    if minimum_width is not None:
        dialog.setMinimumWidth(minimum_width)
    if size is not None:
        w, h = size
        dialog.resize(w, h)


def build_dialog_footer(
    ok_label: str = "확인",
    cancel_label: str | None = "취소",
    ok_object_name: str = "primary_btn",
    cancel_object_name: str = "ghost_btn",
    extra_left_widget=None,
):
    """공통 다이얼로그 푸터 빌더.

    Returns
    -------
    tuple[QHBoxLayout, QPushButton, QPushButton | None]
        (footer_layout, ok_btn, cancel_btn)  — cancel_btn은 cancel_label=None이면 None.
    """
    from PyQt6.QtWidgets import QHBoxLayout, QPushButton

    layout = QHBoxLayout()
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(8)

    if extra_left_widget is not None:
        layout.addWidget(extra_left_widget)

    layout.addStretch()

    cancel_btn = None
    if cancel_label is not None:
        cancel_btn = QPushButton(cancel_label)
        cancel_btn.setObjectName(cancel_object_name)
        layout.addWidget(cancel_btn)

    ok_btn = QPushButton(ok_label)
    ok_btn.setObjectName(ok_object_name)
    layout.addWidget(ok_btn)

    return layout, ok_btn, cancel_btn


def build_collapsible_section(
    title: str,
    content_widget,
    expanded: bool = False,
    settings_key: str | None = None,
):
    """접을 수 있는 섹션 레이아웃 빌더.

    Parameters
    ----------
    title:          토글 버튼 라벨
    content_widget: 펼쳐질 QWidget
    expanded:       초기 펼침 상태
    settings_key:   QSettings 키 — 지정 시 상태 자동 영속화

    Returns
    -------
    tuple[QVBoxLayout, QPushButton]
        (section_layout, toggle_btn)
    """
    from PyQt6.QtWidgets import QPushButton, QVBoxLayout

    settings = None
    if settings_key:
        settings = QSettings("kimhyojin", "Dark Calendar")
        expanded = bool(settings.value(settings_key, expanded))

    toggle = QPushButton()
    toggle.setObjectName("collapsible_toggle")
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    toggle.setProperty("expanded", "true" if expanded else "false")
    content_widget.setVisible(expanded)

    def _arrow(on: bool) -> str:
        return "▼" if on else "▶"

    toggle.setText(f"{_arrow(expanded)}  {title}")

    def _on_toggle(checked: bool):
        content_widget.setVisible(checked)
        toggle.setText(f"{_arrow(checked)}  {title}")
        toggle.setProperty("expanded", "true" if checked else "false")
        toggle.style().unpolish(toggle)
        toggle.style().polish(toggle)
        if settings and settings_key:
            settings.setValue(settings_key, checked)

    toggle.toggled.connect(_on_toggle)

    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(toggle)
    layout.addWidget(content_widget)
    return layout, toggle


class FieldValidator:
    """단일 입력 필드의 인라인 검증 상태를 관리.

    Usage
    -----
    v = FieldValidator(my_line_edit, error_label=my_err_label)
    ok = v.validate(lambda t: len(t) > 0, "필수 항목입니다.")
    """

    def __init__(self, field, error_label=None):
        """
        Parameters
        ----------
        field:       QLineEdit / QTextEdit / QComboBox
        error_label: QLabel (role="field_error") — None이면 자동 생성 안 함
        """
        self._field = field
        self._label = error_label

    def validate(self, fn, error_msg: str = "") -> bool:
        """fn(text) → bool. 실패 시 error 상태 + 메시지 표시, 성공 시 clear."""
        try:
            widget = self._field
            if hasattr(widget, "toPlainText"):
                text = widget.toPlainText()
            elif hasattr(widget, "currentText"):
                text = widget.currentText()
            else:
                text = widget.text()
            ok = bool(fn(text))
        except Exception:
            ok = False
        if ok:
            self.clear()
        else:
            self.set_error(error_msg)
        return ok

    def set_error(self, msg: str = ""):
        self._field.setProperty("state", "error")
        self._field.style().unpolish(self._field)
        self._field.style().polish(self._field)
        if self._label is not None:
            self._label.setText(msg)
            self._label.setVisible(True)

    def set_success(self):
        self._field.setProperty("state", "success")
        self._field.style().unpolish(self._field)
        self._field.style().polish(self._field)
        if self._label is not None:
            self._label.setVisible(False)

    def clear(self):
        self._field.setProperty("state", "")
        self._field.style().unpolish(self._field)
        self._field.style().polish(self._field)
        if self._label is not None:
            self._label.setVisible(False)


def set_footer_loading(
    ok_btn,
    loading: bool,
    cancel_btn=None,
    loading_text: str = "...",
):
    """푸터 버튼의 로딩 상태를 전환.

    로딩 중: ok_btn 비활성화 + 텍스트 교체, cancel_btn 비활성화(선택).
    완료 시: 원래 텍스트/상태 복원.

    Parameters
    ----------
    ok_btn:       확인/저장 버튼 (QPushButton)
    loading:      True = 로딩 시작, False = 로딩 종료
    cancel_btn:   취소 버튼 (비활성화 동반 시)
    loading_text: 로딩 중 표시 텍스트
    """
    _ORIG_KEY = "_footer_orig_text"
    if loading:
        if not ok_btn.property(_ORIG_KEY):
            ok_btn.setProperty(_ORIG_KEY, ok_btn.text() or " ")
        ok_btn.setText(loading_text)
        ok_btn.setEnabled(False)
        if cancel_btn is not None:
            cancel_btn.setEnabled(False)
    else:
        orig = ok_btn.property(_ORIG_KEY)
        if orig:
            ok_btn.setText(orig)
            ok_btn.setProperty(_ORIG_KEY, "")
        ok_btn.setEnabled(True)
        if cancel_btn is not None:
            cancel_btn.setEnabled(True)


def polish_calendar_popup(
    date_edit: QDateEdit, minimum_size: QSize | None = None
) -> QCalendarWidget:
    """Normalize QDateEdit popup calendar sizing and header alignment."""
    date_edit.setCalendarPopup(True)
    calendar = date_edit.calendarWidget()
    if minimum_size is None:
        minimum_size = QSize(284, 236)

    calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
    calendar.setNavigationBarVisible(True)
    calendar.setMinimumSize(minimum_size)
    calendar.setSizePolicy(
        calendar.sizePolicy().horizontalPolicy(), calendar.sizePolicy().verticalPolicy()
    )

    table = calendar.findChild(QTableView)
    if table is not None:
        table.setShowGrid(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setMinimumSectionSize(28)
        table.verticalHeader().setMinimumSectionSize(24)
        table.verticalHeader().hide()

    return calendar
