# -*- coding: utf-8 -*-
"""Unified theme snapshot and semantic token builders."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor

from calendar_app.shared.color_utils import (
    derive_panel_palette,
    derive_text_palette,
    derive_ui_palette,
    hex_to_rgba,
    parse_css_alpha_to_unit,
    parse_hex_color,
    shift_rgb,
)
from calendar_app.shared.system_theme import resolve_effective_appearance
from calendar_app.shared.theme_settings import get_opacity_factor

_RGBA_COLOR_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)


def _resolve_settings(settings=None):
    return settings if settings is not None else QSettings("kimhyojin", "Dark Calendar")


@dataclass(frozen=True)
class ThemeSnapshot:
    theme_color: str
    text_theme: str
    panel_base_color: str
    opacity_factor: float
    input_bg: str
    accent_color: QColor
    text_palette: dict[str, str]
    panel_palette: dict[str, str]
    ui_palette: dict[str, str]
    shape_preset: str
    shape_tokens: dict[str, int]
    dialog_metrics: dict[str, int]


UI_SHAPE_PRESETS: dict[str, dict[str, int]] = {
    "modern": {
        "panel_item_radius": 10,
        "panel_surface_radius": 14,
        "panel_toolbar_radius": 10,
        "panel_toolbar_button_radius": 8,
        "panel_menu_radius": 10,
        "panel_menu_item_radius": 8,
        "panel_group_badge_radius": 6,
        "panel_mode_switch_radius": 12,
        "panel_inline_hover_radius": 8,
        "task_outer_radius": 10,
        "task_title_radius": 10,
        "context_menu_radius": 10,
        "context_menu_item_radius": 6,
        "global_task_button_radius": 12,
        "drag_range_cap_radius": 14,
        "tooltip_radius": 10,
        "top_menu_button_radius": 10,
        "app_menu_radius": 10,
        "app_menu_item_radius": 8,
        "calendar_surface_radius": 14,
        "calendar_toolbar_surface_radius": 12,
        "calendar_toolbar_button_radius": 10,
        "calendar_menu_radius": 10,
        "calendar_menu_item_radius": 8,
        "calendar_date_badge_radius": 14,
        "calendar_selection_badge_radius": 16,
        "calendar_more_button_radius": 6,
    },
    "round": {
        "panel_item_radius": 7,
        "panel_surface_radius": 8,
        "panel_toolbar_radius": 6,
        "panel_toolbar_button_radius": 6,
        "panel_menu_radius": 6,
        "panel_menu_item_radius": 4,
        "panel_group_badge_radius": 4,
        "panel_mode_switch_radius": 7,
        "panel_inline_hover_radius": 5,
        "task_outer_radius": 7,
        "task_title_radius": 7,
        "context_menu_radius": 5,
        "context_menu_item_radius": 3,
        "global_task_button_radius": 7,
        "drag_range_cap_radius": 8,
        "tooltip_radius": 6,
        "top_menu_button_radius": 6,
        "app_menu_radius": 6,
        "app_menu_item_radius": 4,
        "calendar_surface_radius": 8,
        "calendar_toolbar_surface_radius": 8,
        "calendar_toolbar_button_radius": 8,
        "calendar_menu_radius": 6,
        "calendar_menu_item_radius": 4,
        "calendar_date_badge_radius": 9,
        "calendar_selection_badge_radius": 10,
        "calendar_more_button_radius": 4,
    },
    "sharp": {
        "panel_item_radius": 0,
        "panel_surface_radius": 0,
        "panel_toolbar_radius": 0,
        "panel_toolbar_button_radius": 0,
        "panel_menu_radius": 0,
        "panel_menu_item_radius": 0,
        "panel_group_badge_radius": 0,
        "panel_mode_switch_radius": 0,
        "panel_inline_hover_radius": 0,
        "task_outer_radius": 0,
        "task_title_radius": 0,
        "context_menu_radius": 0,
        "context_menu_item_radius": 0,
        "global_task_button_radius": 0,
        "drag_range_cap_radius": 0,
        "tooltip_radius": 0,
        "top_menu_button_radius": 0,
        "app_menu_radius": 0,
        "app_menu_item_radius": 0,
        "calendar_surface_radius": 0,
        "calendar_toolbar_surface_radius": 0,
        "calendar_toolbar_button_radius": 0,
        "calendar_menu_radius": 0,
        "calendar_menu_item_radius": 0,
        "calendar_date_badge_radius": 0,
        "calendar_selection_badge_radius": 0,
        "calendar_more_button_radius": 0,
    },
}

DIALOG_METRIC_DEFAULTS: dict[str, int] = {
    "base_font_pt": 14,
    "title_font_pt": 16,
    "subtitle_font_pt": 12,
    "tab_padding_y": 8,
    "tab_padding_x": 22,
    "tab_min_width": 80,
    "tab_gap": 3,
    "tab_radius": 8,
    "field_height": 34,
    "field_padding_y": 4,
    "field_padding_x": 10,
    "field_radius": 7,
    "textedit_padding_y": 10,
    "textedit_padding_x": 12,
    "textedit_radius": 8,
    "button_height": 24,
    "button_min_width": 45,
    "button_padding_y": 4,
    "button_padding_x": 16,
    "button_radius": 8,
    "toolbutton_height": 28,
    "toolbutton_min_width": 34,
    "toolbutton_padding_y": 4,
    "toolbutton_padding_x": 6,
    "toolbutton_radius": 6,
    "list_item_radius": 5,
    "list_item_margin_bottom": 1,
    "checkbox_spacing": 9,
    "radio_spacing": 9,
    "checkbox_indicator_size": 17,
    "radio_indicator_size": 17,
    "list_radius": 8,
    "list_padding": 4,
    "list_item_padding_y": 9,
    "list_item_padding_x": 10,
    "group_radius": 9,
    "group_margin_top": 18,
}

DIALOG_METRIC_BOUNDS: dict[str, tuple[int, int]] = {
    "base_font_pt": (9, 22),
    "title_font_pt": (11, 28),
    "subtitle_font_pt": (9, 22),
    "tab_padding_y": (2, 20),
    "tab_padding_x": (6, 40),
    "tab_min_width": (48, 220),
    "tab_gap": (0, 20),
    "tab_radius": (0, 18),
    "field_height": (24, 64),
    "field_padding_y": (0, 20),
    "field_padding_x": (4, 32),
    "field_radius": (0, 18),
    "textedit_padding_y": (2, 24),
    "textedit_padding_x": (4, 28),
    "textedit_radius": (0, 18),
    "button_height": (15, 64),
    "button_min_width": (15, 320),
    "button_padding_y": (0, 20),
    "button_padding_x": (6, 36),
    "button_radius": (0, 18),
    "toolbutton_height": (20, 60),
    "toolbutton_min_width": (20, 200),
    "toolbutton_padding_y": (0, 20),
    "toolbutton_padding_x": (2, 24),
    "toolbutton_radius": (0, 18),
    "list_item_radius": (0, 18),
    "list_item_margin_bottom": (0, 16),
    "checkbox_spacing": (2, 24),
    "radio_spacing": (2, 24),
    "checkbox_indicator_size": (10, 32),
    "radio_indicator_size": (10, 32),
    "list_radius": (0, 20),
    "list_padding": (0, 18),
    "list_item_padding_y": (2, 24),
    "list_item_padding_x": (4, 36),
    "group_radius": (0, 18),
    "group_margin_top": (6, 36),
}


def normalize_shape_preset(preset: str | None) -> str:
    raw = str(preset or "sharp").strip().lower()
    if raw == "modern":
        return "modern"
    if raw == "round":
        return "round"
    return "sharp"


def get_shape_preset(settings=None) -> str:
    cfg = _resolve_settings(settings)
    return normalize_shape_preset(cfg.value("ui_shape_preset", "sharp"))


@lru_cache(maxsize=3)
def _build_shape_tokens_cached(preset: str) -> dict[str, int]:
    return dict(UI_SHAPE_PRESETS.get(normalize_shape_preset(preset), UI_SHAPE_PRESETS["sharp"]))


def build_shape_tokens(*, preset: str | None = None, settings=None) -> dict[str, int]:
    resolved_preset = normalize_shape_preset(preset or get_shape_preset(settings))
    return dict(_build_shape_tokens_cached(resolved_preset))


def invalidate_shape_tokens():
    _build_shape_tokens_cached.cache_clear()


def set_shape_preset(preset: str, settings=None) -> str:
    normalized = normalize_shape_preset(preset)
    cfg = _resolve_settings(settings)
    cfg.setValue("ui_shape_preset", normalized)
    invalidate_shape_tokens()
    return normalized


def build_theme_snapshot(
    settings=None,
    *,
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    opacity_factor: float | None = None,
    input_bg: str | None = None,
    persist_opacity: bool = False,
) -> ThemeSnapshot:
    cfg = _resolve_settings(settings)

    requested_theme = str(theme_color or cfg.value("theme_color", "#4da6ff") or "#4da6ff")
    requested_text_theme = str(text_theme or cfg.value("text_theme", "dark") or "dark")
    requested_panel_base = str(
        panel_base_color or cfg.value("panel_base_color", "#1c1c1c") or "#1c1c1c"
    )
    resolved_text_theme, resolved_panel_base, resolved_theme = resolve_effective_appearance(
        cfg,
        text_theme=requested_text_theme,
        panel_base_color=requested_panel_base,
        theme_color=requested_theme,
        allow_family_base=panel_base_color is None,
        allow_family_accent=theme_color is None,
    )

    if opacity_factor is None:
        resolved_opacity = get_opacity_factor(cfg, persist_normalized=persist_opacity)
    else:
        try:
            resolved_opacity = float(opacity_factor)
        except Exception:
            resolved_opacity = get_opacity_factor(cfg, persist_normalized=persist_opacity)
    resolved_opacity = max(0.0, min(1.0, resolved_opacity))

    accent_color = parse_hex_color(resolved_theme, "#4da6ff")
    accent_hex = accent_color.name(QColor.NameFormat.HexRgb)
    text_palette = derive_text_palette(resolved_text_theme, accent_hex)
    panel_palette = derive_panel_palette(resolved_panel_base, resolved_opacity)
    ui_palette = derive_ui_palette(
        resolved_text_theme,
        resolved_panel_base,
        resolved_opacity,
        accent_hex,
    )

    default_input_bg = panel_palette.get("item_bg", "rgba(0, 0, 0, 0.2)")
    resolved_input_bg = str(
        input_bg
        if input_bg is not None
        else cfg.value("custom_input_bg", default_input_bg) or default_input_bg
    )

    return ThemeSnapshot(
        theme_color=accent_hex,
        text_theme=resolved_text_theme,
        panel_base_color=resolved_panel_base,
        opacity_factor=resolved_opacity,
        input_bg=resolved_input_bg,
        accent_color=accent_color,
        text_palette=text_palette,
        panel_palette=panel_palette,
        ui_palette=ui_palette,
        shape_preset=get_shape_preset(cfg),
        shape_tokens=build_shape_tokens(settings=cfg),
        dialog_metrics=build_dialog_metric_tokens(settings=cfg, apply_overrides=True),
    )


def build_shared_ui_tokens(
    settings=None,
    *,
    snapshot: ThemeSnapshot | None = None,
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    opacity_factor: float | None = None,
    input_bg: str | None = None,
    persist_opacity: bool = False,
) -> dict[str, str]:
    snapshot = snapshot or build_theme_snapshot(
        settings=settings,
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
        opacity_factor=opacity_factor,
        input_bg=input_bg,
        persist_opacity=persist_opacity,
    )

    accent = snapshot.accent_color
    accent_hex = snapshot.theme_color
    panel_pal = snapshot.panel_palette
    text_pal = snapshot.text_palette
    shape = snapshot.shape_tokens
    metrics = snapshot.dialog_metrics
    success_hex = "#35b66a"
    warning_hex = "#d39a2a"
    danger_hex = "#d25a66"

    return {
        "accent": accent_hex,
        "accent_hover": shift_rgb(accent, 25).name(QColor.NameFormat.HexRgb),
        "accent_soft": hex_to_rgba(accent_hex, 0.15),
        "accent_border": hex_to_rgba(accent_hex, 0.4),
        "text_primary": text_pal["text_primary"],
        "text_secondary": text_pal["text_secondary"],
        "text_muted": text_pal["text_muted"],
        "text_faint": text_pal["text_faint"],
        "text_inverse": text_pal["text_inverse"],
        "bg_main": panel_pal["surface_bg"],
        "bg_alt": panel_pal["toolbar_bg"],
        "bg_hover": panel_pal["surface_hover_bg"],
        "bg_item": panel_pal["item_bg"],
        "bg_item_hover": panel_pal["item_hover_bg"],
        "bg_top": panel_pal["topbar_bg"],
        "success": success_hex,
        "warning": warning_hex,
        "danger": danger_hex,
        # Compatibility aliases: older widgets still read *_hex / *_soft_bg tokens.
        "success_hex": success_hex,
        "warning_hex": warning_hex,
        "danger_hex": danger_hex,
        "success_soft_bg": hex_to_rgba(success_hex, 0.16),
        "warning_soft_bg": hex_to_rgba(warning_hex, 0.16),
        "danger_soft_bg": hex_to_rgba(danger_hex, 0.16),
        "info": accent_hex,
        "info_hex": accent_hex,
        "border": "rgba(255,255,255,0.12)" if snapshot.text_theme == "dark" else "rgba(0,0,0,0.12)",
        "border_strong": "rgba(255,255,255,0.25)"
        if snapshot.text_theme == "dark"
        else "rgba(0,0,0,0.25)",
        "border_soft": "rgba(255,255,255,0.08)"
        if snapshot.text_theme == "dark"
        else "rgba(0,0,0,0.08)",
        "divider": "rgba(255,255,255,0.08)"
        if snapshot.text_theme == "dark"
        else "rgba(0,0,0,0.08)",
        "radius_sm": f"{metrics.get('toolbutton_radius', 6)}px",
        "radius_md": f"{metrics.get('field_radius', 8)}px",
        "radius_lg": f"{shape.get('panel_surface_radius', metrics.get('group_radius', 12))}px",
        "spacing_xs": "4px",
        "spacing_sm": "8px",
        "spacing_md": "16px",
        "spacing_lg": "24px",
        "input_bg": snapshot.input_bg,
        "input_border": "rgba(255, 255, 255, 0.1)",
        "button_height": f"{metrics.get('button_height', 24)}px",
        "button_radius": f"{metrics.get('button_radius', metrics.get('field_radius', 8))}px",
        "button_padding_y": f"{metrics.get('button_padding_y', 4)}px",
        "button_padding_x": f"{metrics.get('button_padding_x', 16)}px",
        "field_height": f"{metrics.get('field_height', 34)}px",
        "field_radius": f"{metrics.get('field_radius', 8)}px",
        "toolbutton_height": f"{metrics.get('toolbutton_height', 28)}px",
        "toolbutton_radius": f"{metrics.get('toolbutton_radius', 6)}px",
        "toolbutton_padding_y": f"{metrics.get('toolbutton_padding_y', 4)}px",
        "toolbutton_padding_x": f"{metrics.get('toolbutton_padding_x', 6)}px",
        "panel_radius": f"{shape.get('panel_surface_radius', 12)}px",
        "panel_item_radius": f"{shape.get('panel_item_radius', 8)}px",
        "toolbar_button_radius": f"{shape.get('panel_toolbar_button_radius', metrics.get('button_radius', 8))}px",
    }


def build_dialog_base_tokens(
    settings=None,
    *,
    snapshot: ThemeSnapshot | None = None,
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    input_bg: str | None = None,
    opacity_factor: float = 1.0,
) -> dict[str, str]:
    snapshot = snapshot or build_theme_snapshot(
        settings=settings,
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
        opacity_factor=opacity_factor,
        input_bg=input_bg,
    )

    accent = snapshot.accent_color
    accent_hex = snapshot.theme_color
    base = parse_hex_color(snapshot.panel_base_color, "#1c1c1c")
    panel_palette = snapshot.panel_palette
    text_palette = snapshot.text_palette

    def _rgba(color: QColor, alpha_0_to_1: float) -> str:
        alpha = max(0.0, min(1.0, float(alpha_0_to_1)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {int(round(alpha * 255))})"

    success = QColor("#35b66a")
    warning = QColor("#d39a2a")
    danger = QColor("#d25a66")

    return {
        "accent": accent_hex,
        "accent_hover": shift_rgb(accent, 22).name(QColor.NameFormat.HexRgb),
        "accent_soft_bg": _rgba(accent, 0.16),
        "accent_soft_border": _rgba(accent, 0.42),
        "title_bg": panel_palette.get("topbar_bg", "#13131a"),
        "title_text": str(text_palette.get("text_primary", "#e1e1e6")),
        "title_subtext": str(text_palette.get("text_muted", "#9aa0ad")),
        "tab_strip_bg": panel_palette.get("topbar_bg", "#13131a"),
        "tab_idle_bg": panel_palette.get("toolbar_bg", "#1c1c23"),
        "tab_active_bg": panel_palette.get("item_bg", "#111116"),
        "tab_text": str(text_palette.get("text_muted", "#9aa0ad")),
        "tab_text_hover": str(text_palette.get("text_secondary", "#d0d0da")),
        "tab_text_active": accent_hex,
        "text_primary": str(text_palette.get("text_primary", "#e1e1e6")),
        "text_secondary": str(text_palette.get("text_secondary", "#c8ccd4")),
        "text_muted": str(text_palette.get("text_muted", "#9aa0ad")),
        "text_faint": str(text_palette.get("text_faint", "#7a7a8a")),
        "surface_bg": panel_palette.get("surface_bg", "#16161b"),
        "surface_alt": panel_palette.get("toolbar_bg", "#1c1c23"),
        "surface_item": panel_palette.get("item_bg", "#1e1e26"),
        "surface_hover": panel_palette.get("surface_hover_bg", "#18181f"),
        "surface_top": panel_palette.get("topbar_bg", "#13131a"),
        "base_hex": base.name(QColor.NameFormat.HexRgb),
        "border_soft": "rgba(255,255,255,0.10)",
        "border": "rgba(255,255,255,0.16)",
        "success_hex": success.name(QColor.NameFormat.HexRgb),
        "success_soft_bg": _rgba(success, 0.16),
        "warning_hex": warning.name(QColor.NameFormat.HexRgb),
        "warning_soft_bg": _rgba(warning, 0.16),
        "danger_hex": danger.name(QColor.NameFormat.HexRgb),
        "danger_soft_bg": _rgba(danger, 0.16),
        "placeholder_text": str(text_palette.get("text_faint", "#7a7a8a")),
        "input_bg": snapshot.input_bg,
        "list_selected_bg": _rgba(accent, 0.12),
        "list_selected_border": _rgba(accent, 0.25),
        "list_selected_text": shift_rgb(accent, 32).name(QColor.NameFormat.HexRgb),
        "list_hover_bg": _rgba(accent, 0.06),
        "table_header_bg": panel_palette.get("toolbar_bg", "#1e1e26"),
        "table_header_text": str(text_palette.get("text_faint", "#7a7a8a")),
        "check_indicator_bg": panel_palette.get("surface_hover_bg", "#18181f"),
        "check_indicator_border": "rgba(255,255,255,0.22)",
        "check_checked_bg": accent_hex,
        "check_checked_border": accent_hex,
        "button_base_bg": panel_palette.get("item_bg", "#1e1e26"),
        "button_base_text": str(text_palette.get("text_secondary", "#c8ccd4")),
        "button_base_border": "rgba(255,255,255,0.16)",
        "button_base_hover_bg": panel_palette.get("surface_hover_bg", "#26262f"),
        "button_base_hover_text": str(text_palette.get("text_primary", "#ffffff")),
        "button_base_hover_border": "rgba(255,255,255,0.26)",
        "button_pressed_bg": panel_palette.get("topbar_bg", "#18181f"),
        "button_pressed_text": str(text_palette.get("text_primary", "#ffffff")),
        "button_pressed_border": "rgba(255,255,255,0.30)",
        "button_disabled_bg": panel_palette.get("toolbar_bg", "#1c1c23"),
        "button_disabled_text": str(text_palette.get("text_faint", "#7a7a8a")),
        "button_disabled_border": "rgba(255,255,255,0.08)",
        "button_primary_bg": _rgba(accent, 0.10),
        "button_primary_text": accent_hex,
        "button_primary_border": _rgba(accent, 0.55),
        "button_primary_hover_bg": _rgba(accent, 0.18),
        "button_primary_hover_text": str(text_palette.get("text_primary", "#ffffff")),
        "button_primary_hover_border": accent_hex,
        "button_secondary_bg": panel_palette.get("surface_hover_bg", "#18181f"),
        "button_secondary_text": str(text_palette.get("text_muted", "#9aa0ad")),
        "button_secondary_border": "rgba(255,255,255,0.12)",
        "button_secondary_hover_bg": panel_palette.get("toolbar_bg", "#22222a"),
        "button_secondary_hover_text": str(text_palette.get("text_primary", "#e0e0e8")),
        "button_secondary_hover_border": "rgba(255,255,255,0.22)",
        "button_ghost_bg": panel_palette.get("surface_bg", "#16161b"),
        "button_ghost_text": str(text_palette.get("text_muted", "#9aa0ad")),
        "button_ghost_border": "rgba(255,255,255,0.12)",
        "button_ghost_hover_bg": panel_palette.get("surface_hover_bg", "#22222a"),
        "button_ghost_hover_text": str(text_palette.get("text_primary", "#e0e0e8")),
        "button_ghost_hover_border": "rgba(255,255,255,0.24)",
        "button_success_bg": _rgba(success, 0.14),
        "button_success_text": success.name(QColor.NameFormat.HexRgb),
        "button_success_border": _rgba(success, 0.42),
        "button_success_hover_bg": _rgba(success, 0.22),
        "button_success_hover_text": str(text_palette.get("text_primary", "#ffffff")),
        "button_success_hover_border": success.name(QColor.NameFormat.HexRgb),
        "button_danger_bg": "transparent",
        "button_danger_text": danger.name(QColor.NameFormat.HexRgb),
        "button_danger_border": _rgba(danger, 0.35),
        "button_danger_hover_bg": _rgba(danger, 0.12),
        "button_danger_hover_text": shift_rgb(danger, 26).name(QColor.NameFormat.HexRgb),
        "button_danger_hover_border": _rgba(danger, 0.65),
        "toolbutton_bg": panel_palette.get("item_bg", "#1e1e26"),
        "toolbutton_text": str(text_palette.get("text_secondary", "#c8ccd4")),
        "toolbutton_border": "rgba(255,255,255,0.16)",
        "toolbutton_hover_bg": panel_palette.get("surface_hover_bg", "#26262f"),
        "toolbutton_hover_text": str(text_palette.get("text_primary", "#ffffff")),
        "toolbutton_hover_border": "rgba(255,255,255,0.26)",
        "toolbutton_pressed_bg": panel_palette.get("topbar_bg", "#18181f"),
        "toolbutton_pressed_text": str(text_palette.get("text_primary", "#ffffff")),
        "toolbutton_pressed_border": "rgba(255,255,255,0.30)",
        "toolbutton_disabled_bg": panel_palette.get("toolbar_bg", "#1c1c23"),
        "toolbutton_disabled_text": str(text_palette.get("text_faint", "#7a7a8a")),
        "toolbutton_disabled_border": "rgba(255,255,255,0.08)",
    }


def _css_to_qcolor(value: object, fallback: str = "#000000") -> QColor:
    raw = str(value or "").strip()
    if raw:
        match = _RGBA_COLOR_RE.match(raw)
        if match:
            try:
                r, g, b, a_raw = match.groups()
                alpha = float(a_raw)
                if alpha <= 1.0:
                    alpha = alpha * 255.0
                return QColor(
                    max(0, min(255, int(r))),
                    max(0, min(255, int(g))),
                    max(0, min(255, int(b))),
                    max(0, min(255, int(round(alpha)))),
                )
            except Exception:
                pass
        q = QColor(raw)
        if q.isValid():
            return q
    q = QColor(fallback)
    return q if q.isValid() else QColor("#000000")


def _rgba_with_alpha(value: object, alpha: int, fallback: str = "#000000") -> str:
    q = value if isinstance(value, QColor) else _css_to_qcolor(value, fallback)
    return f"rgba({q.red()}, {q.green()}, {q.blue()}, {max(0, min(255, int(alpha)))})"


def _blend_qcolor(base: QColor, mix: QColor, ratio: float) -> QColor:
    r = max(0.0, min(1.0, float(ratio)))
    return QColor(
        int(round(base.red() * (1.0 - r) + mix.red() * r)),
        int(round(base.green() * (1.0 - r) + mix.green() * r)),
        int(round(base.blue() * (1.0 - r) + mix.blue() * r)),
    )


def normalize_color_token(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    if raw.lower() == "transparent":
        return "transparent"

    match = _RGBA_COLOR_RE.match(raw)
    if match:
        try:
            r, g, b, a_raw = match.groups()
            r_i = max(0, min(255, int(r)))
            g_i = max(0, min(255, int(g)))
            b_i = max(0, min(255, int(b)))
            a_f = parse_css_alpha_to_unit(a_raw)
        except Exception:
            return None
        return _rgba_with_alpha(QColor(r_i, g_i, b_i), int(round(a_f * 255)))

    q = QColor(raw)
    if q.isValid():
        if q.alpha() < 255:
            return _rgba_with_alpha(q, q.alpha())
        return q.name(QColor.NameFormat.HexRgb)
    return None


def get_color_token_overrides(
    keys: tuple[str, ...] | list[str],
    *,
    prefix: str,
    settings=None,
) -> dict[str, str]:
    cfg = _resolve_settings(settings)
    overrides: dict[str, str] = {}
    for key in keys:
        qkey = f"{prefix}{key}"
        raw = str(cfg.value(qkey, "") or "").strip()
        normalized = normalize_color_token(raw)
        if normalized:
            overrides[key] = normalized
            if raw != normalized:
                cfg.setValue(qkey, normalized)
        elif raw:
            cfg.remove(qkey)
    return overrides


def set_color_token_overrides(
    keys: tuple[str, ...] | list[str],
    overrides: dict | None,
    *,
    prefix: str,
    settings=None,
):
    cfg = _resolve_settings(settings)
    payload = overrides if isinstance(overrides, dict) else {}
    for key in keys:
        normalized = normalize_color_token(payload.get(key))
        qkey = f"{prefix}{key}"
        if normalized:
            cfg.setValue(qkey, normalized)
        else:
            cfg.remove(qkey)


def normalize_metric_token_value(
    key: str,
    value,
    *,
    defaults: dict[str, int],
    bounds: dict[str, tuple[int, int]],
) -> int | None:
    if key not in defaults:
        return None
    lo, hi = bounds.get(key, (0, 999))
    try:
        parsed = int(value)
    except Exception:
        return None
    return max(lo, min(hi, parsed))


def get_metric_token_overrides(
    defaults: dict[str, int],
    bounds: dict[str, tuple[int, int]],
    *,
    prefix: str,
    settings=None,
) -> dict[str, int]:
    cfg = _resolve_settings(settings)
    overrides: dict[str, int] = {}
    for key in defaults:
        raw = cfg.value(f"{prefix}{key}", None)
        normalized = normalize_metric_token_value(key, raw, defaults=defaults, bounds=bounds)
        if normalized is not None:
            overrides[key] = normalized
    return overrides


def set_metric_token_overrides(
    defaults: dict[str, int],
    bounds: dict[str, tuple[int, int]],
    overrides: dict | None,
    *,
    prefix: str,
    settings=None,
):
    cfg = _resolve_settings(settings)
    payload = overrides if isinstance(overrides, dict) else {}
    for key in defaults:
        qkey = f"{prefix}{key}"
        normalized = normalize_metric_token_value(
            key, payload.get(key), defaults=defaults, bounds=bounds
        )
        if normalized is None or normalized == defaults[key]:
            cfg.remove(qkey)
        else:
            cfg.setValue(qkey, normalized)


def build_dialog_metric_tokens(
    settings=None,
    *,
    apply_overrides: bool = True,
) -> dict[str, int]:
    metrics = dict(DIALOG_METRIC_DEFAULTS)
    if apply_overrides:
        metrics.update(
            get_metric_token_overrides(
                DIALOG_METRIC_DEFAULTS,
                DIALOG_METRIC_BOUNDS,
                prefix="dialog_token.metric.",
                settings=settings,
            )
        )
    return metrics


def build_widget_mode_tokens(
    settings=None,
    *,
    preset_name: str = "Light Aqua Form",
) -> dict[str, str]:
    cfg = _resolve_settings(settings)
    snapshot = build_theme_snapshot(cfg, opacity_factor=1.0)
    base_tokens = build_dialog_base_tokens(cfg, snapshot=snapshot, opacity_factor=1.0)

    try:
        from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
            get_color_preset_tokens,
        )

        preset_tokens = get_color_preset_tokens(preset_name)
        if preset_tokens:
            base_tokens.update(preset_tokens)
    except Exception:
        pass

    try:
        from calendar_app.presentation.dialogs.dialog_styles import (
            _DIALOG_TOKEN_OVERRIDE_PREFIX,
            DIALOG_TOKEN_EDITABLE_KEYS,
        )

        base_tokens.update(
            get_color_token_overrides(
                DIALOG_TOKEN_EDITABLE_KEYS,
                prefix=_DIALOG_TOKEN_OVERRIDE_PREFIX,
                settings=cfg,
            )
        )
    except Exception:
        pass

    accent_q = _css_to_qcolor(base_tokens.get("accent"), snapshot.theme_color)
    accent_soft_q = _css_to_qcolor(base_tokens.get("button_primary_border"), accent_q.name())
    accent_strong_q = _css_to_qcolor(
        base_tokens.get("button_primary_hover_border"), accent_q.name()
    )
    accent_deep_q = _css_to_qcolor(
        base_tokens.get("button_primary_text"), accent_q.darker(130).name()
    )

    panel_bg_q = _css_to_qcolor(base_tokens.get("surface_alt"), "#e8edf4")
    panel_start_q = _css_to_qcolor(base_tokens.get("surface_bg"), "#eef2f6")
    panel_end_q = _css_to_qcolor(base_tokens.get("surface_top"), "#e0e8f1")
    panel_mid_q = _blend_qcolor(panel_start_q, panel_bg_q, 0.55)
    pastel_accent_q = _blend_qcolor(accent_q, QColor("#ffffff"), 0.45)
    shell_start_q = _blend_qcolor(panel_start_q, accent_q, 0.05)
    shell_mid_q = _blend_qcolor(panel_mid_q, QColor("#ffffff"), 0.24)
    shell_end_q = _blend_qcolor(panel_end_q, QColor("#ffffff"), 0.32)
    section_bg_q = _blend_qcolor(panel_bg_q, QColor("#ffffff"), 0.84)
    section_alt_q = _blend_qcolor(panel_mid_q, QColor("#ffffff"), 0.90)
    section_border_q = _blend_qcolor(panel_bg_q, accent_q, 0.14)
    header_shell_q = _blend_qcolor(panel_mid_q, QColor("#ffffff"), 0.34)
    input_bg_q = _blend_qcolor(section_bg_q, QColor("#ffffff"), 0.20)
    shape_tokens = snapshot.shape_tokens
    surface_radius = int(shape_tokens.get("panel_surface_radius", 14))
    item_radius = int(shape_tokens.get("panel_item_radius", 10))
    toolbar_button_radius = int(shape_tokens.get("panel_toolbar_button_radius", 8))
    mode_switch_radius = int(shape_tokens.get("panel_mode_switch_radius", 12))
    menu_radius = int(shape_tokens.get("panel_menu_radius", 10))
    menu_item_radius = int(shape_tokens.get("panel_menu_item_radius", 8))

    return {
        "text_primary": str(
            base_tokens.get("title_text", base_tokens.get("text_primary", "#324a63"))
        ),
        "text_secondary": str(
            base_tokens.get("title_subtext", base_tokens.get("text_secondary", "#5a6f89"))
        ),
        "text_faint": str(base_tokens.get("text_faint", "#90a0b5")),
        "surface_bg": str(base_tokens.get("surface_bg", "#eef2f6")),
        "surface_alt": str(base_tokens.get("surface_alt", "#e8edf4")),
        "calendar_text": str(base_tokens.get("text_primary", "#324a63")),
        "calendar_muted": str(base_tokens.get("text_muted", "#72869e")),
        "card_text_primary": str(base_tokens.get("text_primary", "#33435a")),
        "card_text_secondary": str(base_tokens.get("text_secondary", "#72839b")),
        "accent": accent_q.name(QColor.NameFormat.HexRgb),
        "accent_deep": accent_deep_q.name(QColor.NameFormat.HexRgb),
        "accent_soft": _rgba_with_alpha(accent_soft_q, 84, accent_q.name()),
        "accent_mid": _rgba_with_alpha(accent_soft_q, 150, accent_q.name()),
        "accent_strong": accent_strong_q.name(QColor.NameFormat.HexRgb),
        "panel_bg_start": _rgba_with_alpha(panel_start_q, 246, panel_start_q.name()),
        "panel_bg_mid": _rgba_with_alpha(panel_mid_q, 240, panel_mid_q.name()),
        "panel_bg_end": _rgba_with_alpha(panel_end_q, 246, panel_end_q.name()),
        "panel_bg": _rgba_with_alpha(panel_bg_q, 242, panel_bg_q.name()),
        "header_bg": str(base_tokens.get("title_bg", base_tokens.get("surface_top", "#e6edf4"))),
        "panel_border": str(base_tokens.get("border", "rgba(113, 135, 160, 122)")),
        "panel_border_soft": str(base_tokens.get("border_soft", "rgba(113, 135, 160, 82)")),
        "card_bg": str(base_tokens.get("surface_item", "#f7f9fc")),
        "card_hover": str(base_tokens.get("surface_hover", "#dee7f0")),
        "card_pressed": str(base_tokens.get("button_pressed_bg", "#dbe6f0")),
        "card_border": str(
            base_tokens.get(
                "button_secondary_border",
                base_tokens.get("border_soft", "rgba(113, 135, 160, 82)"),
            )
        ),
        "card_accent": str(
            base_tokens.get(
                "list_selected_border", _rgba_with_alpha(accent_q, 150, accent_q.name())
            )
        ),
        "chip_bg": str(
            base_tokens.get("button_secondary_bg", base_tokens.get("surface_alt", "#edf2f7"))
        ),
        "chip_border": str(
            base_tokens.get(
                "button_secondary_border",
                base_tokens.get("border_soft", "rgba(113, 135, 160, 82)"),
            )
        ),
        "button_bg": str(
            base_tokens.get("toolbutton_bg", base_tokens.get("button_base_bg", "#edf2f7"))
        ),
        "button_hover": str(
            base_tokens.get(
                "toolbutton_hover_bg", base_tokens.get("button_base_hover_bg", "#e6edf4")
            )
        ),
        "button_text": str(
            base_tokens.get("toolbutton_text", base_tokens.get("button_base_text", "#46607c"))
        ),
        "button_primary_bg": str(
            base_tokens.get("button_primary_bg", _rgba_with_alpha(accent_q, 44, accent_q.name()))
        ),
        "button_primary_text": str(
            base_tokens.get("button_primary_text", accent_deep_q.name(QColor.NameFormat.HexRgb))
        ),
        "button_primary_border": str(
            base_tokens.get(
                "button_primary_border", _rgba_with_alpha(accent_q, 160, accent_q.name())
            )
        ),
        "button_primary_hover_bg": str(
            base_tokens.get(
                "button_primary_hover_bg", _rgba_with_alpha(accent_q, 66, accent_q.name())
            )
        ),
        "button_primary_hover_text": str(
            base_tokens.get("button_primary_hover_text", base_tokens.get("text_primary", "#324a63"))
        ),
        "button_primary_hover_border": str(
            base_tokens.get("button_primary_hover_border", accent_q.name(QColor.NameFormat.HexRgb))
        ),
        "pastel_accent": pastel_accent_q.name(QColor.NameFormat.HexRgb),
        "shell_gradient_start": _rgba_with_alpha(shell_start_q, 252, shell_start_q.name()),
        "shell_gradient_mid": _rgba_with_alpha(shell_mid_q, 248, shell_mid_q.name()),
        "shell_gradient_end": _rgba_with_alpha(shell_end_q, 244, shell_end_q.name()),
        "shell_outline": _rgba_with_alpha(section_border_q, 136, section_border_q.name()),
        "shell_outline_soft": _rgba_with_alpha(section_border_q, 88, section_border_q.name()),
        "header_shell_bg": _rgba_with_alpha(header_shell_q, 214, header_shell_q.name()),
        "header_shell_border": _rgba_with_alpha(section_border_q, 118, section_border_q.name()),
        "section_bg": _rgba_with_alpha(section_bg_q, 230, section_bg_q.name()),
        "section_bg_alt": _rgba_with_alpha(section_alt_q, 216, section_alt_q.name()),
        "section_border": _rgba_with_alpha(section_border_q, 126, section_border_q.name()),
        "section_border_soft": _rgba_with_alpha(section_border_q, 80, section_border_q.name()),
        "input_bg": _rgba_with_alpha(input_bg_q, 242, input_bg_q.name()),
        "input_border": _rgba_with_alpha(section_border_q, 110, section_border_q.name()),
        "hero_bg": _rgba_with_alpha(accent_q, 28, accent_q.name()),
        "hero_bg_strong": _rgba_with_alpha(accent_q, 44, accent_q.name()),
        "hero_border": _rgba_with_alpha(accent_q, 104, accent_q.name()),
        "scroll_track": _rgba_with_alpha(panel_bg_q, 84, panel_bg_q.name()),
        "grip_color": _rgba_with_alpha(section_border_q, 170, section_border_q.name()),
        "launcher_radius": str(surface_radius + 8),
        "launcher_button_radius": str(item_radius + 6),
        "widget_surface_radius": str(surface_radius + 2),
        "widget_header_radius": str(max(0, surface_radius - 4)),
        "widget_control_radius": str(toolbar_button_radius + 2),
        "widget_entry_radius": str(item_radius + 2),
        "widget_secondary_radius": str(toolbar_button_radius + 2),
        "widget_input_radius": str(item_radius + 2),
        "widget_submit_radius": str(toolbar_button_radius + 3),
        "widget_chip_radius": str(max(0, mode_switch_radius - 2)),
        "widget_summary_radius": str(surface_radius),
        "widget_menu_radius": str(menu_radius + 4),
        "widget_menu_item_radius": str(menu_item_radius + 2),
        "widget_calendar_nav_radius": str(toolbar_button_radius),
        "widget_calendar_cell_radius": str(max(item_radius, toolbar_button_radius + 2)),
        "widget_calendar_today_radius": str(max(item_radius + 1, toolbar_button_radius + 3)),
    }
