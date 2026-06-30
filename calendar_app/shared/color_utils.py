"""Shared color helpers used by UI rendering/styling modules."""

from PyQt6.QtGui import QColor


def hex_to_rgba(hex_color: str, alpha_0_to_1: float) -> str:
    """Convert hex color string to rgba(r,g,b,a) string."""

    h = (hex_color or "").lstrip("#")

    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2

    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    except (ValueError, IndexError):
        r, g, b = 77, 166, 255  # fallback blue

    return f"rgba({r},{g},{b},{alpha_0_to_1})"


def hue_shifted_rgba(hex_color: str, hue_shift: float, alpha_0_to_1: float) -> str:
    """Rotate hue from source color and return rgba string."""

    c = QColor(hex_color)

    if not c.isValid():
        c = QColor("#4da6ff")

    h, s, v, _ = c.getHsvF()

    shifted = QColor.fromHsvF((h + hue_shift / 360.0) % 1.0, min(s, 1.0), min(v, 1.0))

    return f"rgba({shifted.red()},{shifted.green()},{shifted.blue()},{alpha_0_to_1})"


def parse_hex_color(hex_color: str, fallback: str = "#1c1c1c") -> QColor:
    c = QColor(str(hex_color))

    if not c.isValid():
        c = QColor(fallback)

    return c


def shift_rgb(color: QColor, delta: int) -> QColor:
    return QColor(
        max(0, min(255, color.red() + delta)),
        max(0, min(255, color.green() + delta)),
        max(0, min(255, color.blue() + delta)),
    )


def _shift_rgb(color: QColor, delta: int) -> QColor:
    return shift_rgb(color, delta)


def parse_css_alpha_to_unit(value: str) -> float:
    try:
        alpha = float(value)
    except Exception:
        return 1.0
    if alpha <= 1.0:
        return max(0.0, min(1.0, alpha))
    return max(0.0, min(255.0, alpha)) / 255.0


def rgba_from_qcolor(color: QColor, alpha: int) -> str:
    a = max(0, min(255, int(alpha)))

    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {a})"


def derive_text_palette(text_theme: str = "dark", theme_color: str = "#4da6ff") -> dict:
    """Return shared text color tokens for the active text theme."""

    is_light = text_theme == "light"

    accent = parse_hex_color(theme_color, "#4da6ff")

    if text_theme == "custom":
        try:
            from PyQt6.QtCore import QSettings

            s = QSettings("kimhyojin", "Dark Calendar")

            primary = parse_hex_color(
                str(s.value("custom_text_primary", "#f4f7fb")), "#f4f7fb"
            ).name()

            secondary = rgba_from_qcolor(
                parse_hex_color(str(s.value("custom_text_secondary", "#c5cfda")), "#c5cfda"),
                255,
            )

            muted = rgba_from_qcolor(
                parse_hex_color(str(s.value("custom_text_muted", "#95a1ae")), "#95a1ae"),
                255,
            )

            faint = rgba_from_qcolor(
                parse_hex_color(str(s.value("custom_text_faint", "#6f7b88")), "#6f7b88"),
                255,
            )

            inverse = "#0f1217"

        except Exception:
            primary = "#f4f7fb"

            secondary = "rgba(197,207,218,255)"

            muted = "rgba(149,161,174,255)"

            faint = "rgba(111,123,136,255)"

            inverse = "#0f1217"

    elif is_light:
        primary = "#101318"

        secondary = "rgba(16,19,24,0.74)"

        muted = "rgba(16,19,24,0.54)"

        faint = "rgba(16,19,24,0.38)"

        inverse = "#ffffff"

    else:
        primary = "#f4f7fb"

        secondary = "rgba(244,247,251,0.76)"

        muted = "rgba(244,247,251,0.58)"

        faint = "rgba(244,247,251,0.42)"

        inverse = "#0f1217"

    return {
        "text_primary": primary,
        "text_secondary": secondary,
        "text_muted": muted,
        "text_faint": faint,
        "text_inverse": inverse,
        "text_accent": rgba_from_qcolor(accent, 255),
        "text_accent_soft": rgba_from_qcolor(accent, 214),
    }


def derive_ui_palette(
    text_theme: str = "dark",
    panel_base_color: str = "#1c1c1c",
    opacity_factor: float = 1.0,
    theme_color: str = "#4da6ff",
) -> dict:
    """

    Text theme changes only text colors; background tokens come from panel base color.

    """

    f = max(0.0, min(1.0, opacity_factor))

    def _fa(offset: int = 0) -> int:
        return max(0, min(255, int(f * 255) + offset))

    panel_pal = derive_panel_palette(panel_base_color, f)

    base = parse_hex_color(panel_base_color, "#1c1c1c")

    text_pal = derive_text_palette(text_theme, theme_color)

    text_primary = text_pal["text_primary"]

    text_secondary = text_pal["text_secondary"]

    text_placeholder = text_pal["text_faint"]

    return {
        "bg_primary": panel_pal["surface_bg"],
        "bg_secondary": panel_pal["toolbar_bg"],
        "bg_hover": panel_pal["surface_hover_bg"],
        "text_primary": text_primary,
        "text_secondary": text_secondary,
        "text_muted": text_pal["text_muted"],
        "text_faint": text_pal["text_faint"],
        "text_inverse": text_pal["text_inverse"],
        "text_accent": text_pal["text_accent"],
        "text_accent_soft": text_pal["text_accent_soft"],
        "text_placeholder": text_placeholder,
        "border": "rgba(255,255,255,0.16)",
        "cell_bg": rgba_from_qcolor(base, 0),
        "cell_other_bg": rgba_from_qcolor(base, 0),
        "cell_hover_bg": rgba_from_qcolor(base, 0),
        "task_btn_bg": rgba_from_qcolor(base, _fa(-15)),
        "task_btn_hover": rgba_from_qcolor(base, _fa(0)),
        "task_btn_text": text_primary,
        "scrollbar_handle": "rgba(255,255,255,0.15)",
        "weekday_label": text_secondary,
        "weekday_sat": "#8ab7ff",
        "weekday_sun": "#ff9ea8",
        "weekday_other": "rgba(255,255,255,0.42)",
        "weekday_normal": text_secondary,
        "tooltip_bg": panel_pal["toolbar_bg"],
        "tooltip_text": text_primary,
    }


def derive_panel_palette(base_hex: str, opacity_factor: float = 1.0) -> dict:
    """

    Derive cohesive panel palette from one base color.

    Returns rgba strings for panel surfaces, toolbar, topbar, and side-item cards.

    opacity_factor: 0.0 = fully transparent, 1.0 = fully opaque (alpha=255).
    Each surface has a relative ratio so they look cohesive at any opacity.

    """

    f = max(0.0, min(1.0, opacity_factor))

    # At f=1.0 all surfaces must be fully opaque (alpha=255).
    # At f=0.0 all surfaces are fully transparent (alpha=0).
    # The offsets are applied only below full opacity to keep subtle differentiation.
    def _a(offset: int = 0) -> int:
        if f >= 1.0:
            return 255
        return max(0, min(255, int(f * 255) + offset))

    base = parse_hex_color(base_hex, "#1c1c1c")

    return {
        "surface_bg": rgba_from_qcolor(base, _a(-30)),
        "surface_hover_bg": rgba_from_qcolor(base, _a(-10)),
        "toolbar_bg": rgba_from_qcolor(base, _a(-20)),
        "topbar_bg": rgba_from_qcolor(base, _a(-50)),
        "item_bg": rgba_from_qcolor(base, _a(-5)),
        "item_hover_bg": rgba_from_qcolor(base, _a(0)),
    }
