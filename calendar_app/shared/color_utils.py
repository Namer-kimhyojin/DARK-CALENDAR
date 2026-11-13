# -*- coding: utf-8 -*-
"""Shared color helpers used by UI rendering/styling modules."""

from functools import lru_cache
import re

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


def parse_css_color(value: str | QColor, fallback: str = "#000000") -> QColor:
    """Read Qt CSS colors, including normalized byte or fractional RGBA alpha."""
    if isinstance(value, QColor):
        return QColor(value)
    raw = str(value or "").strip()
    match = re.fullmatch(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)", raw, re.IGNORECASE
    )
    if match:
        red, green, blue, alpha_text = match.groups()
        try:
            alpha = float(alpha_text) if alpha_text is not None else 255.0
            if alpha_text is not None and alpha <= 1.0:
                alpha *= 255.0
            return QColor(
                *(max(0, min(255, round(float(channel)))) for channel in (red, green, blue, alpha))
            )
        except (ValueError, OverflowError):
            pass
    color = parse_hex_color(raw, fallback)
    return color if color.isValid() else QColor("#000000")


def composite_color(foreground: str | QColor, background: str | QColor) -> QColor:
    """Resolve a CSS foreground over its opaque reading surface."""
    front = parse_css_color(foreground)
    back = parse_css_color(background)
    alpha = front.alphaF()
    return QColor(
        *(
            round(a * alpha + b * (1.0 - alpha))
            for a, b in zip(front.getRgb()[:3], back.getRgb()[:3], strict=True)
        )
    )


def shift_rgb(color: QColor, delta: int) -> QColor:
    return QColor(
        max(0, min(255, color.red() + delta)),
        max(0, min(255, color.green() + delta)),
        max(0, min(255, color.blue() + delta)),
    )


