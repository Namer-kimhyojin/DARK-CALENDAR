# -*- coding: utf-8 -*-
"""Shared helpers for top-bar menu buttons."""

from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji

_ICON_KEY_PROPERTY = "_theme_icon_key"
_ICON_ROLE_PROPERTY = "_theme_icon_role"


def format_top_menu_button_text(label: str) -> str:
    text = strip_leading_emoji(str(label or "").strip())
    return f" {text}" if text else ""


def set_themed_icon(target, key: str, color: str, *, role: str = "neutral"):
    """Set an icon and retain enough metadata to recolor it after a mode switch."""

    target.setProperty(_ICON_KEY_PROPERTY, key)
    target.setProperty(_ICON_ROLE_PROPERTY, role)
    target.setIcon(_ic(key, color=color))


def refresh_top_menu_icons(owner, role_colors: dict[str, str]):
    """Rebuild top-menu icons because QIcon colors are fixed at creation time."""

    seen: set[int] = set()

    def _refresh(target):
        if target is None or id(target) in seen:
            return
        seen.add(id(target))
        key = target.property(_ICON_KEY_PROPERTY)
        if key:
            role = str(target.property(_ICON_ROLE_PROPERTY) or "neutral")
            color = role_colors.get(role, role_colors["neutral"])
            target.setIcon(_ic(str(key), color=color))

    def _walk_menu(menu):
        if menu is None:
            return
        _refresh(menu)
        for action in menu.actions():
            _refresh(action)
            submenu = action.menu()
            if submenu is not None:
                _walk_menu(submenu)

    for attr in (
        "add_menu_btn",
        "view_menu_btn",
        "display_menu_btn",
        "widgets_menu_btn",
        "sys_menu_btn",
    ):
        _refresh(getattr(owner, attr, None))

    for attr in ("add_menu", "view_menu", "display_menu", "widgets_menu", "sys_menu"):
        _walk_menu(getattr(owner, attr, None))
