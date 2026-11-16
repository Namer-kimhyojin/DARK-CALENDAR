# -*- coding: utf-8 -*-
"""Overlay Widget Manager Dialog — 위젯 관리자.

UI 토큰 기반 디자인:
  get_dialog_theme_tokens() → accent, text_primary/secondary/muted, surface_*,
                               border, border_soft, danger_hex, success_hex
  get_dialog_metric_tokens() → button_height, button_radius, field_height, …
"""

from __future__ import annotations

import functools
import logging

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
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
from calendar_app.presentation.widgets.overlay_manager import widget_type_label
from calendar_app.presentation.widgets.widget_management_styles import management_styles
from calendar_app.presentation.widgets.widget_management_ui import (
    WidgetAddDialog,
    WidgetModeManagementPanel,
    hub_button,
)
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.typography import get_typography_scale

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
    "launcher_deck": ("⌨", QColor(96, 165, 250).name(QColor.NameFormat.HexRgb)),
    "loop_deck": ("♪", QColor(167, 139, 250).name(QColor.NameFormat.HexRgb)),
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


def _load_tokens(settings=None) -> dict:
    """dialog_theme 토큰 + metric 토큰을 통합한 번들 반환."""
    tok = get_dialog_theme_tokens(settings=settings)
    met = get_dialog_metric_tokens(apply_overrides=True, settings=settings)

    success_hex = str(tok.get("success_hex") or tok.get("button_success_text") or tok.get("accent"))
    danger_hex = str(tok.get("danger_hex") or tok.get("button_danger_text") or tok.get("accent"))

    typography = get_typography_scale(settings=settings)
    return {
        "body_px": typography.body_px,
        "caption_px": typography.caption_px,
        "section_px": typography.section_px,
        "title_px": int(met["title_font_pt"]),
        "accent": str(tok.get("accent", "")),
        "accent_soft": str(tok.get("accent_soft_bg", "")),
        "accent_border": str(tok.get("accent_soft_border", "")),
        "accent_hover": str(tok.get("accent_hover", tok.get("accent", ""))),
        "text_primary": str(tok.get("text_primary", "")),
        "text_secondary": str(tok.get("text_secondary", "")),
        "text_muted": str(tok.get("text_muted", "")),
        "text_faint": str(tok.get("text_faint", tok.get("text_muted", ""))),
        "bg_main": str(tok.get("floating_bg", tok.get("surface_bg", ""))),
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
    metrics = {**get_dialog_metric_tokens(apply_overrides=True), **(metrics or {})}
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
            f"font-size: {int(metrics['subtitle_font_pt'])}px;"
        ),
        "row_name": (
            f"color: {tokens.get('text_primary', '')}; font-size: {int(metrics['base_font_pt'])}px;"
        ),
    }


