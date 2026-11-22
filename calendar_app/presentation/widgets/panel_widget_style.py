# -*- coding: utf-8 -*-
"""Premium widget-mode stylesheet helpers.

The widget mode leans on a layered editorial card language:
  - soft multi-stop surfaces instead of flat panels
  - thin luminous borders instead of hard separators
  - strong typography hierarchy with restrained accent use
  - light interaction feedback without heavy visual effects
"""

from __future__ import annotations

import re

from PyQt6.QtGui import QColor

from calendar_app.presentation.widgets.widget_mode_theme import main_widget_mode_tokens

_RGBA_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)


def css_to_qcolor(value: object, fallback: str = "#000000") -> QColor:
    raw = str(value or "").strip()
    if raw:
        match = _RGBA_RE.match(raw)
        if match:
            try:
                r, g, b, a_raw = match.groups()
                alpha = float(a_raw)
                if alpha <= 1.0:
                    alpha *= 255.0
                return QColor(
                    max(0, min(255, int(r))),
                    max(0, min(255, int(g))),
                    max(0, min(255, int(b))),
                    max(0, min(255, int(round(alpha)))),
                )
            except Exception:
                pass
        resolved = QColor(raw)
        if resolved.isValid():
            return resolved
    fallback_color = QColor(fallback)
    return fallback_color if fallback_color.isValid() else QColor("#000000")


def rgba(value: object, alpha: int, fallback: str = "#000000") -> str:
    qcolor = value if isinstance(value, QColor) else css_to_qcolor(value, fallback)
    return (
        f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {max(0, min(255, int(alpha)))})"
    )


def int_token(tokens: dict[str, str], key: str, default: int) -> int:
    try:
        return max(0, int(float(tokens.get(key, default))))
    except Exception:
        return int(default)


def resolve_tokens(
    tokens: dict[str, str] | None = None,
    *,
    settings=None,
    preset_name: str | None = None,
) -> dict[str, str]:
    del preset_name  # Legacy skins keep geometry while colors follow the main theme.
    resolved = main_widget_mode_tokens(settings)
    if tokens:
        resolved.update(tokens)
    return resolved


def menu_stylesheet(tokens: dict[str, str]) -> str:
    tk = tokens
    menu_radius = int_token(tk, "widget_menu_radius", 14)
    item_radius = int_token(tk, "widget_menu_item_radius", 8)
    return f"""
        QMenu {{
            background: {tk.get("panel_bg", "rgba(13,15,20,238)")};
            color: {tk.get("text_secondary", "#c0cade")};
            border: 1px solid {tk.get("panel_border", "rgba(255,255,255,20)")};
            border-radius: {menu_radius}px;
            padding: 8px;
            font-size: 8.9pt;
            font-weight: 500;
        }}
        QMenu::item {{
            padding: 8px 22px 8px 12px;
            border-radius: {item_radius}px;
            margin: 1px 0;
            background: transparent;
        }}
        QMenu::item:selected {{
            background: {tk.get("section_bg_alt", "rgba(255,255,255,0.08)")};
            color: {tk.get("text_primary", "#ffffff")};
        }}
        QMenu::item:disabled {{
            color: {tk.get("text_faint", "#7c88a3")};
        }}
        QMenu::separator {{
            height: 1px;
            margin: 6px 8px;
            background: {tk.get("section_border_soft", "rgba(255,255,255,12)")};
        }}
    """
