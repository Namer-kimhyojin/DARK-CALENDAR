"""Overlay Widget Manager Dialog — 위젯 관리자.

UI 토큰 기반 디자인:
  get_dialog_theme_tokens() → accent, text_primary/secondary/muted, surface_*,
                               border, border_soft, danger_hex, success_hex
  get_dialog_metric_tokens() → button_height, button_radius, field_height, …
"""

from __future__ import annotations

import functools
import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.overlay_manager import _WIDGET_TYPES, widget_type_label
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se

logger = logging.getLogger(__name__)


# ── 위젯 타입별 아이콘 + 강조색 ──────────────────────────────────────────────
_TYPE_META: dict[str, tuple[str, str]] = {
    "clock": ("🕐", QColor(77, 166, 255).name(QColor.NameFormat.HexRgb)),
    "weather": ("🌤", QColor(56, 189, 248).name(QColor.NameFormat.HexRgb)),
    "stopwatch": ("⏱", QColor(245, 158, 11).name(QColor.NameFormat.HexRgb)),
    "date_card": ("📅", QColor(167, 139, 250).name(QColor.NameFormat.HexRgb)),
    "countdown": ("⏳", QColor(248, 113, 113).name(QColor.NameFormat.HexRgb)),
    "dday": ("📆", QColor(52, 211, 153).name(QColor.NameFormat.HexRgb)),
    "text": ("✏️", QColor(148, 163, 184).name(QColor.NameFormat.HexRgb)),
}


