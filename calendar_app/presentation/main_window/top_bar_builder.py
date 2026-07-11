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
from calendar_app.shared.color_utils import derive_panel_palette, derive_ui_palette
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_settings import get_theme_palette_inputs


def _topbar_palette(settings):
    text_theme, panel_base, opacity_factor = get_theme_palette_inputs(settings)
    return derive_ui_palette(text_theme, panel_base, opacity_factor)


def build_top_bar_frame_style(settings, opacity_factor: float = 1.0):
    raw = settings.value("panel_base_color", "#1c1c1c")
    pal_panel = derive_panel_palette(str(raw), opacity_factor)
    border = "rgba(255, 255, 255, 0.05)"
    return (
        f"background-color: {pal_panel['topbar_bg']}; "
        f"border-radius: 8px; border: 1px solid {border};"
    )


def setup_top_bar(self, _size, _theme, _ta):
    top_bar = QHBoxLayout()
    top_bar.setSpacing(5)

    field_pt = _scaled_pt(_size, 0, 9)
    status_pt = _scaled_pt(_size, 0, 9)
    status_text_pt = _scaled_pt(_size, -1, 8)
    icon_btn_pt = _scaled_pt(_size, 0, 9)
    _tb_pal = _topbar_palette(self.settings)
    _tb_text = _tb_pal["text_primary"]
    _tb_text2 = _tb_pal["text_secondary"]
    self._tb_icon_color = _tb_text  # text_primary is always a hex string; text_secondary is rgba (invalid for qtawesome)
    self._tb_icon_active_color = _theme
    _vline_color = "rgba(255,255,255,20)"
    _hover_bg_weak = "rgba(255,255,255,30)"
    _hover_bg_mid = "rgba(255,255,255,50)"

    build_top_left_menus(self, top_bar, _size, _theme)
    apply_top_menu_theme(self, _size, _theme)

    self.current_date = QDate.currentDate()
    top_bar.addStretch(1)

    self.sync_status_lbl = QLabel(t("topbar.sync_label", "Sync"))
    self.sync_status_lbl.setToolTip(t("topbar.sync_checking"))
    self.sync_status_lbl.setAccessibleName(t("topbar.sync_label", "Sync"))
    self.sync_status_lbl.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.sync_status_lbl.setMinimumWidth(28)
    self.sync_status_lbl.setStyleSheet(
        f"color: {_tb_text2}; font-size: {status_pt}pt; font-weight: bold; margin-right: 4px; background: transparent; border: none;"
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
        f"color: {_tb_text2}; font-size: {status_text_pt}pt; font-weight: bold; margin-right: 8px; background: transparent; border: none;"
    )
    top_bar.addWidget(self.sync_status_text_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

    vline = QFrame()
    vline.setFrameShape(QFrame.Shape.VLine)
    vline.setStyleSheet(
        f"color: {_vline_color}; background: {_vline_color}; max-width: 1px; margin: 2px 15px;"
    )
    top_bar.addWidget(vline)

    # Unified style for mode toggle buttons
    _btn_style = f"""
        QPushButton {{
            color: {_tb_text2};
            background: transparent;
            border: none;
            border-radius: 4px;
            font-size: {icon_btn_pt}pt;
            padding: 0;
        }}
        QPushButton:hover {{
            background: {_hover_bg_weak};
        }}
        QPushButton:checked {{
            color: {_theme};
            background: {_ta(25)};
            border: none;
        }}
        QPushButton:pressed {{
            background: {_ta(40)};
            border: none;
        }}
    """

    # -- Lock Mode Group --
    self.lock_label = QLabel(t("topbar.lock_mode"))
    self.lock_label.setStyleSheet(f"color: {_tb_text2}; background: transparent; border: none;")
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
    self.lock_btn.setMinimumSize(26, 26)
    self.lock_btn.setMaximumSize(32, 32)
    self.lock_btn.setStyleSheet(_btn_style)
    self.lock_btn.clicked.connect(self.toggle_lock_mode)
    top_bar.addWidget(self.lock_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    top_bar.addSpacing(12)

    # -- Magnet Mode Group --
    self.magnet_label = QLabel(t("topbar.magnet_mode"))
    self.magnet_label.setStyleSheet(f"color: {_tb_text2}; background: transparent; border: none;")
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
    self.magnet_btn.setMinimumSize(26, 26)
    self.magnet_btn.setMaximumSize(32, 32)
    self.magnet_btn.setStyleSheet(_btn_style)
    self.magnet_btn.clicked.connect(self.toggle_magnet_mode)
    top_bar.addWidget(self.magnet_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    top_bar.addSpacing(10)

    _search_bg = "rgba(255,255,255,10)"
    _search_bg_hover = "rgba(255,255,255,14)"
    _search_bg_focus = "rgba(255,255,255,20)"
    self.search_edit = QLineEdit()
    self.search_edit.setPlaceholderText(_se(t("topbar.search_placeholder", "Search schedule...")))
    self.search_edit.addAction(
        _ic(ICON.SEARCH, color=_tb_text), QLineEdit.ActionPosition.LeadingPosition
    )
    self.search_edit.setAccessibleName(t("topbar.search_placeholder", "Search schedule..."))
    self.search_edit.setMinimumWidth(140)
    self.search_edit.setMaximumWidth(260)
    self.search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.search_edit.setStyleSheet(
        f"""
        QLineEdit {{
            background: {_search_bg}; border: 1px solid {_ta(80)};
            border-radius: 10px; padding: 4px 6px; color: {_tb_text}; font-size: {field_pt}pt;
        }}
        QLineEdit:hover {{ border: 1px solid {_ta(128)}; background: {_search_bg_hover}; }}
        QLineEdit:focus {{ border: 1px solid {_theme}; background: {_search_bg_focus}; }}
    """
    )
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
    self.widget_mode_btn.setMinimumSize(26, 26)
    self.widget_mode_btn.setMaximumSize(32, 32)
    self.widget_mode_btn.setStyleSheet(
        f"""
        QToolButton {{
            color: {_tb_text2};
            background: transparent;
            border: none;
            border-radius: 11px;
            font-size: {status_pt}pt;
            font-weight: bold;
        }}
        QToolButton:hover {{
            color: {_tb_text};
            background: {_hover_bg_weak};
        }}
    """
    )
    self.widget_mode_btn.clicked.connect(self.toggle_widget_mode_panel)
    top_bar.addWidget(self.widget_mode_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    self.top_bar_frame = QFrame()
    self.top_bar_frame.setObjectName("top_bar_frame")
    self.top_bar_frame.setStyleSheet(build_top_bar_frame_style(self.settings))
    self.top_bar_frame.setLayout(top_bar)
    # top_bar_frame은 ui_builder에서 setMenuWidget()으로 최상단에 고정됨
