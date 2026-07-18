"""Shared helpers for top-bar menu buttons."""

from calendar_app.shared.icon_map import strip_leading_emoji


def format_top_menu_button_text(label: str) -> str:
    text = strip_leading_emoji(str(label or "").strip())
    return f" {text}" if text else ""
