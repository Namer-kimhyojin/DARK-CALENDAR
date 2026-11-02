# -*- coding: utf-8 -*-
"""Native premium weather cards, cached artwork and visibility-aware animation.

The surface owns no settings, database or network access. Gallery previews and
the real overlay use this same painter; preview surfaces never start timers.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime
import math
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImageReader,
    QLinearGradient,
    QMovie,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.weather_asset_packs import (
    weather_asset_pixmap,
    weather_condition_id,
)

SCENE_IDS = ("air_atmosphere", "soft_object", "editorial_mono")
_ART_CACHE: OrderedDict[tuple, QPixmap] = OrderedDict()
_ART_BUDGET = 24 * 1024 * 1024


def cached_weather_art(pack: str, wmo: int, period: str, size: int, dpr: float) -> QPixmap:
    """Reuse decoded, DPR-aware art within a bounded pixel-memory budget."""
    size = max(16, min(320, round(size / 8) * 8))
    dpr = max(1.0, min(3.0, round(dpr, 2)))
    key = (pack, wmo, period, size, dpr)
    if key not in _ART_CACHE:
        pixmap = weather_asset_pixmap(pack, wmo, period, round(size * dpr))
        pixmap.setDevicePixelRatio(dpr)
        _ART_CACHE[key] = pixmap
        while (
            len(_ART_CACHE) > 1
            and sum(p.width() * p.height() * 4 for p in _ART_CACHE.values()) > _ART_BUDGET
        ):
            _ART_CACHE.popitem(last=False)
    _ART_CACHE.move_to_end(key)
    return _ART_CACHE[key]


def system_allows_weather_motion() -> bool:
    """Respect Windows' animation preference and Battery Saver, without polling per frame."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        enabled = ctypes.c_int(1)
        if (
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
            and not enabled.value
        ):
            return False

        class PowerStatus(ctypes.Structure):
            _fields_ = [
                ("ac", ctypes.c_ubyte),
                ("flags", ctypes.c_ubyte),
                ("percent", ctypes.c_ubyte),
                ("saver", ctypes.c_ubyte),
                ("remaining", ctypes.c_ulong),
                ("full", ctypes.c_ulong),
            ]

        power = PowerStatus()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)) and power.saver == 1:
            return False
    except (AttributeError, OSError):
        pass
    return True


class WeatherSceneSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("weatherSceneSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)
        self.data: dict = {}
        self.scene_id = SCENE_IDS[0]
        self.pack = "air_soft"
        self.family = "Segoe UI"
        self.motion = "subtle"
        self.hourly = True
        self.background_alpha = 1.0
        self.text_alpha = 1.0
        self.shadow = False
        self.shadow_opacity = 65
        self.shadow_blur = 8
        self.shadow_distance = 2
        self.shadow_color = "#000000"
        self.foreground = ""
        self.background_override = ""
        self.text_scale = 1.0
        self.auto_contrast = True
        self.graphic_design = ""
        self._design_surface = None
        self.status = ""
        self.animation_dir = ""
        self._active = False
        self._policy_allowed = True
        self._studio_motion_mode = "balanced"
        self._studio_motion_paused = False
        self._started = time.monotonic()
        self._layer: QPixmap | None = None
        self._layer_dpr = 0.0
        self._art_rect = QRectF()
        self._movie: QMovie | None = None
        self._movie_key = None
        self._ticks = 0
        self._previous_art: QPixmap | None = None
        self._transition_started = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._animate)
        self._policy_timer = QTimer(self)
        self._policy_timer.setInterval(60_000)
        self._policy_timer.timeout.connect(self._check_policy)
        self.setMinimumSize(0, 0)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(360, 350)

    def configure(
        self,
        *,
        scene_id: str,
        data: dict,
        pack: str = "air_soft",
        family: str = "Segoe UI",
        motion: str = "subtle",
        hourly: bool = True,
        background_alpha: float = 1.0,
        text_alpha: float = 1.0,
        shadow: bool = False,
        shadow_opacity: int = 65,
        shadow_blur: int = 8,
        shadow_distance: int = 2,
        shadow_color: str = "#000000",
        foreground: str = "",
        background_override: str = "",
        text_scale: float = 1.0,
        auto_contrast: bool = True,
        graphic_design: str = "",
        status: str = "",
        animation_dir: str = "",
    ) -> None:
        data = deepcopy(data) if isinstance(data, dict) else {}
        hours = data.get("hourly")
        data["hourly"] = (
            [dict(item) for item in hours[:6] if isinstance(item, dict)]
            if isinstance(hours, list)
            else []
        )
        for item in data["hourly"]:
            try:
                value = float(item.get("precip_mm"))
                item["precip_mm"] = value if math.isfinite(value) and value >= 0 else None
            except (TypeError, ValueError, OverflowError):
                item["precip_mm"] = None
        values = dict(
            scene_id=scene_id if scene_id in SCENE_IDS else SCENE_IDS[0],
            data=deepcopy(data),
            pack=pack,
            family=family,
            motion=motion if motion in {"off", "subtle", "full"} else "subtle",
            hourly=bool(hourly),
            background_alpha=max(0.0, min(1.0, background_alpha)),
            text_alpha=max(0.0, min(1.0, text_alpha)),
            shadow=shadow,
            shadow_opacity=shadow_opacity,
            shadow_blur=shadow_blur,
            shadow_distance=shadow_distance,
            shadow_color=shadow_color,
            foreground=foreground,
            background_override=background_override,
            text_scale=max(0.65, min(1.5, text_scale)),
            auto_contrast=bool(auto_contrast),
            graphic_design=str(graphic_design or ""),
            status=str(status or ""),
            animation_dir=str(animation_dir or ""),
        )
        changed = any(getattr(self, key) != value for key, value in values.items())
        if not changed:
            return
        if self.data and any(
            self.data.get(key) != data.get(key) for key in ("_wmo", "_day_period")
        ):
            self._previous_art = cached_weather_art(
                self.pack,
                self._wmo(),
                self.data.get("_day_period", "day"),
                round(self._art_rect.width()),
                self.devicePixelRatioF(),
            )
            self._transition_started = time.monotonic()
        for key, value in values.items():
            setattr(self, key, value)
        self._invalidate()
        self._sync_motion()
        self.setAccessibleName(self._accessible_text())
        self.setToolTip(self._accessible_text())

    def set_runtime_active(self, active: bool) -> None:
        self._active = bool(active)
        self._check_policy()

    def _check_policy(self) -> None:
        self._policy_allowed = system_allows_weather_motion()
        self._sync_motion()

    def _sync_motion(self) -> None:
        eligible = (
            self._active
            and self.isVisible()
            and self.motion != "off"
            and self._studio_motion_mode != "static"
            and not self._studio_motion_paused
        )
        live = eligible and self._policy_allowed
        if eligible:
            if not self._policy_timer.isActive():
                self._policy_timer.start()
        else:
            self._policy_timer.stop()
        if live:
            if self._movie is not None:
                self._timer.stop()
                self._movie.start()
                self._movie.setPaused(False)
            elif not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            if self._movie is not None:
                self._movie.setPaused(True)
            self.update()

    def set_motion_policy(self, mode, paused=False):
        state = (mode, bool(paused))
        if state == (self._studio_motion_mode, self._studio_motion_paused):
            return
        self._studio_motion_mode, self._studio_motion_paused = state
        self._timer.setInterval(33 if mode == "rich" else 50)
        self._sync_motion()

    def _animate(self) -> None:
        self._ticks += 1
        self.update(self._art_rect.adjusted(-5, -5, 5, 5).toAlignedRect())

    def _invalidate(self) -> None:
        self._layer = None
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._invalidate()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._check_policy()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._policy_timer.stop()
        if self._movie is not None:
            self._movie.setPaused(True)
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._active = False
        self._sync_motion()
        if self._movie is not None:
            self._movie.stop()
        super().closeEvent(event)

    def layout_tier(self) -> str:
        if self.width() < 250 or self.height() < 190:
            return "compact"
        return "expanded" if self.width() >= 300 and self.height() >= 330 else "standard"

    def _palette(self) -> tuple[str, str, str, str]:
        palette = self._base_palette()
        if self.foreground:
            color = QColor(self.foreground)
            muted = color.darker(128) if color.lightness() > 128 else color.lighter(165)
            palette = (*palette[:2], self.foreground, muted.name())
        if self.background_override:
            palette = (
                self.background_override,
                QColor(self.background_override).darker(112).name(),
                *palette[2:],
            )
        if self.auto_contrast and self.background_alpha > 0.1:
            from calendar_app.presentation.widgets.widget_graphics import readable_foreground

            fg = readable_foreground(palette[2], palette[0], palette[1])
            muted = (
                QColor(fg).darker(128) if QColor(fg).lightness() > 128 else QColor(fg).lighter(155)
            )
            palette = (*palette[:2], fg, muted.name())
        return palette

    def _base_palette(self) -> tuple[str, str, str, str]:
        if self.scene_id == "soft_object":
            return "#f5f8ff", "#dce9f4", "#1c334b", "#48647c"
        if self.scene_id == "editorial_mono":
            return "#f7f5ef", "#eae7de", "#25372f", "#58645c"
        condition = weather_condition_id(self._wmo(), self.data.get("_day_period", "day"))
        if self.data.get("_day_period") in {"night", "twilight"}:
            return "#24395c", "#101c35", "#f4f7ff", "#b5c7e4"
        if condition in {"rain", "heavy_rain", "drizzle", "thunderstorm", "hail"}:
            return "#314e66", "#152c43", "#f5f9ff", "#bed2e2"
        if condition in {"snow", "heavy_snow", "fog"}:
            return "#426d85", "#213b53", "#f7fbff", "#c9dce7"
        if condition == "cloudy":
            return "#445c73", "#26394f", "#f7fbff", "#c1d0df"
        return "#266b9a", "#143b62", "#f7fbff", "#c1dfef"

    def _wmo(self) -> int:
        try:
            return int(self.data.get("_wmo", -1))
        except (TypeError, ValueError, OverflowError):
            return -1

    def _color(self, value: str, alpha: float = 1.0, *, background=False) -> QColor:
        color = QColor(value)
        color.setAlphaF(
            max(0.0, min(1.0, alpha * (self.background_alpha if background else self.text_alpha)))
        )
        return color

    def _font(self, size: float, bold=False) -> QFont:
        font = QFont(self.family)
        font.setPixelSize(max(8, round(size * self.text_scale)))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return font

    def _text(self, painter, text, x, baseline, size, color, *, bold=False, width=None):
        font = self._font(size, bold)
        painter.setFont(font)
        if width is not None:
            text = QFontMetricsF(font).elidedText(
                str(text), Qt.TextElideMode.ElideRight, max(0, width)
            )
        if self.shadow:
            shadow_color = QColor(self.shadow_color)
            gain = (
                0.35 if self.auto_contrast and QColor(self._palette()[0]).lightness() > 128 else 1.0
            )
            shadow_color.setAlpha(
                round(255 * self.text_alpha * self.shadow_opacity / 100 / 5 * gain)
            )
            painter.setPen(shadow_color)
            radius = self.shadow_blur / 4
            for dx, dy in ((0, 0), (-radius, 0), (radius, 0), (0, -radius), (0, radius)):
                painter.drawText(QPointF(x + dx, baseline + self.shadow_distance + dy), str(text))
        painter.setPen(self._color(color))
        painter.drawText(QPointF(x, baseline), str(text))

    def _accessible_text(self) -> str:
        fields = [self.data.get(key, "") for key in ("city", "temp", "unit", "desc")]
        fields += [
            f"{item.get('label', '')} {item.get('temp', '')}°"
            for item in self.data.get("hourly", [])
            if isinstance(item, dict)
        ]
        return " · ".join(str(field) for field in fields if field) + (
            " · " + self.status if self.status else ""
        )

    def _paint_static(self, painter: QPainter) -> None:
        from calendar_app.presentation.widgets.widget_graphic_catalog import graphic_collection

        design = graphic_collection(self.graphic_design)
        if design and design.widget_kind == "weather":
            self._paint_collection_static(painter, design)
            return
        w, h = self.width(), self.height()
        tier = self.layout_tier()
        compact = tier == "compact"
        hourly = self.data.get("hourly") or []
        expanded = tier == "expanded" and self.hourly and bool(hourly)
        scale = max(
            0.65,
            min(
                1.6,
                w / (220 if compact else 360),
                h / (140 if compact else 350 if expanded else 240),
            ),
        )
        pad = max(12, min(30, w * 0.065))
        top, bottom, fg, muted = self._palette()
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, max(0, w - 2), max(0, h - 2)), 24 * scale, 24 * scale)
        painter.setClipPath(path)
        gradient = QLinearGradient(0, 0, w * 0.8, h)
        gradient.setColorAt(0, self._color(top, background=True))
        gradient.setColorAt(1, self._color(bottom, background=True))
        painter.fillPath(path, gradient)
        glow = QRadialGradient(QPointF(w * 0.82, h * 0.15), w * 0.68)
        glow.setColorAt(0, self._color("#ffffff", 0.13, background=True))
        glow.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, glow)
        painter.setPen(
            QPen(
                self._color(
                    "#ffffff" if self.scene_id == "air_atmosphere" else "#587186",
                    0.20,
                    background=True,
                ),
                1,
            )
        )
        painter.drawPath(path)

        city = str(self.data.get("city", "--"))
        self._text(
            painter, city, pad, pad + 12 * scale, 14 * scale, fg, bold=True, width=w - 2 * pad
        )
        temp_size = (45 if compact else 66) * scale
        temp_y = min(h * 0.64, pad + (67 if compact else 89) * scale)
        metrics_y = h - (183 if expanded else 43) * min(1.15, scale)
        if expanded:
            temp_y = min(temp_y, metrics_y - 72 * scale)
        temp = str(self.data.get("temp", "--"))
        art_size = min(w * (0.38 if compact else 0.43), h * (0.55 if compact else 0.45), 220)
        if expanded:
            art_size = min(art_size, h - 165 * min(1.15, scale) - pad - 30 * scale)
        self._art_rect = QRectF(w - pad - art_size, pad + 22 * scale, art_size, art_size)
        available = max(30, self._art_rect.left() - pad - 6)
        while (
            QFontMetricsF(self._font(temp_size, True)).horizontalAdvance(temp) > available
            and temp_size > 22
        ):
            temp_size -= 1
        self._text(painter, temp, pad, temp_y, temp_size, fg, bold=True)
        temp_width = QFontMetricsF(self._font(temp_size, True)).horizontalAdvance(temp)
        self._text(
            painter,
            self.data.get("unit", "°C"),
            pad + temp_width + 3,
            temp_y - temp_size * 0.42,
            max(12, temp_size * 0.32),
            fg,
        )
        desc_y = min(h - 20, temp_y + 27 * scale)
        self._text(
            painter, self.data.get("desc", "--"), pad, desc_y, 14 * scale, fg, width=w - 2 * pad
        )
        if compact:
            if self.data.get("error") or self.data.get("_forecast_expired"):
                self._text(
                    painter, t("weather_premium.previous", "이전 예보"), pad, h - 9, 9, muted
                )
            return

        range_y = min(desc_y + 27 * scale, metrics_y - 21 * scale)
        if self.data.get("forecast_high") not in (None, "--") and range_y > desc_y + 12:
            label = t(
                "weather_premium.range",
                "남은 오늘 {low}° / {high}°",
                low=self.data.get("forecast_low", "--"),
                high=self.data.get("forecast_high", "--"),
            )
            self._text(painter, label, pad, range_y, 11 * scale, muted, width=w - 2 * pad)
        metrics = t(
            "weather_premium.metrics",
            "습도 {humidity}%  ·  바람 {wind} m/s",
            humidity=self.data.get("humidity", "--"),
            wind=self.data.get("wind", "--"),
        )
        self._text(painter, metrics, pad, metrics_y, 11 * scale, muted, width=w - 2 * pad)
        if expanded:
            self._paint_hourly(painter, hourly[:6], pad, h, scale, fg, muted)
        self._text(
            painter, self._freshness(), pad, h - 15 * scale, 9 * scale, muted, width=w - 2 * pad
        )

    def _paint_collection_static(self, painter, design) -> None:
        from calendar_app.presentation.widgets.overlay_shadow import TextShadow
        from calendar_app.presentation.widgets.widget_graphics import WidgetGraphicSurface

        if self._design_surface is None:
            self._design_surface = WidgetGraphicSurface(self)
            self._design_surface.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._design_surface.hide()
        surface = self._design_surface
        hourly = self.data.get("hourly") or []
        expanded = self.layout_tier() == "expanded" and self.hourly and bool(hourly)
        height = max(100, self.height() - 165) if expanded else self.height()
        surface.resize(self.width(), height)
        _, _, foreground, _ = self._palette()
        surface.configure(
            kind="weather",
            collection_id=design.collection_id,
            data={
                "title": self.data.get("city", "--"),
                "main": self.data.get("temp", "--"),
                "minor": self.data.get("unit", "°C"),
                "detail": str(self.data.get("desc", "--"))
                + (
                    "  "
                    + t(
                        "weather_premium.range",
                        "남은 오늘 {low}° / {high}°",
                        low=self.data.get("forecast_low", "--"),
                        high=self.data.get("forecast_high", "--"),
                    )
                    if self.data.get("forecast_high") not in (None, "--")
                    else ""
                ),
                "metrics": t(
                    "weather_premium.metrics",
                    "습도 {humidity}%  ·  바람 {wind} m/s",
                    humidity=self.data.get("humidity", "--"),
                    wind=self.data.get("wind", "--"),
                ),
            },
            family=self.family,
            foreground=foreground,
            background=self.background_override or design.background,
            background_alpha=self.background_alpha,
            text_alpha=self.text_alpha,
            shadow=TextShadow(
                enabled=self.shadow,
                opacity=self.shadow_opacity,
                blur=self.shadow_blur,
                distance=self.shadow_distance,
                color=self.shadow_color,
            ),
            motion=False,
            auto_contrast=self.auto_contrast,
            text_scale=self.text_scale,
        )
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 22, 22)
        painter.setClipPath(clip)
        surface.resize(self.width(), self.height())
        painter.drawPixmap(0, 0, surface._paint_background())
        surface.resize(self.width(), height)
        surface._paint_content(painter)
        self._art_rect = QRectF(surface._design_art_rect)
        if expanded:
            # Keep forecast data and native artwork animation on the original surface.
            pad = max(12, min(30, self.width() * 0.065))
            _, _, fg, muted = self._palette()
            self._paint_hourly(painter, hourly[:6], pad, self.height(), 1, fg, muted)
        status = self._freshness()
        if status:
            self._text(
                painter, status, 16, self.height() - 7, 8, foreground, width=self.width() - 32
            )
        painter.restore()

    def _paint_hourly(self, painter, hourly, pad, h, scale, fg, muted) -> None:
        base = min(1.15, scale)
        line_y = h - 165 * base
        painter.setPen(QPen(self._color(muted, 0.25), 1))
        painter.drawLine(QPointF(pad, line_y), QPointF(self.width() - pad, line_y))
        self._text(
            painter,
            t("weather_premium.upcoming", "시간별 예보"),
            pad,
            line_y + 23 * base,
            10 * scale,
            muted,
        )
        col = (self.width() - 2 * pad) / max(1, len(hourly))
        for index, item in enumerate(hourly):
            if not isinstance(item, dict):
                continue
            center = pad + col * (index + 0.5)
            time_text = str(item.get("label", "--"))
            width = QFontMetricsF(self._font(10 * scale)).horizontalAdvance(time_text)
            self._text(painter, time_text, center - width / 2, h - 114 * base, 10 * scale, muted)
            size = max(18, min(32 * scale, col - 8))
            try:
                wmo = int(item.get("_wmo", -1))
            except (TypeError, ValueError, OverflowError):
                wmo = -1
            art = cached_weather_art(
                self.pack,
                wmo,
                item.get("_day_period", "day"),
                round(size),
                self.devicePixelRatioF(),
            )
            painter.drawPixmap(
                QRectF(center - size / 2, h - 103 * base, size, size), art, QRectF(art.rect())
            )
            text = f"{item.get('temp', '--')}°"
            width = QFontMetricsF(self._font(12 * scale, True)).horizontalAdvance(text)
            self._text(painter, text, center - width / 2, h - 58 * base, 12 * scale, fg, bold=True)
            amount = item.get("precip_mm")
            rain = "—" if amount is None else f"{amount:g} mm"
            width = QFontMetricsF(self._font(8 * scale)).horizontalAdvance(rain)
            self._text(painter, rain, center - width / 2, h - 37 * base, 8 * scale, muted)

    def _freshness(self) -> str:
        if self.status == t("widget.weather.loading", "날씨를 불러오는 중…"):
            return self.status
        if self.data.get("error"):
            return self.status or t("weather_premium.previous", "이전 예보")
        if self.data.get("_forecast_expired"):
            return t("weather_premium.previous", "이전 예보")
        if self.status and not self.data.get("fetched_at"):
            return self.status
        try:
            zone = ZoneInfo(str(self.data.get("timezone", "UTC")))
        except (ZoneInfoNotFoundError, ValueError):
            zone = UTC
        values = []
        for key, label in (
            ("forecast_time", "weather_premium.forecast_at"),
            ("fetched_at", "weather_premium.fetched_at"),
        ):
            try:
                stamp = datetime.fromisoformat(str(self.data[key]).replace("Z", "+00:00"))
                values.append(
                    t(
                        label,
                        "예보 {time}" if key == "forecast_time" else "갱신 {time}",
                        time=stamp.astimezone(zone).strftime("%H:%M"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                pass
        return " · ".join(values)

    def _sync_movie(self) -> None:
        condition = weather_condition_id(self._wmo(), self.data.get("_day_period", "day"))
        key = (
            self.animation_dir,
            condition,
            round(self._art_rect.width()),
            round(self.devicePixelRatioF(), 2),
        )
        if key == self._movie_key:
            return
        self._movie_key = key
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if self.animation_dir:
            for suffix in ("webp", "gif"):
                filename = Path(self.animation_dir) / f"{condition}.{suffix}"
                try:
                    if not filename.is_file() or filename.stat().st_size > 16 * 1024 * 1024:
                        continue
                    reader = QImageReader(str(filename))
                    dimensions = reader.size()
                    if (
                        not dimensions.isValid()
                        or dimensions.width() * dimensions.height() > 16_777_216
                    ):
                        continue
                    movie = QMovie(str(filename), parent=self)
                    movie.setCacheMode(QMovie.CacheMode.CacheNone)
                    size = max(
                        16, min(640, round(self._art_rect.width() * self.devicePixelRatioF()))
                    )
                    movie.setScaledSize(QSize(size, size))
                    if not movie.isValid():
                        movie.deleteLater()
                        continue
                    self._movie = movie
                    movie.frameChanged.connect(
                        lambda _frame: self.update(
                            self._art_rect.adjusted(-4, -4, 4, 4).toAlignedRect()
                        )
                    )
                    movie.error.connect(self._movie_failed)
                    movie.jumpToFrame(0)
                    movie.setSpeed(min(100, max(10, movie.nextFrameDelay() * 2)))
                    break
                except (OSError, ValueError):
                    continue
        self._sync_motion()

    def _movie_failed(self, _error) -> None:
        movie, self._movie = self._movie, None
        if movie is not None:
            movie.stop()
            movie.deleteLater()
        self._sync_motion()
        self.update()

    def _paint_art(self, painter: QPainter) -> None:
        rect = self._art_rect
        live = self._timer.isActive()
        phase = (time.monotonic() - self._started) / 4 if live else 0
        amplitude = 1.0 if self.motion == "subtle" else 2.2
        offset = math.sin(phase * math.tau) * amplitude if live else 0
        painter.save()
        painter.translate(0, offset)
        pixmap = (
            self._movie.currentPixmap()
            if self._movie is not None
            else cached_weather_art(
                self.pack,
                self._wmo(),
                self.data.get("_day_period", "day"),
                round(rect.width()),
                self.devicePixelRatioF(),
            )
        )
        if not pixmap.isNull():
            mix = min(1.0, (time.monotonic() - self._transition_started) / 0.25) if live else 1.0
            if self._previous_art is not None and mix < 1:
                painter.setOpacity(self.text_alpha * (1 - mix))
                painter.drawPixmap(rect, self._previous_art, QRectF(self._previous_art.rect()))
            else:
                self._previous_art = None
            painter.setOpacity(self.text_alpha * mix)
            painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
        painter.setOpacity(1)
        painter.restore()
        if not live:
            return
        condition = weather_condition_id(self._wmo(), self.data.get("_day_period", "day"))
        painter.save()
        painter.setClipRect(rect)
        if condition in {"clear_day", "partly_cloudy_day", "thunderstorm"}:
            flash = 0.04 * (1 + math.sin(phase * math.tau))
            if condition == "thunderstorm":
                flash = 0.12 if phase % 1 < 0.08 else 0
            glow = QRadialGradient(rect.center(), rect.width() * 0.45)
            glow.setColorAt(0, self._color("#fff2c9", flash))
            glow.setColorAt(1, QColor(255, 255, 255, 0))
            painter.fillRect(rect, glow)
        if condition == "fog":
            painter.setPen(QPen(self._color("#d2efff", 0.28), 2))
            for i in range(3):
                shift = math.sin(phase * math.tau + i) * rect.width() * 0.04
                y = rect.top() + rect.height() * (0.64 + i * 0.08)
                painter.drawLine(
                    QPointF(rect.left() + rect.width() * 0.2 + shift, y),
                    QPointF(rect.right() - rect.width() * 0.2 + shift, y),
                )
        if condition in {
            "rain",
            "heavy_rain",
            "drizzle",
            "snow",
            "heavy_snow",
            "hail",
            "thunderstorm",
        }:
            snow = condition in {"snow", "heavy_snow", "hail"}
            painter.setPen(QPen(self._color("#d2efff", 0.7), 1.4))
            for i in range(7 if self.motion == "subtle" else 12):
                x = rect.left() + rect.width() * (0.20 + (i * 0.137) % 0.65)
                y = rect.top() + rect.height() * (
                    0.56 + ((phase * (0.6 if snow else 1.7) + i * 0.23) % 1) * 0.38
                )
                if snow:
                    painter.drawEllipse(QPointF(x + math.sin(phase + i) * 3, y), 1.5, 1.5)
                else:
                    painter.drawLine(QPointF(x, y), QPointF(x - 2.5, y + 6))
        elif self.data.get("_day_period") == "night":
            for i in range(5):
                alpha = 0.25 + 0.5 * (math.sin(phase * 2 + i) + 1) / 2
                painter.setPen(self._color("#f5e9bb", alpha))
                x, y = (
                    rect.left() + rect.width() * (0.1 + i * 0.19),
                    rect.top() + rect.height() * (0.15 + (i % 2) * 0.16),
                )
                painter.drawEllipse(QPointF(x, y), 1.2, 1.2)
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if self.width() <= 1 or self.height() <= 1:
            return
        dpr = self.devicePixelRatioF()
        if self._layer is None or self._layer_dpr != dpr:
            self._layer_dpr = dpr
            self._layer = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
            self._layer.setDevicePixelRatio(dpr)
            self._layer.fill(Qt.GlobalColor.transparent)
            static = QPainter(self._layer)
            static.setRenderHint(QPainter.RenderHint.Antialiasing)
            static.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._paint_static(static)
            static.end()
            self._sync_movie()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self._layer)
        self._paint_art(painter)
        painter.end()


def render_scene_preview(
    scene_id: str,
    data: dict,
    size: QSize,
    *,
    pack="air_soft",
    dpr=1.0,
    foreground="",
    background_alpha=1.0,
    text_alpha=1.0,
    family="Segoe UI",
    background_override="",
    graphic_design="",
) -> QPixmap:
    """Render a static, settings-free preview using the production card surface."""
    surface = WeatherSceneSurface()
    surface.resize(360, 350)
    surface.configure(
        scene_id=scene_id,
        data=data,
        pack=pack,
        motion="off",
        foreground=foreground,
        background_alpha=background_alpha,
        text_alpha=text_alpha,
        family=family,
        background_override=background_override,
        graphic_design=graphic_design,
    )
    canvas = QPixmap(round(size.width() * dpr), round(size.height() * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(QColor("#101b2b"))
    painter = QPainter(canvas)
    scale = min((size.width() - 12) / 360, (size.height() - 12) / 350)
    painter.translate((size.width() - 360 * scale) / 2, (size.height() - 350 * scale) / 2)
    painter.scale(scale, scale)
    surface.render(painter)
    painter.end()
    surface.deleteLater()
    return canvas
