# -*- coding: utf-8 -*-
"""Widget-workspace aliases for the main window's effective theme roles."""

from calendar_app.shared.color_utils import contrasting_text_color, hex_to_rgba
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens


def main_widget_mode_tokens(settings=None) -> dict[str, str]:
    """Reuse main colors/alpha; retain the workspace's established geometry keys."""
    snapshot = build_theme_snapshot(settings, persist_opacity=False)
    ui = get_ui_tokens(settings, snapshot=snapshot)
    palette = snapshot.ui_palette
    tokens = dict(ui)
    # Geometry has no dependency on modal presets or expert dialog color overrides.
    shape = snapshot.shape_tokens
    surface = int(shape.get("panel_surface_radius", 14))
    item = int(shape.get("panel_item_radius", 10))
    toolbar = int(shape.get("panel_toolbar_button_radius", 8))
    switch = int(shape.get("panel_mode_switch_radius", 12))
    menu = int(shape.get("panel_menu_radius", 10))
    menu_item = int(shape.get("panel_menu_item_radius", 8))
    geometry = {
        "launcher_radius": surface + 8,
        "launcher_button_radius": item + 6,
        "widget_surface_radius": surface + 2,
        "widget_header_radius": max(0, surface - 4),
        "widget_control_radius": toolbar + 2,
        "widget_entry_radius": item + 2,
        "widget_secondary_radius": toolbar + 2,
        "widget_input_radius": item + 2,
        "widget_submit_radius": toolbar + 3,
        "widget_chip_radius": max(0, switch - 2),
        "widget_summary_radius": surface,
        "widget_menu_radius": menu + 4,
        "widget_menu_item_radius": menu_item + 2,
        "widget_calendar_nav_radius": toolbar,
        "widget_calendar_cell_radius": max(item, toolbar + 2),
        "widget_calendar_today_radius": max(item + 1, toolbar + 3),
    }
    tokens.update({key: str(value) for key, value in geometry.items()})
    aliases = {
        "calendar_text": "text_primary",
        "calendar_muted": "text_muted",
        "card_text_primary": "text_primary",
        "card_text_secondary": "text_secondary",
        "accent_deep": "accent",
        "accent_strong": "accent",
        "pastel_accent": "accent",
        "panel_bg_start": "bg_main",
        "panel_bg_mid": "bg_main",
        "panel_bg_end": "bg_main",
        "panel_bg": "bg_main",
        "surface_bg": "bg_main",
        "surface_alt": "bg_alt",
        "header_bg": "bg_top",
        "header_shell_bg": "bg_top",
        "panel_border": "border",
        "panel_border_soft": "border_soft",
        "header_shell_border": "border_soft",
        "shell_outline": "border",
        "shell_outline_soft": "border_soft",
        "section_bg": "content_bg",
        "section_bg_alt": "bg_hover",
        "section_border": "border",
        "section_border_soft": "border_soft",
        "card_bg": "bg_item",
        "card_hover": "bg_item_hover",
        "card_pressed": "bg_hover",
        "card_border": "border_soft",
        "card_accent": "accent_border",
        "chip_bg": "bg_alt",
        "chip_border": "border_soft",
        "input_bg": "input_bg",
        "input_border": "input_border",
        "button_text": "text_secondary",
        "button_primary_bg": "accent",
        "button_primary_border": "accent",
        "button_primary_hover_bg": "accent_hover",
        "button_primary_hover_border": "accent",
        "hero_bg": "accent_soft",
        "hero_bg_strong": "accent_soft",
        "hero_border": "accent_border",
        "shell_gradient_start": "bg_main",
        "shell_gradient_mid": "bg_main",
        "shell_gradient_end": "bg_main",
        "scroll_track": "bg_alt",
    }
    tokens.update({target: ui[source] for target, source in aliases.items()})
    tokens.update(
        button_bg=palette["control_bg"],
        button_hover=palette["control_bg_hover"],
        accent_mid=ui["accent_border"],
        button_primary_text=contrasting_text_color(ui["accent"]),
        button_primary_hover_text=contrasting_text_color(ui["accent_hover"]),
        button_danger_bg=hex_to_rgba(ui["danger"], 0.14),
        button_danger_text=ui["danger"],
        button_danger_border=hex_to_rgba(ui["danger"], 0.42),
        button_danger_hover_bg=hex_to_rgba(ui["danger"], 0.22),
        button_danger_hover_border=ui["danger"],
        scroll_thumb=palette["scrollbar_handle"],
        scroll_thumb_hover=ui["accent"],
        hero_bg=palette["selection_bg"],
        hero_bg_strong=palette["selection_bg"],
        calendar_weekday_sat=palette["weekday_sat"],
        calendar_weekday_sun=palette["weekday_sun"],
        grip_color=ui["border"],
        _main_theme_linked="true",
        _main_base_color=snapshot.panel_base_color,
        _main_text_theme=snapshot.text_theme,
        _main_opacity=str(snapshot.opacity_factor),
    )
    return tokens
