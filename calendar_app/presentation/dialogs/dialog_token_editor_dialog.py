# -*- coding: utf-8 -*-
"""Dialog UI token editor with live preview."""

from __future__ import annotations

import re

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_quick_button_style,
    build_editor_text_style,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    DIALOG_METRIC_DEFAULTS,
    DIALOG_TOKEN_EDITABLE_KEYS,
    apply_common_dialog_style,
    build_dialog_preview_stylesheet,
    get_dialog_metric_overrides,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    set_dialog_metric_overrides,
    set_dialog_token_overrides,
)
from calendar_app.shared.color_utils import parse_css_alpha_to_unit
from calendar_app.shared.icon_map import ICON, icon
from calendar_app.shared.theme_snapshot import get_dialog_metric_bounds

_RGBA_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)

_TOKEN_LABELS = {
    "accent": "강조 색상",
    "text_primary": "기본 텍스트",
    "text_secondary": "보조 텍스트",
    "text_muted": "약한 텍스트",
    "text_faint": "희미한 텍스트",
    "placeholder_text": "플레이스홀더 텍스트",
    "surface_bg": "다이얼로그 배경",
    "surface_alt": "보조 배경",
    "surface_item": "입력/아이템 배경",
    "surface_hover": "호버 배경",
    "surface_top": "상단 영역 배경",
    "title_bg": "타이틀 영역 배경",
    "title_text": "타이틀 텍스트",
    "title_subtext": "서브타이틀 텍스트",
    "tab_strip_bg": "탭 스트립 배경",
    "tab_idle_bg": "비활성 탭 배경",
    "tab_active_bg": "활성 탭 배경",
    "tab_text": "탭 텍스트(기본)",
    "tab_text_hover": "탭 텍스트(호버)",
    "tab_text_active": "탭 텍스트(활성)",
    "border": "기본 테두리",
    "border_soft": "약한 테두리",
    "list_selected_bg": "선택 배경",
    "list_selected_border": "선택 테두리",
    "list_selected_text": "선택 텍스트",
    "list_hover_bg": "리스트 호버 배경",
    "table_header_bg": "테이블 헤더 배경",
    "table_header_text": "테이블 헤더 텍스트",
    "check_indicator_bg": "체크/라디오 배경",
    "check_indicator_border": "체크/라디오 테두리",
    "check_checked_bg": "체크됨 배경",
    "check_checked_border": "체크됨 테두리",
    "button_base_bg": "버튼 기본 배경",
    "button_base_text": "버튼 기본 텍스트",
    "button_base_border": "버튼 기본 테두리",
    "button_base_hover_bg": "버튼 호버 배경",
    "button_base_hover_text": "버튼 호버 텍스트",
    "button_base_hover_border": "버튼 호버 테두리",
    "button_pressed_bg": "버튼 눌림 배경",
    "button_pressed_text": "버튼 눌림 텍스트",
    "button_pressed_border": "버튼 눌림 테두리",
    "button_disabled_bg": "버튼 비활성 배경",
    "button_disabled_text": "버튼 비활성 텍스트",
    "button_disabled_border": "버튼 비활성 테두리",
    "button_primary_bg": "Primary 버튼 배경",
    "button_primary_text": "Primary 버튼 텍스트",
    "button_primary_border": "Primary 버튼 테두리",
    "button_primary_hover_bg": "Primary 호버 배경",
    "button_primary_hover_text": "Primary 호버 텍스트",
    "button_primary_hover_border": "Primary 호버 테두리",
    "button_secondary_bg": "Secondary 버튼 배경",
    "button_secondary_text": "Secondary 버튼 텍스트",
    "button_secondary_border": "Secondary 버튼 테두리",
    "button_secondary_hover_bg": "Secondary 호버 배경",
    "button_secondary_hover_text": "Secondary 호버 텍스트",
    "button_secondary_hover_border": "Secondary 호버 테두리",
    "button_ghost_bg": "Ghost 버튼 배경",
    "button_ghost_text": "Ghost 버튼 텍스트",
    "button_ghost_border": "Ghost 버튼 테두리",
    "button_ghost_hover_bg": "Ghost 호버 배경",
    "button_ghost_hover_text": "Ghost 호버 텍스트",
    "button_ghost_hover_border": "Ghost 호버 테두리",
    "button_success_bg": "Success 버튼 배경",
    "button_success_text": "Success 버튼 텍스트",
    "button_success_border": "Success 버튼 테두리",
    "button_success_hover_bg": "Success 호버 배경",
    "button_success_hover_text": "Success 호버 텍스트",
    "button_success_hover_border": "Success 호버 테두리",
    "button_danger_bg": "Danger 버튼 배경",
    "button_danger_text": "Danger 버튼 텍스트",
    "button_danger_border": "Danger 버튼 테두리",
    "button_danger_hover_bg": "Danger 호버 배경",
    "button_danger_hover_text": "Danger 호버 텍스트",
    "button_danger_hover_border": "Danger 호버 테두리",
    "toolbutton_bg": "툴버튼 기본 배경",
    "toolbutton_text": "툴버튼 기본 텍스트",
    "toolbutton_border": "툴버튼 기본 테두리",
    "toolbutton_hover_bg": "툴버튼 호버 배경",
    "toolbutton_hover_text": "툴버튼 호버 텍스트",
    "toolbutton_hover_border": "툴버튼 호버 테두리",
    "toolbutton_pressed_bg": "툴버튼 눌림 배경",
    "toolbutton_pressed_text": "툴버튼 눌림 텍스트",
    "toolbutton_pressed_border": "툴버튼 눌림 테두리",
    "toolbutton_disabled_bg": "툴버튼 비활성 배경",
    "toolbutton_disabled_text": "툴버튼 비활성 텍스트",
    "toolbutton_disabled_border": "툴버튼 비활성 테두리",
}

_METRIC_LABELS = {
    "base_font_pt": "기본 글자 크기",
    "title_font_pt": "타이틀 글자 크기",
    "subtitle_font_pt": "서브타이틀 글자 크기",
    "tab_padding_y": "탭 세로 패딩",
    "tab_padding_x": "탭 가로 패딩",
    "tab_min_width": "탭 최소 너비",
    "tab_gap": "탭 간격",
    "tab_radius": "탭 라운드",
    "field_height": "입력 높이",
    "field_padding_y": "입력 세로 패딩",
    "field_padding_x": "입력 가로 패딩",
    "field_radius": "입력 라운드",
    "textedit_padding_y": "텍스트영역 세로 패딩",
    "textedit_padding_x": "텍스트영역 가로 패딩",
    "textedit_radius": "텍스트영역 라운드",
    "button_height": "버튼 높이",
    "button_min_width": "버튼 최소 너비",
    "button_padding_y": "버튼 세로 패딩",
    "button_padding_x": "버튼 가로 패딩",
    "button_radius": "버튼 라운드",
    "toolbutton_height": "툴버튼 높이",
    "toolbutton_min_width": "툴버튼 최소 너비",
    "toolbutton_padding_y": "툴버튼 세로 패딩",
    "toolbutton_padding_x": "툴버튼 가로 패딩",
    "toolbutton_radius": "툴버튼 라운드",
    "list_radius": "리스트 라운드",
    "list_padding": "리스트 내부 여백",
    "list_item_padding_y": "리스트 아이템 세로 패딩",
    "list_item_padding_x": "리스트 아이템 가로 패딩",
    "list_item_radius": "리스트 아이템 라운드",
    "list_item_margin_bottom": "리스트 아이템 간격",
    "checkbox_spacing": "체크박스 텍스트 간격",
    "radio_spacing": "라디오 텍스트 간격",
    "checkbox_indicator_size": "체크 인디케이터 크기",
    "radio_indicator_size": "라디오 인디케이터 크기",
    "group_radius": "그룹박스 라운드",
    "group_margin_top": "그룹박스 상단 간격",
}

_COLOR_GROUPS = [
    (
        "기본 색상",
        [
            "accent",
            "surface_bg",
            "surface_alt",
            "surface_item",
            "surface_hover",
            "surface_top",
            "border",
            "border_soft",
        ],
    ),
    (
        "텍스트",
        [
            "text_primary",
            "text_secondary",
            "text_muted",
            "text_faint",
            "placeholder_text",
            "title_text",
            "title_subtext",
        ],
    ),
    (
        "타이틀/탭",
        [
            "title_bg",
            "tab_strip_bg",
            "tab_idle_bg",
            "tab_active_bg",
            "tab_text",
            "tab_text_hover",
            "tab_text_active",
        ],
    ),
    (
        "버튼",
        [
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
        ],
    ),
    (
        "Primary/Secondary/Ghost",
        [
            "button_primary_bg",
            "button_primary_text",
            "button_primary_border",
            "button_primary_hover_bg",
            "button_primary_hover_text",
            "button_primary_hover_border",
            "button_secondary_bg",
            "button_secondary_text",
            "button_secondary_border",
            "button_secondary_hover_bg",
            "button_secondary_hover_text",
            "button_secondary_hover_border",
            "button_ghost_bg",
            "button_ghost_text",
            "button_ghost_border",
            "button_ghost_hover_bg",
            "button_ghost_hover_text",
            "button_ghost_hover_border",
        ],
    ),
    (
        "Success/Danger",
        [
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
        ],
    ),
    (
        "툴버튼",
        [
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
        ],
    ),
    (
        "리스트/테이블/체크",
        [
            "list_hover_bg",
            "list_selected_bg",
            "list_selected_border",
            "list_selected_text",
            "table_header_bg",
            "table_header_text",
            "check_indicator_bg",
            "check_indicator_border",
            "check_checked_bg",
            "check_checked_border",
        ],
    ),
]

