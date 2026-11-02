# -*- coding: utf-8 -*-
"""Semantic styles for widget-only navigation, summaries and surface treatments."""


def workspace_styles(tokens, skin):
    ink, secondary = tokens["text_primary"], tokens["text_secondary"]
    surface, alternate = tokens["section_bg"], tokens["section_bg_alt"]
    edge, accent = tokens["panel_border"], tokens["accent"]
    css = f"""
        QLineEdit#workspace_search {{ background: {surface}; color: {ink};
            border: 1px solid {edge}; border-radius: 8px; padding: 8px 10px; }}
        QLineEdit#workspace_search:focus {{ border: 2px solid {accent}; }}
        QFrame#workspace_overview, QFrame#workspace_board {{ background: transparent; border: none; }}
        QToolButton#workspace_metric {{ background: {surface}; color: {secondary};
            border: 1px solid {edge}; border-radius: 9px; padding: 10px 8px; font-weight: 600; }}
        QToolButton#workspace_metric:checked, QToolButton#workspace_metric:hover {{
            background: {alternate}; color: {ink}; border: 1px solid {accent}; }}
        QFrame#unified_container[widgetLayout] QFrame#unified_agenda_section[workspaceLane="true"] {{ background: {surface};
            border: 1px solid {edge}; border-radius: 12px; padding: 8px; }}
    """
    if skin.surface_style == "legacy":
        return css
    radius, item_radius = {
        "soft": (18, 10),
        "paper": (6, 2),
        "outline": (12, 6),
        "glass": (24, 14),
        "compact": (8, 4),
    }[skin.surface_style]
    item_bg = "transparent" if skin.surface_style in {"outline", "paper"} else tokens["card_bg"]
    item_border = (
        f"border: 1px solid {edge};"
        if skin.surface_style != "paper"
        else f"border: none; border-bottom: 1px solid {edge};"
    )
    return (
        css
        + f"""
        QFrame#unified_surface {{ border-radius: {radius}px; }}
        QFrame#agenda_item_task, QFrame#agenda_item_schedule {{
            background: {item_bg}; {item_border} border-radius: {item_radius}px; }}
    """
    )
