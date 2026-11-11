# -*- coding: utf-8 -*-
"""Widget-workspace aliases for the main window's effective theme roles."""

from PyQt6.QtGui import QColor

from calendar_app.shared.color_utils import (
    composite_color,
    contrast_ratio,
    contrasting_text_color,
    hex_to_rgba,
    parse_css_color,
)
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens

# The widget floats over arbitrary wallpaper, so its shell keeps a high floor of
# opacity and every reading color is checked against the worst backdrop.
WIDGET_SHELL_MIN_ALPHA = 242
WIDGET_TEXT_MIN_CONTRAST = {
    "text_primary": 7.0,
    "card_text_primary": 7.0,
    "calendar_text": 7.0,
    "text_secondary": 5.5,
    "card_text_secondary": 5.5,
    "button_text": 5.5,
    "text_muted": 4.5,
    "calendar_muted": 4.5,
    "text_faint": 4.5,
}
_SHELL_KEYS = (
    "panel_bg_start",
    "panel_bg_mid",
    "panel_bg_end",
    "panel_bg",
    "surface_bg",
    "header_bg",
    "header_shell_bg",
    "shell_gradient_start",
    "shell_gradient_mid",
    "shell_gradient_end",
)


def main_widget_mode_tokens(settings=None) -> dict[str, str]:
    """Reuse main colors/alpha; retain the workspace's established geometry keys."""
    snapshot = build_theme_snapshot(settings, persist_opacity=False)
    ui = get_ui_tokens(settings, snapshot=snapshot)
    palette = snapshot.ui_palette
    tokens = dict(ui)
    # Workspace cards have their own compact shape; registered skin overrides
    # remain independent of the main calendar's deliberately square panels.
    surface, item, toolbar, switch, menu, menu_item = 10, 8, 8, 8, 10, 8
    geometry = {
        "launcher_radius": surface,
        "launcher_button_radius": item,
        "widget_surface_radius": surface,
        "widget_header_radius": max(0, surface - 2),
        "widget_control_radius": toolbar,
        "widget_entry_radius": item,
        "widget_secondary_radius": toolbar,
        "widget_input_radius": item,
        "widget_submit_radius": toolbar,
        "widget_chip_radius": switch,
        "widget_summary_radius": item,
        "widget_menu_radius": menu,
        "widget_menu_item_radius": menu_item,
        "widget_calendar_nav_radius": toolbar,
        "widget_calendar_cell_radius": min(8, max(item, toolbar)),
        "widget_calendar_today_radius": min(8, max(item, toolbar)),
    }
    tokens.update({key: str(value) for key, value in geometry.items()})
    aliases = {
        "calendar_text": "text_primary",
        "calendar_muted": "text_muted",
        "card_text_primary": "text_primary",
        "card_text_secondary": "text_secondary",
        "accent_deep": "accent",
        "accent_strong": "accent",
        "pastel_accent": "accent",
        "panel_bg_start": "bg_main",
        "panel_bg_mid": "bg_main",
        "panel_bg_end": "bg_main",
        "panel_bg": "bg_main",
        "surface_bg": "bg_main",
        "surface_alt": "bg_alt",
        "header_bg": "bg_top",
        "header_shell_bg": "bg_top",
        "panel_border": "border",
        "panel_border_soft": "border_soft",
        "header_shell_border": "border_soft",
        "shell_outline": "border",
        "shell_outline_soft": "border_soft",
        "section_bg": "content_bg",
        "section_bg_alt": "bg_hover",
        "section_border": "border",
        "section_border_soft": "border_soft",
        "card_bg": "bg_item",
        "card_hover": "bg_item_hover",
        "card_pressed": "bg_hover",
        "card_border": "border_soft",
        "card_accent": "accent_border",
        "chip_bg": "bg_alt",
        "chip_border": "border_soft",
        "input_bg": "input_bg",
        "input_border": "input_border",
        "button_text": "text_secondary",
        "button_primary_bg": "accent",
        "button_primary_border": "accent",
        "button_primary_hover_bg": "accent_hover",
        "button_primary_hover_border": "accent",
        "hero_bg": "accent_soft",
        "hero_bg_strong": "accent_soft",
        "hero_border": "accent_border",
        "shell_gradient_start": "bg_main",
        "shell_gradient_mid": "bg_main",
        "shell_gradient_end": "bg_main",
        "scroll_track": "bg_alt",
    }
    tokens.update({target: ui[source] for target, source in aliases.items()})
    tokens.update(
        button_bg=palette["control_bg"],
        button_hover=palette["control_bg_hover"],
        accent_mid=ui["accent_border"],
        button_primary_text=contrasting_text_color(ui["accent"]),
        button_primary_hover_text=contrasting_text_color(ui["accent_hover"]),
        button_danger_bg=hex_to_rgba(ui["danger"], 0.14),
        button_danger_text=ui["danger"],
        button_danger_border=hex_to_rgba(ui["danger"], 0.42),
        button_danger_hover_bg=hex_to_rgba(ui["danger"], 0.22),
        button_danger_hover_border=ui["danger"],
        scroll_thumb=palette["scrollbar_handle"],
        scroll_thumb_hover=ui["accent"],
        hero_bg=palette["selection_bg"],
        hero_bg_strong=palette["selection_bg"],
        calendar_weekday_sat=palette["weekday_sat"],
        calendar_weekday_sun=palette["weekday_sun"],
        grip_color=ui["border"],
        _main_theme_linked="true",
        _main_base_color=snapshot.panel_base_color,
        _main_text_theme=snapshot.text_theme,
        _main_opacity=str(snapshot.opacity_factor),
    )
    return harden_widget_readability(tokens, snapshot.panel_base_color)


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        *(
            round(a * (1.0 - amount) + b * amount)
            for a, b in zip(first.getRgb()[:3], second.getRgb()[:3], strict=True)
        )
    )