_METRIC_GROUPS = [
    ("폰트", ["base_font_pt", "title_font_pt", "subtitle_font_pt"]),
    ("탭", ["tab_padding_y", "tab_padding_x", "tab_min_width", "tab_gap", "tab_radius"]),
    ("입력 필드", ["field_height", "field_padding_y", "field_padding_x", "field_radius"]),
    ("텍스트 영역", ["textedit_padding_y", "textedit_padding_x", "textedit_radius"]),
    (
        "버튼",
        [
            "button_height",
            "button_min_width",
            "button_padding_y",
            "button_padding_x",
            "button_radius",
        ],
    ),
    (
        "툴버튼",
        [
            "toolbutton_height",
            "toolbutton_min_width",
            "toolbutton_padding_y",
            "toolbutton_padding_x",
            "toolbutton_radius",
        ],
    ),
    (
        "리스트/아이템",
        [
            "list_radius",
            "list_padding",
            "list_item_padding_y",
            "list_item_padding_x",
            "list_item_radius",
            "list_item_margin_bottom",
        ],
    ),
    (
        "체크/라디오",
        ["checkbox_spacing", "radio_spacing", "checkbox_indicator_size", "radio_indicator_size"],
    ),
    ("그룹박스", ["group_radius", "group_margin_top"]),
]


def _safe_qcolor(value: str | None, fallback: str) -> QColor:
    q = QColor(str(value or "").strip())
    if q.isValid():
        return q
    return QColor(fallback)


def _color_hex(value: str | None, fallback: str) -> str:
    return _safe_qcolor(value, fallback).name(QColor.NameFormat.HexRgb)


def _rgba(color: QColor, alpha: int) -> str:
    a = max(0, min(255, int(alpha)))
    # CSS 1 is opaque, but a QColor alpha byte of 1 is almost transparent.
    value = "0.0039215686" if a == 1 else str(a)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {value})"


def _blend(base: QColor, mix: QColor, ratio: float) -> QColor:
    r = max(0.0, min(1.0, float(ratio)))
    return QColor(
        int(round(base.red() * (1.0 - r) + mix.red() * r)),
        int(round(base.green() * (1.0 - r) + mix.green() * r)),
        int(round(base.blue() * (1.0 - r) + mix.blue() * r)),
    )


def _tint(color: QColor, ratio: float) -> QColor:
    return _blend(color, QColor(255, 255, 255), ratio)


def _shade(color: QColor, ratio: float) -> QColor:
    return _blend(color, QColor(0, 0, 0), ratio)


def _build_full_theme_tokens(
    *,
    accent: str,
    surface_bg: str,
    surface_alt: str,
    surface_item: str,
    surface_hover: str,
    surface_top: str,
    text_primary: str,
    text_secondary: str,
    text_muted: str,
    text_faint: str,
    success: str,
    danger: str,
    border_alpha: int = 40,
    border_soft_alpha: int = 26,
) -> dict[str, str]:
    accent_q = _safe_qcolor(accent, "#4da6ff")
    surface_bg_q = _safe_qcolor(surface_bg, "#10161f")
    surface_alt_q = _safe_qcolor(surface_alt, "#1b2433")
    surface_item_q = _safe_qcolor(surface_item, "#202b3c")
    surface_hover_q = _safe_qcolor(surface_hover, "#2a3650")
    surface_top_q = _safe_qcolor(surface_top, "#151d2b")

    text_primary_q = _safe_qcolor(text_primary, "#e8f0fe")
    text_secondary_q = _safe_qcolor(text_secondary, "#b8ccf0")
    text_muted_q = _safe_qcolor(text_muted, "#8aa6cc")
    text_faint_q = _safe_qcolor(text_faint, "#5e7ea8")

    success_q = _safe_qcolor(success, "#35b66a")
    danger_q = _safe_qcolor(danger, "#d25a66")

    border = _rgba(QColor(255, 255, 255), border_alpha)
    border_soft = _rgba(QColor(255, 255, 255), border_soft_alpha)

    selected_text = _tint(accent_q, 0.28).name(QColor.NameFormat.HexRgb)
    danger_hover_text = _tint(danger_q, 0.20).name(QColor.NameFormat.HexRgb)

    return {
        "accent": accent_q.name(QColor.NameFormat.HexRgb),
        "text_primary": text_primary_q.name(QColor.NameFormat.HexRgb),
        "text_secondary": text_secondary_q.name(QColor.NameFormat.HexRgb),
        "text_muted": text_muted_q.name(QColor.NameFormat.HexRgb),
        "text_faint": text_faint_q.name(QColor.NameFormat.HexRgb),
        "input_bg": surface_item_q.name(QColor.NameFormat.HexRgb),
        "placeholder_text": text_faint_q.name(QColor.NameFormat.HexRgb),
        "surface_bg": surface_bg_q.name(QColor.NameFormat.HexRgb),
        "surface_alt": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "surface_item": surface_item_q.name(QColor.NameFormat.HexRgb),
        "surface_hover": surface_hover_q.name(QColor.NameFormat.HexRgb),
        "surface_top": surface_top_q.name(QColor.NameFormat.HexRgb),
        "title_bg": surface_top_q.name(QColor.NameFormat.HexRgb),
        "title_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "title_subtext": text_muted_q.name(QColor.NameFormat.HexRgb),
        "tab_strip_bg": surface_top_q.name(QColor.NameFormat.HexRgb),
        "tab_idle_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "tab_active_bg": surface_item_q.name(QColor.NameFormat.HexRgb),
        "tab_text": text_muted_q.name(QColor.NameFormat.HexRgb),
        "tab_text_hover": text_secondary_q.name(QColor.NameFormat.HexRgb),
        "tab_text_active": accent_q.name(QColor.NameFormat.HexRgb),
        "border": border,
        "border_soft": border_soft,
        "list_selected_bg": _rgba(accent_q, 32),
        "list_selected_border": _rgba(accent_q, 90),
        "list_selected_text": selected_text,
        "list_hover_bg": _rgba(accent_q, 20),
        "table_header_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "table_header_text": text_faint_q.name(QColor.NameFormat.HexRgb),
        "check_indicator_bg": surface_item_q.name(QColor.NameFormat.HexRgb),
        "check_indicator_border": _rgba(QColor(255, 255, 255), 56),
        "check_checked_bg": accent_q.name(QColor.NameFormat.HexRgb),
        "check_checked_border": accent_q.name(QColor.NameFormat.HexRgb),
        "button_base_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "button_base_text": text_secondary_q.name(QColor.NameFormat.HexRgb),
        "button_base_border": border,
        "button_base_hover_bg": surface_hover_q.name(QColor.NameFormat.HexRgb),
        "button_base_hover_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "button_base_hover_border": _rgba(QColor(255, 255, 255), 72),
        "button_pressed_bg": _shade(surface_hover_q, 0.18).name(QColor.NameFormat.HexRgb),
        "button_pressed_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "button_pressed_border": _rgba(QColor(255, 255, 255), 86),
        "button_disabled_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "button_disabled_text": text_faint_q.name(QColor.NameFormat.HexRgb),
        "button_disabled_border": _rgba(QColor(255, 255, 255), 18),
        "button_primary_bg": _rgba(accent_q, 34),
        "button_primary_text": accent_q.name(QColor.NameFormat.HexRgb),
        "button_primary_border": _rgba(accent_q, 148),
        "button_primary_hover_bg": _rgba(accent_q, 58),
        "button_primary_hover_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "button_primary_hover_border": accent_q.name(QColor.NameFormat.HexRgb),
        "button_secondary_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "button_secondary_text": text_muted_q.name(QColor.NameFormat.HexRgb),
        "button_secondary_border": _rgba(QColor(255, 255, 255), 32),
        "button_secondary_hover_bg": surface_hover_q.name(QColor.NameFormat.HexRgb),
        "button_secondary_hover_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "button_secondary_hover_border": _rgba(QColor(255, 255, 255), 62),
        "button_ghost_bg": surface_bg_q.name(QColor.NameFormat.HexRgb),
        "button_ghost_text": text_muted_q.name(QColor.NameFormat.HexRgb),
        "button_ghost_border": _rgba(QColor(255, 255, 255), 30),
        "button_ghost_hover_bg": surface_item_q.name(QColor.NameFormat.HexRgb),
        "button_ghost_hover_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "button_ghost_hover_border": _rgba(QColor(255, 255, 255), 64),
        "button_success_bg": _rgba(success_q, 36),
        "button_success_text": success_q.name(QColor.NameFormat.HexRgb),
        "button_success_border": _rgba(success_q, 110),
        "button_success_hover_bg": _rgba(success_q, 58),
        "button_success_hover_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "button_success_hover_border": success_q.name(QColor.NameFormat.HexRgb),
        "button_danger_bg": "transparent",
        "button_danger_text": danger_q.name(QColor.NameFormat.HexRgb),
        "button_danger_border": _rgba(danger_q, 100),
        "button_danger_hover_bg": _rgba(danger_q, 34),
        "button_danger_hover_text": danger_hover_text,
        "button_danger_hover_border": _rgba(danger_q, 176),
        "toolbutton_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_text": text_secondary_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_border": border,
        "toolbutton_hover_bg": surface_hover_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_hover_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_hover_border": _rgba(QColor(255, 255, 255), 72),
        "toolbutton_pressed_bg": _shade(surface_hover_q, 0.18).name(QColor.NameFormat.HexRgb),
        "toolbutton_pressed_text": text_primary_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_pressed_border": _rgba(QColor(255, 255, 255), 86),
        "toolbutton_disabled_bg": surface_alt_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_disabled_text": text_faint_q.name(QColor.NameFormat.HexRgb),
        "toolbutton_disabled_border": _rgba(QColor(255, 255, 255), 18),
    }