def _build_web_ui_stylesheet(tokens=None, metrics=None) -> str:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = {**get_dialog_metric_tokens(apply_overrides=True), **(metrics or {})}
    typography = get_typography_scale(base_pt=float(metrics["base_font_pt"]) * 0.75)
    mapped = {
        "title_px": int(metrics["title_font_pt"]),
        "body_px": int(metrics["base_font_pt"]),
        "caption_px": int(metrics["subtitle_font_pt"]),
        "section_px": typography.section_px,
        "accent": str(tokens.get("accent", "")),
        "accent_soft": str(tokens.get("accent_soft_bg", tokens.get("surface_hover", ""))),
        "accent_border": str(tokens.get("accent_soft_border", tokens.get("border", ""))),
        "accent_hover": str(tokens.get("accent_hover", tokens.get("accent", ""))),
        "text_primary": str(tokens.get("text_primary", "")),
        "text_secondary": str(tokens.get("text_secondary", tokens.get("text_muted", ""))),
        "text_muted": str(tokens.get("text_muted", "")),
        "text_faint": str(tokens.get("text_faint", tokens.get("text_muted", ""))),
        "bg_main": str(tokens.get("floating_bg", tokens.get("surface_bg", ""))),
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
        f"QLabel#overlayManagerTitle {{ color: {tok['text_primary']}; font-size: {tok['title_px']}px; font-weight: 700; }}"
        f"QLabel#overlayManagerDesc {{ color: {tok['text_muted']}; font-size: {tok['caption_px']}px; }}"
        f"QFrame#overlayManagerAddBar {{ background: {tok['bg_main']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_md}px; }}"
        f"QLabel#mgrNewLabel {{ color: {tok['text_muted']}; font-size: {tok['caption_px']}px; font-weight: 600;"
        f" background: transparent; border: none; }}"
        f"QComboBox#typeCombo {{ background: {tok['bg_item']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_sm}px; padding: 0 10px; color: {tok['text_primary']};"
        f" font-size: {tok['body_px']}px; font-weight: 500; }}"
        f"QComboBox#typeCombo:hover {{ border-color: {tok['accent_border']}; }}"
        f"QComboBox#typeCombo::drop-down {{ border: none; width: 20px; }}"
        f"QLineEdit#nameEditBar {{ background: {tok['bg_item']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_sm}px; padding: 0 10px; color: {tok['text_primary']}; font-size: {tok['body_px']}px; }}"
        f"QLineEdit#nameEditBar:focus {{ border-color: {tok['accent']}; }}"
        f"QLabel#secLabel {{ color: {tok['text_faint']}; font-size: {tok['caption_px']}px;"
        f" font-weight: 700; letter-spacing: 1px; }}"
        f"QLabel#countBadge {{ background: {tok['bg_item']}; color: {tok['text_muted']};"
        f" border: 1px solid {tok['border']}; border-radius: {min(r_sm, 10)}px;"
        f" font-size: {tok['caption_px']}px; font-weight: 700; padding: 0 7px; min-height: 18px; }}"
        f"QScrollArea#widgetListScroll {{ background: {tok['bg_main']}; border: none; }}"
        f"QWidget#widgetListViewport, QWidget#widgetListContainer {{"
        f" background: {tok['bg_main']}; border: none; }}"
        f"QLabel#emptyLabel {{ color: {tok['text_faint']}; font-size: {tok['body_px']}px; padding: 48px; }}"
        f"QFrame#MgrFoot {{ border-top: 1px solid {tok['divider']}; background: {tok['bg_alt']}; }}"
        f"QLabel#overlayManagerHint {{ color: {tok['text_faint']}; font-size: {tok['caption_px']}px;"
        f" border: none; background: transparent; }}"
        f"QFrame#WidgetCard {{ background: {tok['bg_item']}; border: 1px solid {tok['border']};"
        f" border-radius: {r_card}px; border-left: none;"
        f" border-top-left-radius: 0; border-bottom-left-radius: 0; }}"
        f"QFrame#WidgetCard:hover {{ background: {tok['bg_item_hover']};"
        f" border-color: {tok['accent_border']}; }}"
        f"QLineEdit#cardNameEdit {{ background: transparent; border: none;"
        f" border-bottom: 1px solid transparent; color: {tok['text_primary']};"
        f" font-size: {tok['body_px']}px; font-weight: 600; padding: 0; }}"
        f"QLabel#cardIdLabel {{ color: {tok['text_faint']}; font-size: {tok['caption_px']}px; font-weight: 400; }}"
        f"QPushButton#outlineBtn {{ background: {tok['bg_item']}; color: {tok['text_secondary']};"
        f" border: 1px solid {tok['border']}; border-radius: {r_sm}px;"
        f" font-size: {tok['caption_px']}px; font-weight: 600; padding: 0 12px; }}"
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
            f" font-size: {tokens['caption_px']}px; font-weight: 700; padding: 1px 8px; }}"
        )
        self.setMinimumHeight(max(20, self.fontMetrics().height() + 4))


