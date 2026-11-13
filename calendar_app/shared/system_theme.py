# -*- coding: utf-8 -*-
"""Resolve the effective appearance for the operating-system color scheme."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

_runtime_system_text_theme: str | None = None


def color_scheme_text_theme(color_scheme) -> str | None:
    if color_scheme == Qt.ColorScheme.Dark:
        return "dark"
    if color_scheme == Qt.ColorScheme.Light:
        return "light"
    return None


def set_runtime_system_text_theme(text_theme: str | None) -> str | None:
    global _runtime_system_text_theme
    normalized = str(text_theme or "").strip().lower()
    _runtime_system_text_theme = normalized if normalized in {"dark", "light"} else None
    return _runtime_system_text_theme


def resolve_system_text_theme() -> str:
    if _runtime_system_text_theme in {"dark", "light"}:
        return _runtime_system_text_theme

    app = QApplication.instance()
    if app is None:
        return "dark"
    style_hints = app.styleHints()
    if hasattr(style_hints, "colorScheme"):
        resolved = color_scheme_text_theme(style_hints.colorScheme())
        if resolved is not None:
            return resolved

    base_color = app.palette().color(QPalette.ColorRole.Window)
    return "dark" if base_color.lightness() < 128 else "light"


def _valid_hex(value) -> str | None:
    color = QColor(str(value or ""))
    if not color.isValid():
        return None
    return color.name(QColor.NameFormat.HexRgb)


def resolve_mode_base_color(base: str, mode: str) -> str:
    """Adapt legacy unpaired colors at render time without replacing user data."""
    color = QColor(base)
    hue, saturation, lightness, _alpha = color.getHslF()
    if mode == "light" and lightness < 0.80:
        if saturation < 0.08:
            return "#f6f7fb"
        return QColor.fromHslF(max(0.0, hue), min(0.22, saturation * 0.35), 0.965).name(
            QColor.NameFormat.HexRgb
        )
    if mode == "dark" and lightness > 0.45:
        if saturation < 0.08:
            return "#1c1c1c"
        return QColor.fromHslF(max(0.0, hue), min(0.40, saturation), 0.12).name(
            QColor.NameFormat.HexRgb
        )
    return base


def resolve_effective_appearance(
    settings,
    *,
    text_theme: str,
    panel_base_color: str,
    theme_color: str,
    allow_family_base: bool = True,
    allow_family_accent: bool = True,
) -> tuple[str, str, str]:
    """Return effective text theme, panel base, and accent without persisting values."""
    requested = str(text_theme or "dark").strip().lower()
    base = _valid_hex(panel_base_color) or "#1c1c1c"
    accent = _valid_hex(theme_color) or "#4da6ff"
    if requested not in {"auto", "light", "dark"}:
        return requested, base, accent

    resolved = resolve_system_text_theme() if requested == "auto" else requested
    family = str(settings.value("appearance_style_family", "") or "").strip()
    base_source = str(settings.value("appearance_base_source", "family") or "family").lower()
    if allow_family_base:
        family_base = (
            _valid_hex(settings.value(f"appearance_family_{resolved}_base", ""))
            if family and base_source == "family"
            else None
        )
        base = family_base if family_base is not None else resolve_mode_base_color(base, resolved)

    accent_source = (
        str(settings.value("appearance_accent_source", "custom") or "custom").strip().lower()
    )
    if family and accent_source == "family" and allow_family_accent:
        family_accent = _valid_hex(settings.value(f"appearance_family_{resolved}_accent", ""))
        if family_accent is not None:
            accent = family_accent
    return resolved, base, accent
