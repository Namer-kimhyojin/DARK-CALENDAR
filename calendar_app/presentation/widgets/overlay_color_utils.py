"""Color utility helpers extracted from overlay_base."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog


def _parse_rgba(
    raw: str, fallback_rgb: str = "#101418", fallback_alpha: int = 214
) -> tuple[QColor, int]:
    """Return (QColor-without-alpha, alpha 0-255) from a stored color string."""
    s = str(raw or "").strip()
    if len(s) == 9 and s.startswith("#"):  # #AARRGGBB
        alpha = int(s[1:3], 16)
        rgb = "#" + s[3:]
        c = QColor(rgb)
        if c.isValid():
            return c, alpha
    c = QColor(s)
    if c.isValid():
        return c, fallback_alpha
    return QColor(fallback_rgb), fallback_alpha


def _to_rgba_str(color: QColor, alpha: int) -> str:
    """Encode as #AARRGGBB string."""
    a = max(0, min(255, int(alpha)))
    return f"#{a:02x}{color.red():02x}{color.green():02x}{color.blue():02x}"


def _rgba_css(color: QColor, alpha: int) -> str:
    """Return rgba(r,g,b,a255) CSS string (alpha 0-255)."""
    a = max(0, min(255, int(alpha)))
    return f"rgba({color.red()},{color.green()},{color.blue()},{a})"


def _pick_rgba_color(parent, title: str, current_rgba_str: str) -> str | None:
    """Open QColorDialog with alpha channel. Returns #AARRGGBB or None."""
    c, a = _parse_rgba(current_rgba_str)
    initial = QColor(c)
    initial.setAlpha(a)

    chosen = QColorDialog.getColor(
        initial,
        parent,
        title,
        QColorDialog.ColorDialogOption.ShowAlphaChannel,
    )
    if not chosen.isValid():
        return None
    rgb = QColor(chosen.red(), chosen.green(), chosen.blue())
    return _to_rgba_str(rgb, chosen.alpha())
