# -*- coding: utf-8 -*-
"""Priority/status glyphs and the shared event-chip palette.

Every surface that shows a schedule item (month cell, week bar, today/week/
selected-day lists, routines, directives) takes its icon and tint from here so
the same event reads the same way everywhere:

* the glyph comes from task_constants (user-selectable Font Awesome 6 Solid id);
* its colour comes from the meaning (urgent = danger, completed = success, ...);
* the chip is a translucent tint of the event colour with a solid left bar.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PyQt6.QtGui import QColor, QIcon, QPixmap

from calendar_app.domain import task_constants
from calendar_app.shared.color_utils import (
    composite_color,
    contrast_safe_color,
    parse_css_color,
)
from calendar_app.shared.ui_tokens import get_ui_tokens

SUBSCRIPTION_GLYPH = "fa6s.rss"

_PRIORITY_ROLE = {
    "urgent": "danger_hex",
    "high": "warning_hex",
    "normal": "text_secondary",
    "low": "text_muted",
}
_STATUS_ROLE = {
    "pending": "text_secondary",
    "in_progress": "warning_hex",
    "completed": "success_hex",
    "done": "success_hex",
    "deferred": "text_muted",
    "overdue": "danger_hex",
    "canceled": "text_muted",
}

# Translucent chip tint, as alpha of the event colour (0-255).
CHIP_FILL_ALPHA = 61  # 24 %
CHIP_HOVER_ALPHA = 82  # 32 %
CHIP_BORDER_ALPHA = 102  # 40 %
CHIP_RANGE_HOVER_ALPHA = 92  # 36 %


def _tokens(tokens=None) -> dict:
    merged = dict(get_ui_tokens())
    if tokens:
        merged.update(tokens)
    return merged


def _hex(value, fallback="#9aa0aa") -> str:
    """Return #RRGGBB, or #AARRGGBB when the token is translucent (muted text)."""
    color = parse_css_color(value, fallback)
    if color.alpha() < 255:
        return color.name(QColor.NameFormat.HexArgb)
    return color.name(QColor.NameFormat.HexRgb)


# Contrast targets on the composited chip surface (WCAG 1.4.11 / 1.4.3 plus a
# small margin for wallpapers lighter or darker than the reference).
GLYPH_MIN_CONTRAST = 3.6
META_MIN_CONTRAST = 4.6
# Reference backdrop behind a translucent panel and the event tint that is the
# hardest case for chip text: the lightest tint (yellow) under light text, a
# deep tint (violet) under dark text.
_REFERENCE_WALLPAPER = {"dark": "#3a4250", "light": "#c9ced6"}
_REFERENCE_EVENT = {"dark": "#facc15", "light": "#7c3aed"}


@lru_cache(maxsize=64)
def _reference_surface(bg_main: str, text_primary: str, accent: str) -> QColor:
    text = parse_css_color(text_primary, "#f4f7fb")
    mode = "dark" if text.lightnessF() >= 0.5 else "light"
    panel = composite_color(bg_main, _REFERENCE_WALLPAPER[mode])
    tint = parse_css_color(_REFERENCE_EVENT[mode])
    tint.setAlpha(CHIP_FILL_ALPHA)
    return composite_color(tint, panel)


@lru_cache(maxsize=256)
def _readable(value: str, bg_main: str, text_primary: str, accent: str, minimum: float) -> str:
    surface = _reference_surface(bg_main, text_primary, accent)
    opaque = composite_color(parse_css_color(value, "#9aa0aa"), surface)
    return contrast_safe_color(opaque, surface, minimum=minimum)


def _role_color(role: str, tk: dict, minimum: float) -> str:
    return _readable(
        str(tk.get(role) or tk.get("text_secondary") or "#9aa0aa"),
        str(tk.get("bg_main") or "#151a26"),
        str(tk.get("text_primary") or "#f4f7fb"),
        str(tk.get("accent") or "#4da6ff"),
        minimum,
    )


def priority_color(priority, tokens=None) -> str:
    """Meaning colour of a priority glyph, kept at 3:1+ on a chip."""
    role = _PRIORITY_ROLE.get(str(priority or ""), "text_secondary")
    return _role_color(role, _tokens(tokens), GLYPH_MIN_CONTRAST)


