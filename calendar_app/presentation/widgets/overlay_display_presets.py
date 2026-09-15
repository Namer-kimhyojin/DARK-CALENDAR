# -*- coding: utf-8 -*-
"""Shared, designer-authored appearance presets for desktop overlay widgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverlayDisplayPreset:
    """A complete visual treatment shared by every overlay widget type."""

    preset_id: str
    label_key: str
    label_default: str
    font_candidates: tuple[str, ...]
    text_rgba: str
    background_rgba: str
    border_rgba: str
    style_params: dict[str, object]


_PRESETS: tuple[OverlayDisplayPreset, ...] = (
    OverlayDisplayPreset(
        "midnight_glass",
        "widget.display_preset.midnight_glass",
        "Midnight Glass · Calm depth",
        ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI"),
        "#f5f7ffff",
        "#be101827",
        "#667ea6ff",
        {
            "margins": [20, 12, 20, 12],
            "radius": 18,
            "border_width": 1,
            "glass": True,
            "glass_bg_cap": 190,
            "glass_border_boost": 34,
        },
    ),
    OverlayDisplayPreset(
        "pearl_mist",
        "widget.display_preset.pearl_mist",
        "Pearl Mist · Soft clarity",
        ("Segoe UI Variable Text", "Segoe UI", "Malgun Gothic"),
        "#ff1b2430",
        "#dcf5f7fa",
        "#d2ffffff",
        {
            "margins": [20, 12, 20, 12],
            "radius": 18,
            "border_width": 1,
            "glass": True,
            "glass_bg_cap": 220,
            "glass_border_boost": 18,
        },
    ),
    OverlayDisplayPreset(
        "graphite_minimal",
        "widget.display_preset.graphite_minimal",
        "Graphite Minimal · Quiet restraint",
        ("Segoe UI Variable Text", "Segoe UI", "Malgun Gothic"),
        "#fff1f3f5",
        "#e6181b20",
        "#48606772",
        {"margins": [14, 8, 14, 8], "radius": 8, "border_width": 1},
    ),
    OverlayDisplayPreset(
        "pure_type",
        "widget.display_preset.pure_type",
        "Pure Type · Text only",
        ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI"),
        "#fff5f7fb",
        "#00101827",
        "#00ffffff",
        {
            "margins": [8, 5, 8, 5],
            "radius": 0,
            "border_width": 0,
            "background_type": "transparent",
            "border_type": "transparent",
        },
    ),
    OverlayDisplayPreset(
        "electric_cyan",
        "widget.display_preset.electric_cyan",
        "Electric Cyan · Crisp neon",
        ("Bahnschrift", "Segoe UI Variable Display", "Segoe UI"),
        "#ffbffbff",
        "#cd06171c",
        "#dc38e8ff",
        {"margins": [18, 11, 18, 11], "radius": 12, "border_width": 2},
    ),
    OverlayDisplayPreset(
        "aurora_violet",
        "widget.display_preset.aurora_violet",
        "Aurora Violet · Dreamlike glow",
        ("Segoe UI Variable Display", "Segoe UI", "Malgun Gothic"),
        "#fff5ecff",
        "#cd211237",
        "#a0b580ff",
        {
            "margins": [20, 12, 20, 12],
            "radius": 22,
            "border_width": 1,
            "glass": True,
            "glass_bg_cap": 205,
            "glass_border_boost": 34,
        },
    ),
    OverlayDisplayPreset(
        "forest_moss",
        "widget.display_preset.forest_moss",
        "Forest Moss · Natural focus",
        ("Aptos", "Segoe UI Variable Text", "Segoe UI"),
        "#fff0f7ee",
        "#dc14251d",
        "#8079aa88",
        {"margins": [19, 11, 19, 11], "radius": 14, "border_width": 1},
    ),
    OverlayDisplayPreset(
        "sunset_coral",
        "widget.display_preset.sunset_coral",
        "Sunset Coral · Warm energy",
        ("Aptos Display", "Segoe UI Variable Display", "Segoe UI"),
        "#fffff4f0",
        "#d4371d24",
        "#c8ff8068",
        {"margins": [20, 12, 20, 12], "radius": 16, "border_width": 2},
    ),
    OverlayDisplayPreset(
        "champagne_gold",
        "widget.display_preset.champagne_gold",
        "Champagne Gold · Refined warmth",
        ("Georgia", "Cambria", "Times New Roman"),
        "#fffff4d6",
        "#e61d1812",
        "#b4d7b56d",
        {
            "margins": [22, 13, 22, 13],
            "radius": 10,
            "border_type": "double",
            "border_width": 2,
        },
    ),
    OverlayDisplayPreset(
        "paper_ivory",
        "widget.display_preset.paper_ivory",
        "Paper Ivory · Editorial calm",
        ("Cambria", "Georgia", "Malgun Gothic"),
        "#ff29251f",
        "#f0f5eddf",
        "#8c9d8f7b",
        {
            "margins": [22, 14, 22, 14],
            "radius": 4,
            "border_type": "left_only",
            "border_width": 2,
        },
    ),
    OverlayDisplayPreset(
        "terminal_green",
        "widget.display_preset.terminal_green",
        "Terminal Green · Technical rhythm",
        ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New"),
        "#ff79f2a1",
        "#ed07110b",
        "#9e3ad66b",
        {"margins": [16, 10, 16, 10], "radius": 3, "border_width": 1, "letter_spacing": 1},
    ),
    OverlayDisplayPreset(
        "retro_amber",
        "widget.display_preset.retro_amber",
        "Retro Amber · Analog nostalgia",
        ("Cascadia Mono", "Consolas", "Courier New"),
        "#ffffc45c",
        "#ed1c1408",
        "#b8d88a28",
        {
            "margins": [18, 11, 18, 11],
            "radius": 6,
            "border_type": "double",
            "border_width": 2,
            "letter_spacing": 1,
        },
    ),
    OverlayDisplayPreset(
        "high_contrast",
        "widget.display_preset.high_contrast",
        "High Contrast · Maximum legibility",
        ("Arial", "Segoe UI", "Malgun Gothic"),
        "#ffffffff",
        "#f5000000",
        "#ffffffff",
        {"margins": [18, 11, 18, 11], "radius": 6, "border_width": 2},
    ),
)

_PRESET_BY_ID = {preset.preset_id: preset for preset in _PRESETS}
DEFAULT_DISPLAY_PRESET_ID = "midnight_glass"
CUSTOM_DISPLAY_PRESET_ID = "custom"


def overlay_display_presets() -> tuple[OverlayDisplayPreset, ...]:
    """Return presets in their stable, user-facing order."""

    return _PRESETS


def overlay_display_preset(preset_id: str) -> OverlayDisplayPreset | None:
    """Return one preset, or ``None`` for custom/unknown values."""

    return _PRESET_BY_ID.get(str(preset_id or ""))
