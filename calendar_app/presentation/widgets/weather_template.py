# -*- coding: utf-8 -*-
"""Shared weather rendering for the desktop widget and its design previews."""

from __future__ import annotations

from html import escape
import math
import re

from calendar_app.presentation.widgets.overlay_base import (
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _extract_global_lh,
    _inject_global_lh,
    _protect_align_tags,
    _scale_template_html,
)
from calendar_app.presentation.widgets.weather_asset_packs import weather_asset_html


def weather_icon_size(hints: list[str], base_font_size: int) -> int:
    """Scale image pixels by the same 24-point reference used by text hints."""
    size = 32.0 * base_font_size / 24
    for hint in hints:
        if not hint.strip().startswith("size="):
            continue
        raw = hint.strip()[5:].strip()
        try:
            if raw == "base":
                candidate = float(base_font_size)
            elif raw.endswith("x"):
                candidate = float(raw[:-1]) * base_font_size
            elif raw.endswith("%"):
                candidate = float(raw[:-1]) * base_font_size / 100
            elif raw.startswith(("+", "-")):
                candidate = base_font_size + float(raw)
            else:
                candidate = float(raw) * base_font_size / 24
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            size = candidate
    return max(16, min(1536, round(size)))


def _safe_size_hints(hints: list[str]) -> list[str]:
    """Invalid manual sizes must not break a live resize or preview."""
    safe = []
    for hint in hints:
        hint = hint.strip()
        if hint.startswith("size="):
            raw = hint[5:].strip()
            if raw != "base":
                try:
                    value = float(raw.rstrip("x%"))
                except (ValueError, OverflowError):
                    continue
                if not math.isfinite(value) or abs(value) > 2048:
                    continue
        elif hint.startswith(("lh=", "line=", "line_height=")):
            if not _valid_line_height(hint.split("=", 1)[1]):
                continue
        safe.append(hint)
    return safe


def _valid_line_height(raw: str) -> bool:
    raw = raw.strip()
    value = raw[:-2] if raw.endswith("pt") else raw.rstrip("x%")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return False
    return math.isfinite(number) and 0 < number <= 2048


def render_weather_template(
    template: str,
    data: dict,
    *,
    asset_pack_id: str = "air_soft",
    base_font_size: int = 24,
    icon_color: str = "#f5f7ff",
    resolve_text_sizes: bool = True,
    color_aliases: dict[str, str] | None = None,
) -> str:
    """Render one weather design without settings writes or network requests.

    The widget defers text markers to its common label renderer, while standalone
    previews receive complete CSS. Image dimensions use the same font reference
    in both paths, so a larger widget keeps the illustration/text balance.
    """
    try:
        base_font_size = max(6, min(500, int(base_font_size)))
    except (TypeError, ValueError, OverflowError):
        base_font_size = 24
    try:
        wmo = int(data.get("_wmo", -1))
    except (TypeError, ValueError, OverflowError):
        wmo = -1
    period = "night" if str(data.get("_day_period", "day")).lower() == "night" else "day"
    prepared = _inject_global_lh(str(template or ""))
    prepared = re.sub(
        r"<lh\s+([^>]+)>",
        lambda match: match.group(0) if _valid_line_height(match.group(1)) else "",
        prepared,
        flags=re.IGNORECASE,
    )
    prepared = _protect_align_tags(prepared)
    prepared = _BaseOverlayWidget._process_conditionals(prepared, data)

    def metric_unit(match: re.Match) -> str:
        key, raw_hints, suffix = match.groups()
        if key == "humidity" and suffix.strip() != "%" or key == "wind" and suffix.strip() != "m/s":
            return match.group(0)
        hints = _safe_size_hints(raw_hints.split("|")[1:])
        if not any(hint.startswith("size=") for hint in hints):
            hints.append("size=base")
        return f"{{{key}{raw_hints}}}" + _apply_span(escape(suffix), hints)

    prepared = re.sub(r"\{(humidity|wind)((?:\|[^}]+)?)\}([ \t]*(?:%|m/s))", metric_unit, prepared)

    def replace(match: re.Match) -> str:
        parts = match.group(1).split("|")
        key, hints = parts[0].strip(), _safe_size_hints(parts[1:])
        if key == "icon":
            image = weather_asset_html(
                asset_pack_id,
                wmo,
                period,
                weather_icon_size(hints, base_font_size),
                color=icon_color,
            )
            if image:
                return image.replace("<img ", f'<img data-weather-font="{base_font_size}" ', 1)
            return _apply_span(escape(str(data.get("desc", "--"))), hints)
        # QLabel's stylesheet can give unstyled text a fixed pixel size. Explicit
        # inheritance keeps units and custom plain fields in the resize flow.
        if not any(hint.startswith("size=") for hint in hints):
            hints.append("size=base")
        value = data.get(key, "")
        return _apply_span(escape(str(value if value is not None else "")), hints)

    html = _apply_align_tags(re.sub(r"\{([^}]+)\}", replace, prepared))
    # Alignment tags already create block lines. A <br> beside those blocks
    # inserts an extra empty row in Qt rich text and stretches information cards.
    html = html.replace("</div><br>", "</div>")
    html = re.sub(r'<br>(?=<div style="text-align:)', "", html)
    if resolve_text_sizes:
        html, line_height = _extract_global_lh(html, base_font_size)
        html = _scale_template_html(html, base_font_size)
        if line_height:
            html = f'<div style="line-height:{line_height}">{html}</div>'
        aliases = color_aliases or {}
        html = re.sub(
            r"color:([a-zA-Z_]+)(?=[;\"])",
            lambda match: f"color:{aliases.get(match.group(1), icon_color)}",
            html,
        )
    return html


def scale_weather_preview_images(html: str, base_font_size: int) -> str:
    """Keep images proportional when the common template preview box changes."""

    def scale_image(match: re.Match) -> str:
        tag = match.group(0)
        reference = re.search(r'data-weather-font="(\d+)"', tag)
        if reference is None:
            return tag
        ratio = base_font_size / max(1, int(reference.group(1)))
        return re.sub(
            r'(width|height)="(\d+)"',
            lambda dimension: (
                f'{dimension.group(1)}="'
                f'{max(16, min(1536, round(int(dimension.group(2)) * ratio)))}"'
            ),
            tag,
        )

    return re.sub(r"<img\b[^>]*>", scale_image, html)


__all__ = ["render_weather_template", "scale_weather_preview_images", "weather_icon_size"]
