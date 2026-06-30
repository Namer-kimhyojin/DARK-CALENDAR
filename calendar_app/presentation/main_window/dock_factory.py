"""Factory helpers to construct main dock layout."""

from PyQt6.QtWidgets import QFrame, QWidget

from calendar_app.presentation.main_window.dock_sections import (
    create_center_dock,
    create_directive_dock,
    create_left_dock,
    create_routine_dock,
)
from calendar_app.shared.color_utils import derive_panel_palette, derive_ui_palette
from calendar_app.shared.theme_settings import get_theme_palette_inputs


def build_dock_manager_style(settings, theme_color):
    text_theme, panel_base, opacity_factor = get_theme_palette_inputs(settings)
    panel_pal = derive_panel_palette(panel_base, opacity_factor)
    ui_pal = derive_ui_palette(text_theme, panel_base, opacity_factor)
    tab_bg = panel_pal["topbar_bg"]
    tab_hover = panel_pal["surface_hover_bg"]
    tab_active = panel_pal["toolbar_bg"]
    tab_text = ui_pal["text_secondary"]
    tab_text_active = ui_pal["text_primary"]
    tab_border = "rgba(255, 255, 255, 0.10)"
    pane_line = "rgba(255, 255, 255, 0.08)"
    return f"""
        QMainWindow::separator {{
            background-color: rgba(255, 255, 255, 10);
            width: 3px; height: 3px;
            margin: 0px;
        }}
        QMainWindow::separator:hover {{
            background-color: {theme_color};
        }}
        QMainWindow::tab-bar {{
            alignment: left;
        }}
        QTabBar::tab {{
            background-color: {tab_bg};
            color: {tab_text};
            border: 1px solid {tab_border};
            border-top: 2px solid transparent;
            border-bottom: none;
            padding: 5px 12px;
            margin-right: 3px;
            min-width: 54px;
        }}
        QTabBar::tab:top {{
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }}
        QTabBar::tab:bottom {{
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
            border-bottom-left-radius: 6px;
            border-bottom-right-radius: 6px;
            margin-top: 0px;
            padding-top: 4px;
            padding-bottom: 6px;
        }}
        QTabBar::tab:hover {{
            background-color: {tab_hover};
            color: {tab_text_active};
        }}
        QTabBar::tab:selected {{
            background-color: {tab_active};
            color: {tab_text_active};
            border-color: rgba(255, 255, 255, 0.16);
            border-top: 2px solid {theme_color};
        }}
        QTabBar::tab:top:!selected {{
            margin-top: 2px;
        }}
        QTabBar::tab:bottom:selected {{
            margin-top: -1px;
            padding-top: 5px;
            padding-bottom: 7px;
        }}
        QTabBar::tab:bottom:!selected {{
            margin-top: 2px;
        }}
        QTabBar::pane {{
            border-top: 1px solid {pane_line};
        }}
    """


def setup_body_and_docks(self, theme_color):
    # OverlayApp is now QMainWindow — self directly manages docks.
    # dock_manager alias kept so all existing callsites (dock_layout_presets etc.)
    # continue to work without change.
    self.dock_manager = self
    self.setDockNestingEnabled(True)
    self.setAnimated(True)
    self.setDockOptions(
        self.DockOption.AllowNestedDocks
        | self.DockOption.AllowTabbedDocks
        | self.DockOption.AnimatedDocks
    )
    self.setStyleSheet(
        self.styleSheet() + "\n" + build_dock_manager_style(self.settings, theme_color)
    )
    # top_bar_frame은 setMenuWidget으로 고정됨.
    # main_layout에 남은 위젯이 없으므로 centralWidget을 완전히 숨겨서
    # dock들이 창 전체를 채우도록 한다.
    central = QWidget()
    central.setObjectName("CentralWidget")
    central.setStyleSheet("background: transparent; border: none;")
    central.setFixedSize(0, 0)
    central.setContentsMargins(0, 0, 0, 0)
    self.setCentralWidget(central)
    central.hide()
    self.setMinimumSize(400, 300)

    create_left_dock(self)
    create_center_dock(self)
    create_routine_dock(self)
    create_directive_dock(self)

    # Load panel contents after all four docks are created and placed.
    self.load_left_panel()
    self.load_center_panel()
    self.load_right_panel()

    self.sync_panel_menu_state()

    self.focus_frame = QFrame()
    self.focus_frame.setStyleSheet(
        f"QFrame {{ background-color: rgba(30, 30, 30, 240); border-radius: 8px; border: 2px solid {theme_color}; }}"
    )
    self.focus_frame.hide()