def status_color(status, tokens=None) -> str:
    """Meaning colour of a status glyph, kept at 3:1+ on a chip."""
    role = _STATUS_ROLE.get(str(status or ""), "text_secondary")
    return _role_color(role, _tokens(tokens), GLYPH_MIN_CONTRAST)


def chip_alert_color(tokens=None) -> str:
    """Red text on a chip (overdue due date) that still reads at 4.5:1."""
    return _role_color("danger_hex", _tokens(tokens), META_MIN_CONTRAST)


def chip_meta_color(tokens=None) -> str:
    """Muted text on a chip (time, due date) that still reads at 4.5:1."""
    return _role_color("text_secondary", _tokens(tokens), META_MIN_CONTRAST)


@lru_cache(maxsize=256)
def glyph_icon(name: str, color: str) -> QIcon:
    """Return a cached QIcon for a qtawesome glyph id in one colour."""
    if not name:
        return QIcon()
    try:
        import qtawesome as qta  # type: ignore[import]

        return qta.icon(name, color=color)
    except Exception:
        return QIcon()


def glyph_pixmap(name: str, color: str, size: int) -> QPixmap:
    icon = glyph_icon(name, color)
    if icon.isNull():
        return QPixmap()
    return icon.pixmap(QSize(size, size))


def priority_qicon(priority, tokens=None) -> QIcon:
    return glyph_icon(task_constants.priority_icon(priority), priority_color(priority, tokens))


def status_qicon(status, tokens=None) -> QIcon:
    return glyph_icon(task_constants.status_icon(status), status_color(status, tokens))


def is_completed_row(row) -> bool:
    """Whether a task/routine row is done (status or legacy is_completed flag)."""
    if not row:
        return False
    status = str(row.get("status") or "").lower()
    if status in ("completed", "done"):
        return True
    return row.get("is_completed") in (1, True, "1")


def event_qicon(row, tokens=None):
    """Glyph before an event title: done check, source feed or priority."""
    if is_completed_row(row):
        return status_qicon("completed", tokens)
    if row.get("is_subscription"):
        return subscription_qicon(tokens)
    if row.get("priority"):
        return priority_qicon(row["priority"], tokens)
    return None


def subscription_qicon(tokens=None) -> QIcon:
    return glyph_icon(
        SUBSCRIPTION_GLYPH, _role_color("text_secondary", _tokens(tokens), GLYPH_MIN_CONTRAST)
    )


@lru_cache(maxsize=128)
def _glyph_data_uri(name: str, color: str, size: int) -> str:
    pixmap = glyph_pixmap(name, color, size * 2)
    if pixmap.isNull():
        return ""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return "data:image/png;base64," + base64.b64encode(bytes(data)).decode("utf-8", errors="strict")


def glyph_html(name: str, color: str, size: int = 13) -> str:
    """Inline <img> for rich-text tooltips; empty when the glyph is unavailable."""
    uri = _glyph_data_uri(name, color, size)
    if not uri:
        return ""
    return f"<img src='{uri}' width='{size}' height='{size}' style='vertical-align:middle;'>"


def priority_glyph_html(priority, tokens=None, size: int = 13) -> str:
    return glyph_html(
        task_constants.priority_icon(priority), priority_color(priority, tokens), size
    )


def chip_palette(color, tokens=None) -> dict:
    """Return the colours for one event chip tinted by its event/calendar colour."""
    tk = _tokens(tokens)
    base = parse_css_color(color or tk.get("accent"), "#4da6ff")
    r, g, b = base.red(), base.green(), base.blue()

    def rgba(alpha):
        return f"rgba({r}, {g}, {b}, {alpha})"

    return {
        "bar": rgba(255),
        "fill": rgba(CHIP_FILL_ALPHA),
        "hover": rgba(CHIP_HOVER_ALPHA),
        "border": rgba(CHIP_BORDER_ALPHA),
        "range_hover": rgba(CHIP_RANGE_HOVER_ALPHA),
    }


def clear_glyph_cache():
    """Drop cached icons after a theme or label change."""
    glyph_icon.cache_clear()
    _glyph_data_uri.cache_clear()
    _readable.cache_clear()
    _reference_surface.cache_clear()
