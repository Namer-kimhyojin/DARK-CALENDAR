# -*- coding: utf-8 -*-
"""Bundled GIF postcards and a settings-free, visibility-aware native renderer."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QDate, QLocale, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QMovie, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QWidget

from calendar_app.app_paths import get_resource_path
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.weather_scene import system_allows_weather_motion
from calendar_app.shared.typography import ui_font_families


@dataclass(frozen=True)
class DateAnimation:
    animation_id: str
    label: str
    background: str
    foreground: str
    accent: str

    def title(self) -> str:
        return t(f"date_animation.{self.animation_id}", self.label)

    def filename(self) -> str:
        return get_resource_path("date_animations", f"{self.animation_id}.gif")


DATE_ANIMATIONS = (
    DateAnimation("sakura", "벚꽃 산책", "#fff4f2", "#593e4c", "#9c526b"),
    DateAnimation("ocean", "바다의 오후", "#edf9f6", "#234c55", "#256873"),
    DateAnimation("moon", "달빛 여우", "#24243e", "#fff3dc", "#e5bc80"),
    DateAnimation("forest", "반딧불 숲", "#eff0df", "#354536", "#55673d"),
    DateAnimation("coffee", "모닝 커피", "#fff3e3", "#654532", "#88562c"),
    DateAnimation("cat", "구름 고양이", "#f3edfa", "#524565", "#72559a"),
)
_BY_ID = {item.animation_id: item for item in DATE_ANIMATIONS}


def date_animation(animation_id: object) -> DateAnimation:
    return _BY_ID.get(str(animation_id), DATE_ANIMATIONS[0])


class AnimatedDateSurface(QWidget):
    """Paint live date text separately from GIF frames; previews never write settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("animatedDateSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)
        self.animation = DATE_ANIMATIONS[0]
        self.day = QDate.currentDate()
        self.family = self.font().family()
        self.base_size = 30
        self.motion = True
        self._movie = None
        self._poster = QPixmap()
        self._active = False
        self._motion_mode = "balanced"
        self._motion_paused = False
        self._text_bounds = []

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(round(self.base_size * 8), round(self.base_size * 10.5))

    def configure(self, animation_id, *, family=None, base_size=30, motion=True, day=None):
        selected = date_animation(animation_id)
        if self._movie is None or selected != self.animation:
            self._dispose_movie()
            self.animation = selected
            movie = QMovie(selected.filename(), parent=self)
            movie.setCacheMode(QMovie.CacheMode.CacheNone)
            if movie.isValid():
                movie.jumpToFrame(0)
                self._poster = movie.currentPixmap()
                movie.frameChanged.connect(self._frame_changed)
                self._movie = movie
            else:
                movie.deleteLater()
                self._poster = QPixmap()
        self.day = day if day is not None else QDate.currentDate()
        self.setAccessibleName(QLocale().toString(self.day, QLocale.FormatType.LongFormat))
        self.setAccessibleDescription(selected.title())
        self.family = family or self.font().family()
        size = max(6, int(base_size))
        if self.base_size != size:
            self.base_size = size
            self.updateGeometry()
        self.motion = bool(motion)
        self._sync_motion()
        self.update()

    def _frame_changed(self, _frame):
        self.update()

    def _dispose_movie(self):
        if self._movie is not None:
            self._movie.stop()
            self._movie.frameChanged.disconnect(self._frame_changed)
            self._movie.deleteLater()
            self._movie = None

    def set_runtime_active(self, active):
        self._active = bool(active)
        self._sync_motion()

    def set_motion_policy(self, mode, paused=False):
        self._motion_mode, self._motion_paused = mode, bool(paused)
        self._sync_motion()

    def _sync_motion(self):
        if self._movie is None:
            return
        live = (
            self._active
            and self.isVisible()
            and self.motion
            and self._motion_mode != "static"
            and not self._motion_paused
            and system_allows_weather_motion()
        )
        if live:
            if self._movie.state() == QMovie.MovieState.NotRunning:
                self._movie.start()
            elif self._movie.state() == QMovie.MovieState.Paused:
                self._movie.setPaused(False)
        elif self._movie.state() == QMovie.MovieState.Running:
            self._movie.setPaused(True)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._sync_motion()

    def hideEvent(self, event):  # noqa: N802
        if self._movie is not None:
            self._movie.setPaused(True)
        super().hideEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self._active = False
        self._dispose_movie()
        super().closeEvent(event)

    def _font(self, pixels, *, bold=False):
        font = QFont(self.family)
        font.setFamilies(ui_font_families(self.family))
        font.setPixelSize(max(6, round(pixels)))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return font

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        width, height = self.width(), self.height()
        if width < 1 or height < 1:
            painter.end()
            return
        card = QRectF(0, 0, width, height)
        clip = QPainterPath()
        radius = min(20, width * 0.08, height * 0.08)
        clip.addRoundedRect(card, radius, radius)
        painter.setClipPath(clip)
        painter.fillRect(card, QColor(self.animation.background))
        art_height = min(width, height * 0.69)
        art_rect = QRectF(0, 0, width, art_height)
        picture = self._movie.currentPixmap() if self._movie is not None else self._poster
        if not picture.isNull():
            ratio = max(width / picture.width(), art_height / picture.height())
            source = QRectF(
                (picture.width() - width / ratio) / 2,
                (picture.height() - art_height / ratio) / 2,
                width / ratio,
                art_height / ratio,
            )
            painter.drawPixmap(art_rect, picture, source)
        footer_height = height - art_height
        padding = min(width * 0.08, footer_height * 0.17)
        day_rect = QRectF(padding, art_height, width * 0.37, footer_height)
        detail_rect = QRectF(
            width * 0.45, art_height + padding, width * 0.55 - padding, footer_height - padding * 2
        )
        self._text_bounds = []

        def text(rect, value, pixels, color, bold=False):
            font = self._font(pixels, bold=bold)
            while (
                font.pixelSize() > 6 and QFontMetricsF(font).horizontalAdvance(value) > rect.width()
            ):
                font.setPixelSize(font.pixelSize() - 1)
            metrics = QFontMetricsF(font)
            painter.setFont(font)
            painter.setPen(QColor(color))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, value
            )
            self._text_bounds.append(
                QRectF(
                    rect.x(),
                    rect.center().y() - metrics.height() / 2,
                    min(rect.width(), metrics.horizontalAdvance(value)),
                    metrics.height(),
                )
            )

        text(
            day_rect,
            str(self.day.day()),
            min(width * 0.27, footer_height * 0.72),
            self.animation.foreground,
            True,
        )
        weekday_rect = QRectF(
            detail_rect.x(), detail_rect.y(), detail_rect.width(), detail_rect.height() * 0.55
        )
        month_rect = QRectF(
            detail_rect.x(), weekday_rect.bottom(), detail_rect.width(), detail_rect.height() * 0.45
        )
        text(
            weekday_rect,
            QLocale().toString(self.day, "dddd"),
            min(width * 0.068, footer_height * 0.19),
            self.animation.foreground,
            True,
        )
        text(
            month_rect,
            QLocale().toString(self.day, "yyyy. MM"),
            min(width * 0.058, footer_height * 0.16),
            self.animation.accent,
        )
        painter.end()