def contrast_ratio(foreground: str | QColor, background: str | QColor) -> float:
    """Return the WCAG contrast ratio for two opaque colors."""

    def _relative_luminance(value: str | QColor) -> float:
        color = QColor(value) if isinstance(value, QColor) else parse_hex_color(value, "#000000")
        channels = []
        for channel in (color.redF(), color.greenF(), color.blueF()):
            channels.append(
                channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light = _relative_luminance(foreground)
    dark = _relative_luminance(background)
    return (max(light, dark) + 0.05) / (min(light, dark) + 0.05)


def contrasting_text_color(
    background: str | QColor,
    *,
    light: str = "#ffffff",
    dark: str = "#101318",
    surface: str | QColor = "#ffffff",
) -> str:
    """Choose whichever text color has the stronger contrast on ``background``.

    With the default light/dark pair the text is a deep (or pale) shade of the
    background's own hue rather than plain black or white, picked at the first
    shade that reads at 7:1; harsh black on a colored button was too heavy.
    """

    resolved = composite_color(background, surface)
    chosen = light if contrast_ratio(light, resolved) >= contrast_ratio(dark, resolved) else dark
    if light == "#ffffff" and dark == "#101318":
        toward = QColor("#ffffff") if chosen == light else QColor("#000000")
        shades = [
            QColor(
                round(resolved.red() + (toward.red() - resolved.red()) * step / 100),
                round(resolved.green() + (toward.green() - resolved.green()) * step / 100),
                round(resolved.blue() + (toward.blue() - resolved.blue()) * step / 100),
            )
            for step in range(55, 100, 2)
        ]
        # Comfortable 7:1 first; mid-tone colors cannot reach it with their own hue,
        # so they take the most colorful shade that still meets the 4.5:1 minimum.
        for minimum in (7.0, 4.5):
            for shade in shades:
                if contrast_ratio(shade, resolved) >= minimum:
                    return shade.name(QColor.NameFormat.HexRgb)
    if contrast_ratio(chosen, resolved) < 4.5:
        return (
            "#ffffff"
            if contrast_ratio("#ffffff", resolved) >= contrast_ratio("#000000", resolved)
            else "#000000"
        )
    return chosen


def contrast_safe_color(
    foreground: str | QColor,
    background: str | QColor,
    *,
    minimum: float = 3.0,
) -> str:
    """Preserve a semantic hue while moving it toward a readable lightness.

    This is intended for non-text identity colors such as calendar icons and
    focus borders. Body text should continue to use the semantic text tokens.
    """

    source = QColor(foreground) if isinstance(foreground, QColor) else parse_hex_color(foreground)
    bg = QColor(background) if isinstance(background, QColor) else parse_hex_color(background)
    if contrast_ratio(source, bg) >= float(minimum):
        return source.name(QColor.NameFormat.HexRgb)

    black = QColor("#000000")
    white = QColor("#ffffff")
    target = black if contrast_ratio(black, bg) >= contrast_ratio(white, bg) else white
    for step in range(1, 101):
        ratio = step / 100.0
        candidate = QColor(
            round(source.red() * (1.0 - ratio) + target.red() * ratio),
            round(source.green() * (1.0 - ratio) + target.green() * ratio),
            round(source.blue() * (1.0 - ratio) + target.blue() * ratio),
        )
        if contrast_ratio(candidate, bg) >= float(minimum):
            return candidate.name(QColor.NameFormat.HexRgb)
    return target.name(QColor.NameFormat.HexRgb)


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


BORDER_RECOMMENDED_CONTRAST = 1.5


def _mix_colors(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(first.red() + (second.red() - first.red()) * amount),
        round(first.green() + (second.green() - first.green()) * amount),
        round(first.blue() + (second.blue() - first.blue()) * amount),
    )


@lru_cache(maxsize=256)
def recommend_border_color(base_color: str, accent_color: str) -> str:
    """Suggest a border that separates surfaces without competing with content.

    The background is tinted toward the accent just until a quiet 1.5:1 contrast
    appears; an accent too close to the background is then moved toward white (dark
    backgrounds) or black (light ones) until it does.
    """
    base = parse_hex_color(base_color, "#1c1c1c")
    accent = parse_hex_color(accent_color, "#4da6ff")
    for step in range(1, 16):
        candidate = _mix_colors(base, accent, step * 0.02)
        if contrast_ratio(candidate, base) >= BORDER_RECOMMENDED_CONTRAST:
            return candidate.name(QColor.NameFormat.HexRgb)
    toward = QColor("#ffffff") if base.lightnessF() < 0.5 else QColor("#000000")
    tinted = _mix_colors(base, accent, 0.30)
    for step in range(21):
        candidate = _mix_colors(tinted, toward, step * 0.05)
        if contrast_ratio(candidate, base) >= BORDER_RECOMMENDED_CONTRAST:
            return candidate.name(QColor.NameFormat.HexRgb)
    return toward.name(QColor.NameFormat.HexRgb)


TEXT_OPACITY_KEYS = ("text_primary", "text_secondary", "text_muted", "text_faint")
MIN_TEXT_OPACITY = 77  # 30%: lighter text would stop being readable at all


def faded_text_color(text_color: str, background: str, opacity_factor: float) -> str:
    """Text drawn at an opacity, as the opaque color it shows on this background.

    Composited colors stay valid hex for code that parses text colors, and they
    look the same as translucent text on the panel.
    """
    text = parse_css_color(text_color, "#ffffff")
    if text.alpha() < 255:
        text = composite_color(text, background)
    back = parse_css_color(background, "#1c1c1c")
    return _mix_colors(back, text, max(0.0, min(1.0, float(opacity_factor)))).name(
        QColor.NameFormat.HexRgb
    )


def border_tokens_for(color: str, opacity_factor: float) -> dict[str, str]:
    """Border, soft border and strong border from one color and the border opacity."""
    border = parse_hex_color(color, "#808080")
    opacity = max(0.0, min(1.0, float(opacity_factor)))
    soft = rgba_from_qcolor(border, round(255 * opacity * 0.6))
    return {
        "border": rgba_from_qcolor(border, round(255 * opacity)),
        "border_soft": soft,
        "border_strong": rgba_from_qcolor(border, round(255 * min(1.0, opacity * 1.6))),
        # Grid lines and rules are borders too. The gaps between panels are not:
        # painting them in the border color doubled every panel's own outline.
        "divider": soft,
    }


BORDER_SOURCE_KEY = "appearance_border_source"
BORDER_COLOR_KEY = "panel_border_color"
BORDER_OPACITY_KEY = "last_border_opacity"
DEFAULT_BORDER_OPACITY = 80


def _appearance_settings(settings):
    if settings is not None:
        return settings
    from PyQt6.QtCore import QSettings

    return QSettings("kimhyojin", "Dark Calendar")


def resolve_border_color(settings, panel_base_color: str, theme_color: str) -> str:
    """The chosen border color, or the recommendation for this background and accent."""
    cfg = _appearance_settings(settings)
    if str(cfg.value(BORDER_SOURCE_KEY, "") or "").lower() == "custom":
        custom = QColor(str(cfg.value(BORDER_COLOR_KEY, "") or ""))
        if custom.isValid():
            return custom.name(QColor.NameFormat.HexRgb)
    return recommend_border_color(
        parse_hex_color(panel_base_color, "#1c1c1c").name(),
        parse_hex_color(theme_color, "#4da6ff").name(),
    )


def resolve_border_tokens(settings, panel_base_color: str, theme_color: str) -> dict[str, str]:
    """Border tokens for a user-chosen border; empty keeps the neutral defaults."""
    cfg = _appearance_settings(settings)
    if str(cfg.value(BORDER_SOURCE_KEY, "") or "").lower() not in {"auto", "custom"}:
        return {}
    try:
        opacity = int(cfg.value(BORDER_OPACITY_KEY, DEFAULT_BORDER_OPACITY))
    except (TypeError, ValueError):
        opacity = DEFAULT_BORDER_OPACITY
    color = resolve_border_color(cfg, panel_base_color, theme_color)
    return border_tokens_for(color, max(0, min(255, opacity)) / 255.0)


TEXT_OPACITY_KEY = "text_opacity"


def resolve_text_opacity(settings) -> int:
    """Readability's text opacity as a byte; text is never fainter than 30%."""
    cfg = _appearance_settings(settings)
    try:
        value = int(cfg.value(TEXT_OPACITY_KEY, 255))
    except (TypeError, ValueError):
        value = 255
    return max(MIN_TEXT_OPACITY, min(255, value))


def derive_text_palette(
    text_theme: str = "dark",
    theme_color: str = "#4da6ff",
    settings=None,
    *,
    background: str | None = None,
    faded: bool = True,
) -> dict:
    """Return shared text color tokens for the active text theme.

    The custom theme reads its colors from ``settings`` when given, so a caller
    that resolves a snapshot from one settings store is not affected by another
    (for example the user's real settings while a test or preview uses its own).

    Text opacity from Readability applies here, so every caller shows the same
    text. ``faded=False`` returns the colors as chosen: use it when a color is
    read in order to be edited or saved, or the fading would be stored twice.
    """
    palette = _chosen_text_palette(text_theme, theme_color, settings)
    if not faded:
        return palette
    opacity = resolve_text_opacity(settings)
    if opacity >= 255:
        return palette
    if not background:
        from calendar_app.shared.system_theme import resolve_effective_appearance

        cfg = _appearance_settings(settings)
        _theme, background, _accent = resolve_effective_appearance(
            cfg,
            text_theme=str(text_theme),
            panel_base_color=str(cfg.value("panel_base_color", "#1c1c1c") or "#1c1c1c"),
            theme_color=str(theme_color),
        )
    factor = opacity / 255.0
    return {
        key: faded_text_color(value, background, factor) if key in TEXT_OPACITY_KEYS else value
        for key, value in palette.items()
    }


def _chosen_text_palette(text_theme: str, theme_color: str, settings) -> dict:

    is_light = text_theme == "light"

    accent = parse_hex_color(theme_color, "#4da6ff")

    if text_theme == "custom":
        try:
            from PyQt6.QtCore import QSettings

            s = settings if settings is not None else QSettings("kimhyojin", "Dark Calendar")

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
        primary = "#20283a"

        # Reading colors stay opaque in light mode. Alpha-based text changes
        # contrast with the user's wallpaper whenever a panel is translucent.
        secondary = "#5e687c"

        muted = "#6b7487"

        faint = "#778094"

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


def derive_state_palette(text_theme: str = "dark") -> dict[str, str]:
    """Use readable state text on light cards and their tinted badge surfaces."""
    if text_theme == "light":
        return {"success": "#14532d", "warning": "#713f12", "danger": "#881337"}
    return {"success": "#35b66a", "warning": "#d39a2a", "danger": "#d25a66"}


def derive_modal_state_palette(theme_color: str, surface_bg: str) -> dict[str, str]:
    """Keep modal status/action colors in the accent family with readable tints."""
    source = parse_hex_color(theme_color, "#4da6ff")
    surface = parse_css_color(surface_bg)
    black, white = QColor("#000000"), QColor("#ffffff")
    target = black if contrast_ratio(black, surface) >= contrast_ratio(white, surface) else white
    role = target
    for step in range(101):
        ratio = step / 100
        candidate = QColor(
            *(
                round(a * (1 - ratio) + b * ratio)
                for a, b in zip(source.getRgb()[:3], target.getRgb()[:3], strict=True)
            )
        )
        badge = composite_color(hex_to_rgba(candidate.name(), 0.32), surface)
        if contrast_ratio(candidate, surface) >= 4.5 and contrast_ratio(candidate, badge) >= 4.5:
            role = candidate
            break
    value = role.name(QColor.NameFormat.HexRgb)
    return {"success": value, "warning": value, "danger": value}


def derive_ui_palette(
    text_theme: str = "dark",
    panel_base_color: str = "#1c1c1c",
    opacity_factor: float = 1.0,
    theme_color: str = "#4da6ff",
    settings=None,
) -> dict:
    """

    Text theme changes only text colors; background tokens come from panel base color.

    """

    f = max(0.0, min(1.0, opacity_factor))

    def _fa(offset: int = 0) -> int:
        return max(0, min(255, int(f * 255) + offset))

    panel_pal = derive_panel_palette(panel_base_color, f)

    base = parse_hex_color(panel_base_color, "#1c1c1c")

    text_pal = derive_text_palette(text_theme, theme_color, settings, background=panel_base_color)

    text_primary = text_pal["text_primary"]

    text_secondary = text_pal["text_secondary"]

    text_placeholder = text_pal["text_faint"]

    is_light = text_theme == "light" or (text_theme != "dark" and base.lightnessF() >= 0.58)
    neutral_rgb = "0,0,0" if is_light else "255,255,255"

    palette = {
        "bg_primary": panel_pal["surface_bg"],
        "bg_secondary": panel_pal["toolbar_bg"],
        "bg_hover": panel_pal["surface_hover_bg"],
        "content_bg": panel_pal["content_bg"],
        "floating_bg": panel_pal["floating_bg"],
        "text_primary": text_primary,
        "text_secondary": text_secondary,
        "text_muted": text_pal["text_muted"],
        "text_faint": text_pal["text_faint"],
        "text_inverse": text_pal["text_inverse"],
        "text_accent": text_pal["text_accent"],
        "text_accent_soft": text_pal["text_accent_soft"],
        "text_placeholder": text_placeholder,
        "border": "#cbd3e1" if is_light else f"rgba({neutral_rgb},0.16)",
        "border_soft": "#dde2ed" if is_light else f"rgba({neutral_rgb},0.10)",
        "border_strong": "#a4b0c4" if is_light else f"rgba({neutral_rgb},0.28)",
        "divider": "#dde2ed" if is_light else "rgba(255,255,255,0.08)",
        # The gap between panels shares the panels' surface. A near-transparent gap
        # on the translucent window let the desktop show through as a bright line.
        "separator_bg": "#dde2ed" if is_light else panel_pal["surface_bg"],
        "control_bg": rgba_from_qcolor(QColor("#ffffff"), _fa())
        if is_light
        else f"rgba({neutral_rgb},0.05)",
        "control_bg_hover": panel_pal["item_hover_bg"] if is_light else f"rgba({neutral_rgb},0.10)",
        "control_bg_pressed": panel_pal["surface_hover_bg"]
        if is_light
        else f"rgba({neutral_rgb},0.04)",
        "selection_bg": rgba_from_qcolor(
            composite_color(hex_to_rgba(theme_color, 0.13), "#ffffff"), _fa()
        )
        if is_light
        else panel_pal["toolbar_bg"],
        "cell_bg": rgba_from_qcolor(base, 0),
        "cell_other_bg": rgba_from_qcolor(base, 0),
        "cell_hover_bg": rgba_from_qcolor(base, 0),
        "task_btn_bg": panel_pal["item_bg"],
        "task_btn_hover": panel_pal["item_hover_bg"],
        "task_btn_text": text_primary,
        "scrollbar_handle": "#778094" if is_light else f"rgba({neutral_rgb},0.15)",
        "weekday_label": text_secondary,
        "weekday_sat": "#386ec4" if is_light else "#8ab7ff",
        "weekday_sun": "#ba4961" if is_light else "#ff9ea8",
        "weekday_other": text_pal["text_faint"],
        "weekday_normal": text_secondary,
        "tooltip_bg": panel_pal["toolbar_bg"],
        "tooltip_text": text_primary,
    }
    # Every caller, snapshot or not, gets the user's border; there is one source.
    palette.update(resolve_border_tokens(settings, panel_base_color, theme_color))
    return palette


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

    def _mix(target: QColor, ratio: float) -> QColor:
        amount = max(0.0, min(1.0, float(ratio)))
        return QColor(
            round(base.red() * (1.0 - amount) + target.red() * amount),
            round(base.green() * (1.0 - amount) + target.green() * amount),
            round(base.blue() * (1.0 - amount) + target.blue() * amount),
        )

    # Light mode needs an actual surface ladder. Alpha-only differentiation
    # collapses at full opacity and is unpredictable over desktop wallpaper.
    if base.lightnessF() >= 0.58:
        white = QColor("#ffffff")
        ink = QColor("#20283a")
        surface = base
        surface_hover = _mix(ink, 0.045)
        toolbar = _mix(white, 0.66)
        topbar = _mix(white, 0.18)
        item = white
        item_hover = _mix(white, 0.45)
        content = white
        floating = white
    else:
        white = QColor("#ffffff")
        surface = base
        surface_hover = _mix(white, 0.035)
        toolbar = _mix(white, 0.04)
        topbar = _mix(white, 0.025)
        item = _mix(white, 0.055)
        item_hover = _mix(white, 0.10)
        content = surface
        floating = toolbar

    return {
        "surface_bg": rgba_from_qcolor(surface, _a(-30)),
        "surface_hover_bg": rgba_from_qcolor(surface_hover, _a(-10)),
        "toolbar_bg": rgba_from_qcolor(toolbar, _a(-20)),
        # Same see-through as the panels: the top bar and quick navigation used a
        # deeper offset and read as a different, more transparent material.
        "topbar_bg": rgba_from_qcolor(topbar, _a(-30)),
        "item_bg": rgba_from_qcolor(item, _a(-5)),
        "item_hover_bg": rgba_from_qcolor(item_hover, _a(0)),
        # Reading and floating surfaces need stable contrast even when the
        # decorative shell is intentionally translucent.
        "content_bg": rgba_from_qcolor(content, max(_a(-30), 220)),
        "floating_bg": rgba_from_qcolor(floating, max(_a(-20), 248)),
    }
