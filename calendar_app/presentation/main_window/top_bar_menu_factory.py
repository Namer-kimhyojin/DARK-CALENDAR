# -*- coding: utf-8 -*-
"""Factory orchestrator for top-bar menu groups."""

from calendar_app.presentation.main_window.top_menus import (
    build_display_menu,
    build_register_menu,
    build_system_menu,
    build_widgets_menu_btn,
    build_work_menu,
)
from calendar_app.presentation.theme.style_builder import (
    _build_app_menu_style,
    _build_top_menu_button_style,
)
from calendar_app.shared.theme_snapshot import build_theme_snapshot


def build_top_left_menus(self, top_bar, size, theme_color):
    menu_btn_pt = max(9, size)
    menu_btn_style = _build_top_menu_button_style(menu_btn_pt, theme_color)
    snapshot = build_theme_snapshot(self.settings)
    menu_style = _build_app_menu_style(
        size,
        theme_color,
        snapshot.text_theme,
        panel_base_color=snapshot.panel_base_color,
        opacity_factor=snapshot.opacity_factor,
        settings=self.settings,
        persist_opacity=False,
    )

    build_register_menu(self, top_bar, menu_btn_style, menu_style)
    build_work_menu(self, top_bar, menu_btn_style, menu_style)
    build_display_menu(self, top_bar, menu_btn_style, menu_style)
    build_widgets_menu_btn(self, top_bar, menu_btn_style, menu_style)
    build_system_menu(self, top_bar, menu_btn_style, menu_style)
