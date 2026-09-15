# -*- coding: utf-8 -*-
"""Independent foreground/background alpha for the widget and its live preview."""

import re

from calendar_app.presentation.widgets.panel_widget_style import css_to_qcolor, rgba

TEXT_OPACITY_KEY = "widget_mode_text_opacity"
BACKGROUND_OPACITY_KEY = "widget_mode_background_opacity"


def read_widget_opacities(settings) -> tuple[int, int]:
    def percent(key, default, minimum):
        try:
            return max(minimum, min(100, int(settings.value(key, default))))
        except (TypeError, ValueError, OverflowError):
            return default

    # The former whole-window control becomes background-only; text stays readable.
    legacy = percent("widget_mode_opacity", 100, 0)
    return percent(TEXT_OPACITY_KEY, 100, 20), percent(BACKGROUND_OPACITY_KEY, legacy, 0)


_DECLARATION = re.compile(
    r"(?P<prefix>(?:^|[;{])\s*)(?P<property>color|background(?:-color)?|border(?:-[a-z]+)*)"
    r"\s*:(?P<value>[^;{}]+)(?=;)",
    re.MULTILINE,
)
_COLOR = re.compile(r"rgba\([^)]*\)|\#[0-9a-fA-F]{3,8}\b", re.IGNORECASE)


def apply_widget_opacity(stylesheet: str, text: int, background: int) -> str:
    """Transform paint declarations only, preserving hex icon tokens and font values."""

    def declaration(match):
        prop = match["property"]
        factor = (text if prop == "color" else background) / 100

        def color(match):
            value = css_to_qcolor(match[0])
            return rgba(value, round(value.alpha() * factor))

        value = _COLOR.sub(color, match["value"])
        # Do not consume the trailing separator: the next declaration needs it.
        return f"{match['prefix']}{prop}:{value}"

    return _DECLARATION.sub(declaration, stylesheet)