_METRIC_PRESET_COMPACT = {
    "base_font_pt": 13,
    "title_font_pt": 15,
    "subtitle_font_pt": 11,
    "tab_padding_y": 6,
    "tab_padding_x": 18,
    "tab_min_width": 72,
    "tab_gap": 2,
    "tab_radius": 6,
    "field_height": 30,
    "field_padding_y": 3,
    "field_padding_x": 8,
    "field_radius": 6,
    "textedit_padding_y": 8,
    "textedit_padding_x": 10,
    "textedit_radius": 7,
    "button_height": 24,
    "button_min_width": 45,
    "button_padding_y": 3,
    "button_padding_x": 12,
    "button_radius": 6,
    "toolbutton_height": 26,
    "toolbutton_min_width": 30,
    "toolbutton_padding_y": 3,
    "toolbutton_padding_x": 5,
    "toolbutton_radius": 5,
    "list_item_radius": 4,
    "list_item_margin_bottom": 1,
    "checkbox_spacing": 7,
    "radio_spacing": 7,
    "checkbox_indicator_size": 15,
    "radio_indicator_size": 15,
    "list_radius": 7,
    "list_padding": 3,
    "list_item_padding_y": 7,
    "list_item_padding_x": 8,
    "group_radius": 8,
    "group_margin_top": 14,
}


_METRIC_PRESET_COMFORTABLE = {
    "base_font_pt": 15,
    "title_font_pt": 18,
    "subtitle_font_pt": 13,
    "tab_padding_y": 10,
    "tab_padding_x": 26,
    "tab_min_width": 92,
    "tab_gap": 4,
    "tab_radius": 10,
    "field_height": 38,
    "field_padding_y": 6,
    "field_padding_x": 12,
    "field_radius": 9,
    "textedit_padding_y": 12,
    "textedit_padding_x": 14,
    "textedit_radius": 10,
    "button_height": 38,
    "button_min_width": 90,
    "button_padding_y": 6,
    "button_padding_x": 18,
    "button_radius": 10,
    "toolbutton_height": 32,
    "toolbutton_min_width": 38,
    "toolbutton_padding_y": 5,
    "toolbutton_padding_x": 8,
    "toolbutton_radius": 8,
    "list_item_radius": 7,
    "list_item_margin_bottom": 2,
    "checkbox_spacing": 10,
    "radio_spacing": 10,
    "checkbox_indicator_size": 18,
    "radio_indicator_size": 18,
    "list_radius": 10,
    "list_padding": 5,
    "list_item_padding_y": 10,
    "list_item_padding_x": 12,
    "group_radius": 11,
    "group_margin_top": 20,
}


def _color_preset_payload(tokens: dict | None = None, note: str = "") -> dict:
    return {
        "tokens": dict(tokens or {}),
        "note": note,
    }


def _metric_preset_payload(metrics: dict | None = None, note: str = "") -> dict:
    return {
        "metrics": dict(metrics or {}),
        "note": note,
    }


def _preset_with_token_overrides(
    base_tokens: dict[str, str], overrides: dict[str, str] | None = None
) -> dict[str, str]:
    merged = dict(base_tokens or {})
    if overrides:
        merged.update({k: str(v) for k, v in overrides.items()})
    return merged


_DARK_COLOR_PRESETS = {
    "Arctic Blue Pro": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#58a6ff",
            surface_bg="#0f1626",
            surface_alt="#1b2436",
            surface_item="#202b40",
            surface_hover="#28344c",
            surface_top="#121b2b",
            text_primary="#e6edf7",
            text_secondary="#c9d5e8",
            text_muted="#9cb0ce",
            text_faint="#6f85a8",
            success="#3ecf8e",
            danger="#d96574",
        ),
        note="Balanced blue preset for general use.",
    ),
    "Graphite Charcoal": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#77d4ff",
            surface_bg="#141414",
            surface_alt="#202020",
            surface_item="#262626",
            surface_hover="#313131",
            surface_top="#191919",
            text_primary="#f2f2f2",
            text_secondary="#dfdfdf",
            text_muted="#b6b6b6",
            text_faint="#8f8f8f",
            success="#4dc37c",
            danger="#d36a73",
        ),
        note="Neutral dark preset with clear contrast.",
    ),
    "Slate Indigo": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#8ec1ff",
            surface_bg="#1a2130",
            surface_alt="#232d40",
            surface_item="#2a3448",
            surface_hover="#334058",
            surface_top="#1f283a",
            text_primary="#e8edf7",
            text_secondary="#d6deed",
            text_muted="#acb9d0",
            text_faint="#7b8ea9",
            success="#47bf87",
            danger="#d26d7a",
        ),
        note="Calm indigo palette for long work sessions.",
    ),
    "Emerald Dusk": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#4fd5b3",
            surface_bg="#0f1f1d",
            surface_alt="#18302d",
            surface_item="#1f3a37",
            surface_hover="#2a4a46",
            surface_top="#142926",
            text_primary="#e6f5f1",
            text_secondary="#b8ddd4",
            text_muted="#8fc0b5",
            text_faint="#5f9187",
            success="#49cf8e",
            danger="#db6f7f",
        ),
        note="Emerald accent with softened dark backgrounds.",
    ),
    "Amber Night": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#f2b84b",
            surface_bg="#20170d",
            surface_alt="#2d2114",
            surface_item="#36281a",
            surface_hover="#433325",
            surface_top="#271c11",
            text_primary="#fff2de",
            text_secondary="#e9d5b2",
            text_muted="#c8ad82",
            text_faint="#967b52",
            success="#58c67e",
            danger="#e1736b",
        ),
        note="Warm amber accent with high readability.",
    ),
    "Crimson Noir": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#ff6f91",
            surface_bg="#1f1016",
            surface_alt="#2c1721",
            surface_item="#351d29",
            surface_hover="#432536",
            surface_top="#25131b",
            text_primary="#ffe7ee",
            text_secondary="#f2bfd0",
            text_muted="#d695ab",
            text_faint="#9d667a",
            success="#53c889",
            danger="#f0717c",
        ),
        note="Strong contrast for focus-heavy workflows.",
    ),
}

_LIGHT_COLOR_PRESETS = {
    "Quiet White": _color_preset_payload(
        tokens=_build_full_theme_tokens(
            accent="#4da6ff",
            surface_bg="#fcfcfc",
            surface_alt="#f2f2f2",
            surface_item="#ffffff",
            surface_hover="#f8f8f8",
            surface_top="#f5f5f5",
            text_primary="#2b2b2b",
            text_secondary="#555555",
            text_muted="#888888",
            text_faint="#aaaaaa",
            success="#35b66a",
            danger="#e06060",
            border_alpha=0,
            border_soft_alpha=0,
        ),
        note="Minimalist light theme.",
    ),
    "Light Aqua Form": _color_preset_payload(
        tokens=_preset_with_token_overrides(
            _build_full_theme_tokens(
                accent="#22c3ca",
                surface_bg="#eef2f6",
                surface_alt="#e8edf4",
                surface_item="#f7f9fc",
                surface_hover="#dee7f0",
                surface_top="#e0e8f1",
                text_primary="#31465f",
                text_secondary="#4f6581",
                text_muted="#6f839a",
                text_faint="#8fa0b4",
                success="#26b9a2",
                danger="#d86f82",
                border_alpha=0,
                border_soft_alpha=0,
            ),
            {
                "title_bg": "#e6edf4",
                "tab_strip_bg": "#e6edf4",
                "tab_text_active": "#19b5bd",
                "border": "rgba(113, 135, 160, 122)",
                "border_soft": "rgba(113, 135, 160, 82)",
            },
        ),
        note="Light card UI with aqua accent.",
    ),
    "Light Aqua Form (Soft)": _color_preset_payload(
        tokens=_preset_with_token_overrides(
            _build_full_theme_tokens(
                accent="#2ec0c7",
                surface_bg="#f1f4f8",
                surface_alt="#ebf0f6",
                surface_item="#fafbfd",
                surface_hover="#e4ebf3",
                surface_top="#e7edf4",
                text_primary="#344a62",
                text_secondary="#566e88",
                text_muted="#7589a0",
                text_faint="#98a8ba",
                success="#2cbca6",
                danger="#d9788b",
                border_alpha=0,
                border_soft_alpha=0,
            ),
            {
                "title_bg": "#eaf0f6",
                "tab_strip_bg": "#eaf0f6",
                "tab_text_active": "#1fb3bb",
                "border": "rgba(122, 143, 166, 116)",
                "border_soft": "rgba(122, 143, 166, 78)",
            },
        ),
        note="Softer light variation variation.",
    ),
}

_COLOR_PRESETS = {
    "Default (Auto)": _color_preset_payload(note="Dialog defaults from current theme."),
    "System Default": _color_preset_payload(
        note="시스템 기본값으로 모든 색상 설정을 초기화합니다."
    ),
    **_DARK_COLOR_PRESETS,
    **_LIGHT_COLOR_PRESETS,
}


def get_color_preset_tokens(preset_name: str) -> dict[str, str]:
    payload = _COLOR_PRESETS.get(str(preset_name), {})
    if isinstance(payload, dict):
        tokens = payload.get("tokens")
        if isinstance(tokens, dict):
            return dict(tokens)
    return {}


_METRIC_PRESETS = {
    "Default (Auto)": _metric_preset_payload(
        note="Use default dialog metric tokens.",
    ),
    "System Default": _metric_preset_payload(
        note="시스템 기본값으로 모든 크기 및 간격 설정을 초기화합니다.",
    ),
    "Compact Dense": _metric_preset_payload(
        metrics=_METRIC_PRESET_COMPACT,
        note="Dense spacing for information-heavy views.",
    ),
    "Comfortable Spacious": _metric_preset_payload(
        metrics=_METRIC_PRESET_COMFORTABLE,
        note="Larger controls and wider spacing for readability.",
    ),
}