def _hex_rgb(hex_color: str) -> str:
    """hex → 'r,g,b' 변환."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r},{g},{b}"
    return "77,166,255"


def _type_color(wtype: str, tok: dict) -> str:
    """위젯 타입 강조색 — 가능한 경우 테마 토큰 사용."""
    if wtype in ("clock", "weather"):
        return tok["accent"]
    if wtype == "countdown":
        return tok["danger"]
    if wtype == "dday":
        return tok["success"]
    if wtype == "text":
        return tok["text_muted"]
    # stopwatch("#f59e0b"), date_card("#a78bfa") — 고유 의미색 유지
    _, color = _TYPE_META.get(wtype, ("▪", tok["accent"]))
    return color


# ── 토큰 번들 ─────────────────────────────────────────────────────────────────


def _q(h: str, a: float) -> str:
    """hex + alpha → CSS color string."""
    from PyQt6.QtGui import QColor as _QColor

    c = _QColor(h)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


def _load_tokens() -> dict:
    """dialog_theme 토큰 + metric 토큰을 통합한 번들 반환."""
    tok = get_dialog_theme_tokens()
    met = get_dialog_metric_tokens(apply_overrides=True)

    success_hex = str(tok.get("success_hex") or tok.get("button_success_text") or tok.get("accent"))
    danger_hex = str(tok.get("danger_hex") or tok.get("button_danger_text") or tok.get("accent"))

    return {
        "accent": str(tok.get("accent", "")),
        "accent_soft": str(tok.get("accent_soft_bg", "")),
        "accent_border": str(tok.get("accent_soft_border", "")),
        "accent_hover": str(tok.get("accent_hover", tok.get("accent", ""))),
        "text_primary": str(tok.get("text_primary", "")),
        "text_secondary": str(tok.get("text_secondary", "")),
        "text_muted": str(tok.get("text_muted", "")),
        "text_faint": str(tok.get("text_faint", tok.get("text_muted", ""))),
        "bg_main": str(tok.get("surface_bg", "")),
        "bg_alt": str(tok.get("surface_alt", "")),
        "bg_item": str(tok.get("surface_item", "")),
        "bg_item_hover": str(tok.get("surface_hover", "")),
        "border": str(tok.get("border", "")),
        "border_strong": str(tok.get("border_strong") or tok.get("border", "")),
        "divider": str(tok.get("border_soft") or tok.get("border", "")),
        "success": success_hex,
        "success_bg": _q(success_hex, 0.20),
        "success_bg_hover": _q(success_hex, 0.32),
        "success_border": _q(success_hex, 0.45),
        "danger": danger_hex,
        "btn_h": int(met.get("button_height") or 34),
        "fld_h": int(met.get("field_height") or 34),
        "btn_r": int(met.get("button_radius") or 8),
        "r_sm": int(met.get("toolbutton_radius") or 6),
        "r_md": int(met.get("field_radius") or 8),
        "r_card": int(met.get("list_radius") or 8),
    }


def _overlay_manager_style_bundle(tokens=None, metrics=None) -> dict:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    return {
        "accent": str(tokens.get("accent", "")),
        "danger": str(tokens.get("danger_hex", tokens.get("accent", ""))),
        "success": str(tokens.get("success_hex", tokens.get("accent", ""))),
        "add_bar": (
            f"background: {tokens.get('surface_alt', '')}; "
            f"border: 1px solid {tokens.get('border', '')}; "
            f"border-radius: {int(metrics.get('field_radius', 8))}px;"
        ),
        "description": (
            f"color: {tokens.get('text_muted', '')}; "
            f"font-size: {int(metrics.get('subtitle_font_pt', 10))}pt;"
        ),
        "row_name": (
            f"color: {tokens.get('text_primary', '')}; "
            f"font-size: {int(metrics.get('base_font_pt', 10))}pt;"
        ),
    }


def _build_web_ui_stylesheet(tokens=None, metrics=None) -> str:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    mapped = {
        "accent": str(tokens.get("accent", "")),
        "accent_soft": str(tokens.get("accent_soft_bg", tokens.get("surface_hover", ""))),
        "accent_border": str(tokens.get("accent_soft_border", tokens.get("border", ""))),
        "accent_hover": str(tokens.get("accent_hover", tokens.get("accent", ""))),
        "text_primary": str(tokens.get("text_primary", "")),
        "text_secondary": str(tokens.get("text_secondary", tokens.get("text_muted", ""))),
        "text_muted": str(tokens.get("text_muted", "")),
        "text_faint": str(tokens.get("text_faint", tokens.get("text_muted", ""))),
        "bg_main": str(tokens.get("surface_bg", "")),
        "bg_alt": str(tokens.get("surface_alt", "")),
        "bg_item": str(tokens.get("surface_item", "")),
        "bg_item_hover": str(tokens.get("surface_hover", "")),
        "border": str(tokens.get("border", "")),
        "border_strong": str(tokens.get("border", "")),
        "divider": str(tokens.get("border_soft", tokens.get("border", ""))),
        "success": str(tokens.get("success_hex", tokens.get("accent", ""))),
        "success_bg": str(tokens.get("success_soft_bg", tokens.get("surface_hover", ""))),
        "success_bg_hover": str(tokens.get("success_soft_bg", tokens.get("surface_hover", ""))),
        "success_border": str(tokens.get("success_hex", tokens.get("accent", ""))),
        "danger": str(tokens.get("danger_hex", tokens.get("accent", ""))),
        "btn_h": int(metrics.get("button_height", 34)),
        "fld_h": int(metrics.get("field_height", 34)),
        "btn_r": int(metrics.get("button_radius", 8)),
        "r_sm": int(metrics.get("toolbutton_radius", 6)),
        "r_md": int(metrics.get("field_radius", 8)),
        "r_card": int(metrics.get("list_radius", 8)),
    }
    return (
        _build_manager_css(mapped)
        + f"/* border-radius: {int(metrics.get('button_radius', 8)) + 2}px; */"
    )


def _overlay_toggle_styles(tokens=None, metrics=None) -> dict:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    radius = int(metrics.get("button_radius", 8))
    return {
        "on": f"background: {tokens.get('success_hex', tokens.get('accent', ''))}; border-radius: {radius}px;",
        "off": f"background: {tokens.get('surface_item', '')}; border-radius: {radius}px;",
    }


def _overlay_action_icon_style(tokens=None, metrics=None, tone="accent") -> str:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    color = tokens.get("danger_hex" if tone == "danger" else "accent", "")
    return f"color: {color}; border-radius: {int(metrics.get('toolbutton_radius', 6))}px;"


def _build_manager_css(tok: dict) -> str:
    """다이얼로그 전체 정적 스타일시트 (objectName 셀렉터 기반)."""
    r_md = tok["r_md"]
    r_sm = tok["r_sm"]
    r_card = tok["r_card"]
    return (
        f"QDialog {{ background: {tok['bg_main']}; color: {tok['text_primary']}; }}"
        f"QFrame#MgrHdr {{ background: {tok['bg_alt']}; border-bottom: 1px solid {tok['divider']}; }}"
        f"QLabel#overlayManagerTitle {{ color: {tok['text_primary']}; font-size: 14pt; font-weight: 700; }}"
        f"QLabel#overlayManagerDesc {{ color: {tok['text_muted']}; font-size: 9pt; }}"
        f"QFrame#overlayManagerAddBar {{ background: {tok['bg_main']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_md}px; }}"
        f"QLabel#mgrNewLabel {{ color: {tok['text_muted']}; font-size: 9pt; font-weight: 600;"
        f" background: transparent; border: none; }}"
        f"QComboBox#typeCombo {{ background: {tok['bg_item']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_sm}px; padding: 0 10px; color: {tok['text_primary']};"
        f" font-size: 10pt; font-weight: 500; }}"
        f"QComboBox#typeCombo:hover {{ border-color: {tok['accent_border']}; }}"
        f"QComboBox#typeCombo::drop-down {{ border: none; width: 20px; }}"
        f"QLineEdit#nameEditBar {{ background: {tok['bg_item']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_sm}px; padding: 0 10px; color: {tok['text_primary']}; font-size: 10pt; }}"
        f"QLineEdit#nameEditBar:focus {{ border-color: {tok['accent']}; }}"
        f"QLabel#secLabel {{ color: {tok['text_faint']}; font-size: 8.5pt;"
        f" font-weight: 700; letter-spacing: 1px; }}"
        f"QLabel#countBadge {{ background: {tok['bg_item']}; color: {tok['text_muted']};"
        f" border: 1px solid {tok['border']}; border-radius: {min(r_sm, 10)}px;"
        f" font-size: 8pt; font-weight: 700; padding: 0 7px; min-height: 18px; }}"
        f"QScrollArea {{ background: transparent; border: none; }}"
        f"QLabel#emptyLabel {{ color: {tok['text_faint']}; font-size: 10.5pt; padding: 48px; }}"
        f"QFrame#MgrFoot {{ border-top: 1px solid {tok['divider']}; background: {tok['bg_alt']}; }}"
        f"QLabel#overlayManagerHint {{ color: {tok['text_faint']}; font-size: 9pt;"
        f" border: none; background: transparent; }}"
        f"QPushButton#primary_btn {{ background: {tok['accent_soft']}; color: {tok['accent']};"
        f" border: 1px solid {tok['accent_border']}; border-radius: {tok['btn_r']}px;"
        f" font-size: 9.5pt; font-weight: 700; padding: 0 14px; }}"
        f"QPushButton#primary_btn:hover {{ background: {tok['accent_hover']}; color: {tok['text_primary']};"
        f" border-color: {tok['accent']}; }}"
        f"QPushButton#ghost_btn {{ background: {tok['bg_item']}; color: {tok['text_secondary']};"
        f" border: 1px solid {tok['border']}; border-radius: {tok['btn_r']}px;"
        f" font-size: 9.5pt; font-weight: 600; padding: 0 14px; }}"
        f"QPushButton#ghost_btn:hover {{ background: {tok['bg_item_hover']}; color: {tok['text_primary']};"
        f" border-color: {tok['border_strong']}; }}"
        f"QFrame#WidgetCard {{ background: {tok['bg_item']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_card}px; border-left: none;"
        f" border-top-left-radius: 0; border-bottom-left-radius: 0; }}"
        f"QFrame#WidgetCard:hover {{ background: {tok['bg_item_hover']};"
        f" border-color: {tok['accent_border']}; }}"
        f"QLineEdit#cardNameEdit {{ background: transparent; border: none;"
        f" border-bottom: 1px solid transparent; color: {tok['text_primary']};"
        f" font-size: 11pt; font-weight: 600; padding: 0; }}"
        f"QLabel#cardIdLabel {{ color: {tok['text_faint']}; font-size: 8pt; font-weight: 400; }}"
        f"QPushButton#outlineBtn {{ background: {tok['bg_item']}; color: {tok['text_secondary']};"
        f" border: 1px solid {tok['border']}; border-radius: {r_sm}px;"
        f" font-size: 9pt; font-weight: 600; padding: 0 12px; }}"
        f"QPushButton#outlineBtn:hover {{ background: {tok['bg_item_hover']}; color: {tok['text_primary']};"
        f" border-color: {tok['accent_border']}; }}"
    )


# ── 서브 위젯 ─────────────────────────────────────────────────────────────────


class _Chip(QLabel):
    """타입 표시용 색상 칩."""

    def __init__(self, wtype: str, tokens: dict, parent=None):
        super().__init__(parent)
        icon_char, _ = _TYPE_META.get(wtype, ("▪", ""))
        color = _type_color(wtype, tokens)
        self.setText(f"{icon_char} {_se(widget_type_label(wtype))}")
        r = tokens["r_sm"]
        self.setStyleSheet(
            f"QLabel {{ background: {_q(color, 0.15)}; color: {color};"
            f" border: 1px solid {_q(color, 0.30)}; border-radius: {r}px;"
            f" font-size: 8.5pt; font-weight: 700; padding: 1px 8px; }}"
        )
        self.setFixedHeight(20)


class _ToggleBtn(QPushButton):
    """ON/OFF 알약 토글 버튼."""

    def __init__(self, enabled: bool, tokens: dict, parent=None):
        super().__init__(parent)
        self._tokens = tokens
        self.setCheckable(True)
        self.setChecked(enabled)
        self.setFixedSize(54, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()
        self.toggled.connect(lambda _: self._refresh())

    def _refresh(self):
        on = self.isChecked()
        tok = self._tokens
        r = min(tok["r_md"], 12)
        if on:
            bg = tok["success_bg"]
            bh = tok["success_bg_hover"]
            col = tok["success"]
            brd = tok["success_border"]
        else:
            bg = tok["bg_item"]
            bh = tok["bg_item_hover"]
            col = tok["text_muted"]
            brd = tok["border"]

        self.setText("ON" if on else "OFF")
        self.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {col}; border: 1px solid {brd};"
            f" border-radius: {r}px; font-weight: 800; font-size: 8pt; letter-spacing: 0.5px; }}"
            f"QPushButton:hover {{ background: {bh}; }}"
        )


class _GhostBtn(QPushButton):
    """투명 배경의 소형 아이콘 버튼."""

    def __init__(self, qicon, tip: str, color: str, tokens: dict, parent=None):
        super().__init__(parent)
        self.setIcon(qicon)
        self.setIconSize(QSize(15, 15))
        self.setToolTip(tip)
        r = tokens["r_sm"]
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" border-radius: {r}px; }}"
            f"QPushButton:hover {{ background: {_q(color, 0.14)}; }}"
        )


class _OutlineBtn(QPushButton):
    """테두리형 소형 버튼."""

    def __init__(self, text: str, tokens: dict, parent=None):
        super().__init__(text, parent)
        self.setObjectName("outlineBtn")
        self.setFixedHeight(max(tokens["btn_h"] - 8, 24))
        self.setCursor(Qt.CursorShape.PointingHandCursor)


# ── 위젯 카드 ─────────────────────────────────────────────────────────────────


class WidgetCard(QFrame):
    """한 줄 위젯 카드: [ accent_bar │ chip │ name/id │ toggle │ 설정 │ ◎ ↺ ✕ ]"""

    def __init__(
        self,
        iid: str,
        name: str,
        wtype: str,
        widget,
        tokens: dict,
        on_toggle,
        on_rename,
        on_focus,
        on_reset,
        on_delete,
        on_settings,
        parent=None,
    ):
        super().__init__(parent)
        self.iid = iid
        self._tokens = tokens
        self.setObjectName("WidgetCard")

        is_on = widget.is_enabled()
        accent = _type_color(wtype, tokens)
        text_primary = tokens["text_primary"]

        card_h = max(tokens["btn_h"] + 18, 54)
        self.setFixedHeight(card_h)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 10, 0)
        root.setSpacing(6)

        # 왼쪽 액센트 바 — type color or muted
        self._bar = QFrame()
        self._bar.setFixedWidth(3)
        bar_color = accent if is_on else tokens["divider"]
        self._bar.setStyleSheet(f"background: {bar_color}; border-radius: 0;")
        root.addWidget(self._bar)

        # 타입 칩
        root.addWidget(_Chip(wtype, tokens))

        # 이름 + ID
        info = QVBoxLayout()
        info.setSpacing(1)
        info.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.name_edit = QLineEdit(name or t("widget_manager.unnamed", "이름 없음"))
        self.name_edit.setObjectName("cardNameEdit")
        self.name_edit.setPlaceholderText(t("widget_manager.unnamed", "이름 없음"))
        self.name_edit.editingFinished.connect(lambda: on_rename(iid, self.name_edit.text()))

        id_lbl = QLabel(iid)
        id_lbl.setObjectName("cardIdLabel")

        info.addWidget(self.name_edit)
        info.addWidget(id_lbl)
        root.addLayout(info, 1)

        # ON/OFF 토글
        self.toggle = _ToggleBtn(is_on, tokens)
        self.toggle.toggled.connect(functools.partial(on_toggle, iid))
        root.addWidget(self.toggle)

        # 설정 버튼
        btn_cfg = _GhostBtn(
            _ic(ICON.SETTINGS, color=text_primary),
            t("widget_manager.btn_settings", "설정"),
            tokens["accent"],
            tokens,
        )
        btn_cfg.clicked.connect(lambda: on_settings(iid))
        root.addWidget(btn_cfg)

        # 액션 아이콘
        btn_focus = _GhostBtn(
            _ic(ICON.SNAP_CENTER, color=text_primary),
            t("widget_manager.tip_center", "화면 중앙으로"),
            tokens["accent"],
            tokens,
        )
        btn_reset = _GhostBtn(
            _ic(ICON.RESET_POS, color=text_primary),
            t("widget_manager.tip_reset", "위치 초기화"),
            tokens["text_muted"],
            tokens,
        )
        btn_del = _GhostBtn(
            _ic(ICON.DELETE, color=text_primary),
            t("widget_manager.tip_delete", "삭제"),
            tokens["danger"],
            tokens,
        )
        btn_focus.clicked.connect(lambda: on_focus(iid))
        btn_reset.clicked.connect(lambda: on_reset(iid))
        btn_del.clicked.connect(lambda: on_delete(iid))
        root.addWidget(btn_focus)
        root.addWidget(btn_reset)
        root.addWidget(btn_del)


# ── 메인 다이얼로그 ───────────────────────────────────────────────────────────


class OverlayManagerDialog(QDialog):
    """위젯 관리자 다이얼로그 — dialog_styles 토큰 기반."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._mgr = manager
        self._tok = _load_tokens()

        apply_dialog_title(self, t("widget_manager.title", "위젯 관리자"))
        apply_common_dialog_style(self, minimum_width=760, size=(840, 560))
        self.setStyleSheet(_build_manager_css(self._tok))

        self._cards: dict[str, WidgetCard] = {}
        self._build_ui()
        self._populate()
        self._mgr.add_listener(self._sync_from_manager)

    # ── UI 구성 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        tok = self._tok
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 헤더 ──
        hdr = QFrame()
        hdr.setObjectName("MgrHdr")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(18, 12, 18, 10)
        hdr_lay.setSpacing(8)

        # 제목 행
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title_lbl = QLabel(t("widget_manager.title", "위젯 관리자"))
        title_lbl.setObjectName("overlayManagerTitle")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        self.btn_show_all = self._mk_btn(
            t("widget_manager.btn_show_all", "모두 표시"), primary=True
        )
        self.btn_hide_all = self._mk_btn(
            t("widget_manager.btn_hide_all", "모두 숨김"), primary=False
        )
        self.btn_delete_all = self._mk_btn(
            t("widget_manager.btn_delete_all", "전체 삭제..."), primary=False
        )
        self.btn_delete_all.setObjectName("DangerBtn")
        self.btn_show_all.setFixedWidth(84)
        self.btn_hide_all.setFixedWidth(84)
        self.btn_delete_all.setFixedWidth(90)
        self.btn_show_all.clicked.connect(self._show_all)
        self.btn_hide_all.clicked.connect(self._hide_all)
        self.btn_delete_all.clicked.connect(self._delete_all)
        title_row.addWidget(self.btn_show_all)
        title_row.addWidget(self.btn_hide_all)
        title_row.addWidget(self.btn_delete_all)
        hdr_lay.addLayout(title_row)

        desc_lbl = QLabel(t("widget_manager.desc", "화면에 표시할 위젯을 관리합니다."))
        desc_lbl.setObjectName("overlayManagerDesc")
        hdr_lay.addWidget(desc_lbl)

        # 추가 바
        add_bar = QFrame()
        add_bar.setObjectName("overlayManagerAddBar")
        add_lay = QHBoxLayout(add_bar)
        add_lay.setContentsMargins(10, 5, 8, 5)
        add_lay.setSpacing(6)

        self._type_combo = QComboBox()
        self._type_combo.setObjectName("typeCombo")
        self._type_combo.setFixedHeight(tok["fld_h"] - 4)
        self._type_combo.setFixedWidth(172)
        for wtype in _WIDGET_TYPES:
            icon_char, _ = _TYPE_META.get(wtype, ("▪", ""))
            self._type_combo.addItem(
                f"{icon_char}  {_se(widget_type_label(wtype))}", userData=wtype
            )
        add_lay.addWidget(self._type_combo)

        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("nameEditBar")
        self._name_edit.setPlaceholderText(t("widget_manager.name_placeholder", "위젯 이름 (선택)"))
        self._name_edit.setFixedHeight(tok["fld_h"] - 4)
        self._name_edit.returnPressed.connect(self._add_instance)
        add_lay.addWidget(self._name_edit, 1)

        btn_add = self._mk_btn(t("widget_manager.btn_add", "+ 추가"), primary=True)
        btn_add.setFixedWidth(72)
        btn_add.clicked.connect(self._add_instance)
        add_lay.addWidget(btn_add)
        hdr_lay.addWidget(add_bar)
        root.addWidget(hdr)

        # ── 목록 섹션 헤더 ──
        sec = QFrame()
        sec_lay = QHBoxLayout(sec)
        sec_lay.setContentsMargins(18, 8, 18, 4)
        sec_lay.setSpacing(8)

        sec_lbl = QLabel(t("widget_manager.list_heading", "위젯 목록"))
        sec_lbl.setObjectName("secLabel")
        self._count_badge = QLabel("0")
        self._count_badge.setObjectName("countBadge")
        sec_lay.addWidget(sec_lbl)
        sec_lay.addWidget(self._count_badge)
        sec_lay.addStretch()
        root.addWidget(sec)

        # ── 스크롤 목록 ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_container = QWidget()
        self._list_lay = QVBoxLayout(self._list_container)
        self._list_lay.setContentsMargins(16, 4, 16, 10)
        self._list_lay.setSpacing(3)

        self._empty_lbl = QLabel(
            t("widget_manager.empty", "위젯이 없습니다.\n상단에서 새 위젯을 추가하세요.")
        )
        self._empty_lbl.setObjectName("emptyLabel")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_lay.addWidget(self._empty_lbl)
        self._list_lay.addStretch()

        self._scroll.setWidget(self._list_container)
        root.addWidget(self._scroll, 1)

        # ── 푸터 ──
        foot = QFrame()
        foot.setObjectName("MgrFoot")
        foot_lay = QHBoxLayout(foot)
        foot_lay.setContentsMargins(18, 8, 18, 8)

        hint = QLabel(t("widget_manager.footer_hint", "이름 클릭 → 수정  ·  설정 버튼 → 위젯 옵션"))
        hint.setObjectName("overlayManagerHint")
        foot_lay.addWidget(hint)
        foot_lay.addStretch()

        btn_close = self._mk_btn(t("common.close", "닫기"), primary=False)
        btn_close.setFixedWidth(72)
        btn_close.clicked.connect(self.close)
        foot_lay.addWidget(btn_close)
        root.addWidget(foot)

    # ── 버튼 팩토리 ──────────────────────────────────────────────────────────
    def _mk_btn(self, text: str, primary: bool) -> QPushButton:
        tok = self._tok
        b = QPushButton(text)
        b.setFixedHeight(max(tok["btn_h"] - 4, 28))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setObjectName("primary_btn" if primary else "ghost_btn")
        return b

    # ── 목록 갱신 ────────────────────────────────────────────────────────────
    def _populate(self):
        for card in list(self._cards.values()):
            self._list_lay.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            if item and item.widget() and item.widget() is not self._empty_lbl:
                pass

        instances = self._mgr.all_instances()
        count = len(instances)

        self._count_badge.setText(str(count))
        self._empty_lbl.setVisible(count == 0)

        if count == 0:
            self._list_lay.addWidget(self._empty_lbl)
            self._list_lay.addStretch()
            return

        for iid, name, wtype, widget in instances:
            card = WidgetCard(
                iid,
                name,
                wtype,
                widget,
                tokens=self._tok,
                on_toggle=self._on_toggle,
                on_rename=self._on_rename,
                on_focus=self._on_focus,
                on_reset=self._on_reset_pos,
                on_delete=self._on_delete,
                on_settings=self._on_settings,
                parent=self._list_container,
            )
            self._list_lay.addWidget(card)
            self._cards[iid] = card

        self._list_lay.addStretch()

    def _sync_from_manager(self):
        self._populate()

    # ── 액션 ─────────────────────────────────────────────────────────────────
    def _add_instance(self):
        wtype = self._type_combo.currentData()
        name = self._name_edit.text().strip() or None
        iid = self._mgr.add_instance(wtype, name)
        self._mgr.show_instance(iid)
        self._name_edit.clear()
        self._populate()

    def _on_toggle(self, iid: str, checked: bool):
        if checked:
            self._mgr.show_instance(iid)
        else:
            self._mgr.hide_instance(iid)

    def _on_rename(self, iid: str, text: str):
        if text.strip():
            self._mgr.rename_instance(iid, text.strip())

    def _on_focus(self, iid: str):
        from PyQt6.QtWidgets import QApplication

        w = self._mgr.get_widget(iid)
        if not w:
            return
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            w.move(g.x() + (g.width() - w.width()) // 2, g.y() + (g.height() - w.height()) // 2)
            w.save_position()
        if not w.is_enabled():
            self._mgr.show_instance(iid)
            self._populate()
        else:
            w.raise_()

    def _on_reset_pos(self, iid: str):
        w = self._mgr.get_widget(iid)
        if w and hasattr(w, "_action_reset_position"):
            w._action_reset_position()

    def _on_delete(self, iid: str):
        self._mgr._ui_remove_with_confirm(iid, parent_widget=self)
        self._populate()

    def _on_settings(self, iid: str):
        w = self._mgr.get_widget(iid)
        if w and hasattr(w, "_open_settings"):
            w._open_settings()

    def _show_all(self):
        for iid, _, _, _ in self._mgr.all_instances():
            self._mgr.show_instance(iid)
        self._populate()

    def _hide_all(self):
        for iid, _, _, _ in self._mgr.all_instances():
            self._mgr.hide_instance(iid)
        self._populate()

    def _delete_all(self):
        self._mgr._ui_remove_all_with_confirm(parent_widget=self)
        self._populate()

    def closeEvent(self, e):
        self._mgr.remove_listener(self._sync_from_manager)
        super().closeEvent(e)
