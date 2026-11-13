# -*- coding: utf-8 -*-
"""Menu locations quoted in help text, stored as the i18n keys the menus are built from.

The labels are read from the locale at display time, so renaming a menu item
cannot leave a stale path in the shortcut guide or in a setup message.
"""

from __future__ import annotations

from collections.abc import Iterable

from calendar_app.shared.icon_map import strip_leading_emoji

# Top-bar menu buttons (see presentation/main_window/top_menus).
TOP_MENU_BUTTON_KEYS: tuple[str, ...] = (
    "menu.register_btn",
    "menu.work_btn",
    "menu.display_btn",
    "menu.widgets",
    "menu.system",
)

# Not a menu label: names the menu that right-clicking a selected item opens.
SELECTED_ITEM_MENU_KEY = "shortcut.menu_roots.selected_item"

# Where a Google account is connected: Settings > Calendars and sync > the sync
# hub > its connections tab, which lists the Google Calendar card.
GOOGLE_SYNC_SETUP_PATH: tuple[str, ...] = (
    "menu.system",
    "sync_unified.menu",
    "sync_ui.hub_title",
    "sync_redesign.connections_tab",
)


def menu_label(key: str) -> str:
    """Return the label a menu shows for ``key``, without its emoji or trailing ellipsis."""
    from calendar_app.infrastructure.i18n import t

    # Non-literal key: tests/test_help_menu_paths.py checks every path key exists.
    text = strip_leading_emoji(str(t(key) or "")).strip()
    for suffix in ("...", "…"):
        text = text.removesuffix(suffix)
    return text.strip()


def format_menu_path(keys: Iterable[str]) -> str:
    """Join the live labels of ``keys`` the way help text writes a menu path."""
    return " > ".join(menu_label(key) for key in keys)