def _hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def _readable(
    color: str | QColor, backgrounds: list[QColor], minimum: float, toward: QColor
) -> str:
    """Move a color toward ``toward`` until it reads on every background, keeping its hue."""
    source = composite_color(color, backgrounds[0])
    for step in range(0, 101, 2):
        candidate = _mix(source, toward, step / 100.0)
        if min(contrast_ratio(candidate, bg) for bg in backgrounds) >= minimum:
            return _hex(candidate)
    return _hex(toward)


def harden_widget_readability(tokens: dict[str, str], base_color: str) -> dict[str, str]:
    """Make widget-only mode legible on any wallpaper and at any main-window opacity.

    The main window may be deliberately translucent and may fade its text. A
    floating widget has no panel behind it, so it gets a near-opaque shell, an
    opaque surface ladder derived from the same base color, and text roles that
    meet WCAG contrast against the worst-case backdrop.
    """
    hardened = dict(tokens)
    base = composite_color(parse_css_color(base_color, "#1c1c1c"), QColor("#808080"))
    dark = base.lightnessF() < 0.5
    white, black = QColor("#ffffff"), QColor("#000000")
    ink = white if dark else QColor("#141a26")
    accent = composite_color(tokens.get("accent", "#4da6ff"), base)

    def lift(amount: float) -> QColor:
        # Dark themes rise toward white; light themes deepen toward ink.
        return _mix(base, white, amount) if dark else _mix(base, ink, amount)

    shell_alpha = WIDGET_SHELL_MIN_ALPHA
    for key in _SHELL_KEYS:
        current = parse_css_color(tokens.get(key, ""), _hex(base))
        hardened[key] = (
            f"rgba({current.red()}, {current.green()}, {current.blue()}, "
            f"{max(shell_alpha, current.alpha())})"
        )
    # A faint diagonal tint gives the flat shell depth without hurting contrast.
    hardened["panel_bg_start"] = f"rgba({_rgb(_mix(base, accent, 0.06))}, {shell_alpha + 4})"
    hardened["panel_bg_end"] = (
        f"rgba({_rgb(_mix(base, black if dark else white, 0.10))}, {shell_alpha + 4})"
    )

    card = lift(0.06) if dark else _mix(base, white, 0.72)
    alt = lift(0.04) if dark else _mix(base, white, 0.45)
    button = lift(0.09) if dark else _mix(base, white, 0.60)
    button_hover = lift(0.15) if dark else lift(0.07)
    chip = _mix(base, accent, 0.26 if dark else 0.16)
    border = lift(0.16 if dark else 0.14)
    border_strong = lift(0.24 if dark else 0.22)
    hardened.update(
        section_bg=_hex(card),
        card_bg=_hex(card),
        surface_alt=_hex(alt),
        section_bg_alt=_hex(button_hover),
        card_hover=_hex(button_hover),
        card_pressed=_hex(lift(0.18) if dark else lift(0.10)),
        button_bg=_hex(button),
        button_hover=_hex(button_hover),
        chip_bg=_hex(chip),
        chip_border=_hex(_mix(chip, accent, 0.65)),
        # Selected day tile and emphasis panels: a visible accent tint on the
        # opaque shell (alpha-only tints vanished once the shell became opaque).
        hero_bg=_hex(_mix(base, accent, 0.12 if dark else 0.08)),
        hero_bg_strong=_hex(_mix(base, accent, 0.22 if dark else 0.14)),
        hero_border=_hex(_mix(base, accent, 0.70)),
        input_bg=_hex(card),
        card_border=_hex(border),
        section_border=_hex(border_strong),
        section_border_soft=_hex(border),
        panel_border=_hex(border_strong),
        panel_border_soft=_hex(border),
        header_shell_border=_hex(border),
        shell_outline=_hex(border_strong),
        shell_outline_soft=_hex(border),
        scroll_track="transparent",
        scroll_thumb=_hex(lift(0.30)),
        scroll_thumb_hover=_hex(accent),
    )

    # Worst case: the near-opaque shell over a black or a white wallpaper.
    shell = parse_css_color(hardened["panel_bg"], _hex(base))
    backdrops = [composite_color(shell, black), composite_color(shell, white)]
    text_surfaces = backdrops + [card, alt, button]
    for key, minimum in WIDGET_TEXT_MIN_CONTRAST.items():
        if key in hardened:
            hardened[key] = _readable(hardened[key], text_surfaces, minimum, ink)
    # Accent-colored text sits on the shell and on the selected-chip tint.
    accent_text = _readable(accent, backdrops + [chip, card], 4.5, ink)
    hardened["accent_deep"] = accent_text
    hardened["pastel_accent"] = accent_text
    for key in ("calendar_weekday_sat", "calendar_weekday_sun"):
        if key in hardened:
            hardened[key] = _readable(hardened[key], backdrops + [card], 4.5, ink)
    primary_bg = parse_css_color(hardened.get("button_primary_bg", _hex(accent)), _hex(accent))
    hardened["button_primary_text"] = contrasting_text_color(primary_bg, surface=base)
    hover_bg = parse_css_color(hardened.get("button_primary_hover_bg", _hex(accent)), _hex(accent))
    hardened["button_primary_hover_text"] = contrasting_text_color(hover_bg, surface=base)
    return hardened


def _rgb(color: QColor) -> str:
    return f"{color.red()}, {color.green()}, {color.blue()}"
