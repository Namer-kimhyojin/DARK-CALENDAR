# -*- coding: utf-8 -*-
"""Bundled illustration packs for the desktop weather widget."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import functools

from PyQt6.QtCore import QBuffer, QIODevice, QRect, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap

from calendar_app.app_paths import get_resource_path


@dataclass(frozen=True, slots=True)
class WeatherAssetPack:
    pack_id: str
    label_key: str
    label_default: str
    filename: str | None


DEFAULT_WEATHER_ASSET_PACK_ID = "air_soft"

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


def weather_condition_id(wmo_code: int, day_period: str = "day") -> str:
    """Collapse WMO values into the authored illustration slots."""

    period = str(day_period or "day").strip().lower()
    is_night = period == "night"
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
    return sprite.copy(QRect(left, top, right - left, bottom - top))


def _classic_pixmap(wmo_code: int, color: str, size: int) -> QPixmap:
    try:
        import qtawesome as qta

        icon_name = _CLASSIC_ICON_MAP.get(wmo_code, _CLASSIC_ICON_FALLBACK)
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
    target_size = max(16, min(int(size), 320))
    if pack.pack_id == "classic":
        return _classic_pixmap(wmo_code, color, target_size)
    cell = _sprite_cell(pack.pack_id, weather_condition_id(wmo_code, day_period))
    if cell.isNull():
        return _classic_pixmap(wmo_code, color, target_size)
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
    rendered_size = max(16, min(int(size), 320))
    return (
        f'<img src="data:image/png;base64,{png_b64}" '
        f'width="{rendered_size}" height="{rendered_size}" />'
    )


def weather_pack_preview_pixmap(pack_id: object, size: QSize) -> QPixmap:
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
    "WeatherAssetPack",
    "get_weather_asset_pack",
    "weather_asset_html",
    "weather_asset_packs",
    "weather_asset_pixmap",
    "weather_condition_id",
    "weather_pack_icon",
    "weather_pack_preview_pixmap",
]