class _ToggleBtn(QPushButton):
    """ON/OFF 알약 토글 버튼."""

    def __init__(self, enabled: bool, tokens: dict, parent=None):
        super().__init__(parent)
        self._tokens = tokens
        self.setCheckable(True)
        self.setChecked(enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()
        # Fonts with tall line spacing (Segoe UI, Malgun Gothic) need more than px + 10.
        self.ensurePolished()
        self.setMinimumSize(54, max(24, tokens["caption_px"] + 10, self.fontMetrics().height() + 4))
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

        self.setText(t("common.toggle_on", "ON") if on else t("common.toggle_off", "OFF"))
        self.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {col}; border: 1px solid {brd};"
            f" border-radius: {r}px; font-weight: 800; font-size: {tok['caption_px']}px; letter-spacing: 0.5px; }}"
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
        self.setMinimumHeight(max(tokens["btn_h"] - 8, tokens["body_px"] + 10, 24))
        self.setCursor(Qt.CursorShape.PointingHandCursor)


# ── 위젯 카드 ─────────────────────────────────────────────────────────────────


class WidgetCard(QFrame):
    """Stable, editable row with visible primary actions and a secondary menu."""

    def __init__(
        self,
        iid,
        name,
        wtype,
        widget,
        tokens,
        on_toggle,
        on_rename,
        on_focus,
        on_reset,
        on_duplicate,
        on_delete,
        on_settings,
        on_graphics=None,
        parent=None,
    ):
        super().__init__(parent)
        self.iid, self.wtype, self.widget = iid, wtype, widget
        self._tokens = tokens
        self.setObjectName("WidgetCard")
        self.setProperty("role", "dialogCard")
        self.setMinimumHeight(86)
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 10, 12, 10)
        root.setSpacing(12)
        info = QVBoxLayout()
        info.setSpacing(3)
        self.name_edit = QLineEdit(name or t("widget_manager.unnamed", "이름 없음"))
        self.name_edit.setObjectName("cardNameEdit")
        self.name_edit.setAccessibleName(t("widget_hub.rename", "위젯 이름 변경"))
        self.name_edit.setToolTip(
            t("widget_hub.rename_hint", "이름을 수정하고 Enter를 눌러 저장하세요")
        )
        self.name_edit.editingFinished.connect(lambda: on_rename(iid, self.name_edit.text()))
        self.detail = QLabel()
        self.detail.setObjectName("cardIdLabel")
        self.detail.setToolTip(iid)
        info.addWidget(self.name_edit)
        info.addWidget(self.detail)
        root.addLayout(info, 1)
        self.toggle = _ToggleBtn(widget.is_enabled(), tokens)
        self.toggle.setAutoDefault(False)
        self.toggle.setMinimumSize(64, max(28, self.toggle.minimumHeight()))
        self.toggle.toggled.connect(functools.partial(on_toggle, iid))
        root.addWidget(self.toggle)
        self.find_button = hub_button(t("widget_hub.find", "찾기"), lambda: on_focus(iid))
        self.find_button.setToolTip(t("widget_hub.find_hint", "이 화면 중앙으로 가져와 표시합니다"))
        root.addWidget(self.find_button)
        self.graphics_button = hub_button(
            t("loopdeck.open", "루프 믹서 열기")
            if wtype == "loop_deck"
            else t("widget_hub.decorate", "꾸미기"),
            lambda: on_graphics(iid),
            primary=True,
        )
        self.graphics_button.setEnabled(
            callable(on_graphics)
            and hasattr(
                widget, "_open_settings" if wtype == "loop_deck" else "_open_graphic_collections"
            )
        )
        root.addWidget(self.graphics_button)
        self.more_button = hub_button(t("widget_hub.more", "더보기"), lambda: None)
        self.more_menu = QMenu(self.more_button)
        self.more_menu.addAction(t("widget_manager.btn_settings", "설정"), lambda: on_settings(iid))
        lock_reader = getattr(widget, "placement_is_locked", None)
        self.lock_action = None
        if callable(lock_reader):
            self.lock_action = self.more_menu.addAction(
                t("widget_hub.lock_position", "위치·크기 잠금")
            )
            self.lock_action.setCheckable(True)
            self.lock_action.triggered.connect(self._lock_position)
        self.more_menu.addAction(
            t("widget_manager.tip_reset", "위치 초기화"), lambda: on_reset(iid)
        )
        self.more_menu.addAction(
            t("widget_manager.tip_duplicate", "복제"), lambda: on_duplicate(iid)
        )
        self.more_menu.addSeparator()
        self.more_menu.addAction(t("widget_manager.tip_delete", "삭제"), lambda: on_delete(iid))
        self.more_menu.aboutToShow.connect(lambda: self.update_state(self.name_edit.text(), widget))
        self.more_button.setMenu(self.more_menu)
        root.addWidget(self.more_button)
        self.update_state(name, widget)

    def _lock_position(self, checked):
        self.widget._set_placement_locked(checked)
        self.update_state(self.name_edit.text(), self.widget)

    def update_state(self, name, widget):
        self.widget = widget
        if not self.name_edit.hasFocus() and not self.name_edit.isModified():
            self.name_edit.setText(name or t("widget_manager.unnamed", "이름 없음"))
        enabled = widget.is_enabled()
        self.toggle.blockSignals(True)
        self.toggle.setChecked(enabled)
        self.toggle._refresh()
        self.toggle.setText(
            t("widget_hub.shown", "표시 중") if enabled else t("widget_hub.hidden", "숨김")
        )
        self.toggle.setAccessibleName(
            t("widget_hub.visibility_for", "{name} 표시 전환").format(name=name)
        )
        self.toggle.blockSignals(False)
        locked = bool(getattr(widget, "placement_is_locked", lambda: False)())
        state = t("widget_hub.shown", "표시 중") if enabled else t("widget_hub.hidden", "숨김")
        group = getattr(widget, "_overlay_manager_stack_state", lambda: None)()
        if enabled and group and group["members"][group["index"]] != self.iid:
            state = t("widget_studio.stack_waiting", "스택 대기")
        from calendar_app.presentation.widgets.widget_workspace_preview import widget_health

        health, label, hint = widget_health(widget, self.wtype)
        if health != "normal":
            state += " · " + label
        self.detail.setToolTip(hint or self.iid)
        if locked:
            state += " · " + t("widget_hub.position_locked", "배치 잠김")
        self.detail.setText(f"{_se(widget_type_label(self.wtype))}  ·  {state}")
        if self.lock_action is not None:
            self.lock_action.setChecked(locked)


