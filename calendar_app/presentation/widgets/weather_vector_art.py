# -*- coding: utf-8 -*-
"""Six transparent, resolution-independent weather illustration families."""

from __future__ import annotations

from dataclasses import dataclass
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

VECTOR_WEATHER_PACK_IDS = frozenset(
    {
        "outline_weather",
        "neon_weather",
        "flat_weather",
        "pixel_weather",
        "orbit_weather",
        "vintage_weather",
    }
)


@dataclass(frozen=True, slots=True)
class _Palette:
    outline: str
    cloud: str
    sun: str
    moon: str
    rain: str
    snow: str


_PALETTES = {
    "outline_weather": _Palette("#a9d6e8", "#a9d6e8", "#ffd681", "#c4bcf5", "#68c7eb", "#c8eafa"),
    "neon_weather": _Palette("#70eaff", "#172c49", "#ffce63", "#bd95ff", "#38d9ff", "#a2ffff"),
    "flat_weather": _Palette("#244767", "#e2edf4", "#f8b53b", "#b8b3ee", "#38a8cf", "#b8e0f1"),
    "pixel_weather": _Palette("#283a58", "#c6d5e8", "#ffc94f", "#aaa0ec", "#50b6e6", "#b5e9ff"),
    "orbit_weather": _Palette("#7fa7ce", "#d5eafa", "#f4cb78", "#b7a8ed", "#6baadc", "#c2e7f7"),
    "vintage_weather": _Palette("#806345", "#f0e5c9", "#d4a149", "#9eabb7", "#789ca9", "#e8dbc0"),
}
_CONDITIONS = frozenset(
    {
        "clear_day",
        "clear_night",
        "partly_cloudy_day",
        "partly_cloudy_night",
        "cloudy",
        "fog",
        "drizzle",
        "rain",
        "heavy_rain",
        "snow",
        "heavy_snow",
        "thunderstorm",
        "hail",
        "unknown",
    }
)


def _pen(color: str, width: float) -> QPen:
    return QPen(
        QColor(color),
        width,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )


def _shape(painter: QPainter, path: QPainterPath, style: str, fill: str, stroke: str) -> None:
    if style == "neon_weather":
        for width, alpha in ((14.0, 15), (9.0, 28), (5.0, 70)):
            color = QColor(stroke)
            color.setAlpha(alpha)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    color,
                    width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(path)
        dark = QColor(fill)
        dark.setAlpha(190)
        painter.setBrush(dark)
        painter.setPen(_pen(stroke, 2.4))
        painter.drawPath(path)
    elif style == "outline_weather":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(stroke, 4.3))
        painter.drawPath(path)
    elif style == "vintage_weather":
        painter.setBrush(QColor(fill))
        painter.setPen(_pen(stroke, 1.9))
        painter.drawPath(path)
        painter.save()
        painter.setClipPath(path)
        hatch = QColor(stroke)
        hatch.setAlpha(50)
        painter.setPen(QPen(hatch, 0.8))
        for position in range(-120, 220, 7):
            painter.drawLine(QPointF(position, 10), QPointF(position + 90, 120))
        painter.restore()
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawPath(path)


def _ellipse(painter: QPainter, rect: QRectF, style: str, fill: str, stroke: str) -> None:
    path = QPainterPath()
    path.addEllipse(rect)
    _shape(painter, path, style, fill, stroke)


def _sun(painter: QPainter, center: QPointF, radius: float, style: str, palette: _Palette) -> None:
    painter.setPen(_pen(palette.sun, 3.3 if style != "vintage_weather" else 1.7))
    for index in range(8 if style != "vintage_weather" else 12):
        angle = index * math.tau / (8 if style != "vintage_weather" else 12)
        inner = QPointF(
            center.x() + (radius + 6) * math.cos(angle), center.y() + (radius + 6) * math.sin(angle)
        )
        outer = QPointF(
            center.x() + (radius + 13) * math.cos(angle),
            center.y() + (radius + 13) * math.sin(angle),
        )
        painter.drawLine(inner, outer)
    _ellipse(
        painter,
        QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
        style,
        palette.sun,
        palette.sun,
    )


def _moon(painter: QPainter, center: QPointF, radius: float, style: str, palette: _Palette) -> None:
    path = QPainterPath()
    path.addEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))
    cutout = QPainterPath()
    cutout.addEllipse(
        QRectF(center.x() - radius * 0.3, center.y() - radius * 1.3, radius * 1.7, radius * 1.7)
    )
    _shape(painter, path.subtracted(cutout), style, palette.moon, palette.moon)
    painter.setPen(_pen(palette.moon, 1.5))
    for x, y, width in ((98, 31, 3), (82, 17, 2)):
        painter.drawLine(QPointF(x - width, y), QPointF(x + width, y))
        painter.drawLine(QPointF(x, y - width), QPointF(x, y + width))


