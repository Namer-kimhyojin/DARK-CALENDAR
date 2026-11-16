# -*- coding: utf-8 -*-
"""Keep the main window's text readable over whatever wallpaper is behind it.

Light text on a translucent dark panel washes out over a bright wallpaper (and
dark text over a dark one). The window checks the wallpaper of the screen it is
on and, when needed, raises the panel opacity just enough for text to keep a
4.5:1 contrast. The user's saved opacity is not changed.

The whole screen's wallpaper is measured, not just the part behind the window:
measuring under the window made the panels change opacity every time the window
was moved or resized, which read as flicker. The floor now changes only with
the wallpaper, the theme or the screen.
"""

from __future__ import annotations

import logging
import math

from PyQt6.QtCore import QTimer

from calendar_app.shared.color_utils import (
    contrast_ratio,
    panel_opacity_floor_for_backdrop,
    parse_css_color,
)
from calendar_app.shared.theme_settings import (
    set_wallpaper_opacity_floor,
    wallpaper_opacity_floor,
)

logger = logging.getLogger(__name__)

ADAPTIVE_WALLPAPER_KEY = "adaptive_wallpaper_contrast"
_POLL_MS = 15000
_MOVE_DEBOUNCE_MS = 700
# Small floor changes are not worth a full theme pass.
_FLOOR_STEP = 0.02


def adaptive_wallpaper_enabled(settings) -> bool:
    """Off unless chosen in Appearance > Readability; the panels then stay as set."""
    try:
        value = settings.value(ADAPTIVE_WALLPAPER_KEY, False)
    except Exception:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def install_wallpaper_contrast(window) -> None:
    """Start watching the wallpaper for ``window`` (the main OverlayApp)."""
    if getattr(window, "_wallpaper_contrast_timer", None) is not None:
        return
    from PyQt6.QtGui import QGuiApplication

    # Offscreen windows (tests, thumbnails) have no desktop behind them.
    if QGuiApplication.platformName() == "offscreen":
        return
    poll = QTimer(window)
    poll.setInterval(_POLL_MS)
    poll.timeout.connect(lambda: refresh_wallpaper_contrast(window))
    window._wallpaper_contrast_timer = poll
    debounce = QTimer(window)
    debounce.setSingleShot(True)
    debounce.setInterval(_MOVE_DEBOUNCE_MS)
    debounce.timeout.connect(lambda: refresh_wallpaper_contrast(window))
    window._wallpaper_contrast_debounce = debounce
    poll.start()
    QTimer.singleShot(0, lambda: refresh_wallpaper_contrast(window))


def schedule_wallpaper_contrast_refresh(window) -> None:
    """Check again shortly after the window moved; only a new screen changes it."""
    debounce = getattr(window, "_wallpaper_contrast_debounce", None)
    if debounce is not None:
        debounce.start()


def _window_and_screen(window):
    handle = window.windowHandle()
    screen = handle.screen() if handle is not None else None
    if screen is None:
        screen = window.screen()
    if screen is None:
        return None, None
    return window.frameGeometry(), screen.geometry()


def compute_wallpaper_floor(settings, window_rect, screen_rect, wallpaper=None) -> float:
    """The panel opacity floor for this window position and theme (0.0 = none)."""
    from calendar_app.infrastructure.runtime.wallpaper_backdrop import (
        current_wallpaper,
        sample_backdrop,
    )
    from calendar_app.shared.theme_snapshot import build_theme_snapshot

    info = wallpaper if wallpaper is not None else current_wallpaper()
    if info is None:
        return 0.0
    snapshot = build_theme_snapshot(settings, persist_opacity=False)
    base = snapshot.panel_base_color
    text = str(snapshot.text_palette.get("text_secondary", "#c5cfda"))
    text_color = parse_css_color(text, "#ffffff")
    # Light text needs the bright end of the wallpaper; dark text the dark end.
    light_text = contrast_ratio(text_color, "#000000") > contrast_ratio(text_color, "#ffffff")
    backdrop = sample_backdrop(info, window_rect, screen_rect, brightest=light_text)
    if backdrop is None:
        return 0.0
    floor = panel_opacity_floor_for_backdrop(base, text, backdrop)
    return math.ceil(floor / _FLOOR_STEP) * _FLOOR_STEP if floor > 0 else 0.0


def refresh_wallpaper_contrast(window) -> bool:
    """Recompute the floor; reapply the theme when the visible opacity changes."""
    if getattr(window, "_is_shutting_down", False):
        return False
    settings = getattr(window, "settings", None)
    if settings is None:
        return False
    floor = 0.0
    if adaptive_wallpaper_enabled(settings):
        window_rect, screen_rect = _window_and_screen(window)
        if window_rect is not None:
            try:
                from calendar_app.infrastructure.runtime.wallpaper_backdrop import (
                    current_wallpaper,
                )

                info = current_wallpaper()
                # The 15 s poll is nearly free while nothing it depends on changed.
                key = (
                    info.signature if info is not None else None,
                    screen_rect.getRect(),
                    tuple(window._theme_signature_bits())
                    if hasattr(window, "_theme_signature_bits")
                    else None,
                )
                if key == getattr(window, "_wallpaper_contrast_key", None):
                    return False
                window._wallpaper_contrast_key = key
                floor = (
                    # The whole screen, so moving or resizing the window on the
                    # same screen never changes the panels' opacity.
                    compute_wallpaper_floor(settings, screen_rect, screen_rect, info)
                    if info is not None
                    else 0.0
                )
            except Exception:
                logger.debug("Wallpaper contrast check failed", exc_info=True)
                floor = wallpaper_opacity_floor()
    from calendar_app.shared.theme_settings import get_opacity_byte

    saved = get_opacity_byte(settings) / 255.0
    before = max(saved, wallpaper_opacity_floor())
    if not set_wallpaper_opacity_floor(floor):
        return False
    if abs(max(saved, floor) - before) < 1e-6:
        return False
    if getattr(window, "_ui_fully_initialized", False) and hasattr(window, "apply_theme_settings"):
        window.apply_theme_settings(persist_opacity=False)
    return True