def _normalize_color(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    if raw.lower() == "transparent":
        return "transparent"

    match = _RGBA_RE.match(raw)
    if match:
        try:
            r = max(0, min(255, int(match.group(1))))
            g = max(0, min(255, int(match.group(2))))
            b = max(0, min(255, int(match.group(3))))
            a = parse_css_alpha_to_unit(match.group(4))
            a_i = int(round(a * 255))
            return _rgba(QColor(r, g, b), a_i)
        except Exception:
            return None

    q = QColor(raw)
    if q.isValid():
        if q.alpha() < 255:
            return _rgba(q, q.alpha())
        return q.name(QColor.NameFormat.HexRgb)
    return None


def _fallback_token_label(key: str) -> str:
    return key.replace("_", " ").title()


def _to_qcolor(color_text: str | None, fallback: str = "#4da6ff") -> QColor:
    normalized = _normalize_color(color_text)
    if normalized == "transparent":
        return QColor(Qt.GlobalColor.transparent)
    if not normalized:
        return QColor(fallback)
    match = _RGBA_RE.match(normalized)
    if match:
        return QColor(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            round(parse_css_alpha_to_unit(match.group(4)) * 255),
        )
    q = QColor(normalized)
    return q if q.isValid() else QColor(fallback)


def _collect_grouped_keys(
    groups: list[tuple[str, list[str]]], all_keys: tuple[str, ...]
) -> list[tuple[str, list[str]]]:
    seen: set[str] = set()
    out: list[tuple[str, list[str]]] = []
    for title, keys in groups:
        valid = [k for k in keys if k in all_keys and k not in seen]
        if valid:
            out.append((title, valid))
            seen.update(valid)
    rest = [k for k in all_keys if k not in seen]
    if rest:
        out.append(("기타", rest))
    return out


_RECOMMENDED_COLORS = frozenset(
    {
        "accent",
        "surface_bg",
        "surface_alt",
        "surface_item",
        "text_primary",
        "text_secondary",
        "border",
        "button_primary_bg",
        "button_primary_text",
        "button_base_bg",
        "button_base_text",
        "placeholder_text",
        "check_checked_bg",
        "list_selected_bg",
        "list_selected_text",
        "table_header_bg",
        "table_header_text",
    }
)
_RECOMMENDED_METRICS = frozenset(
    {
        "base_font_pt",
        "title_font_pt",
        "field_height",
        "field_radius",
        "button_height",
        "button_min_width",
        "button_radius",
        "list_item_padding_y",
        "list_radius",
        "tab_padding_y",
        "checkbox_indicator_size",
    }
)


def _control_category(key: str, *, metric: bool = False) -> str:
    if key.startswith(("button_", "toolbutton_")):
        return "buttons"
    if key.startswith(("field_", "textedit_", "check", "radio")) or key in {
        "surface_item",
        "placeholder_text",
    }:
        return "fields"
    if key.startswith(("list_", "table_")):
        return "lists"
    return "appearance"


class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True
        return super().eventFilter(obj, event)


def _dialog_token_editor_style_bundle(tokens=None, metrics=None) -> dict[str, str]:
    tokens = dict(tokens or get_dialog_theme_tokens(apply_overrides=True))
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    base_font_px = max(12, int(metrics.get("base_font_pt", 14)))
    group_radius = max(10, int(metrics.get("group_radius", 10)))
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_alt = tokens.get("surface_alt", "#1c1c23")
    surface_item = tokens.get("surface_item", "#111116")
    text_faint = tokens.get("text_faint", "rgba(255,255,255,0.45)")
    danger = tokens.get("button_danger_text", tokens.get("danger_hex", "#d25a66"))
    return {
        "desc": build_editor_text_style(tokens, tone="muted", font_px=max(12, base_font_px - 1)),
        "preset_bar": (
            f"QFrame#presetBar {{ background: {surface_alt}; border-bottom: 1px solid {border}; }}"
        ),
        "preset_note": build_editor_text_style(
            tokens, tone="muted", font_px=max(12, base_font_px - 2), padding="4px 8px 8px 8px"
        ),
        "preview_wrap": (
            "QFrame#tokenPreviewWrap { "
            f"background: {surface_item}; border: 1px solid {border_soft}; border-radius: {group_radius}px; "
            "}"
        ),
        "metric_hint": f"color: {text_faint};",
        "feedback_info": build_editor_text_style(
            tokens, tone="muted", font_px=max(12, base_font_px - 2), weight=600
        ),
        "feedback_success": build_editor_text_style(
            tokens, tone="success", font_px=max(12, base_font_px - 2), weight=600
        ),
        "feedback_warning": build_editor_text_style(
            tokens, tone="warning", font_px=max(12, base_font_px - 2), weight=600
        ),
        "feedback_error": build_editor_text_style(
            tokens, tone="danger", font_px=max(12, base_font_px - 2), weight=600
        ),
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_accent": build_editor_quick_button_style(tokens, metrics, tone="accent"),
        "button_danger": build_editor_quick_button_style(tokens, metrics, tone="danger"),
        "button_ghost": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "swatch_frame": f"border: 1px solid {border}; border-radius: 4px; background: {{fill}};",
        "invalid_edit": f"border: 1px solid {danger};",
    }


def _retarget_button_style(css: str, selector: str) -> str:
    return (
        css.replace("QPushButton:hover", f"{selector}:hover")
        .replace("QPushButton:pressed", f"{selector}:pressed")
        .replace("QPushButton", selector)
    )


def _preview_variant_stylesheet(tokens=None, metrics=None) -> str:
    return "\n".join(
        [
            _retarget_button_style(
                build_editor_quick_button_style(tokens=tokens, metrics=metrics, tone="accent"),
                'QPushButton[previewVariant="primary"]',
            ),
            _retarget_button_style(
                build_editor_quick_button_style(tokens=tokens, metrics=metrics, tone="secondary"),
                'QPushButton[previewVariant="secondary"]',
            ),
            _retarget_button_style(
                build_editor_quick_button_style(tokens=tokens, metrics=metrics, tone="secondary"),
                'QPushButton[previewVariant="ghost"]',
            ),
            _retarget_button_style(
                build_editor_quick_button_style(tokens=tokens, metrics=metrics, tone="success"),
                'QPushButton[previewVariant="success"]',
            ),
            _retarget_button_style(
                build_editor_quick_button_style(tokens=tokens, metrics=metrics, tone="danger"),
                'QPushButton[previewVariant="danger"]',
            ),
        ]
    )


class _TokenDraftSettings:
    """Keep normalizing readers' writes in memory until the editor is accepted."""

    def __init__(self, source):
        self.source = source
        self._values = {}
        self._removed = set()

    def value(self, key, default=None, type=None):  # noqa: A002
        if key in self._removed:
            return default
        if key not in self._values:
            if type is not None:
                return self.source.value(key, default, type=type)
            return self.source.value(key, default)
        value = self._values[key]
        if type is bool and isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return type(value) if type is not None and value is not None else value

    def contains(self, key):
        if key in self._removed:
            return False
        if key in self._values:
            return True
        contains = getattr(self.source, "contains", None)
        return contains(key) if callable(contains) else self.source.value(key, None) is not None

    def allKeys(self):  # noqa: N802
        method = getattr(self.source, "allKeys", None)
        original = set(method()) if callable(method) else set()
        return sorted((original | self._values.keys()) - self._removed)

    def setValue(self, key, value):  # noqa: N802
        self._removed.discard(key)
        self._values[key] = value

    def remove(self, key):
        self._values.pop(key, None)
        self._removed.add(key)


class DialogTokenEditorDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        theme_color: str | None = None,
        text_theme: str | None = None,
        panel_base_color: str | None = None,
        base_tokens: dict | None = None,
        initial_color_overrides: dict | None = None,
        initial_metric_overrides: dict | None = None,
        persist_on_apply: bool = True,
        settings=None,
    ):
        super().__init__(parent)
        self._settings = settings if settings is not None else getattr(parent, "settings", None)
        source = (
            self._settings
            if self._settings is not None
            else QSettings("kimhyojin", "Dark Calendar")
        )
        self._read_settings = _TokenDraftSettings(source)
        self._dc_chrome_settings = self._read_settings
        apply_dialog_title(self, t("dialog.token_editor.title", "세부 모양 조정"))
        apply_common_dialog_style(
            self,
            minimum_width=760,
            size=(1200, 820),
            theme_color=theme_color,
            text_theme=text_theme,
            panel_base_color=panel_base_color,
            settings=self._read_settings,
        )
        self.setModal(True)

        self._theme_color = theme_color
        self._text_theme = text_theme
        self._panel_base_color = panel_base_color
        self._persist_on_apply = bool(persist_on_apply)
        self._result_color_overrides: dict | None = None
        self._result_metric_overrides: dict | None = None

        self._default_tokens = dict(
            base_tokens
            or get_dialog_theme_tokens(
                theme_color=theme_color,
                text_theme=text_theme,
                panel_base_color=panel_base_color,
                apply_overrides=False,
                settings=self._read_settings,
            )
        )
        if initial_color_overrides is None:
            self._current_tokens = get_dialog_theme_tokens(
                theme_color=theme_color,
                text_theme=text_theme,
                panel_base_color=panel_base_color,
                apply_overrides=True,
                settings=self._read_settings,
            )
        else:
            self._current_tokens = dict(self._default_tokens)
            self._current_tokens.update(initial_color_overrides)
        self._default_metrics = get_dialog_metric_tokens(
            apply_overrides=False, settings=self._read_settings
        )
        self._metric_bounds = get_dialog_metric_bounds(self._read_settings)
        self._original_metric_overrides = dict(
            get_dialog_metric_overrides(settings=self._read_settings)
            if initial_metric_overrides is None
            else initial_metric_overrides
        )
        self._metric_reset_keys: set[str] = set()
        if initial_metric_overrides is None:
            self._current_metrics = get_dialog_metric_tokens(
                apply_overrides=True, settings=self._read_settings
            )
        else:
            self._current_metrics = dict(self._default_metrics)
            self._current_metrics.update(initial_metric_overrides)
        self._style_bundle = _dialog_token_editor_style_bundle(
            self._current_tokens, self._current_metrics
        )

        self._wheel_blocker = WheelBlocker(self)

        self._color_rows: dict[str, QFrame] = {}
        self._metric_rows: dict[str, QFrame] = {}
        self._search_query = ""
        self._responsive_mode = None
        self._color_category = "appearance"
        self._metric_category = "metrics"
        self._color_edits: dict[str, QLineEdit] = {}
        self._color_swatches: dict[str, QLabel] = {}
        self._metric_spins: dict[str, QSpinBox] = {}
        self._last_preview_css: str = ""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(60)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._grouped_color_keys = _collect_grouped_keys(_COLOR_GROUPS, DIALOG_TOKEN_EDITABLE_KEYS)
        self._grouped_metric_keys = _collect_grouped_keys(
            _METRIC_GROUPS, tuple(DIALOG_METRIC_DEFAULTS.keys())
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        heading = QHBoxLayout()
        desc = QLabel(t("dialog.token_editor.desc", "필요한 항목을 찾아 색상과 간격을 조정하세요."))
        desc.setWordWrap(True)
        desc.setStyleSheet(self._style_bundle["desc"])
        heading.addWidget(desc, 1)
        self.expert_mode_check = QCheckBox(
            t("dialog.token_editor.expert_mode", "개별 값 직접 조정 (전문가)"),
        )
        self.expert_mode_check.setToolTip(
            t(
                "dialog.token_editor.expert_help",
                "전문가 보기에서는 모든 내부 값을 조정할 수 있습니다.",
            )
        )
        heading.addWidget(self.expert_mode_check)
        self.file_button = QToolButton()
        self.file_button.setText(t("dialog.token_editor.file_tools", "파일"))
        self.file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.file_menu = QMenu(self.file_button)
        self.export_btn = self.file_menu.addAction(
            t("dialog.token_editor.export", "JSON 내보내기"), self._export_tokens
        )
        self.import_btn = self.file_menu.addAction(
            t("dialog.token_editor.import", "JSON 가져오기"), self._import_tokens
        )
        self.file_button.setMenu(self.file_menu)
        heading.addWidget(self.file_button)
        root.addLayout(heading)

        self.color_preset_combo = QComboBox()
        self.preset_mode_all = QRadioButton(t("dialog.token_editor.mode_all", "모두"))
        self.preset_mode_dark = QRadioButton(t("dialog.token_editor.mode_dark", "다크"))
        self.preset_mode_light = QRadioButton(t("dialog.token_editor.mode_light", "라이트"))
        settings = self._read_settings
        text_theme = str(self._text_theme or settings.value("text_theme", "dark")).lower()
        (self.preset_mode_light if text_theme == "light" else self.preset_mode_dark).setChecked(
            True
        )
        for button in (self.preset_mode_all, self.preset_mode_dark, self.preset_mode_light):
            button.toggled.connect(self._refresh_color_preset_list)
        self.color_preset_note = QLabel("")
        self.color_preset_note.setWordWrap(True)
        self.color_preset_note.setProperty("role", "dialogSubtitle")
        self.color_preset_combo.currentTextChanged.connect(self._on_color_preset_changed)
        self.metric_preset_combo = QComboBox()
        self.metric_preset_combo.addItems(list(_METRIC_PRESETS.keys()))
        self.metric_preset_note = QLabel("")
        self.metric_preset_note.setWordWrap(True)
        self.metric_preset_note.setProperty("role", "dialogSubtitle")
        self.metric_preset_combo.currentTextChanged.connect(self._on_metric_preset_changed)
        for combo in (self.color_preset_combo, self.metric_preset_combo):
            combo.installEventFilter(self._wheel_blocker)

        self._main_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._main_layout.setSpacing(12)
        root.addLayout(self._main_layout, 1)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setObjectName("tokenEditorTabs")
        self.editor_tabs.setMinimumWidth(0)
        self.editor_tabs.addTab(self._build_color_tab(), t("dialog.token_editor.tab_color", "색상"))
        self.editor_tabs.addTab(
            self._build_metric_tab(), t("dialog.token_editor.tab_metric", "크기·간격")
        )
        self._main_layout.addWidget(self.editor_tabs, 3)

        self.preview_wrap = QFrame()
        self.preview_wrap.setObjectName("tokenPreviewWrap")
        self.preview_wrap.setStyleSheet(self._style_bundle["preview_wrap"])
        self.preview_wrap.setMinimumWidth(0)
        preview_lay = QVBoxLayout(self.preview_wrap)
        preview_lay.setContentsMargins(12, 10, 12, 10)
        preview_lay.setSpacing(8)
        preview_caption = QLabel(t("dialog.token_editor.preview_title", "실시간 미리보기"))
        preview_caption.setProperty("role", "dialogTitle")
        preview_lay.addWidget(preview_caption)
        self.preview_root = self._build_preview_widget()
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.viewport().setAutoFillBackground(False)
        self.preview_scroll.setWidget(self.preview_root)
        preview_lay.addWidget(self.preview_scroll, 1)
        self._main_layout.addWidget(self.preview_wrap, 2)

        self.feedback_label = QLabel("")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet(self._style_bundle["feedback_info"])
        self.feedback_label.setVisible(False)
        root.addWidget(self.feedback_label)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.reset_all_btn = QPushButton(t("dialog.token_editor.reset_all", "전체 기본값 복원"))
        self.reset_all_btn.setObjectName("danger_btn")
        self.change_summary = QLabel()
        self.change_summary.setProperty("role", "dialogSubtitle")
        self.cancel_btn = QPushButton(t("dialog.common.cancel", "취소"))
        self.cancel_btn.setObjectName("ghost_btn")
        self.apply_btn = QPushButton(t("dialog.common.apply", "적용"))
        self.apply_btn.setObjectName("primary_btn")
        for button in (self.reset_all_btn, self.cancel_btn, self.apply_btn):
            button.setAutoDefault(False)
        self.reset_all_btn.clicked.connect(self._reset_all)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn.clicked.connect(self._apply)
        footer.addWidget(self.reset_all_btn)
        footer.addWidget(self.change_summary, 1)
        footer.addWidget(self.cancel_btn)
        footer.addWidget(self.apply_btn)
        root.addLayout(footer)

        self._opening_colors, _ = self._collect_color_overrides(diff_only=False)
        self._opening_metric_overrides = self._collect_metric_overrides(diff_only=True)
        self.expert_mode_check.toggled.connect(self._set_expert_mode)
        self._set_expert_mode(False)
        self._refresh_color_preset_list()
        self._on_metric_preset_changed(self.metric_preset_combo.currentText())
        self._refresh_preview(force=True)
        self._update_responsive_layout()

    def _build_control_browser(self, *, metric: bool):
        browser = QWidget()
        layout = QVBoxLayout(browser)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        search = QLineEdit()
        search.setClearButtonEnabled(True)
        search.setPlaceholderText(
            t("dialog.token_editor.search_placeholder", "이름 또는 내부 키로 검색")
        )
        search.setAccessibleName(t("dialog.token_editor.search_label", "조정 항목 검색"))
        search.textChanged.connect(lambda text: self._set_search_query(text, metric=metric))
        layout.addWidget(search)
        row = QHBoxLayout()
        row.setSpacing(10)
        layout.addLayout(row, 1)
        navigation = QListWidget()
        navigation.setObjectName("tokenCategoryNavigation")
        navigation.setAccessibleName(t("dialog.token_editor.nav_title", "조정할 영역"))
        navigation.setWordWrap(True)
        navigation.setTextElideMode(Qt.TextElideMode.ElideNone)
        navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navigation.setMinimumWidth(112)
        navigation.setMaximumWidth(158)
        for category, key, fallback in (
            ("appearance", "group_appearance", "배경과 글자"),
            ("buttons", "group_buttons", "버튼"),
            ("fields", "group_fields", "입력 필드"),
            ("lists", "group_lists", "목록과 표"),
            ("metrics", "group_metrics", "크기·간격"),
        ):
            item = QListWidgetItem(t("dialog.token_editor." + key, fallback))
            item.setData(Qt.ItemDataRole.UserRole, category)
            navigation.addItem(item)
        row.addWidget(navigation)
        area = QScrollArea()
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidgetResizable(True)
        area.viewport().setAutoFillBackground(False)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body = QWidget()
        body.setAutoFillBackground(False)
        body.setMinimumWidth(0)
        rows = QVBoxLayout(body)
        rows.setContentsMargins(0, 0, 4, 0)
        rows.setSpacing(8)
        area.setWidget(body)
        # setWidget() turns auto-fill back on; keep the editor's reading surface.
        body.setAutoFillBackground(False)
        row.addWidget(area, 1)
        empty = QLabel(t("dialog.token_editor.no_results", "검색 결과가 없습니다."))
        empty.setWordWrap(True)
        empty.setProperty("role", "dialogSubtitle")
        rows.addWidget(empty)
        if metric:
            self.metric_search_edit, self.metric_category_nav = search, navigation
            self.metric_token_area, self._metric_empty = area, empty
        else:
            self.search_edit, self.category_nav = search, navigation
            self.color_token_area, self._color_empty = area, empty
        navigation.currentRowChanged.connect(lambda _: self._category_changed(metric=metric))
        return browser, rows

    def _row_shell(self, key: str, label_text: str):
        row = QFrame()
        row.setObjectName("tokenControlRow")
        row.setProperty("role", "dialogCard")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(5)
        label = QLabel(label_text)
        label.setWordWrap(True)
        label.setToolTip(key)
        layout.addWidget(label)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        layout.addLayout(controls)
        reset = QToolButton()
        reset.setIcon(
            icon(ICON.REFRESH, color=_to_qcolor(self._current_tokens.get("text_primary")).name())
        )
        reset.setToolTip(t("dialog.token_editor.reset_one", "기본값"))
        reset.setAccessibleName(label_text + " · " + reset.toolTip())
        return row, controls, reset

    def _build_color_tab(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(8)
        self.color_tab_layout = layout
        bar = QFrame()
        bar.setObjectName("presetBar")
        bar.setStyleSheet(self._style_bundle["preset_bar"])
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(8, 6, 8, 6)
        bar_layout.setSpacing(6)
        modes = QHBoxLayout()
        modes.addWidget(QLabel(t("dialog.token_editor.preset_filter_label", "프리셋 분류")))
        for button in (self.preset_mode_all, self.preset_mode_dark, self.preset_mode_light):
            modes.addWidget(button)
        modes.addStretch(1)
        bar_layout.addLayout(modes)
        presets = QHBoxLayout()
        presets.addWidget(self.color_preset_combo, 1)
        apply_preset = QPushButton(t("dialog.token_editor.apply_color_preset", "프리셋 적용"))
        apply_preset.setAutoDefault(False)
        apply_preset.clicked.connect(self._apply_selected_color_preset)
        presets.addWidget(apply_preset)
        bar_layout.addLayout(presets)
        layout.addWidget(bar)
        self.color_preset_note.setStyleSheet(self._style_bundle["preset_note"])
        layout.addWidget(self.color_preset_note)
        browser, rows = self._build_control_browser(metric=False)
        layout.addWidget(browser, 1)
        for _title, keys in self._grouped_color_keys:
            for key in keys:
                row, controls, reset = self._row_shell(
                    key, _TOKEN_LABELS.get(key, _fallback_token_label(key))
                )
                edit = QLineEdit(self._current_color(key))
                edit.setMinimumWidth(230)
                edit.setPlaceholderText("hex / rgba(r,g,b,a) / transparent")
                edit.setAccessibleName(_TOKEN_LABELS.get(key, key))
                swatch = QToolButton()
                swatch.setMinimumSize(34, 28)
                swatch.setToolTip(t("dialog.token_editor.pick", "선택") + " · " + key)
                swatch.setAccessibleName(swatch.toolTip())
                swatch.clicked.connect(lambda _=False, k=key: self._pick_color(k))
                reset.clicked.connect(lambda _=False, k=key: self._reset_color_key(k))
                edit.textChanged.connect(lambda _text, k=key: self._on_color_changed(k))
                controls.addWidget(swatch)
                controls.addWidget(edit, 1)
                controls.addWidget(reset)
                self._color_edits[key] = edit
                self._color_swatches[key] = swatch
                self._color_rows[key] = row
                rows.addWidget(row)
                self._update_color_row(key)
        rows.addStretch(1)
        self.category_nav.setCurrentRow(0)
        return wrapper

    def _build_metric_tab(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(8)
        self.metric_tab_layout = layout
        bar = QFrame()
        bar.setObjectName("presetBar")
        bar.setStyleSheet(self._style_bundle["preset_bar"])
        presets = QHBoxLayout(bar)
        presets.setContentsMargins(8, 6, 8, 6)
        presets.addWidget(self.metric_preset_combo, 1)
        button = QPushButton(t("dialog.token_editor.apply_metric_preset", "적용"))
        button.setAutoDefault(False)
        button.clicked.connect(self._apply_selected_metric_preset)
        presets.addWidget(button)
        layout.addWidget(bar)
        self.metric_preset_note.setStyleSheet(self._style_bundle["preset_note"])
        layout.addWidget(self.metric_preset_note)
        browser, rows = self._build_control_browser(metric=True)
        layout.addWidget(browser, 1)
        for _title, keys in self._grouped_metric_keys:
            for key in keys:
                default = int(self._default_metrics[key])
                text = _METRIC_LABELS.get(key, _fallback_token_label(key))
                row, controls, reset = self._row_shell(key, text)
                spin = QSpinBox()
                spin.installEventFilter(self._wheel_blocker)
                spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                spin.setAccessibleName(text)
                spin.setSuffix(" px")
                spin.setRange(*self._metric_bounds.get(key, (0, 999)))
                spin.setValue(int(self._current_metrics.get(key, default)))
                spin.valueChanged.connect(self._schedule_preview_refresh)
                reset.clicked.connect(lambda _=False, k=key: self._reset_metric_key(k))
                controls.addWidget(spin, 1)
                controls.addWidget(reset)
                self._metric_spins[key] = spin
                self._metric_rows[key] = row
                rows.addWidget(row)
        rows.addStretch(1)
        self.metric_category_nav.setCurrentRow(4)
        return wrapper

    def _set_search_query(self, text: str, *, metric: bool):
        self._search_query = text.strip().casefold()
        peer = self.search_edit if metric else getattr(self, "metric_search_edit", None)
        if peer is not None and peer.text() != text:
            blocked = peer.blockSignals(True)
            peer.setText(text)
            peer.blockSignals(blocked)
        self._filter_control_rows()

    def _category_changed(self, *, metric: bool):
        navigation = self.metric_category_nav if metric else self.category_nav
        item = navigation.currentItem()
        category = item.data(Qt.ItemDataRole.UserRole) if item else "appearance"
        if metric:
            self._metric_category = category
        elif category == "metrics" and self.editor_tabs.count() > 1:
            # This is a shortcut, not an empty color category. Preserve the
            # last color section when the user returns through the top tab.
            self.metric_category_nav.setCurrentRow(4)
            self.editor_tabs.setCurrentIndex(1)
            blocked = navigation.blockSignals(True)
            for index in range(navigation.count()):
                if navigation.item(index).data(Qt.ItemDataRole.UserRole) == self._color_category:
                    navigation.setCurrentRow(index)
                    break
            navigation.blockSignals(blocked)
        else:
            self._color_category = category
        self._filter_control_rows()

    def _set_expert_mode(self, enabled: bool):
        del enabled
        self._filter_control_rows()

    def _filter_control_rows(self):
        expert = self.expert_mode_check.isChecked()
        for metric, rows, category, recommended, labels, empty_name in (
            (
                False,
                self._color_rows,
                self._color_category,
                _RECOMMENDED_COLORS,
                _TOKEN_LABELS,
                "_color_empty",
            ),
            (
                True,
                self._metric_rows,
                self._metric_category,
                _RECOMMENDED_METRICS,
                _METRIC_LABELS,
                "_metric_empty",
            ),
        ):
            visible = 0
            for key, row in rows.items():
                matches = category == "metrics" if metric else False
                matches = (
                    bool(self._search_query)
                    or matches
                    or _control_category(key, metric=metric) == category
                )
                text = (labels.get(key, "") + " " + key).casefold()
                show = (
                    matches
                    and (expert or key in recommended)
                    and (not self._search_query or self._search_query in text)
                )
                row.setVisible(show)
                visible += int(show)
            empty = getattr(self, empty_name, None)
            if empty is not None:
                empty.setVisible(visible == 0)

    def _update_change_summary(self):
        if not hasattr(self, "_opening_colors"):
            return
        colors, invalid = self._collect_color_overrides(diff_only=False)
        changed = sum(
            (_normalize_color(edit.text()) or edit.text().strip()).lower()
            != self._opening_colors[key].lower()
            for key, edit in self._color_edits.items()
        )
        metrics = self._collect_metric_overrides(diff_only=True)
        missing = object()
        changed += sum(
            metrics.get(key, missing) != self._opening_metric_overrides.get(key, missing)
            for key in metrics.keys() | self._opening_metric_overrides.keys()
        )
        self.change_count = changed
        self.change_summary.setText(
            t("dialog.token_editor.changes_count", "변경 {count}개", count=changed)
            if changed
            else t("dialog.token_editor.no_changes", "변경 사항 없음")
        )
        self.apply_btn.setEnabled(bool(changed) and invalid is None)

    def _reveal_color_key(self, key):
        self.editor_tabs.setCurrentIndex(0)
        self.search_edit.clear()
        if key not in _RECOMMENDED_COLORS:
            self.expert_mode_check.setChecked(True)
        category = _control_category(key)
        for index in range(self.category_nav.count()):
            if self.category_nav.item(index).data(Qt.ItemDataRole.UserRole) == category:
                self.category_nav.setCurrentRow(index)
                break
        self._filter_control_rows()
        self.color_token_area.ensureWidgetVisible(self._color_rows[key])
        self._color_edits[key].setFocus()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "preview_wrap"):
            self._update_responsive_layout()

    def _update_responsive_layout(self):
        narrow = self.width() < 1060
        if narrow == self._responsive_mode:
            return
        self._responsive_mode = narrow
        self._main_layout.removeWidget(self.editor_tabs)
        self._main_layout.removeWidget(self.preview_wrap)
        self._main_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        )
        self.preview_wrap.setMaximumHeight(230 if narrow else 16777215)
        self._main_layout.addWidget(
            self.preview_wrap if narrow else self.editor_tabs, 2 if narrow else 3
        )
        self._main_layout.addWidget(
            self.editor_tabs if narrow else self.preview_wrap, 3 if narrow else 2
        )

    def _build_preview_widget(self) -> QWidget:
        root = QWidget()
        root.setObjectName("tokenLivePreview")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)

        title = QLabel(t("dialog.token_editor.preview_dialog_title", "샘플 다이얼로그 제목"))
        title.setProperty("role", "dialogTitle")
        subtitle = QLabel(
            t(
                "dialog.token_editor.preview_dialog_subtitle",
                "버튼 유형/입력 필드/리스트 스타일을 한 번에 확인합니다.",
            )
        )
        subtitle.setProperty("role", "dialogSubtitle")
        lay.addWidget(title)
        lay.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.setObjectName("tokenPreviewTabs")

        tab_form = QWidget()
        tab_form.setObjectName("tokenPreviewPage")
        form_page = QVBoxLayout(tab_form)
        form_page.setContentsMargins(0, 0, 0, 0)
        form_body = QWidget()
        form_body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form_page.addWidget(form_body, 0, Qt.AlignmentFlag.AlignTop)
        form_page.addStretch(1)
        form = QFormLayout(form_body)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setContentsMargins(8, 8, 8, 8)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        form.addRow(
            QLabel(t("dialog.token_editor.preview.title_label", "제목")),
            QLineEdit(t("dialog.token_editor.preview.title_value", "신규 업무")),
        )
        combo = QComboBox()
        combo.addItems(
            [
                t("dialog.token_editor.preview.status_pending", "미정"),
                t("dialog.token_editor.preview.status_in_progress", "진행"),
                t("dialog.token_editor.preview.status_done", "완료"),
            ]
        )
        form.addRow(QLabel(t("dialog.token_editor.preview.status_label", "상태")), combo)
        note = QTextEdit(t("dialog.token_editor.preview.memo_value", "메모 미리보기"))
        note.setFixedHeight(72)
        form.addRow(QLabel(t("dialog.token_editor.preview.memo_label", "메모")), note)

        urgency = QHBoxLayout()
        urgent = QCheckBox(t("dialog.token_editor.preview.urgent", "중요 일정"))
        urgent.setChecked(True)
        option = QRadioButton(t("dialog.token_editor.preview.repeat", "반복"))
        option.setChecked(True)
        urgency.addWidget(urgent)
        urgency.addWidget(option)
        urgency.addStretch(1)
        form.addRow(urgency)
        tabs.addTab(tab_form, t("dialog.token_editor.preview.tab_form", "폼"))

        tab_buttons = QWidget()
        tab_buttons.setObjectName("tokenPreviewPage")
        btn_lay = QVBoxLayout(tab_buttons)
        btn_lay.setContentsMargins(8, 8, 8, 8)
        btn_lay.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QPushButton(t("dialog.token_editor.preview.btn_default", "기본")))
        primary = QPushButton(t("dialog.token_editor.preview.btn_primary", "Primary"))
        primary.setProperty("previewVariant", "primary")
        row1.addWidget(primary)
        secondary = QPushButton(t("dialog.token_editor.preview.btn_secondary", "Secondary"))
        secondary.setProperty("previewVariant", "secondary")
        row1.addWidget(secondary)
        ghost = QPushButton(t("dialog.token_editor.preview.btn_ghost", "Ghost"))
        ghost.setProperty("previewVariant", "ghost")
        row1.addWidget(ghost)
        btn_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        success = QPushButton(t("dialog.token_editor.preview.btn_success", "Success"))
        success.setProperty("previewVariant", "success")
        row2.addWidget(success)
        danger = QPushButton(t("dialog.token_editor.preview.btn_danger", "Danger"))
        danger.setProperty("previewVariant", "danger")
        row2.addWidget(danger)
        disabled = QPushButton(t("dialog.token_editor.preview.btn_disabled", "Disabled"))
        disabled.setEnabled(False)
        row2.addWidget(disabled)
        row2.addStretch(1)
        btn_lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        tool1 = QToolButton()
        tool1.setText(t("dialog.token_editor.preview.tool_a", "툴 A"))
        tool2 = QToolButton()
        tool2.setText(t("dialog.token_editor.preview.tool_b", "툴 B"))
        tool3 = QToolButton()
        tool3.setText(t("dialog.token_editor.preview.tool_disabled", "툴 비활성"))
        tool3.setEnabled(False)
        row3.addWidget(tool1)
        row3.addWidget(tool2)
        row3.addWidget(tool3)
        row3.addStretch(1)
        btn_lay.addLayout(row3)
        btn_lay.addStretch(1)
        tabs.addTab(tab_buttons, t("dialog.token_editor.preview.tab_buttons", "버튼"))

        tab_list = QWidget()
        tab_list.setObjectName("tokenPreviewPage")
        list_lay = QVBoxLayout(tab_list)
        list_lay.setContentsMargins(8, 8, 8, 8)
        list_lay.setSpacing(8)
        lst = QListWidget()
        lst.addItems(
            [
                t("dialog.token_editor.preview.list_a", "항목 A"),
                t("dialog.token_editor.preview.list_b", "항목 B"),
                t("dialog.token_editor.preview.list_c", "항목 C"),
            ]
        )
        lst.setCurrentRow(1)
        table = QTableWidget(2, 3)
        table.setHorizontalHeaderLabels(
            [
                t("dialog.token_editor.preview.header_type", "유형"),
                t("dialog.token_editor.preview.header_desc", "설명"),
                t("dialog.token_editor.preview.header_status", "상태"),
            ]
        )
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setItem(0, 0, QTableWidgetItem(t("dialog.token_editor.preview.row1_type", "업무")))
        table.setItem(0, 1, QTableWidgetItem(t("dialog.token_editor.preview.row1_desc", "UI 점검")))
        table.setItem(
            0, 2, QTableWidgetItem(t("dialog.token_editor.preview.status_in_progress", "진행"))
        )
        table.setItem(1, 0, QTableWidgetItem(t("dialog.token_editor.preview.row2_type", "회의")))
        table.setItem(
            1, 1, QTableWidgetItem(t("dialog.token_editor.preview.row2_desc", "주간 보고"))
        )
        table.setItem(1, 2, QTableWidgetItem(t("dialog.token_editor.preview.status_done", "완료")))
        table.selectRow(0)
        list_lay.addWidget(lst)
        list_lay.addWidget(table)
        tabs.addTab(tab_list, t("dialog.token_editor.preview.tab_list", "리스트"))

        lay.addWidget(tabs, 1)
        return root

    def _default_color(self, key: str) -> str:
        return _normalize_color(self._default_tokens.get(key)) or "#4da6ff"

    def _current_color(self, key: str) -> str:
        return _normalize_color(self._current_tokens.get(key)) or self._default_color(key)

    def _update_color_row(self, key: str):
        edit = self._color_edits[key]
        swatch = self._color_swatches[key]
        normalized = _normalize_color(edit.text())
        edit.setToolTip(edit.text())
        if normalized:
            edit.setStyleSheet("")
            swatch.setStyleSheet(self._style_bundle["swatch_frame"].format(fill=normalized))
        else:
            edit.setStyleSheet(self._style_bundle["invalid_edit"])
            swatch.setStyleSheet(self._style_bundle["swatch_frame"].format(fill="transparent"))

    def _on_color_changed(self, key: str):
        self._update_color_row(key)
        self._schedule_preview_refresh()

    def _pick_color(self, key: str):
        edit = self._color_edits[key]
        initial = _to_qcolor(edit.text(), fallback=self._default_color(key))
        chosen = QColorDialog.getColor(
            initial,
            self,
            t("dialog.token_editor.pick_title", "색상 선택"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel
            | QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if chosen.isValid():
            edit.setText(
                chosen.name(QColor.NameFormat.HexRgb)
                if chosen.alpha() == 255
                else _rgba(chosen, chosen.alpha())
            )

    def _reset_color_key(self, key: str):
        self._color_edits[key].setText(self._default_color(key))

    def _reset_metric_key(self, key: str):
        self._metric_reset_keys.add(key)
        self._metric_spins[key].setValue(
            int(self._default_metrics.get(key, DIALOG_METRIC_DEFAULTS[key]))
        )
        self._schedule_preview_refresh()

    def _collect_color_overrides(self, diff_only: bool) -> tuple[dict, str | None]:
        overrides = {}
        for key, edit in self._color_edits.items():
            normalized = _normalize_color(edit.text())
            if not normalized:
                return {}, key
            if (not diff_only) or (normalized.lower() != self._default_color(key).lower()):
                overrides[key] = normalized
        return overrides, None

    def _collect_metric_overrides(self, diff_only: bool) -> dict:
        out = {}
        for key, spin in self._metric_spins.items():
            val = int(spin.value())
            default = int(self._default_metrics.get(key, DIALOG_METRIC_DEFAULTS[key]))
            preserve_explicit = (
                key in self._original_metric_overrides and key not in self._metric_reset_keys
            )
            if (not diff_only) or (val != default) or preserve_explicit:
                out[key] = val
        return out

    def _set_color_value_silently(self, key: str, value: str):
        edit = self._color_edits[key]
        if edit.text() == value:
            self._update_color_row(key)
            return
        blocked = edit.blockSignals(True)
        edit.setText(value)
        edit.blockSignals(blocked)
        self._update_color_row(key)

    def _set_metric_value_silently(self, key: str, value: int):
        spin = self._metric_spins[key]
        if int(spin.value()) == int(value):
            return
        blocked = spin.blockSignals(True)
        spin.setValue(int(value))
        spin.blockSignals(blocked)

    def _schedule_preview_refresh(self):
        self._update_change_summary()
        self._preview_timer.start()

    def _invalid_feedback_text(self) -> str:
        return t(
            "dialog.token_editor.invalid_short",
            "One or more color values are invalid. Use a hex color, rgba(r,g,b,a), or transparent.",
        )

    def _refresh_preview(self, force: bool = False):
        self._update_change_summary()
        token_overrides, invalid_key = self._collect_color_overrides(diff_only=False)
        invalid_feedback = self._invalid_feedback_text()
        if invalid_key:
            self._set_feedback(invalid_feedback, "error")
            token_overrides = {}
        elif self.feedback_label.isVisible() and self.feedback_label.text() == invalid_feedback:
            self._set_feedback()
        metric_overrides = self._collect_metric_overrides(diff_only=False)
        preview_tokens = dict(self._current_tokens)
        preview_tokens.update(token_overrides)
        preview_metrics = dict(self._current_metrics)
        preview_metrics.update(metric_overrides)
        css = build_dialog_preview_stylesheet(
            token_overrides=token_overrides,
            metric_overrides=metric_overrides,
            theme_color=self._theme_color,
            text_theme=self._text_theme,
            panel_base_color=self._panel_base_color,
            settings=self._read_settings,
        )
        preview_surface = preview_tokens["surface_bg"]
        preview_text = preview_tokens["text_primary"]
        css = (
            f"{css}\n{_preview_variant_stylesheet(tokens=preview_tokens, metrics=preview_metrics)}\n"
            "QWidget#tokenLivePreview, QWidget#tokenPreviewPage { "
            f"background: {preview_surface}; color: {preview_text}; "
            "}\nQTabWidget#tokenPreviewTabs::pane { "
            f"background: {preview_surface}; "
            "}"
        )
        if (not force) and css == self._last_preview_css:
            return
        self._last_preview_css = css
        self.preview_root.setStyleSheet(css)
        self.preview_root.style().unpolish(self.preview_root)
        self.preview_root.style().polish(self.preview_root)
        self.preview_root.update()

    def _resolve_color_preset_payload(self, preset_name: str) -> tuple[dict, str]:
        payload = _COLOR_PRESETS.get(preset_name, {})
        if isinstance(payload, dict):
            token_map = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
            note = str(payload.get("note") or "")
            return token_map, note
        return {}, ""

    def _resolve_metric_preset_payload(self, preset_name: str) -> tuple[dict, str]:
        payload = _METRIC_PRESETS.get(preset_name, {})
        if isinstance(payload, dict):
            metric_map = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            note = str(payload.get("note") or "")
            return metric_map, note
        return {}, ""

    def _on_color_preset_changed(self, preset_name: str):
        _, note = self._resolve_color_preset_payload(preset_name)
        if not note:
            note = "Preset applies color tokens only."
        self.color_preset_note.setText(note)

    def _on_metric_preset_changed(self, preset_name: str):
        _, note = self._resolve_metric_preset_payload(preset_name)
        if not note:
            note = "Preset applies spacing/size metric tokens only."
        self.metric_preset_note.setText(note)

    def _set_feedback(self, text: str = "", tone: str = "info"):
        self.feedback_label.setText(text)
        self.feedback_label.setVisible(bool(text))
        self.feedback_label.setStyleSheet(
            self._style_bundle.get(f"feedback_{tone}", self._style_bundle["feedback_info"])
        )

    def _refresh_color_preset_list(self):
        self.color_preset_combo.blockSignals(True)
        current = self.color_preset_combo.currentText()
        self.color_preset_combo.clear()

        items = ["Default (Auto)", "System Default"]
        if self.preset_mode_all.isChecked():
            items += list(_DARK_COLOR_PRESETS.keys()) + list(_LIGHT_COLOR_PRESETS.keys())
        elif self.preset_mode_dark.isChecked():
            items += list(_DARK_COLOR_PRESETS.keys())
        elif self.preset_mode_light.isChecked():
            items += list(_LIGHT_COLOR_PRESETS.keys())

        self.color_preset_combo.addItems(items)
        if current in items:
            self.color_preset_combo.setCurrentText(current)
        else:
            self.color_preset_combo.setCurrentIndex(0)
        self.color_preset_combo.blockSignals(False)
        self._on_color_preset_changed(self.color_preset_combo.currentText())

    def _export_tokens(self):
        import json

        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self,
            t("dialog.token_editor.export_title", "UI 토큰 내보내기"),
            "dc_theme_tokens.json",
            "JSON Files (*.json)",
        )
        if path:
            try:
                data = {
                    "version": "1.0",
                    "colors": self.get_color_overrides_from_edits(),
                    "metrics": self.get_metric_overrides_from_spins(),
                }
                with open(path, "w", encoding="utf-8", errors="strict") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                self._set_feedback(
                    t("dialog.token_editor.export_success", "UI tokens exported successfully."),
                    "success",
                )
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox

                self._set_feedback(
                    t(
                        "dialog.token_editor.export_failed",
                        "Failed to export UI tokens: {error}",
                        error=str(e),
                    ),
                    "error",
                )
                QMessageBox.warning(
                    self, t("dialog.token_editor.export_failed_title", "내보내기 실패"), str(e)
                )

    def _import_tokens(self):
        import json

        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self,
            t("dialog.token_editor.import_title", "UI 토큰 가져오기"),
            "",
            "JSON Files (*.json)",
        )
        if path:
            try:
                with open(path, encoding="utf-8", errors="strict") as f:
                    data = json.load(f)

                colors = data.get("colors", {})
                metrics = data.get("metrics", {})

                # Apply colors
                for key, val in colors.items():
                    if key in self._color_edits:
                        self._color_edits[key].setText(val)

                # Apply metrics
                for key, val in metrics.items():
                    if key in self._metric_spins:
                        self._metric_spins[key].setValue(int(val))

                self._refresh_preview(force=True)
                self._set_feedback(
                    t(
                        "dialog.token_editor.import_success",
                        "UI tokens imported successfully. Preview updated.",
                    ),
                    "success",
                )
            except Exception as e:
                self._set_feedback(
                    t(
                        "dialog.token_editor.import_failed",
                        "Could not load JSON: {error}",
                        error=str(e),
                    ),
                    "error",
                )
                QMessageBox.warning(
                    self, t("dialog.token_editor.import_failed_title", "가져오기 실패"), str(e)
                )

    def get_color_overrides_from_edits(self) -> dict:
        overrides = {}
        for key, edit in self._color_edits.items():
            val = edit.text().strip()
            if val:
                overrides[key] = val
        return overrides

    def get_metric_overrides_from_spins(self) -> dict:
        return self._collect_metric_overrides(diff_only=True)

    def _apply_selected_color_preset(self):
        preset_name = self.color_preset_combo.currentText()
        if preset_name == "System Default":
            for key in DIALOG_TOKEN_EDITABLE_KEYS:
                self._set_color_value_silently(key, self._default_color(key))
        else:
            token_map, _ = self._resolve_color_preset_payload(preset_name)
            for key in DIALOG_TOKEN_EDITABLE_KEYS:
                target = _normalize_color(token_map.get(key)) or self._default_color(key)
                self._set_color_value_silently(key, target)
        self._refresh_preview(force=True)
        self._set_feedback(
            t("dialog.token_editor.preset_applied", "Applied preset: {name}", name=preset_name),
            "info",
        )

    def _apply_metric_map(self, metric_map: dict):
        self._metric_reset_keys.update(self._metric_spins)
        for key in self._metric_spins:
            default = int(self._default_metrics.get(key, DIALOG_METRIC_DEFAULTS[key]))
            value = metric_map.get(key, default)
            try:
                value = int(value)
            except Exception:
                value = default
            lo, hi = self._metric_bounds.get(key, (0, 999))
            value = max(lo, min(hi, value))
            self._set_metric_value_silently(key, value)

    def _apply_selected_metric_preset(self):
        preset_name = self.metric_preset_combo.currentText()
        if preset_name == "System Default":
            self._metric_reset_keys.update(self._metric_spins)
            for key in self._metric_spins:
                default = int(self._default_metrics.get(key, DIALOG_METRIC_DEFAULTS[key]))
                self._set_metric_value_silently(key, default)
        else:
            metric_map, _ = self._resolve_metric_preset_payload(preset_name)
            self._apply_metric_map(metric_map)
        self._refresh_preview(force=True)
        self._set_feedback(
            t(
                "dialog.token_editor.metric_preset_applied",
                "Applied metric preset: {name}",
                name=preset_name,
            ),
            "info",
        )

    def _reset_all(self):
        self._metric_reset_keys.update(self._metric_spins)
        for key in self._color_edits:
            self._set_color_value_silently(key, self._default_color(key))
        for key in self._metric_spins:
            self._set_metric_value_silently(
                key, int(self._default_metrics.get(key, DIALOG_METRIC_DEFAULTS[key]))
            )
        self.color_preset_combo.setCurrentIndex(0)
        self.metric_preset_combo.setCurrentIndex(0)
        self._refresh_preview(force=True)
        self._set_feedback(
            t("dialog.token_editor.reset_done", "All dialog tokens were reset to defaults."),
            "warning",
        )

    def _apply(self):
        color_overrides, invalid_key = self._collect_color_overrides(diff_only=True)
        if invalid_key:
            self._set_feedback(self._invalid_feedback_text(), "error")
            QMessageBox.warning(
                self,
                t("dialog.token_editor.invalid_title", "입력 오류"),
                t(
                    "dialog.token_editor.invalid_msg",
                    "잘못된 색상 형식이 있습니다. 16진 색상 또는 rgba(r,g,b,a) 또는 transparent 형식으로 입력해 주세요.",
                ),
            )
            self._reveal_color_key(invalid_key)
            return

        metric_overrides = self._collect_metric_overrides(diff_only=True)
        self._result_color_overrides = dict(color_overrides)
        self._result_metric_overrides = dict(metric_overrides)
        if self._persist_on_apply:
            set_dialog_token_overrides(color_overrides, settings=self._settings)
            set_dialog_metric_overrides(metric_overrides, settings=self._settings)
        self._set_feedback(
            t("dialog.token_editor.apply_done", "Dialog token changes are ready to apply."),
            "success",
        )
        self.accept()

    def selected_color_overrides(self) -> dict:
        """Return the accepted sparse color overrides without exposing editor widgets."""
        return dict(self._result_color_overrides or {})

    def selected_metric_overrides(self) -> dict:
        """Return the accepted sparse metric overrides without exposing editor widgets."""
        return dict(self._result_metric_overrides or {})
