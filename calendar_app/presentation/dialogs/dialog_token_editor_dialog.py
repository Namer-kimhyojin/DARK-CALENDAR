"""Dialog UI token editor with live preview."""

from __future__ import annotations

import re

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
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
    DIALOG_METRIC_BOUNDS,
    DIALOG_METRIC_DEFAULTS,
    DIALOG_TOKEN_EDITABLE_KEYS,
    apply_common_dialog_style,
    build_dialog_preview_stylesheet,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    set_dialog_metric_overrides,
    set_dialog_token_overrides,
)
from calendar_app.shared.color_utils import parse_css_alpha_to_unit

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
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {a})"


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
            return f"rgba({r}, {g}, {b}, {a_i})"
        except Exception:
            return None

    q = QColor(raw)
    if q.isValid():
        if q.alpha() < 255:
            return f"rgba({q.red()}, {q.green()}, {q.blue()}, {q.alpha()})"
        return q.name(QColor.NameFormat.HexRgb)
    return None


def _fallback_token_label(key: str) -> str:
    return key.replace("_", " ").title()


def _to_qcolor(color_text: str | None, fallback: str = "#4da6ff") -> QColor:
    normalized = _normalize_color(color_text)
    if not normalized or normalized == "transparent":
        return QColor(fallback)
    match = _RGBA_RE.match(normalized)
    if match:
        return QColor(int(match.group(1)), int(match.group(2)), int(match.group(3)))
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


class DialogTokenEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("dialog.token_editor.title", "다이얼로그 UI 토큰 설정"))
        apply_common_dialog_style(self, minimum_width=1080, size=(1200, 820))
        self.setModal(True)

        self._default_tokens = get_dialog_theme_tokens(apply_overrides=False)
        self._current_tokens = get_dialog_theme_tokens(apply_overrides=True)
        self._default_metrics = get_dialog_metric_tokens(apply_overrides=False)
        self._current_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _dialog_token_editor_style_bundle(
            self._current_tokens, self._current_metrics
        )
        self._style_bundle = _dialog_token_editor_style_bundle(
            self._current_tokens, self._current_metrics
        )

        self._wheel_blocker = WheelBlocker(self)

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

        desc = QLabel(
            t(
                "dialog.token_editor.desc",
                "다이얼로그 공통 색상/크기/간격 토큰을 조정합니다. 버튼 타입별 스타일도 포함되며 우측 미리보기에서 즉시 확인할 수 있습니다.",
            )
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(self._style_bundle["desc"])
        root.addWidget(desc)

        # 프리셋 콤보/버튼/노트는 각 탭 내부(_build_color_tab/_build_metric_tab)에 배치.
        # 여기서는 콤보박스/노트 위젯만 미리 생성해 두고 탭 빌더에서 레이아웃에 삽입한다.
        self.color_preset_combo = QComboBox()
        self.preset_mode_all = QRadioButton(t("dialog.token_editor.mode_all", "모두"))
        self.preset_mode_dark = QRadioButton(t("dialog.token_editor.mode_dark", "다크"))
        self.preset_mode_light = QRadioButton(t("dialog.token_editor.mode_light", "라이트"))

        # Auto-select mode based on current settings
        settings = QSettings("kimhyojin", "Dark Calendar")
        text_theme = str(settings.value("text_theme", "dark")).lower()
        if text_theme == "light":
            self.preset_mode_light.setChecked(True)
        else:
            self.preset_mode_dark.setChecked(True)

        self.preset_mode_all.toggled.connect(self._refresh_color_preset_list)
        self.preset_mode_dark.toggled.connect(self._refresh_color_preset_list)
        self.preset_mode_light.toggled.connect(self._refresh_color_preset_list)

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

        main_row = QHBoxLayout()
        main_row.setSpacing(12)
        root.addLayout(main_row, 1)

        tabs = QTabWidget()
        tabs.addTab(self._build_color_tab(), t("dialog.token_editor.tab_color", "색상 토큰"))
        tabs.addTab(self._build_metric_tab(), t("dialog.token_editor.tab_metric", "크기/간격 토큰"))

        # 탭 빌드 후 시그널 초기 실행
        self._on_color_preset_changed(self.color_preset_combo.currentText())
        self._on_metric_preset_changed(self.metric_preset_combo.currentText())
        main_row.addWidget(tabs, 1)

        preview_wrap = QFrame()
        preview_wrap.setObjectName("tokenPreviewWrap")
        preview_wrap.setStyleSheet(self._style_bundle["preview_wrap"])
        preview_lay = QVBoxLayout(preview_wrap)
        preview_lay.setContentsMargins(8, 8, 8, 8)
        preview_lay.setSpacing(8)
        preview_caption = QLabel(t("dialog.token_editor.preview_title", "실시간 미리보기"))
        preview_caption.setProperty("role", "dialogTitle")
        preview_lay.addWidget(preview_caption)
        self.preview_root = self._build_preview_widget()
        preview_lay.addWidget(self.preview_root, 1)
        preview_wrap.setMinimumWidth(430)
        main_row.addWidget(preview_wrap, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)
        self.feedback_label = QLabel("")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet(self._style_bundle["feedback_info"])
        self.feedback_label.setVisible(False)
        footer_row.addWidget(self.feedback_label, 1)

        btn_row = QHBoxLayout()
        self.reset_all_btn = QPushButton(t("dialog.token_editor.reset_all", "전체 기본값 복원"))
        self.reset_all_btn.setObjectName("danger_btn")
        self.cancel_btn = QPushButton(t("dialog.common.cancel", "취소"))
        self.cancel_btn.setObjectName("ghost_btn")
        self.apply_btn = QPushButton(t("dialog.common.apply", "적용"))
        self.apply_btn.setObjectName("primary_btn")

        self.reset_all_btn.clicked.connect(self._reset_all)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn.clicked.connect(self._apply)

        btn_row.addWidget(self.reset_all_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.apply_btn)
        footer_row.addLayout(btn_row, 1)
        root.addLayout(footer_row)

        self._refresh_preview(force=True)

    def _build_color_tab(self) -> QWidget:
        # 탭 전체 래퍼 (프리셋 바 + 스크롤 콘텐츠)
        wrapper = QWidget()
        wrapper_lay = QVBoxLayout(wrapper)
        wrapper_lay.setContentsMargins(0, 0, 0, 0)
        wrapper_lay.setSpacing(0)

        # ── 프리셋 바 ─────────────────────────────────────────────────────────
        preset_bar = QFrame()
        preset_bar.setObjectName("presetBar")
        preset_bar.setStyleSheet(self._style_bundle["preset_bar"])
        bar_lay = QVBoxLayout(preset_bar)
        bar_lay.setContentsMargins(10, 8, 10, 8)
        bar_lay.setSpacing(6)

        # 1행: 테마 모드 라디오 + Export/Import 버튼 (우측)
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        mode_label = QLabel(t("dialog.token_editor.preset_color_mode", "테마 모드:"))
        row1.addWidget(mode_label)
        row1.addWidget(self.preset_mode_all)
        row1.addWidget(self.preset_mode_dark)
        row1.addWidget(self.preset_mode_light)
        row1.addStretch(1)
        export_btn = QPushButton("JSON 내보내기")
        export_btn.setStyleSheet(self._style_bundle["button_ghost"])
        export_btn.setFixedWidth(100)
        export_btn.clicked.connect(self._export_tokens)
        import_btn = QPushButton("JSON 가져오기")
        import_btn.setStyleSheet(self._style_bundle["button_ghost"])
        import_btn.setFixedWidth(100)
        import_btn.clicked.connect(self._import_tokens)
        row1.addWidget(export_btn)
        row1.addWidget(import_btn)
        bar_lay.addLayout(row1)

        # 2행: 프리셋 선택 콤보 + 적용 버튼
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(QLabel(t("dialog.token_editor.preset_color", "색상 프리셋:")))
        row2.addWidget(self.color_preset_combo, 1)
        color_preset_apply_btn = QPushButton(
            t("dialog.token_editor.apply_color_preset", "프리셋 적용")
        )
        color_preset_apply_btn.setStyleSheet(self._style_bundle["button_secondary"])
        color_preset_apply_btn.setFixedWidth(90)
        color_preset_apply_btn.clicked.connect(self._apply_selected_color_preset)
        row2.addWidget(color_preset_apply_btn)
        bar_lay.addLayout(row2)

        wrapper_lay.addWidget(preset_bar)
        self.color_preset_note.setStyleSheet(self._style_bundle["preset_note"])
        wrapper_lay.addWidget(self.color_preset_note)

        # ── 스크롤 토큰 목록 ─────────────────────────────────────────────────
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(4, 4, 4, 4)
        body_lay.setSpacing(10)

        for title, keys in self._grouped_color_keys:
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)
            grid.setContentsMargins(12, 14, 12, 10)
            # col 0: 토큰명(고정), col 1: 색상값 입력(stretch), col 2: 스와치(고정), col 3: 선택버튼(고정), col 4: 기본값버튼(고정)
            grid.setColumnStretch(1, 1)
            grid.setColumnMinimumWidth(0, 140)
            grid.setColumnMinimumWidth(2, 36)
            grid.setColumnMinimumWidth(3, 66)
            grid.setColumnMinimumWidth(4, 72)

            # 헤더 행
            for col, text in enumerate(
                [
                    t("dialog.token_editor.header_token", "토큰"),
                    t("dialog.token_editor.header_value", "색상값"),
                    t("dialog.token_editor.header_preview", "미리보기"),
                    "",
                    "",
                ]
            ):
                lbl = QLabel(text)
                if col == 0:
                    lbl.setFixedWidth(140)
                grid.addWidget(lbl, 0, col)

            row = 1
            for key in keys:
                label = QLabel(_TOKEN_LABELS.get(key, _fallback_token_label(key)))
                label.setToolTip(key)
                label.setFixedWidth(140)
                edit = QLineEdit()
                edit.setPlaceholderText("hex / rgba(r,g,b,a) / transparent")
                edit.setText(self._current_color(key))
                swatch = QLabel()
                swatch.setFixedSize(32, 22)
                pick_btn = QPushButton(t("dialog.token_editor.pick", "선택"))
                pick_btn.setStyleSheet(self._style_bundle["button_secondary"])
                pick_btn.setFixedWidth(66)
                reset_btn = QPushButton(t("dialog.token_editor.reset_one", "기본값"))
                reset_btn.setStyleSheet(self._style_bundle["button_ghost"])
                reset_btn.setFixedWidth(72)

                edit.textChanged.connect(lambda _text, k=key: self._on_color_changed(k))
                pick_btn.clicked.connect(lambda _=False, k=key: self._pick_color(k))
                reset_btn.clicked.connect(lambda _=False, k=key: self._reset_color_key(k))

                grid.addWidget(label, row, 0)
                grid.addWidget(edit, row, 1)
                grid.addWidget(swatch, row, 2, alignment=Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(pick_btn, row, 3)
                grid.addWidget(reset_btn, row, 4)

                self._color_edits[key] = edit
                self._color_swatches[key] = swatch
                self._update_color_row(key)
                row += 1

            body_lay.addWidget(box)

        body_lay.addStretch(1)
        area.setWidget(body)
        wrapper_lay.addWidget(area, 1)
        return wrapper

    def _build_metric_tab(self) -> QWidget:
        # 탭 전체 래퍼 (프리셋 바 + 스크롤 콘텐츠)
        wrapper = QWidget()
        wrapper_lay = QVBoxLayout(wrapper)
        wrapper_lay.setContentsMargins(0, 0, 0, 0)
        wrapper_lay.setSpacing(0)

        # ── 프리셋 바 ─────────────────────────────────────────────────────────
        preset_bar = QFrame()
        preset_bar.setObjectName("presetBar")
        preset_bar.setStyleSheet(self._style_bundle["preset_bar"])
        bar_lay = QHBoxLayout(preset_bar)
        bar_lay.setContentsMargins(8, 6, 8, 6)
        bar_lay.setSpacing(8)

        bar_lay.addWidget(QLabel(t("dialog.token_editor.preset_metric", "프리셋")))
        bar_lay.addWidget(self.metric_preset_combo, 1)
        metric_preset_apply_btn = QPushButton(t("dialog.token_editor.apply_metric_preset", "적용"))
        metric_preset_apply_btn.setStyleSheet(self._style_bundle["button_secondary"])
        metric_preset_apply_btn.setFixedWidth(72)
        metric_preset_apply_btn.clicked.connect(self._apply_selected_metric_preset)
        bar_lay.addWidget(metric_preset_apply_btn)
        wrapper_lay.addWidget(preset_bar)
        self.metric_preset_note.setStyleSheet(self._style_bundle["preset_note"])
        wrapper_lay.addWidget(self.metric_preset_note)

        # ── 스크롤 토큰 목록 ─────────────────────────────────────────────────
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(4, 4, 4, 4)
        body_lay.setSpacing(10)

        for title, keys in self._grouped_metric_keys:
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)
            grid.setContentsMargins(12, 14, 12, 10)
            # col 0: 항목명(고정), col 1: 스핀박스(고정), col 2: 기본값버튼(고정), col 3: 힌트(stretch)
            grid.setColumnMinimumWidth(0, 160)
            grid.setColumnMinimumWidth(1, 80)
            grid.setColumnMinimumWidth(2, 72)
            grid.setColumnStretch(3, 1)

            for row, key in enumerate(keys):
                default = int(DIALOG_METRIC_DEFAULTS[key])
                label = QLabel(_METRIC_LABELS.get(key, _fallback_token_label(key)))
                label.setToolTip(key)
                label.setFixedWidth(160)

                spin = QSpinBox()
                spin.installEventFilter(self._wheel_blocker)
                spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                spin.setFixedWidth(80)
                lo, hi = DIALOG_METRIC_BOUNDS.get(key, (0, 999))
                spin.setRange(lo, hi)
                spin.setValue(int(self._current_metrics.get(key, default)))
                spin.valueChanged.connect(self._schedule_preview_refresh)

                reset_btn = QPushButton(t("dialog.token_editor.reset_one", "기본값"))
                reset_btn.setStyleSheet(self._style_bundle["button_ghost"])
                reset_btn.setFixedWidth(72)
                reset_btn.clicked.connect(lambda _=False, k=key: self._reset_metric_key(k))

                hint = QLabel(f"기본: {default}")
                hint.setStyleSheet(self._style_bundle["metric_hint"])
                hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

                grid.addWidget(label, row, 0)
                grid.addWidget(spin, row, 1)
                grid.addWidget(reset_btn, row, 2)
                grid.addWidget(hint, row, 3)
                self._metric_spins[key] = spin

            body_lay.addWidget(box)

        body_lay.addStretch(1)
        area.setWidget(body)
        wrapper_lay.addWidget(area, 1)
        return wrapper

    def _build_preview_widget(self) -> QWidget:
        root = QWidget()
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

        tab_form = QWidget()
        form = QFormLayout(tab_form)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(8)
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
            initial, self, t("dialog.token_editor.pick_title", "색상 선택")
        )
        if chosen.isValid():
            edit.setText(chosen.name(QColor.NameFormat.HexRgb))

    def _reset_color_key(self, key: str):
        self._color_edits[key].setText(self._default_color(key))

    def _reset_metric_key(self, key: str):
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
            if (not diff_only) or (val != default):
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
        self._preview_timer.start()

    def _invalid_feedback_text(self) -> str:
        return t(
            "dialog.token_editor.invalid_short",
            "One or more color values are invalid. Use a hex color, rgba(r,g,b,a), or transparent.",
        )

    def _refresh_preview(self, force: bool = False):
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
        )
        css = (
            f"{css}\n{_preview_variant_stylesheet(tokens=preview_tokens, metrics=preview_metrics)}"
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
        overrides = {}
        for key, spin in self._metric_spins.items():
            val = spin.value()
            if val != DIALOG_METRIC_DEFAULTS.get(key):
                overrides[key] = val
        return overrides

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
        for key in self._metric_spins:
            default = int(self._default_metrics.get(key, DIALOG_METRIC_DEFAULTS[key]))
            value = metric_map.get(key, default)
            try:
                value = int(value)
            except Exception:
                value = default
            lo, hi = DIALOG_METRIC_BOUNDS.get(key, (0, 999))
            value = max(lo, min(hi, value))
            self._set_metric_value_silently(key, value)

    def _apply_selected_metric_preset(self):
        preset_name = self.metric_preset_combo.currentText()
        if preset_name == "System Default":
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
            self._color_edits[invalid_key].setFocus()
            return

        metric_overrides = self._collect_metric_overrides(diff_only=True)
        set_dialog_token_overrides(color_overrides)
        set_dialog_metric_overrides(metric_overrides)
        self._set_feedback(
            t("dialog.token_editor.apply_done", "Dialog token changes are ready to apply."),
            "success",
        )
        self.accept()
