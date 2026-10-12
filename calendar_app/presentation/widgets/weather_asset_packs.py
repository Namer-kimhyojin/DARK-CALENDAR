# -*- coding: utf-8 -*-
"""Bundled illustration packs for the desktop weather widget."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import functools

from PyQt6.QtCore import QBuffer, QIODevice, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from calendar_app.app_paths import get_resource_path
from calendar_app.presentation.widgets.weather_vector_art import (
    VECTOR_WEATHER_PACK_IDS,
    render_weather_vector,
)


@dataclass(frozen=True, slots=True)
class WeatherAssetPack:
    pack_id: str
    label_key: str
    label_default: str
    filename: str | None


DEFAULT_WEATHER_ASSET_PACK_ID = "air_soft"
MAX_WEATHER_ART_SIZE = 1536

_PACKS = (
    WeatherAssetPack(
        "air_soft",
        "widget.weather.asset_pack_air_soft",
        "Air Soft · Soft 3D",
        "air-soft-sprites.png",
    ),
    WeatherAssetPack(
        "paper_weather",
        "widget.weather.asset_pack_paper_weather",
        "Paper Weather · Layered paper",
        "paper-weather-sprites.png",
    ),
    WeatherAssetPack(
        "mono_atmosphere",
        "widget.weather.asset_pack_mono_atmosphere",
        "Mono Atmosphere · Crisp minimal",
        "mono-atmosphere-sprites.png",
    ),
    WeatherAssetPack(
        "classic",
        "widget.weather.asset_pack_classic",
        "Classic · Original icons",
        None,
    ),
    WeatherAssetPack(
        "outline_weather",
        "widget.weather.asset_pack_outline_weather",
        "Outline · 선으로 그린 날씨",
        None,
    ),
    WeatherAssetPack(
        "neon_weather",
        "widget.weather.asset_pack_neon_weather",
        "Neon · 빛나는 네온",
        None,
    ),
    WeatherAssetPack(
        "flat_weather",
        "widget.weather.asset_pack_flat_weather",
        "Flat · 또렷한 컬러",
        None,
    ),
    WeatherAssetPack(
        "pixel_weather",
        "widget.weather.asset_pack_pixel_weather",
        "Pixel · 픽셀 아트",
        None,
    ),
    WeatherAssetPack(
        "orbit_weather",
        "widget.weather.asset_pack_orbit_weather",
        "Orbit · 궤도 배지",
        None,
    ),
    WeatherAssetPack(
        "vintage_weather",
        "widget.weather.asset_pack_vintage_weather",
        "Vintage · 빈티지 삽화",
        None,
    ),
)
_PACK_BY_ID = {pack.pack_id: pack for pack in _PACKS}

# 4 x 4 generated sprite sheets. The final two cells are intentionally empty.
_STATE_TO_CELL = {
    "clear_day": 0,
    "clear_night": 1,
    "partly_cloudy_day": 2,
    "partly_cloudy_night": 3,
    "cloudy": 4,
    "fog": 5,
    "drizzle": 6,
    "rain": 7,
    "heavy_rain": 8,
    "snow": 9,
    "heavy_snow": 10,
    "thunderstorm": 11,
    "hail": 12,
    "unknown": 13,
}

_CLASSIC_ICON_MAP: dict[int, str] = {
    0: "mdi6.weather-sunny",
    1: "mdi6.weather-sunny",
    2: "mdi6.weather-partly-cloudy",
    3: "mdi6.weather-cloudy",
    45: "mdi6.weather-fog",
    48: "mdi6.weather-fog",
    51: "mdi6.weather-partly-rainy",
    53: "mdi6.weather-partly-rainy",
    55: "mdi6.weather-rainy",
    61: "mdi6.weather-rainy",
    63: "mdi6.weather-rainy",
    65: "mdi6.weather-pouring",
    71: "mdi6.weather-snowy",
    73: "mdi6.weather-snowy",
    75: "mdi6.weather-snowy-heavy",
    77: "mdi6.snowflake",
    80: "mdi6.weather-partly-rainy",
    81: "mdi6.weather-rainy",
    82: "mdi6.weather-pouring",
    85: "mdi6.weather-partly-snowy",
    86: "mdi6.weather-snowy-heavy",
    95: "mdi6.weather-lightning",
    96: "mdi6.weather-lightning-rainy",
    99: "mdi6.weather-lightning-rainy",
}
_CLASSIC_ICON_FALLBACK = "mdi6.weather-partly-cloudy"


def weather_asset_packs() -> tuple[WeatherAssetPack, ...]:
    return _PACKS


def get_weather_asset_pack(pack_id: object) -> WeatherAssetPack:
    normalized = str(pack_id or "").strip().lower()
    return _PACK_BY_ID.get(normalized, _PACK_BY_ID[DEFAULT_WEATHER_ASSET_PACK_ID])


def _safe_size(value: object, default: int = 96) -> int:
    try:
        return max(16, min(int(value), MAX_WEATHER_ART_SIZE))
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_wmo(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return -1


def _safe_color(value: object) -> str:
    color = QColor(str(value or "#4db8ff"))
    return color.name() if color.isValid() else "#4db8ff"


def weather_condition_id(wmo_code: int, day_period: str = "day") -> str:
    """Collapse WMO values into the authored illustration slots."""

    period = str(day_period or "day").strip().lower()
    is_night = period == "night"
    wmo_code = _safe_wmo(wmo_code)
    if wmo_code in {0, 1}:
        return "clear_night" if is_night else "clear_day"
    if wmo_code == 2:
        return "partly_cloudy_night" if is_night else "partly_cloudy_day"
    if wmo_code == 3:
        return "cloudy"
    if wmo_code in {45, 48}:
        return "fog"
    if wmo_code in {51, 53, 55}:
        return "drizzle"
    if wmo_code in {65, 82}:
        return "heavy_rain"
    if wmo_code in {61, 63, 80, 81}:
        return "rain"
    if wmo_code in {75, 86}:
        return "heavy_snow"
    if wmo_code in {71, 73, 77, 85}:
        return "snow"
    if wmo_code in {96, 99}:
        return "hail"
    if wmo_code == 95:
        return "thunderstorm"
    return "unknown"


@functools.lru_cache(maxsize=len(_PACKS))
def _load_sprite(pack_id: str) -> QPixmap:
    pack = get_weather_asset_pack(pack_id)
    if not pack.filename:
        return QPixmap()
    return QPixmap(get_resource_path("weather", pack.filename))


@functools.lru_cache(maxsize=42)
def _sprite_cell(pack_id: str, condition_id: str) -> QPixmap:
    sprite = _load_sprite(pack_id)
    if sprite.isNull():
        return QPixmap()
    index = _STATE_TO_CELL.get(condition_id, _STATE_TO_CELL["unknown"])
    row, column = divmod(index, 4)
    left = round(column * sprite.width() / 4)
    right = round((column + 1) * sprite.width() / 4)
    top = round(row * sprite.height() / 4)
    bottom = round((row + 1) * sprite.height() / 4)
    return _trim_transparent(sprite.copy(QRect(left, top, right - left, bottom - top)))


def _trim_transparent(cell: QPixmap) -> QPixmap:
    """Fit authored art rather than its mostly empty sprite cell, retaining soft edges."""
    if cell.isNull():
        return cell
    image = cell.toImage().convertToFormat(QImage.Format.Format_Alpha8)
    pointer = image.constBits()
    if pointer is None:
        return cell
    alpha = pointer.asstring(image.sizeInBytes())
    stride, width, height = image.bytesPerLine(), image.width(), image.height()
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        row = alpha[y * stride : y * stride + width]
        first = next((x for x, opacity in enumerate(row) if opacity > 4), None)
        if first is None:
            continue
        last = width - 1 - next(x for x, opacity in enumerate(reversed(row)) if opacity > 4)
        left, right = min(left, first), max(right, last)
        top, bottom = min(top, y), max(bottom, y)
    if right < left:
        return cell
    padding = max(2, round(max(right - left + 1, bottom - top + 1) * 0.035))
    rect = QRect(left, top, right - left + 1, bottom - top + 1)
    rect = rect.adjusted(-padding, -padding, padding, padding).intersected(cell.rect())
    return cell.copy(rect)


def _classic_pixmap(wmo_code: int, color: str, size: int, day_period: str = "day") -> QPixmap:
    try:
        import qtawesome as qta

        icon_name = _CLASSIC_ICON_MAP.get(wmo_code, _CLASSIC_ICON_FALLBACK)
        if day_period == "night" and wmo_code in {0, 1, 2}:
            icon_name = (
                "mdi6.weather-night" if wmo_code in {0, 1} else "mdi6.weather-night-partly-cloudy"
            )
        return qta.icon(icon_name, color=color).pixmap(size, size)
    except Exception:
        return QPixmap()


def weather_asset_pixmap(
    pack_id: object,
    wmo_code: int,
    day_period: str,
    size: int,
    *,
    color: str = "#4db8ff",
) -> QPixmap:
    pack = get_weather_asset_pack(pack_id)
    target_size = _safe_size(size)
    wmo_code = _safe_wmo(wmo_code)
    color = _safe_color(color)
    period = str(day_period or "day").strip().lower()
    if pack.pack_id in VECTOR_WEATHER_PACK_IDS:
        return render_weather_vector(
            pack.pack_id, weather_condition_id(wmo_code, period), target_size, day_period=period
        )
    if pack.pack_id == "classic":
        return _classic_pixmap(wmo_code, color, target_size, period)
    cell = _sprite_cell(pack.pack_id, weather_condition_id(wmo_code, day_period))
    if cell.isNull():
        return _classic_pixmap(wmo_code, color, target_size, period)
    scaled = cell.scaled(
        QSize(target_size, target_size),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QPixmap(target_size, target_size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(
        (target_size - scaled.width()) // 2,
        (target_size - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas


def weather_asset_html(
    pack_id: object,
    wmo_code: int,
    day_period: str,
    size: int,
    *,
    color: str = "#4db8ff",
) -> str:
    """Return the same data-URL image contract at a bounded, normalized resolution."""
    pack = get_weather_asset_pack(pack_id)
    return _weather_asset_html_cached(
        pack.pack_id,
        _safe_wmo(wmo_code),
        str(day_period or "day").strip().lower(),
        _safe_size(size),
        _safe_color(color),
    )


@functools.lru_cache(maxsize=64)
def _weather_asset_html_cached(
    pack_id: str, wmo_code: int, day_period: str, size: int, color: str
) -> str:
    pixmap = weather_asset_pixmap(pack_id, wmo_code, day_period, size, color=color)
    if pixmap.isNull():
        return ""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        buffer.close()
        return ""
    png_b64 = base64.b64encode(bytes(buffer.data())).decode("utf-8", errors="strict")
    buffer.close()
    rendered_size = size
    return (
        f'<img src="data:image/png;base64,{png_b64}" '
        f'width="{rendered_size}" height="{rendered_size}" />'
    )


def weather_pack_preview_pixmap(pack_id: object, size: QSize) -> QPixmap:
    if not isinstance(size, QSize):
        size = QSize(300, 104)
    size = QSize(
        max(1, min(size.width(), MAX_WEATHER_ART_SIZE)),
        max(1, min(size.height(), MAX_WEATHER_ART_SIZE)),
    )
    canvas = QPixmap(size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    tile_size = min(88, max(48, size.height() - 18))
    samples = ((0, "day"), (61, "day"), (0, "night"))
    gap = max(4, (size.width() - tile_size * len(samples)) // (len(samples) + 1))
    x = gap
    for wmo_code, period in samples:
        pixmap = weather_asset_pixmap(pack_id, wmo_code, period, tile_size)
        y = (size.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)
        x += tile_size + gap
    painter.end()
    return canvas


def weather_pack_icon(pack_id: object) -> QIcon:
    pixmap = weather_asset_pixmap(pack_id, 2, "day", 48)
    return QIcon(pixmap)


__all__ = [
    "DEFAULT_WEATHER_ASSET_PACK_ID",
    "MAX_WEATHER_ART_SIZE",
    "WeatherAssetPack",
    "get_weather_asset_pack",
    "weather_asset_html",
    "weather_asset_packs",
    "weather_asset_pixmap",
    "weather_condition_id",
    "weather_pack_icon",
    "weather_pack_preview_pixmap",
]
