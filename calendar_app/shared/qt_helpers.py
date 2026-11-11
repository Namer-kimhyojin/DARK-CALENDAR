# -*- coding: utf-8 -*-
"""Qt widget helper functions shared across presentation modules."""

from PyQt6.QtWidgets import QApplication, QDockWidget

from calendar_app.shared.typography import DEFAULT_FONT_PT


def mnemonic_safe(text) -> str:
    """Show a literal "&" on buttons, tabs, menus and group boxes.

    Qt treats "&" in those labels as a keyboard-mnemonic marker and hides it, so
    translated labels such as "Save & Continue" rendered as "Save  Continue".
    """
    return str(text or "").replace("&", "&&")


def find_parent_dock(widget, dock_ref=None):
    """Return cached dock or walk parent chain to locate QDockWidget."""
    if dock_ref is not None:
        return dock_ref
    parent = widget.parent()
    while parent:
        if isinstance(parent, QDockWidget):
            return parent
        parent = parent.parent()
    return None


def apply_hover_state(widget, hovered: bool):
    """Apply hover property and refresh Qt style for the given widget."""
    widget.setProperty("hovered", bool(hovered))
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)


def app_font_point_size(default=DEFAULT_FONT_PT):
    """Return current QApplication base point size with a safe fallback."""
    try:
        app = QApplication.instance()
        if app is not None:
            base = int(app.font().pointSize())
        else:
            base = int(default)
    except Exception:
        base = int(default)
    if base <= 0:
        base = int(default)
    return base


def scaled_pt(delta=0, minimum=6, default=DEFAULT_FONT_PT):
    """Return a CSS pt string based on app font size plus delta."""
    return f"{max(int(minimum), app_font_point_size(default) + int(delta))}pt"