def _cloud_path(top: float = 34.0) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(32, top + 42)
    path.cubicTo(13, top + 42, 11, top + 13, 34, top + 12)
    path.cubicTo(40, top - 7, 69, top - 9, 79, top + 12)
    path.cubicTo(104, top + 5, 121, top + 41, 96, top + 42)
    path.closeSubpath()
    return path


def _cloud(painter: QPainter, top: float, style: str, palette: _Palette) -> None:
    _shape(painter, _cloud_path(top), style, palette.cloud, palette.outline)
    if style == "flat_weather":
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(42, top + 1, 25, 18))


def _snowflake(
    painter: QPainter, x: float, y: float, radius: float, color: str, style: str
) -> None:
    painter.setPen(_pen(color, 2.4 if style != "vintage_weather" else 1.5))
    for angle in (0.0, math.pi / 3, math.pi * 2 / 3):
        dx, dy = math.cos(angle) * radius, math.sin(angle) * radius
        painter.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))


def _precipitation(painter: QPainter, condition: str, style: str, palette: _Palette) -> None:
    if condition in {"drizzle", "rain", "heavy_rain"}:
        count = {"drizzle": 3, "rain": 3, "heavy_rain": 5}[condition]
        for index in range(count):
            x = 35 + index * 58 / max(1, count - 1)
            y = 90 + (index % 2) * 4
            if condition == "drizzle":
                _ellipse(
                    painter,
                    QRectF(x - 2.2, y, 4.4, 4.4),
                    "flat_weather",
                    palette.rain,
                    palette.rain,
                )
            elif style in {"outline_weather", "neon_weather", "vintage_weather"}:
                painter.setPen(_pen(palette.rain, 3.3 if style != "vintage_weather" else 1.8))
                painter.drawLine(QPointF(x + 3, y - 3), QPointF(x - 2, y + 11))
            else:
                drop = QPainterPath()
                drop.moveTo(x, y - 5)
                drop.cubicTo(x + 11, y + 8, x - 8, y + 16, x - 4, y + 6)
                drop.closeSubpath()
                _shape(painter, drop, style, palette.rain, palette.rain)
    elif condition in {"snow", "heavy_snow"}:
        count = 3 if condition == "snow" else 5
        for index in range(count):
            _snowflake(
                painter,
                32 + index * 64 / (count - 1),
                95 + (index % 2) * 10,
                5,
                palette.snow,
                style,
            )
    elif condition == "hail":
        for x, y in ((34, 93), (52, 105), (76, 93), (96, 104)):
            _ellipse(painter, QRectF(x - 4, y - 4, 8, 8), style, palette.snow, palette.outline)
    elif condition == "thunderstorm":
        bolt = QPainterPath()
        bolt.addPolygon(
            QPolygonF(
                [
                    QPointF(62, 78),
                    QPointF(50, 97),
                    QPointF(61, 97),
                    QPointF(54, 113),
                    QPointF(80, 89),
                    QPointF(66, 89),
                    QPointF(74, 78),
                ]
            )
        )
        bolt.closeSubpath()
        _shape(painter, bolt, style, palette.sun, palette.sun)


def _pixel_rect(
    painter: QPainter, x: float, y: float, width: float, height: float, color: str
) -> None:
    painter.fillRect(QRectF(x * 4, y * 4, width * 4, height * 4), QColor(color))


