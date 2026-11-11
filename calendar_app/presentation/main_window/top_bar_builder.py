# -*- coding: utf-8 -*-
from PyQt6.QtCore import QDate, QEvent, QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from calendar_app.app_metadata import APP_NAME
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_bar_menu_factory import build_top_left_menus
from calendar_app.presentation.main_window.top_menus.common import set_themed_icon
from calendar_app.presentation.theme.style_builder import apply_top_menu_theme
from calendar_app.shared.brand_assets import brand_mark_pixmap
from calendar_app.shared.color_utils import (
    contrast_safe_color,
    contrasting_text_color,
    hex_to_rgba,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.typography import get_typography_scale


class _TopBarFrame(QFrame):
    """Keep menu actions and search reachable as the main window narrows."""

    def __init__(self, brand, search, sync_status, settings):
        super().__init__()
        self._brand = brand
        self._search = search
        self._sync_status = sync_status
        self._settings = settings
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._brand.setVisible(self.width() >= 1000)
        self._sync_status.setVisible(self.width() >= 800)
        self._search.setMinimumWidth(120 if self.width() < 820 else 180)
        self._refresh_brand_mark()

    def _refresh_brand_mark(self):
        mark = self._brand.findChild(QLabel, "app_brand_icon")
        if mark is None:
            return
        snapshot = build_theme_snapshot(self._settings)
        pixmap = brand_mark_pixmap(
            snapshot.theme_color,
            30,
            background=snapshot.panel_palette["topbar_bg"],
            base=snapshot.panel_base_color,
            dpr=self.devicePixelRatioF(),
        )
        if mark.pixmap().cacheKey() != pixmap.cacheKey():
            mark.setPixmap(pixmap)

    def event(self, event):
        result = super().event(event)
        if hasattr(self, "_settings") and event.type() in (
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.DevicePixelRatioChange,
        ):
            self._refresh_brand_mark()
        return result


def _topbar_palette(settings):
    return build_theme_snapshot(settings).ui_palette


def build_top_bar_frame_style(settings, opacity_factor: float | None = None):
    snapshot = build_theme_snapshot(settings, opacity_factor=opacity_factor)
    radius = snapshot.shape_tokens["panel_surface_radius"]
    brand_pt = get_typography_scale(settings).title_pt
    return (
        f"QFrame#top_bar_frame {{ background-color: {snapshot.panel_palette['topbar_bg']}; "
        f"border-radius: {radius}px; border: 1px solid {snapshot.ui_palette['border_soft']}; }}"
        f"QLabel#app_brand {{ color: {snapshot.ui_palette['text_primary']}; "
        f"background: transparent; border: none; font-size: {brand_pt}pt; font-weight: 600; }}"
    )


def build_sync_toolbar_styles(settings, *, busy=False, attention=False):
    """Keep ordinary status neutral and clear stale provider-specific styling."""
    snapshot = build_theme_snapshot(settings)
    palette = snapshot.ui_palette
    panel_base = snapshot.panel_base_color
    radius = snapshot.shape_tokens["panel_toolbar_button_radius"]
    typography = get_typography_scale(settings)
    color = palette["text_primary"]
    if busy:
        color = contrast_safe_color(
            settings.value("theme_color", "#4da6ff", type=str), panel_base, minimum=3.0
        )
    elif attention:
        color = contrast_safe_color("#d39a2a", panel_base, minimum=3.0)
    return {
        "icon_color": color,
        "button": f"""
            QToolButton {{
                color: {palette["text_secondary"]}; background: transparent;
                border: 1px solid transparent; border-radius: {radius}px; padding: 0;
            }}
            QToolButton:hover, QToolButton:focus {{
                background: {palette["control_bg_hover"]};
                border-color: {palette["border_soft"]};
            }}
            QToolButton:pressed {{ background: {palette["control_bg_pressed"]}; }}
        """,
        "label": (
            f"color: {palette['text_secondary']}; background: transparent; border: none; "
            f"font-size: {typography.caption_pt:g}pt; font-weight: normal; margin-right: 6px;"
        ),
    }


def build_top_bar_runtime_styles(settings, size: int, theme_color: str) -> dict[str, str]:
    """Return mode-aware styles for every persistent top-bar element."""
    snapshot = build_theme_snapshot(settings)
    palette = snapshot.ui_palette
    button_radius = snapshot.shape_tokens["panel_toolbar_button_radius"]
    search_radius = snapshot.shape_tokens["calendar_toolbar_surface_radius"]
    typography = get_typography_scale(settings, base_pt=size)
    field_pt = typography.body_pt
    button_pt = typography.body_pt
    accent_soft = hex_to_rgba(theme_color, 0.10)
    accent_pressed = hex_to_rgba(theme_color, 0.18)
    return {
        "label": (f"color: {palette['text_secondary']}; background: transparent; border: none;"),
        "divider": (
            f"color: {palette['border_soft']}; background: {palette['border_soft']}; "
            "max-width: 1px; margin: 7px 8px;"
        ),
        "mode_button": f"""
            QPushButton {{
                color: {palette["text_secondary"]}; background: transparent;
                border: 1px solid transparent; border-radius: {button_radius}px;
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
                border-radius: {search_radius}px; padding: 6px 12px; color: {palette["text_primary"]};
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
                color: {palette["text_secondary"]}; background: transparent;
                border: 1px solid transparent; border-radius: {button_radius}px;
                font-size: {button_pt}pt; font-weight: 600;
            }}
            QToolButton:hover {{
                color: {palette["text_primary"]}; background: {palette["control_bg_hover"]};
            }}
            QToolButton:focus {{ border-color: {theme_color}; }}
            QToolButton:pressed {{ background: {palette["control_bg_pressed"]}; }}
        """,
        "navigation_rail": f"""
            QToolBar#navigation_rail {{
                background: {snapshot.panel_palette["topbar_bg"]};
                border: 1px solid {palette["border_soft"]};
                border-radius: {snapshot.shape_tokens["panel_surface_radius"]}px;
                padding: 8px 5px; spacing: 8px;
            }}
            QToolBar#navigation_rail QToolButton {{
                background: transparent; border: 1px solid transparent;
                border-radius: {button_radius}px; padding: 0;
                min-width: 42px; min-height: 42px;
            }}
            QToolBar#navigation_rail QToolButton:hover {{
                background: {palette["control_bg_hover"]};
            }}
            QToolBar#navigation_rail QToolButton:focus {{ border-color: {theme_color}; }}
            QToolBar#navigation_rail QToolButton:checked {{
                background: {accent_soft}; border-color: transparent;
            }}
            QToolBar#navigation_rail QToolButton#navigation_add {{
                background: {theme_color}; border-color: transparent;
            }}
            QToolBar#navigation_rail::separator {{
                background: {palette["border_soft"]}; height: 1px; margin: 5px;
            }}
        """,
    }


def _setup_navigation_rail(owner, styles, icon_color, accent_color):
    if not isinstance(owner, QMainWindow) or getattr(owner, "navigation_rail", None) is not None:
        return
    rail = QToolBar(t("topbar.navigation_rail", "빠른 이동"), owner)
    rail.setObjectName("navigation_rail")
    rail.setAllowedAreas(Qt.ToolBarArea.LeftToolBarArea | Qt.ToolBarArea.RightToolBarArea)
    rail.setMovable(True)
    rail.setFloatable(False)
    rail.setIconSize(QSize(20, 20))
    rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    rail.setStyleSheet(styles["navigation_rail"])
    add_action = rail.addAction(_se(t("menu.add_schedule")), owner.open_task_dialog)
    set_themed_icon(add_action, ICON.ADD, contrasting_text_color(accent_color), role="on_accent")
    rail.widgetForAction(add_action).setObjectName("navigation_add")
    rail.addSeparator()
    for attr in ("act_calendar", "act_today", "act_routine", "act_directive"):
        action = getattr(owner, attr, None)
        if action is not None:
            rail.addAction(action)
    rail.addSeparator()
    widgets_action = rail.addAction(
        t("topbar.widget_mode_hint", "위젯 전용 모드 열기"), owner.toggle_widget_mode_panel
    )
    set_themed_icon(widgets_action, ICON.WIDGET_MGR, icon_color)
    spacer = QWidget(rail)
    spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    rail.addWidget(spacer)
    appearance_action = rail.addAction(
        _se(t("menu.ui_theme_open", "모양 설정...")), owner.open_panel_background_color_dialog
    )
    set_themed_icon(appearance_action, ICON.DISPLAY_STYLE, icon_color)
    rail.setEnabled(not bool(getattr(owner, "is_locked", False)))
    owner.addToolBar(Qt.ToolBarArea.LeftToolBarArea, rail)
    owner.navigation_rail = rail
    window_menu = getattr(owner, "display_window_menu", None)
    if window_menu is not None:
        toggle_action = rail.toggleViewAction()
        # Text only: the global shortcut registry owns Ctrl+Shift+R itself.
        toggle_action.setText(f"{rail.windowTitle()}\t{get_key('navigation_rail')}")
        window_menu.addAction(toggle_action)


def setup_top_bar(self, _size, _theme, _ta):
    top_bar = QHBoxLayout()
    top_bar.setContentsMargins(14, 7, 12, 7)
    top_bar.setSpacing(6)
    top_bar.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    typography = get_typography_scale(self.settings, base_pt=_size)
    status_pt = typography.caption_pt
    _tb_pal = _topbar_palette(self.settings)
    _tb_text = _tb_pal["text_primary"]
    self._tb_icon_color = _tb_text  # qtawesome icon colors use the semantic hex text token.
    self._tb_icon_active_color = _theme
    runtime_styles = build_top_bar_runtime_styles(self.settings, _size, _theme)

    snapshot = build_theme_snapshot(self.settings)
    brand_group = QWidget()
    brand_group.setObjectName("app_brand_group")
    brand_layout = QHBoxLayout(brand_group)
    brand_layout.setContentsMargins(0, 0, 0, 0)
    brand_layout.setSpacing(8)
    brand_mark = QLabel()
    brand_mark.setObjectName("app_brand_icon")
    brand_mark.setFixedSize(30, 30)
    brand_mark.setPixmap(
        brand_mark_pixmap(
            snapshot.theme_color,
            30,
            background=snapshot.panel_palette["topbar_bg"],
            base=snapshot.panel_base_color,
            dpr=self.devicePixelRatioF(),
        )
    )
    brand_mark.setScaledContents(True)
    brand_layout.addWidget(brand_mark)
    brand = QLabel(APP_NAME)
    brand.setObjectName("app_brand")
    brand_font = brand.font()
    brand_font.setPointSizeF(typography.title_pt)
    brand.setFont(brand_font)
    brand_layout.addWidget(brand)
    top_bar.addWidget(brand_group)
    top_bar.addSpacing(10)
    build_top_left_menus(self, top_bar, _size, _theme)
    menu_buttons = [
        button
        for attr in (
            "add_menu_btn",
            "view_menu_btn",
            "display_menu_btn",
            "widgets_menu_btn",
            "sys_menu_btn",
        )
        if (button := getattr(self, attr, None)) is not None
    ]
    for button in menu_buttons:
        button.setProperty("compactTopMenu", True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(36, 36)
        button.setIconSize(QSize(18, 18))
        button.setToolTip(button.text().strip())
        button.setAccessibleName(button.text().strip())
    apply_top_menu_theme(
        self,
        _size,
        _theme,
        snapshot.text_theme,
        snapshot.panel_base_color,
        snapshot.opacity_factor,
        persist_opacity=False,
    )

    self.current_date = QDate.currentDate()
    top_bar.addStretch(1)
    search_position = top_bar.count()

    self.sync_status_lbl = QLabel(t("topbar.sync_label", "Sync"))
    self.sync_status_lbl.setToolTip(t("topbar.sync_checking"))
    self.sync_status_lbl.setAccessibleName(t("topbar.sync_label", "Sync"))
    self.sync_status_lbl.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.sync_status_lbl.setFixedWidth(0)
    self.sync_status_lbl.hide()
    self.sync_status_lbl.setStyleSheet(
        runtime_styles["label"]
        + f" font-size: {status_pt}pt; font-weight: bold; margin-right: 4px;"
    )

    self.sync_action_btn = QToolButton()
    self.sync_action_btn.setAutoRaise(True)
    self.sync_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    sync_styles = build_sync_toolbar_styles(self.settings)
    self.sync_action_btn.setIcon(_ic(ICON.SYNC, color=sync_styles["icon_color"]))
    self.sync_action_btn.setIconSize(QSize(16, 16))
    self.sync_action_btn.setToolTip(t("sync_redesign.connections_tab", "연결 및 구독"))
    self.sync_action_btn.setAccessibleName(self.sync_action_btn.toolTip())
    self.sync_action_btn.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_action_btn.setFixedSize(36, 36)
    self.sync_action_btn.setStyleSheet(sync_styles["button"])
    self.sync_action_btn.clicked.connect(lambda: self.open_calendar_sync_hub(section="services"))
    top_bar.addWidget(self.sync_action_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    self.sync_status_text_lbl = QLabel(t("topbar.sync_waiting"))
    self.sync_status_text_lbl.setAccessibleName(t("topbar.sync_label", "Sync"))
    self.sync_status_text_lbl.setAccessibleDescription(t("topbar.sync_checking"))
    self.sync_status_text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.sync_status_text_lbl.setTextFormat(Qt.TextFormat.PlainText)
    self.sync_status_text_lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    self.sync_status_text_lbl.setMinimumWidth(
        self.sync_status_text_lbl.fontMetrics().horizontalAdvance(
            t("sync_unified.local_only", "로컬 모드")
        )
        + 12
    )
    self.sync_status_text_lbl.setStyleSheet(sync_styles["label"])
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
    self.lock_label.hide()

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
    self.lock_btn.setFixedSize(36, 36)
    self.lock_btn.setStyleSheet(_btn_style)
    self.lock_btn.clicked.connect(self.toggle_lock_mode)
    top_bar.addWidget(self.lock_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    # -- Magnet Mode Group --
    self.magnet_label = QLabel(t("topbar.magnet_mode"))
    self.magnet_label.setStyleSheet(runtime_styles["label"])
    self.magnet_label.hide()

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
    self.magnet_btn.setFixedSize(36, 36)
    self.magnet_btn.setStyleSheet(_btn_style)
    self.magnet_btn.clicked.connect(self.toggle_magnet_mode)
    top_bar.addWidget(self.magnet_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    self.search_edit = QLineEdit()
    self.search_edit.setPlaceholderText(_se(t("topbar.search_placeholder", "Search schedule...")))
    self.search_edit.addAction(
        _ic(ICON.SEARCH, color=_tb_text), QLineEdit.ActionPosition.LeadingPosition
    )
    self.search_edit.setAccessibleName(t("topbar.search_placeholder", "Search schedule..."))
    self.search_edit.setAccessibleDescription(
        t("topbar.search_accessible_hint", "일정, 루틴, 지시사항을 검색합니다.")
    )
    self.search_edit.setMinimumHeight(36)
    self.search_edit.setMinimumWidth(180)
    self.search_edit.setMaximumWidth(340)
    self.search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.search_edit.setStyleSheet(runtime_styles["search"])
    self.search_edit.textChanged.connect(self.handle_search_changed)
    top_bar.insertWidget(
        search_position, self.search_edit, 1, alignment=Qt.AlignmentFlag.AlignVCenter
    )

    self.widget_mode_btn = QToolButton()
    self.widget_mode_btn.setIcon(_ic(ICON.WIDGET_MGR, color=_tb_text))
    self.widget_mode_btn.setIconSize(QSize(16, 16))
    self.widget_mode_btn.setToolTip(t("topbar.widget_mode_hint", "위젯 전용 모드 열기"))
    self.widget_mode_btn.setAccessibleName(t("topbar.widget_mode_hint", "위젯 전용 모드 열기"))
    self.widget_mode_btn.setAccessibleDescription(
        t("topbar.widget_mode_hint", "위젯 전용 모드 열기")
    )
    self.widget_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self.widget_mode_btn.setFixedSize(36, 36)
    self.widget_mode_btn.setStyleSheet(runtime_styles["tool_button"])
    self.widget_mode_btn.clicked.connect(self.toggle_widget_mode_panel)
    top_bar.addWidget(self.widget_mode_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    self.top_bar_frame = _TopBarFrame(
        brand_group, self.search_edit, self.sync_status_text_lbl, self.settings
    )
    self.lock_label.setParent(self.top_bar_frame)
    self.magnet_label.setParent(self.top_bar_frame)
    self.top_bar_frame.setObjectName("top_bar_frame")
    self.top_bar_frame.setStyleSheet(build_top_bar_frame_style(self.settings))
    self.top_bar_frame.setLayout(top_bar)
    _setup_navigation_rail(self, runtime_styles, _tb_text, _theme)
    # top_bar_frame은 ui_builder에서 setMenuWidget()으로 최상단에 고정됨
