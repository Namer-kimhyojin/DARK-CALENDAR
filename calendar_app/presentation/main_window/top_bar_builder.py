# -*- coding: utf-8 -*-
from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.top_bar_menu_factory import build_top_left_menus
from calendar_app.presentation.theme.style_builder import _scaled_pt, apply_top_menu_theme
from calendar_app.shared.color_utils import derive_panel_palette, derive_ui_palette, hex_to_rgba
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_settings import get_theme_palette_inputs


def _topbar_palette(settings):
    text_theme, panel_base, opacity_factor = get_theme_palette_inputs(settings)
    return derive_ui_palette(text_theme, panel_base, opacity_factor)


def build_top_bar_frame_style(settings, opacity_factor: float = 1.0):
    text_theme, panel_base, _ = get_theme_palette_inputs(settings)
    pal_panel = derive_panel_palette(panel_base, opacity_factor)
    border = "rgba(0,0,0,0.10)" if text_theme == "light" else "rgba(255,255,255,0.05)"
    return (
        f"background-color: {pal_panel['topbar_bg']}; "
        f"border-radius: 8px; border: 1px solid {border};"
    )


def build_top_bar_runtime_styles(settings, size: int, theme_color: str) -> dict[str, str]:
    """Return mode-aware styles for every persistent top-bar element."""
    palette = _topbar_palette(settings)
    field_pt = _scaled_pt(size, 0, 9)
    button_pt = _scaled_pt(size, 0, 9)
    accent_soft = hex_to_rgba(theme_color, 0.10)
    accent_pressed = hex_to_rgba(theme_color, 0.18)
    return {
        "label": (f"color: {palette['text_secondary']}; background: transparent; border: none;"),
        "divider": (
            f"color: {palette['border_soft']}; background: {palette['border_soft']}; "
            "max-width: 1px; margin: 2px 15px;"
        ),
        "mode_button": f"""
            QPushButton {{
                color: {palette["text_secondary"]}; background: transparent;
                border: 1px solid transparent; border-radius: 6px;
                font-size: {button_pt}pt; font-weight: 600; padding: 0;
            }}
            QPushButton:hover {{
                color: {palette["text_primary"]}; background: {palette["control_bg_hover"]};
                border-color: {palette["border_soft"]};
            }}
            QPushButton:checked {{
                color: {palette["text_primary"]}; background: {accent_soft};
                border-color: {hex_to_rgba(theme_color, 0.55)};
            }}
            QPushButton:pressed {{ background: {accent_pressed}; }}
        """,
        "search": f"""
            QLineEdit {{
                background: {palette["control_bg"]}; border: 1px solid {palette["border"]};
                border-radius: 10px; padding: 4px 10px; color: {palette["text_primary"]};
                font-size: {field_pt}pt;
            }}
            QLineEdit:hover {{
                border-color: {palette["border_strong"]}; background: {palette["control_bg_hover"]};
            }}
            QLineEdit:focus {{
                border-color: {theme_color}; background: {palette["control_bg_pressed"]};
            }}
        """,
        "tool_button": f"""
            QToolButton {{
                color: {palette["text_secondary"]}; background: transparent; border: none;
                border-radius: 8px; font-size: {button_pt}pt; font-weight: 600;
            }}
            QToolButton:hover {{
                color: {palette["text_primary"]}; background: {palette["control_bg_hover"]};
            }}
        """,
    }