def _pixel_art(painter: QPainter, condition: str, night: bool, palette: _Palette) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    clear = condition.startswith("clear_")
    partly = condition.startswith("partly_cloudy_")
    if clear or partly:
        shift_x, shift_y = (0, 0) if clear else (-1, -1)
        color = palette.moon if night else palette.sun
        pixels = ((11, 7, 10, 2), (8, 9, 16, 3), (7, 12, 18, 8), (8, 20, 16, 3), (11, 23, 10, 2))
        if night:
            pixels = (
                (11, 7, 4, 2),
                (9, 9, 4, 3),
                (8, 12, 4, 8),
                (10, 20, 5, 3),
                (13, 23, 8, 2),
                (18, 19, 6, 4),
            )
        for x, y, width, height in pixels:
            _pixel_rect(painter, x + shift_x, y + shift_y, width, height, color)
        if not night:
            for x, y, width, height in (
                (15, 2, 2, 3),
                (15, 27, 2, 3),
                (2, 15, 3, 2),
                (27, 15, 3, 2),
                (5, 5, 2, 2),
                (25, 5, 2, 2),
                (5, 25, 2, 2),
                (25, 25, 2, 2),
            ):
                _pixel_rect(painter, x + shift_x, y + shift_y, width, height, color)
    if not clear:
        for x, y, width, height in (
            (10, 9, 8, 2),
            (8, 11, 14, 3),
            (5, 14, 23, 4),
            (4, 18, 25, 4),
            (6, 22, 21, 2),
        ):
            _pixel_rect(painter, x, y, width, height, palette.outline)
        for x, y, width, height in ((11, 10, 6, 3), (9, 13, 12, 3), (6, 16, 20, 4), (7, 20, 19, 2)):
            _pixel_rect(painter, x, y, width, height, palette.cloud)
    if condition == "fog":
        for index in range(3):
            _pixel_rect(
                painter, 5 + index % 2 * 3, 25 + index * 2, 20 - index % 2 * 4, 1, palette.rain
            )
    elif condition in {"drizzle", "rain", "heavy_rain"}:
        count = 5 if condition == "heavy_rain" else 3
        for index in range(count):
            x = 8 + index * (16 / max(1, count - 1))
            _pixel_rect(
                painter, x, 25 + index % 2, 1, 1 if condition == "drizzle" else 4, palette.rain
            )
    elif condition in {"snow", "heavy_snow", "hail"}:
        count = 5 if condition == "heavy_snow" else 3
        for index in range(count):
            x, y = 7 + index * 18 / max(1, count - 1), 26 + index % 2
            if condition == "hail":
                _pixel_rect(painter, x, y, 2, 2, palette.snow)
            else:
                _pixel_rect(painter, x + 1, y, 1, 3, palette.snow)
                _pixel_rect(painter, x, y + 1, 3, 1, palette.snow)
    elif condition == "thunderstorm":
        for rect in ((15, 24, 4, 1), (14, 25, 4, 2), (17, 27, 2, 1), (15, 28, 3, 2)):
            _pixel_rect(painter, *rect, palette.sun)
    elif condition == "unknown":
        for rect in (
            (14, 12, 5, 1),
            (18, 13, 2, 3),
            (16, 16, 3, 1),
            (15, 17, 2, 2),
            (15, 21, 2, 2),
        ):
            _pixel_rect(painter, *rect, palette.outline)


def render_weather_vector(
    pack_id: str, condition_id: str, size: int, *, day_period: str = "day"
) -> QPixmap:
    """Render a registered vector family into a square, transparent pixmap.

    Callers normalize size and WMO values; this entry point also bounds direct inputs.
    No files, settings, fonts, network requests or external assets are used.
    """
    if not isinstance(pack_id, str) or pack_id not in VECTOR_WEATHER_PACK_IDS:
        return QPixmap()
    try:
        target_size = max(16, min(int(size), 1536))
    except (TypeError, ValueError, OverflowError):
        target_size = 96
    condition = (
        condition_id if isinstance(condition_id, str) and condition_id in _CONDITIONS else "unknown"
    )
    night = condition.endswith("_night") or str(day_period or "day").strip().lower() == "night"
    palette = _PALETTES[pack_id]
    canvas = QPixmap(target_size, target_size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(target_size / 128.0, target_size / 128.0)
    try:
        if pack_id == "pixel_weather":
            _pixel_art(painter, condition, night, palette)
            return canvas
        if pack_id == "orbit_weather":
            painter.setBrush(QColor("#14243b" if night else "#24354d"))
            painter.setPen(_pen(palette.outline, 1.6))
            painter.drawEllipse(QRectF(7, 7, 114, 114))
            painter.save()
            painter.translate(64, 64)
            painter.rotate(-28)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            orbit_pen = _pen(palette.outline, 1.4)
            orbit_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(orbit_pen)
            painter.drawEllipse(QRectF(-59, -29, 118, 58))
            painter.restore()
            painter.translate(16, 17)
            painter.scale(0.75, 0.75)
        clear = condition.startswith("clear_")
        partly = condition.startswith("partly_cloudy_")
        if clear:
            if night:
                _moon(painter, QPointF(57, 64), 31, pack_id, palette)
            else:
                _sun(painter, QPointF(64, 64), 29, pack_id, palette)
        else:
            if partly or night:
                if night:
                    _moon(painter, QPointF(46, 34), 20, pack_id, palette)
                else:
                    _sun(painter, QPointF(44, 38), 18, pack_id, palette)
            cloud_top = 36 if partly or condition == "cloudy" else 30
            _cloud(painter, cloud_top, pack_id, palette)
            if condition == "fog":
                for index, (left, right) in enumerate(((21, 103), (31, 94), (20, 105))):
                    painter.setPen(_pen(palette.rain, 3 if pack_id != "vintage_weather" else 1.5))
                    painter.drawLine(
                        QPointF(left, 87 + index * 10), QPointF(right, 87 + index * 10)
                    )
            elif condition == "unknown":
                question = QPainterPath()
                question.moveTo(57, 46)
                question.cubicTo(53, 36, 77, 37, 73, 48)
                question.cubicTo(72, 52, 63, 51, 63, 59)
                painter.setPen(_pen(palette.outline, 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(question)
                painter.drawPoint(QPointF(63, 66))
            else:
                _precipitation(painter, condition, pack_id, palette)
    finally:
        painter.end()
    return canvas


__all__ = ["VECTOR_WEATHER_PACK_IDS", "render_weather_vector"]