class OverlayManagerDialog(QDialog):
    """Nonmodal hub; querying, filtering and opening editors never enters widget mode."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._mgr = manager
        self._tok = _load_tokens(settings=getattr(parent, "settings", None))
        self._cards = {}
        self._instances = []
        self._listening = True
        factory = getattr(manager, "workspace_service", None)
        self.studio = factory() if callable(factory) else None
        self.gallery = None
        self._snap_action = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._populate)
        apply_dialog_title(self, t("widget_manager.title", "위젯 관리자"))
        apply_common_dialog_style(
            self,
            minimum_width=760,
            size=(940, 680),
            extra_stylesheet=_build_manager_css(self._tok) + management_styles(self._tok),
        )
        self._build_ui()
        self._populate()
        self._mgr.add_listener(self._sync_from_manager)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        self._header_frame = header
        header.setObjectName("MgrHdr")
        header.setProperty("role", "dialogHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(20, 16, 20, 14)
        title = QLabel(t("widget_manager.title", "위젯 관리자"))
        title.setObjectName("overlayManagerTitle")
        head.addWidget(title)
        desc = QLabel(
            t(
                "widget_hub.description",
                "바탕화면 위젯부터 캘린더 전용 화면까지, 한곳에서 관리하세요.",
            )
        )
        desc.setObjectName("overlayManagerDesc")
        desc.setWordWrap(True)
        head.addWidget(desc)
        root.addWidget(header)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("hubTabs")
        desktop = QWidget()
        desktop.setObjectName("hubDesktopBody")
        desktop.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body = QVBoxLayout(desktop)
        body.setContentsMargins(18, 14, 18, 8)
        body.setSpacing(12)
        addbar = QFrame()
        addbar.setObjectName("overlayManagerAddBar")
        tools = QHBoxLayout(addbar)
        tools.setContentsMargins(10, 8, 10, 8)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("hubSearch")
        self.search_edit.setPlaceholderText(t("widget_hub.search", "이름 또는 위젯 종류 검색"))
        self.search_edit.setAccessibleName(t("widget_hub.search", "이름 또는 위젯 종류 검색"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filters)
        tools.addWidget(self.search_edit, 1)
        self.visibility_combo = QComboBox()
        self.visibility_combo.setObjectName("hubFilter")
        self.visibility_combo.setAccessibleName(t("widget_hub.visibility_filter", "표시 상태 필터"))
        for key, label in (
            ("all", t("widget_hub.all", "전체 상태")),
            ("shown", t("widget_hub.shown", "표시 중")),
            ("hidden", t("widget_hub.hidden", "숨김")),
        ):
            self.visibility_combo.addItem(label, key)
        self.visibility_combo.currentIndexChanged.connect(self._apply_filters)
        if self.studio is not None:
            self.visibility_combo.addItem(t("widget_studio.stack_waiting", "스택 대기"), "waiting")
        tools.addWidget(self.visibility_combo)
        self.add_button = self._mk_btn(t("widget_hub.add", "위젯 추가"), True)
        self.add_button.clicked.connect(self._add_instance)
        tools.addWidget(self.add_button)
        body.addWidget(addbar)
        row = QHBoxLayout()
        self._count_badge = QLabel()
        self._count_badge.setObjectName("hubBody")
        row.addWidget(self._count_badge)
        self.view_combo = QComboBox()
        self.view_combo.setObjectName("hubView")
        self.view_combo.setAccessibleName(t("widget_studio.view", "관리창 보기"))
        self.view_combo.addItem(t("widget_studio.list_view", "목록"))
        if self.studio is not None:
            self.view_combo.addItem(t("widget_studio.gallery_view", "갤러리"))
        self.view_combo.currentIndexChanged.connect(self._set_view)
        row.addWidget(self.view_combo)
        row.addStretch()
        self.btn_show_all = self._mk_btn(t("widget_hub.show_all", "전체 표시"), False)
        self.btn_hide_all = self._mk_btn(t("widget_hub.hide_all", "전체 숨김"), False)
        self.btn_show_all.clicked.connect(self._show_all)
        self.btn_hide_all.clicked.connect(self._hide_all)
        row.addWidget(self.btn_show_all)
        row.addWidget(self.btn_hide_all)
        self.bulk_more = self._mk_btn(t("widget_hub.more", "더보기"), False)
        bulk_menu = QMenu(self.bulk_more)
        bulk_menu.addAction(t("widget_manager.btn_delete_all", "전체 삭제..."), self._delete_all)
        if self.studio is not None:
            bulk_menu.addSeparator()
            bulk_menu.addAction(
                t("widget_studio.layout_editor", "바탕화면 배치 편집"), self._edit_desktop
            )
            bulk_menu.addAction(
                t("widget_studio.create_stack", "선택 위젯 스택 만들기"), self._create_stack
            )
            bulk_menu.addAction(
                t("widget_studio.ungroup_selected", "선택 위젯 스택 해제"), self._ungroup_selected
            )
            bulk_menu.addAction(t("widget_studio.undo", "최근 적용 되돌리기"), self.studio.undo)
            self._snap_action = bulk_menu.addAction(
                t("widget_manager.snap_enabled", "가장자리와 위젯에 맞춤")
            )
            self._snap_action.setCheckable(True)
        self.bulk_more.setMenu(bulk_menu)
        row.addWidget(self.bulk_more)
        body.addLayout(row)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("widgetListScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.viewport().setObjectName("widgetListViewport")
        self._list_container = QWidget()
        self._list_container.setObjectName("widgetListContainer")
        self._list_lay = QVBoxLayout(self._list_container)
        self._list_lay.setContentsMargins(0, 0, 6, 8)
        self._list_lay.setSpacing(8)
        self._empty_lbl = QLabel()
        self._empty_lbl.setObjectName("emptyLabel")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._list_lay.addWidget(self._empty_lbl)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._list_container)
        self._views = QStackedWidget()
        self._views.setMinimumHeight(80)
        self._views.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self._views.addWidget(self._scroll)
        if self.studio is not None:
            from calendar_app.presentation.widgets.widget_workspace_gallery import WidgetGallery

            self.gallery = WidgetGallery(self, self.studio)
            self._views.addWidget(self.gallery)
        body.addWidget(self._views, 1)
        self._snap_check = QCheckBox(t("widget_manager.snap_enabled", "가장자리와 위젯에 맞춤"))
        self._snap_check.setObjectName("hubSnap")
        settings_getter = getattr(self._mgr, "_settings", None)
        settings = settings_getter() if callable(settings_getter) else None
        self._snap_check.setChecked(
            settings.value("overlay_snap_enabled", True, type=bool)
            if settings is not None
            else True
        )
        if settings is not None:
            self._snap_check.toggled.connect(
                lambda enabled: settings.setValue("overlay_snap_enabled", enabled)
            )
        body.addWidget(self._snap_check)
        if self._snap_action is not None:
            self._snap_action.setChecked(self._snap_check.isChecked())
            self._snap_action.toggled.connect(self._snap_check.setChecked)
            self._snap_check.toggled.connect(self._snap_action.setChecked)
        self.tabs.addTab(desktop, t("widget_hub.desktop_tab", "바탕화면 위젯"))
        mode_scroll = QScrollArea()
        mode_scroll.setObjectName("hubModeScroll")
        mode_scroll.viewport().setObjectName("hubModeViewport")
        mode_scroll.setWidgetResizable(True)
        mode_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.mode_panel = WidgetModeManagementPanel(getattr(self._mgr, "_owner", None), self)
        mode_scroll.setWidget(self.mode_panel)
        self.tabs.addTab(mode_scroll, t("widget_hub.mode_tab", "위젯 전용 모드"))
        if self.studio is not None:
            from calendar_app.presentation.widgets.widget_workspace_panel import (
                WidgetWorkspacePanel,
            )

            self.workspace_panel = WidgetWorkspacePanel(self.studio, self)
            self.workspace_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
            workspace_scroll = QScrollArea()
            workspace_scroll.setObjectName("hubWorkspaceScroll")
            workspace_scroll.viewport().setObjectName("hubWorkspaceViewport")
            workspace_scroll.setWidgetResizable(True)
            workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
            workspace_scroll.setWidget(self.workspace_panel)
            self.tabs.addTab(workspace_scroll, t("widget_studio.workspace_tab", "작업 공간"))
        self.tabs.currentChanged.connect(self._tab_changed)
        root.addWidget(self.tabs, 1)
        footer = QFrame()
        footer.setObjectName("MgrFoot")
        footer.setProperty("role", "dialogFooter")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(20, 10, 20, 10)
        hint = QLabel(
            t("widget_hub.footer", "이름 수정 후 Enter · 찾기로 화면에 가져오기 · 더보기에서 설정")
        )
        hint.setObjectName("overlayManagerHint")
        self._footer_hint = hint
        hint.setWordWrap(True)
        foot.addWidget(hint, 1)
        close = self._mk_btn(t("common.close", "닫기"), False)
        close.clicked.connect(self.close)
        foot.addWidget(close)
        root.addWidget(footer)

    def _mk_btn(self, text, primary=False):
        return hub_button(text, lambda: None, primary=primary)

    def _tab_changed(self, index):
        self.mode_panel.refresh()
        if index == 2:
            self._footer_hint.setText(
                t(
                    "widget_studio.workspace_footer",
                    "현재 상태 저장 · 작업 공간 적용 · 자동 전환과 움직임 설정",
                )
            )
            return
        self._footer_hint.setText(
            t(
                "widget_hub.mode_edit_hint",
                "꾸미기는 미리보기에서 적용하거나 취소할 수 있어요. 모드를 실행하지 않고도 설정할 수 있습니다.",
            )
            if index
            else t(
                "widget_hub.footer", "이름 수정 후 Enter · 찾기로 화면에 가져오기 · 더보기에서 설정"
            )
        )

    def _set_view(self, index):
        self._views.setCurrentIndex(index)
        self._update_compact_controls()
        self._apply_filters()

    def _update_compact_controls(self):
        compact = self.height() < 560
        self._header_frame.setVisible(not compact)
        self._snap_check.setVisible(not (compact and self._views.currentIndex() == 1))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_views") and hasattr(self, "_snap_check"):
            self._update_compact_controls()

    def _edit_desktop(self):
        from calendar_app.presentation.dialogs.widget_desktop_layout_dialog import (
            WidgetDesktopLayoutDialog,
        )

        if self.studio is None:
            return
        dialog = WidgetDesktopLayoutDialog(self.studio, self)
        dialog.exec()
        dialog.deleteLater()
        if self.gallery is not None:
            self.gallery.cache.clear()
        self._populate()

    def _create_stack(self):
        from PyQt6.QtWidgets import QMessageBox

        ids = self.gallery.selected_ids() if self.gallery is not None else []
        if self.studio is None or len(ids) < 2:
            QMessageBox.information(
                self,
                t("widget_studio.stack", "위젯 스택"),
                t(
                    "widget_studio.select_stack",
                    "갤러리에서 Ctrl+클릭으로 잠금 해제된 위젯을 두 개 이상 선택하세요.",
                ),
            )
            return
        from calendar_app.presentation.widgets.overlay_manager import _prompt_widget_name

        name, accepted = _prompt_widget_name(
            self,
            t("widget_studio.create_stack", "선택 위젯 스택 만들기"),
            t("widget_studio.stack_name", "스택 이름"),
            t("widget_studio.stack", "위젯 스택"),
        )
        if accepted:
            try:
                self.studio.stacks.create(ids, name)
            except ValueError:
                QMessageBox.information(
                    self,
                    t("widget_studio.stack", "위젯 스택"),
                    t(
                        "widget_studio.stack_invalid",
                        "기존 스택을 해제하고 선택한 위젯의 배치 잠금을 해제하세요.",
                    ),
                )

    def _ungroup_selected(self):
        if self.studio is not None and self.gallery is not None:
            groups = {
                group["id"]
                for iid in self.gallery.selected_ids()
                if (group := self.studio.stacks.group_for(iid))
            }
            for group_id in groups:
                self.studio.stacks.remove(group_id)

    def _populate(self):
        self._refresh_timer.stop()
        self._instances = list(self._mgr.all_instances())
        current_ids = {item[0] for item in self._instances}
        for iid in set(self._cards) - current_ids:
            card = self._cards.pop(iid)
            self._list_lay.removeWidget(card)
            card.hide()
            card.deleteLater()
        for index, (iid, name, kind, widget) in enumerate(self._instances):
            card = self._cards.get(iid)
            if card is None:
                card = WidgetCard(
                    iid,
                    name,
                    kind,
                    widget,
                    self._tok,
                    self._on_toggle,
                    self._on_rename,
                    self._on_focus,
                    self._on_reset_pos,
                    self._on_duplicate,
                    self._on_delete,
                    self._on_settings,
                    self._on_graphics,
                    parent=self._list_container,
                )
                self._cards[iid] = card
                self._list_lay.insertWidget(index, card)
            else:
                card.update_state(name, widget)
        self._apply_filters()

    def _apply_filters(self, *_):
        query = self.search_edit.text().strip().casefold()
        state = self.visibility_combo.currentData()
        matches = shown = 0
        for iid, name, kind, widget in self._instances:
            enabled = widget.is_enabled()
            group = self.studio.stacks.group_for(iid) if self.studio is not None else None
            waiting = bool(enabled and group and group["members"][group["index"]] != iid)
            shown += bool(enabled and not waiting)
            match = (not query or query in f"{name} {widget_type_label(kind)}".casefold()) and (
                state == "all"
                or (state == "shown" and enabled and not waiting)
                or (state == "hidden" and not enabled)
                or (state == "waiting" and waiting)
            )
            self._cards[iid].setVisible(match)
            matches += bool(match)
        total = len(self._instances)
        self._count_badge.setText(
            t("widget_hub.count", "{matches}/{total}개 · 표시 중 {shown}개").format(
                matches=matches, total=total, shown=shown
            )
        )
        self._empty_lbl.setVisible(matches == 0)
        self._empty_lbl.setText(
            t(
                "widget_hub.no_match",
                "조건에 맞는 위젯이 없습니다.\n검색어나 표시 상태를 바꿔보세요.",
            )
            if total
            else t(
                "widget_hub.no_widgets",
                "첫 위젯을 추가해 보세요.\n‘위젯 추가’에서 원하는 종류를 고를 수 있어요.",
            )
        )
        for button in (self.btn_show_all, self.btn_hide_all, self.bulk_more):
            button.setEnabled(total > 0)
        if self.gallery is not None and self.gallery.isVisible():
            self.gallery.populate(
                self._instances, {iid for iid, card in self._cards.items() if not card.isHidden()}
            )

    def _sync_from_manager(self):
        if self._listening and not self._refresh_timer.isActive():
            self._refresh_timer.start(0)

    def _add_instance(self):
        dialog = WidgetAddDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            kind, name = dialog.selection()
            iid = self._mgr.add_instance(kind, name)
            self._mgr.show_instance(iid)
            self.search_edit.clear()
            self.visibility_combo.setCurrentIndex(0)
            self._populate()
            self._scroll.ensureWidgetVisible(self._cards[iid])
        dialog.deleteLater()

    def _on_toggle(self, iid, checked):
        (self._mgr.show_instance if checked else self._mgr.hide_instance)(iid)

    def _on_rename(self, iid, text):
        name = text.strip()
        previous = next((item[1] for item in self._instances if item[0] == iid), "")
        if name and name != previous:
            self._mgr.rename_instance(iid, name)
        card = self._cards.get(iid)
        if card is not None:
            card.name_edit.setText(name or previous)
            card.name_edit.setModified(False)

    def _on_focus(self, iid):
        widget = self._mgr.get_widget(iid)
        if widget is None:
            return
        self._mgr.show_instance(iid)
        if self.studio is not None:
            group = self.studio.stacks.group_for(iid)
            if group:
                self.studio.stacks.select(group["id"], group["members"].index(iid))
        screen = self.screen()
        if screen is not None:
            geometry = screen.availableGeometry()
            widget.move(
                geometry.x() + max(0, (geometry.width() - widget.width()) // 2),
                geometry.y() + max(0, (geometry.height() - widget.height()) // 2),
            )
            widget.save_position()
        widget.raise_()

    def _on_reset_pos(self, iid):
        widget = self._mgr.get_widget(iid)
        if widget is not None and hasattr(widget, "_action_reset_position"):
            widget._action_reset_position()

    def _on_delete(self, iid):
        self._mgr._ui_remove_with_confirm(iid, parent_widget=self)
        self._populate()

    def _on_duplicate(self, iid):
        new_id = self._mgr.duplicate_instance(iid)
        if new_id:
            self._mgr.show_instance(new_id)
        self._populate()

    def _on_settings(self, iid):
        widget = self._mgr.get_widget(iid)
        if widget is not None and hasattr(widget, "_open_settings"):
            widget._open_settings()
            if self.gallery is not None:
                self.gallery.cache.clear()

    def _on_graphics(self, iid):
        kind = next((row[2] for row in self._mgr.all_instances() if row[0] == iid), None)
        if kind == "loop_deck":
            self._on_settings(iid)
            return
        widget = self._mgr.get_widget(iid)
        if widget is not None and hasattr(widget, "_open_graphic_collections"):
            widget._open_graphic_collections()
            if self.gallery is not None:
                self.gallery.cache.clear()

    def _show_all(self):
        for iid, _, _, widget in self._mgr.all_instances():
            if not widget.is_enabled():
                self._mgr.show_instance(iid)

    def _hide_all(self):
        for iid, _, _, widget in self._mgr.all_instances():
            if widget.is_enabled():
                self._mgr.hide_instance(iid)

    def _delete_all(self):
        self._mgr._ui_remove_all_with_confirm(parent_widget=self)
        self._populate()

    def showEvent(self, event):
        super().showEvent(event)
        tokens = _load_tokens(settings=getattr(self.parent(), "settings", None))
        if tokens != self._tok:
            self._tok = tokens
            apply_common_dialog_style(
                self,
                keep_existing_stylesheet=False,
                extra_stylesheet=_build_manager_css(tokens) + management_styles(tokens),
            )
            for card in self._cards.values():
                card._tokens = card.toggle._tokens = tokens
        if not self._listening:
            self._mgr.add_listener(self._sync_from_manager)
            self._listening = True
        self._populate()
        self.mode_panel.refresh()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.ActivationChange
            and self.isActiveWindow()
            and hasattr(self, "mode_panel")
        ):
            self.mode_panel.refresh()

    def _pause_sync(self):
        self._refresh_timer.stop()
        if self._listening:
            self._mgr.remove_listener(self._sync_from_manager)
            self._listening = False

    def hideEvent(self, event):
        self._pause_sync()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._pause_sync()
        super().closeEvent(event)
