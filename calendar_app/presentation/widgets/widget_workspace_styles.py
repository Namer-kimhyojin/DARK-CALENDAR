# -*- coding: utf-8 -*-
"""Semantic styles for widget-only navigation, summaries and surface treatments."""

from calendar_app.presentation.widgets.widget_mode_surfaces import WidgetModeSurface


def workspace_styles(tokens, surface: WidgetModeSurface) -> str:
    ink, secondary = tokens["text_primary"], tokens["text_secondary"]
    fill, alternate = tokens["section_bg"], tokens["section_bg_alt"]
    edge, accent = tokens["panel_border"], tokens["accent"]
    css = f"""
        QLineEdit#workspace_search {{ background: {fill}; color: {ink};
            border: 1px solid {edge}; border-radius: 8px; padding: 8px 10px; }}
        QLineEdit#workspace_search:focus {{ border: 2px solid {accent}; }}
        QFrame#workspace_overview, QFrame#workspace_board {{ background: transparent; border: none; }}
        QToolButton#workspace_metric {{ background: {fill}; color: {secondary};
            border: 1px solid {edge}; border-radius: 9px; padding: 10px 8px; font-weight: 600; }}
        QToolButton#workspace_metric:checked, QToolButton#workspace_metric:hover {{
            background: {alternate}; color: {ink}; border: 1px solid {accent}; }}
        QFrame#unified_container[widgetLayout] QFrame#unified_agenda_section[workspaceLane="true"] {{ background: {fill};
            border: 1px solid {edge}; border-radius: 12px; padding: 8px; }}
    """
    item_bg = "transparent" if surface.item_background == "transparent" else tokens["card_bg"]
    # The card surface is today's look: items keep the soft card border.
    item_edge = tokens.get("card_border", edge) if surface.key == "card" else edge
    item_border = (
        f"border: none; border-bottom: 1px solid {edge};"
        if surface.item_border == "bottom"
        else f"border: 1px solid {item_edge};"
    )
    return (
        css
        + f"""
        QFrame#unified_surface {{ border-radius: {surface.radius}px; }}
        QFrame#agenda_item_task, QFrame#agenda_item_schedule {{
            background: {item_bg}; {item_border} border-radius: {surface.item_radius}px; }}
    """
    )