def setup_top_bar(self, _size, _theme, _ta):
    top_bar = QHBoxLayout()
    top_bar.setSpacing(5)

    status_pt = _scaled_pt(_size, 0, 9)
    status_text_pt = _scaled_pt(_size, -1, 8)
    _tb_pal = _topbar_palette(self.settings)
    _tb_text = _tb_pal["text_primary"]
    self._tb_icon_color = _tb_text  # qtawesome icon colors use the semantic hex text token.
    self._tb_icon_active_color = _theme
    runtime_styles = build_top_bar_runtime_styles(self.settings, _size, _theme)

    effective_text_theme, effective_panel_base, effective_opacity = get_theme_palette_inputs(
        self.settings
    )
    build_top_left_menus(self, top_bar, _size, _theme)
    apply_top_menu_theme(
        self,
        _size,
        _theme,
        effective_text_theme,
        effective_panel_base,
        effective_opacity,
        persist_opacity=False,
    )

    self.current_date = QDate.currentDate()
    top_bar.addStretch(1)

    self.sync_status_lbl = QLabel(t("topbar.sync_label", "Sync"))
    self.sync_status_lbl.setToolTip(t("topbar.sync_checking"))
    self.sync_status_lbl.setAccessibleName(t("topbar.sync_label", "Sync"))
    self.sync_status_lbl.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.sync_status_lbl.setMinimumWidth(28)
    self.sync_status_lbl.setStyleSheet(
        runtime_styles["label"]
        + f" font-size: {status_pt}pt; font-weight: bold; margin-right: 4px;"
    )
    top_bar.addWidget(self.sync_status_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

    self.sync_action_btn = QToolButton()
    self.sync_action_btn.setAutoRaise(True)
    self.sync_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self.sync_action_btn.setIcon(_ic(ICON.SYNC, color=_theme))
    self.sync_action_btn.setIconSize(QSize(18, 18))
    self.sync_action_btn.setToolTip(t("topbar.sync_now"))
    self.sync_action_btn.setAccessibleName(t("topbar.sync_now"))
    self.sync_action_btn.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_action_btn.setMinimumSize(32, 32)
    self.sync_action_btn.setMaximumSize(36, 36)
    self.sync_action_btn.setStyleSheet(
        f"""
        QToolButton {{
            color: {_theme};
            background: transparent;
            border: none;
            font-size: {status_pt}pt;
            font-weight: bold;
            margin-right: 4px;
            padding: 2px 6px;
        }}
        QToolButton:hover {{
            background: {_ta(40)};
            border-radius: 6px;
        }}
    """
    )
    self.sync_action_btn.clicked.connect(self.sync_google_calendar)
    top_bar.addWidget(self.sync_action_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    self.sync_status_text_lbl = QLabel(t("topbar.sync_waiting"))
    self.sync_status_text_lbl.setToolTip(t("topbar.sync_checking"))
    self.sync_status_text_lbl.setAccessibleName(t("topbar.sync_label", "Sync"))
    self.sync_status_text_lbl.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_status_text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.sync_status_text_lbl.setStyleSheet(
        runtime_styles["label"]
        + f" font-size: {status_text_pt}pt; font-weight: bold; margin-right: 8px;"
    )
    top_bar.addWidget(self.sync_status_text_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

    self.top_bar_divider = QFrame()
    self.top_bar_divider.setFrameShape(QFrame.Shape.VLine)
    self.top_bar_divider.setStyleSheet(runtime_styles["divider"])
    top_bar.addWidget(self.top_bar_divider)

    # Unified style for mode toggle buttons
    _btn_style = runtime_styles["mode_button"]

    # -- Lock Mode Group --
    self.lock_label = QLabel(t("topbar.lock_mode"))
    self.lock_label.setStyleSheet(runtime_styles["label"])
    top_bar.addWidget(self.lock_label, alignment=Qt.AlignmentFlag.AlignCenter)
    top_bar.addSpacing(2)

    is_locked = self.settings.value("lock_enabled", False, type=bool)
    self.lock_btn = QPushButton("")
    self.lock_btn.setCheckable(True)
    self.lock_btn.setChecked(is_locked)
    self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    _lock_icon_color = _theme if is_locked else _tb_text
    self.lock_btn.setIcon(_ic(ICON.LOCK if is_locked else ICON.UNLOCK, color=_lock_icon_color))
    self.lock_btn.setIconSize(QSize(16, 16))
    self.lock_btn.setToolTip(t("topbar.lock_on_hint") if is_locked else t("topbar.lock_off_hint"))
    self.lock_btn.setAccessibleName(t("topbar.lock_mode"))
    self.lock_btn.setAccessibleDescription(
        t("topbar.lock_on_hint") if is_locked else t("topbar.lock_off_hint")
    )
    self.lock_btn.setMinimumSize(32, 32)
    self.lock_btn.setMaximumSize(36, 36)
    self.lock_btn.setStyleSheet(_btn_style)
    self.lock_btn.clicked.connect(self.toggle_lock_mode)
    top_bar.addWidget(self.lock_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    top_bar.addSpacing(12)

    # -- Magnet Mode Group --
    self.magnet_label = QLabel(t("topbar.magnet_mode"))
    self.magnet_label.setStyleSheet(runtime_styles["label"])
    top_bar.addWidget(self.magnet_label, alignment=Qt.AlignmentFlag.AlignCenter)
    top_bar.addSpacing(2)

    is_magnet = self.settings.value("magnet_enabled", True, type=bool)
    self.magnet_btn = QPushButton("")
    self.magnet_btn.setCheckable(True)
    self.magnet_btn.setChecked(is_magnet)
    self.magnet_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self.magnet_btn.setIcon(_ic(ICON.MAGNET if is_magnet else ICON.MAGNET_OFF, color=_tb_text))
    self.magnet_btn.setIconSize(QSize(16, 16))
    self.magnet_btn.setToolTip(
        t("topbar.magnet_on_hint") if is_magnet else t("topbar.magnet_off_hint")
    )
    self.magnet_btn.setAccessibleName(t("topbar.magnet_mode"))
    self.magnet_btn.setAccessibleDescription(
        t("topbar.magnet_on_hint") if is_magnet else t("topbar.magnet_off_hint")
    )
    self.magnet_btn.setMinimumSize(32, 32)
    self.magnet_btn.setMaximumSize(36, 36)
    self.magnet_btn.setStyleSheet(_btn_style)
    self.magnet_btn.clicked.connect(self.toggle_magnet_mode)
    top_bar.addWidget(self.magnet_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    top_bar.addSpacing(10)

    self.search_edit = QLineEdit()
    self.search_edit.setPlaceholderText(_se(t("topbar.search_placeholder", "Search schedule...")))
    self.search_edit.addAction(
        _ic(ICON.SEARCH, color=_tb_text), QLineEdit.ActionPosition.LeadingPosition
    )
    self.search_edit.setAccessibleName(t("topbar.search_placeholder", "Search schedule..."))
    self.search_edit.setAccessibleDescription(
        t("topbar.search_accessible_hint", "일정, 루틴, 지시사항을 검색합니다.")
    )
    self.search_edit.setMinimumHeight(32)
    self.search_edit.setMinimumWidth(140)
    self.search_edit.setMaximumWidth(260)
    self.search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.search_edit.setStyleSheet(runtime_styles["search"])
    self.search_edit.textChanged.connect(self.handle_search_changed)
    top_bar.addWidget(self.search_edit, alignment=Qt.AlignmentFlag.AlignCenter)

    top_bar.addSpacing(4)

    self.widget_mode_btn = QToolButton()
    self.widget_mode_btn.setIcon(_ic(ICON.WIDGET_MGR, color=_tb_text))
    self.widget_mode_btn.setIconSize(QSize(16, 16))
    self.widget_mode_btn.setToolTip(t("topbar.widget_mode_hint", "위젯 전용 모드 열기"))
    self.widget_mode_btn.setAccessibleName(t("topbar.widget_mode_hint", "위젯 전용 모드 열기"))
    self.widget_mode_btn.setAccessibleDescription(
        t("topbar.widget_mode_hint", "위젯 전용 모드 열기")
    )
    self.widget_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self.widget_mode_btn.setMinimumSize(32, 32)
    self.widget_mode_btn.setMaximumSize(36, 36)
    self.widget_mode_btn.setStyleSheet(runtime_styles["tool_button"])
    self.widget_mode_btn.clicked.connect(self.toggle_widget_mode_panel)
    top_bar.addWidget(self.widget_mode_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    self.top_bar_frame = QFrame()
    self.top_bar_frame.setObjectName("top_bar_frame")
    self.top_bar_frame.setStyleSheet(build_top_bar_frame_style(self.settings))
    self.top_bar_frame.setLayout(top_bar)
    # top_bar_frame은 ui_builder에서 setMenuWidget()으로 최상단에 고정됨
