# -*- coding: utf-8 -*-
"""Shared graphic collections and native, responsive faces for overlay widgets."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import math

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget

from calendar_app.presentation.widgets.clock_flipbook import clock_flip_text, paint_flipbook_clock
from calendar_app.presentation.widgets.moment_asset_packs import moment_asset_pixmap
from calendar_app.presentation.widgets.weather_asset_packs import _trim_transparent
from calendar_app.presentation.widgets.weather_scene import system_allows_weather_motion
from calendar_app.presentation.widgets.widget_graphic_catalog import (
    CLOCK_FLIPBOOK_COLLECTION_IDS,
    COLLECTIONS,
    graphic_collection,
)
from calendar_app.shared.typography import DEFAULT_UI_FONT, ui_font_families


def contrast_ratio(first: str, second: str) -> float:
    def luminance(raw):
        color = QColor(raw)
        channels = [color.redF(), color.greenF(), color.blueF()]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


def readable_foreground(foreground: str, *backgrounds: str) -> str:
    if all(contrast_ratio(foreground, background) >= 4.5 for background in backgrounds):
        return foreground
    return max(
        ("#f7faff", "#162536"),
        key=lambda color: min(contrast_ratio(color, bg) for bg in backgrounds),
    )


def keydeck_collection_deck(deck: dict, collection_id: str) -> dict:
    """Change colour/lighting only in a copy; actions, geometry and personal art survive."""
    from calendar_app.presentation.widgets.keydeck.model import beatmaker_state

    result = deepcopy(deck)
    palettes = {
        "pure_air": ("#17212d", "#2b3a4d", "#91baff"),
        "soft_object": ("#e0e8f1", "#f1f5f9", "#6497bd"),
        "air_instrument": ("#14242b", "#263b43", "#79d6d2"),
    }
    design = graphic_collection(collection_id)
    if design and design.widget_kind == "launcher_deck":
        palettes[collection_id] = (
            design.background,
            QColor(design.accent).lighter(125).name(),
            design.accent,
        )
    if collection_id not in palettes:
        return result
    case, cap, accent = palettes[collection_id]
    result["case"].update(color=case, accent=accent)
    for page in result["pages"]:
        performance = beatmaker_state(page) is not None
        for key in page["keys"]:
            if performance and key.get("action", {}).get("type") == "sound":
                continue
            key["cap"]["color"] = cap
            key["led"]["color"] = accent
            if key["insert"]["kind"] not in {"image", "panorama"}:
                key["insert"].update(color=cap, color2=QColor(cap).darker(115).name())
                key["legend"]["color"] = readable_foreground("#f5f8ff", cap)
    return result


def keydeck_visual_values(deck: dict) -> dict:
    return {
        "case": {field: deck["case"][field] for field in ("color", "accent")},
        "keys": {
            key["id"]: {
                group: {field: key[group].get(field) for field in fields}
                for group, fields in (
                    ("cap", ("color",)),
                    ("legend", ("color",)),
                    ("led", ("color",)),
                    ("insert", ("color", "color2")),
                )
            }
            for page in deck["pages"]
            for key in page["keys"]
        },
    }


@lru_cache(maxsize=16)
def _moment_art(pack: str, moment: str, size: int) -> QPixmap:
    return _trim_transparent(moment_asset_pixmap(pack, moment, max(16, min(600, size))))


class WidgetGraphicSurface(QWidget):
    """Information graphics only; data, settings and timers stay with the owner."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.collection_id = "pure_air"
        self.kind = "clock"
        self.data: dict = {}
        self.family = DEFAULT_UI_FONT
        self.foreground = "#f5f7fb"
        self.background = "#101a28"
        self.background_alpha = 0.0
        self.text_alpha = 1.0
        self.motion = True
        self.auto_contrast = True
        self.text_scale = 1.0
        self.shadow = None
        self._active = False
        self._studio_motion_mode = "balanced"
        self._studio_motion_paused = False
        self._layer: QPixmap | None = None
        self._background_layer: QPixmap | None = None
        self._old_layer: QPixmap | None = None
        self._flip_from: str | None = None
        self._blend = 1.0
        self._text_bounds: list[QRectF] = []
        self._transition = QVariantAnimation(self)
        self._transition.setDuration(180)
        self._transition.setStartValue(0.0)
        self._transition.setEndValue(1.0)
        self._transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._transition.valueChanged.connect(self._blend_changed)
        self._transition.finished.connect(self._finish_transition)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 220)

    def configure(
        self,
        *,
        kind: str,
        collection_id: str,
        data: dict,
        family: str,
        foreground: str,
        background: str,
        background_alpha: float,
        text_alpha: float,
        shadow=None,
        motion=True,
        auto_contrast=True,
        text_scale=1.0,
    ) -> None:
        style = (
            kind,
            collection_id,
            family,
            foreground,
            background,
            background_alpha,
            text_alpha,
            shadow,
            motion,
            auto_contrast,
            max(0.65, min(1.5, float(text_scale))),
        )
        previous_style = (
            self.kind,
            self.collection_id,
            self.family,
            self.foreground,
            self.background,
            self.background_alpha,
            self.text_alpha,
            self.shadow,
            self.motion,
            self.auto_contrast,
            self.text_scale,
        )
        if style == previous_style and data == self.data:
            return
        state_changed = bool(self.data) and any(
            self.data.get(key) != data.get(key) for key in ("running", "done")
        )
        previous_second = self.data.get("clock_second_of_day")
        current_second = data.get("clock_second_of_day")
        flip_changed = (
            kind == "clock"
            and collection_id in CLOCK_FLIPBOOK_COLLECTION_IDS
            and style == previous_style
            and previous_second is not None
            and current_second is not None
            and (current_second - previous_second) % 86400 in (1, 2)
            and clock_flip_text(self.data) != clock_flip_text(data)
        )
        if (
            (state_changed or flip_changed)
            and self._active
            and self.isVisible()
            and motion
            and self._studio_motion_mode != "static"
            and not self._studio_motion_paused
            and system_allows_weather_motion()
        ):
            self._transition.stop()
            self._old_layer = None if flip_changed else self._layer
            self._flip_from = clock_flip_text(self.data) if flip_changed else None
            self._transition.setDuration(360 if flip_changed else 180)
            self._transition.setEasingCurve(
                QEasingCurve.Type.Linear if flip_changed else QEasingCurve.Type.OutCubic
            )
            self._transition.start()
        elif self._flip_from is not None:
            self._transition.stop()
            self._finish_transition()
        if style != previous_style:
            self._background_layer = None
        (
            self.kind,
            self.collection_id,
            self.family,
            self.foreground,
            self.background,
            self.background_alpha,
            self.text_alpha,
            self.shadow,
            self.motion,
            self.auto_contrast,
            self.text_scale,
        ) = style
        self.data = dict(data)
        self._layer = None
        if not motion:
            self._transition.stop()
            self._finish_transition()
        full = str(data.get("accessible", ""))
        self.setAccessibleName(full)
        self.setToolTip(full)
        self.update()

    def set_runtime_active(self, active: bool) -> None:
        self._active = bool(active)
        if not active:
            self._transition.stop()
            self._finish_transition()

    def set_motion_policy(self, mode, paused=False):
        if (mode, bool(paused)) == (self._studio_motion_mode, self._studio_motion_paused):
            return
        self._studio_motion_mode, self._studio_motion_paused = mode, bool(paused)
        if mode == "static" or paused:
            self._transition.stop()
            self._finish_transition()

    def _blend_changed(self, value) -> None:
        self._blend = float(value)
        self.update()

    def _finish_transition(self) -> None:
        self._old_layer, self._flip_from, self._blend = None, None, 1.0
        self.update()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._transition.stop()
        self._finish_transition()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._layer = self._background_layer = None
        self._transition.stop()
        self._finish_transition()
        super().resizeEvent(event)

    def _font(self, size: float, bold=False) -> QFont:
        font = QFont(self.family)
        font.setFamilies(ui_font_families(self.family))
        font.setPixelSize(max(6, round(size * self.text_scale)))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return font

    def _ink(self, color: str, opacity=1.0) -> QColor:
        ink = QColor(color)
        ink.setAlphaF(max(0.0, min(1.0, self.text_alpha * opacity)))
        return ink

    def _label(
        self,
        painter,
        text: str,
        box: QRectF,
        size: float,
        color: str,
        *,
        bold=False,
        wrap=False,
        align=Qt.AlignmentFlag.AlignLeft,
    ):
        text = str(text or "")
        flags = int(align | Qt.AlignmentFlag.AlignVCenter)
        if wrap:
            flags |= int(Qt.TextFlag.TextWordWrap)
        size = min(size, max(6, box.height() * 0.8 / self.text_scale))
        while size > 9:
            metrics = QFontMetricsF(self._font(size, bold))
            needed = metrics.boundingRect(box, flags, text)
            if needed.width() <= box.width() + 0.5 and needed.height() <= box.height() + 0.5:
                break
            size -= 1
        font = self._font(size, bold)
        painter.setFont(font)
        if not wrap:
            text = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, box.width())
        if self.shadow is not None and self.shadow.active:
            shadow = QColor(self.shadow.color)
            gain = 0.4 if self.auto_contrast and QColor(self.background).lightness() > 128 else 1.0
            shadow.setAlphaF(self.text_alpha * self.shadow.opacity / 100 * 0.07 * gain)
            painter.setPen(shadow)
            radius = self.shadow.blur / 4
            for dx, dy in ((0, 0), (-radius, 0), (radius, 0), (0, -radius), (0, radius)):
                painter.drawText(box.translated(dx, self.shadow.distance + dy), flags, text)
        painter.setPen(self._ink(color))
        painter.drawText(box, flags, text)
        self._text_bounds.append(QRectF(box))

    def _number(self, painter, main: str, minor: str, box: QRectF, size: float, color: str) -> None:
        # A fixed cell for every digit keeps positions steady even in proportional fonts.
        def dimensions(font_size):
            major = QFontMetricsF(self._font(font_size, True))
            small = QFontMetricsF(self._font(font_size * 0.43))
            cell = max(major.horizontalAdvance(c) for c in "0123456789")
            little = max(small.horizontalAdvance(c) for c in "0123456789")
            width = sum(cell if c.isdigit() else major.horizontalAdvance(c) for c in main)
            width += sum(little if c.isdigit() else small.horizontalAdvance(c) for c in minor)
            return width, cell, little

        size = min(size, box.height() * 0.8 / self.text_scale)
        while size > 6 and dimensions(size)[0] > box.width():
            size -= 1
        _, cell, little = dimensions(size)
        x = box.left()
        baseline = box.center().y() + QFontMetricsF(self._font(size, True)).ascent() * 0.33
        painter.setPen(self._ink(color))
        for value, font_size, advance, bold in (
            (main, size, cell, True),
            (minor, size * 0.43, little, False),
        ):
            font = self._font(font_size, bold)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            for char in value:
                width = advance if char.isdigit() else metrics.horizontalAdvance(char)
                px = x + (width - metrics.horizontalAdvance(char)) / 2
                if self.shadow is not None and self.shadow.active:
                    shade = QColor(self.shadow.color)
                    gain = (
                        0.4
                        if self.auto_contrast and QColor(self.background).lightness() > 128
                        else 1.0
                    )
                    shade.setAlphaF(self.text_alpha * self.shadow.opacity / 100 * 0.07 * gain)
                    painter.setPen(shade)
                    radius = self.shadow.blur / 4
                    for dx, dy in ((0, 0), (-radius, 0), (radius, 0), (0, -radius), (0, radius)):
                        painter.drawText(
                            QPointF(px + dx, baseline + self.shadow.distance + dy), char
                        )
                painter.setPen(self._ink(color, 1 if bold else 0.78))
                painter.drawText(QPointF(px, baseline), char)
                x += width
        self._text_bounds.append(QRectF(box))

    def _palette(self):
        collection = graphic_collection(self.collection_id) or COLLECTIONS[0]
        fg = self.foreground
        if self.auto_contrast and self.background_alpha > 0.1:
            fg = readable_foreground(fg, self.background)
        base = QColor(fg)
        muted = base.darker(135) if base.lightness() > 128 else base.lighter(155)
        return fg, muted.name(), collection.accent

    def _pixmap(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr)))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    def _paint_background(self) -> QPixmap:
        pixmap = self._pixmap()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        design = graphic_collection(self.collection_id)
        if self.background_alpha > 0 and not (design and design.clock_sticker):
            path = QPainterPath()
            radius = min(24, self.height() * 0.13)
            path.addRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), radius, radius)
            gradient = QLinearGradient(0, 0, self.width() * 0.7, self.height())
            first, last = QColor(self.background).lighter(105), QColor(self.background)
            first.setAlphaF(self.background_alpha)
            last.setAlphaF(self.background_alpha)
            gradient.setColorAt(0, first)
            gradient.setColorAt(1, last)
            painter.fillPath(path, gradient)
            border = QColor("#ffffff" if QColor(self.background).lightness() < 128 else "#66849e")
            border.setAlphaF(0.17 * self.background_alpha)
            painter.setPen(QPen(border, 1))
            painter.drawPath(path)
        from calendar_app.presentation.widgets.widget_graphic_layouts import paint_design_decoration

        paint_design_decoration(self, painter)
        painter.end()
        return pixmap

    def _paint_design_moment(self, painter, rect):
        art = _moment_art(
            str(self.data.get("art_pack", "air_moments")),
            str(self.data.get("moment", "calm")),
            round(rect.width() * self.devicePixelRatioF() / 16) * 16,
        )
        if not art.isNull():
            painter.drawPixmap(rect, art, QRectF(art.rect()))

    def _dial(
        self,
        painter,
        rect: QRectF,
        accent: str,
        *,
        hour=None,
        minute=None,
        seconds=None,
        progress=None,
    ):
        painter.save()
        center, radius = rect.center(), rect.width() / 2
        painter.setPen(QPen(self._ink(accent, 0.18), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect.adjusted(3, 3, -3, -3))
        for i in range(60):
            angle = math.tau * i / 60 - math.pi / 2
            length = 8 if i % 5 == 0 else 3
            painter.setPen(QPen(self._ink(accent, 0.65 if i % 5 == 0 else 0.26), 1.4))
            start = QPointF(
                center.x() + math.cos(angle) * (radius - 4),
                center.y() + math.sin(angle) * (radius - 4),
            )
            end = QPointF(
                center.x() + math.cos(angle) * (radius - 4 - length),
                center.y() + math.sin(angle) * (radius - 4 - length),
            )
            painter.drawLine(start, end)
        if progress is not None:
            painter.setPen(
                QPen(self._ink(accent), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawArc(
                rect.adjusted(3, 3, -3, -3), 90 * 16, -round(360 * 16 * max(0, min(1, progress)))
            )
        for value, maximum, length, width in (
            (hour, 12, 0.48, 3.5),
            (minute, 60, 0.73, 2),
            (seconds, 60, 0.78, 1),
        ):
            if value is None:
                continue
            angle = math.tau * float(value) / maximum - math.pi / 2
            painter.setPen(
                QPen(self._ink(accent), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(
                center,
                QPointF(
                    center.x() + radius * length * math.cos(angle),
                    center.y() + radius * length * math.sin(angle),
                ),
            )
        painter.restore()

    def _paint_content(self, painter) -> None:
        if self.kind == "clock" and self.collection_id in CLOCK_FLIPBOOK_COLLECTION_IDS:
            paint_flipbook_clock(self, painter)
            return
        design = graphic_collection(self.collection_id)
        if design and design.widget_kind:
            from calendar_app.presentation.widgets.widget_graphic_layouts import (
                paint_design_content,
            )

            self._design_art_rect = paint_design_content(self, painter)
            return
        w, h = self.width(), self.height()
        pad = max(12, min(28, w * 0.065))
        inner = QRectF(pad, pad, max(1, w - 2 * pad), max(1, h - 2 * pad))
        scale = max(0.65, min(1.6, w / 320, h / 200))
        fg, muted, accent = self._palette()
        self._text_bounds = []
        compact = w < 250 or h < 150
        instrument = self.collection_id == "air_instrument" and not compact
        kind = self.kind
        title = str(self.data.get("title", ""))
        if kind != "text":
            self._label(
                painter,
                title,
                QRectF(inner.left(), inner.top(), inner.width(), 24 * scale),
                13 * scale,
                muted,
            )
        hero = QRectF(
            inner.left(),
            inner.top() + 26 * scale,
            inner.width(),
            max(24, inner.height() - 65 * scale),
        )
        footer = QRectF(inner.left(), inner.bottom() - 22 * scale, inner.width(), 24 * scale)
        if kind in {"clock", "stopwatch", "countdown"}:
            if instrument:
                size = min(inner.height() - 25, inner.width() * 0.39)
                dial = QRectF(
                    inner.right() - size, inner.top() + (inner.height() - size) / 2, size, size
                )
                hero.setWidth(max(30, inner.width() - size - 12))
                self._dial(
                    painter,
                    dial,
                    accent,
                    hour=self.data.get("hour") if kind == "clock" else None,
                    minute=self.data.get("minute") if kind == "clock" else None,
                    seconds=self.data.get("second") if kind != "countdown" else None,
                    progress=self.data.get("progress") if kind == "countdown" else None,
                )
            urgent = bool(self.data.get("urgent"))
            number_color = (
                "#d68b4c"
                if urgent and QColor(self.background).lightness() > 128
                else "#ffd09c"
                if urgent
                else fg
            )
            self._number(
                painter,
                str(self.data.get("main", "--:--")),
                str(self.data.get("minor", "")),
                hero,
                66 * scale,
                number_color,
            )
            if not compact:
                status = str(self.data.get("detail", ""))
                if kind == "stopwatch":
                    painter.setBrush(self._ink(accent if self.data.get("running") else muted, 0.9))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QPointF(inner.left() + 3, footer.center().y()), 3, 3)
                    footer.adjust(14, 0, 0, 0)
                self._label(painter, status, footer, 12 * scale, muted)
        elif kind in {"date_card", "dday"}:
            art_space = 0
            if self.collection_id == "soft_object" and not compact:
                art_space = min(inner.width() * 0.42, inner.height() * 0.8)
                art = _moment_art(
                    str(self.data.get("art_pack", "air_moments")),
                    str(self.data.get("moment", "calm")),
                    round(art_space * self.devicePixelRatioF() / 16) * 16,
                )
                if not art.isNull():
                    rect = QRectF(
                        inner.right() - art_space, inner.top() + 25 * scale, art_space, art_space
                    )
                    painter.drawPixmap(rect, art, QRectF(art.rect()))
                    hero.setWidth(max(40, inner.width() - art_space - 8))
            self._number(
                painter,
                str(self.data.get("main", "--")),
                "",
                hero,
                (88 if kind == "date_card" else 65) * scale,
                fg,
            )
            if not compact:
                detail = str(self.data.get("detail", ""))
                detail_box = QRectF(footer)
                if kind == "dday" and self.data.get("date"):
                    detail_box.translate(0, -22 * scale)
                    self._label(painter, detail, detail_box, 14 * scale, fg, bold=True)
                    self._label(painter, self.data["date"], footer, 11 * scale, muted)
                else:
                    self._label(painter, detail, footer, 12 * scale, muted)
        else:
            body = str(self.data.get("body", ""))
            align = {
                "left": Qt.AlignmentFlag.AlignLeft,
                "center": Qt.AlignmentFlag.AlignHCenter,
                "right": Qt.AlignmentFlag.AlignRight,
            }.get(self.data.get("alignment", "left"), Qt.AlignmentFlag.AlignLeft)
            title_box = QRectF(inner.left(), inner.top() + 2, inner.width(), 40 * scale)
            self._label(
                painter, title, title_box, (24 if body else 38) * scale, fg, bold=True, align=align
            )
            if body:
                body_box = QRectF(
                    inner.left(),
                    title_box.bottom() + 14 * scale,
                    inner.width(),
                    max(15, inner.bottom() - title_box.bottom() - 14 * scale),
                )
                self._label(
                    painter,
                    body[:8192],
                    body_box,
                    15 * scale,
                    muted,
                    wrap=bool(self.data.get("wrap", True)),
                    align=align,
                )
            if self.collection_id == "air_instrument":
                painter.setPen(QPen(self._ink(accent), 2))
                painter.drawLine(
                    QPointF(inner.left(), title_box.bottom() + 7),
                    QPointF(inner.left() + 38, title_box.bottom() + 7),
                )

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if self.width() < 2 or self.height() < 2:
            return
        expected = QSize(
            round(self.width() * self.devicePixelRatioF()),
            round(self.height() * self.devicePixelRatioF()),
        )
        if self._background_layer is None or self._background_layer.size() != expected:
            self._background_layer = self._paint_background()
            self._layer = None
        flipping = self._flip_from is not None
        layer = self._layer
        if layer is None or flipping:
            layer = self._pixmap()
            painter = QPainter(layer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._paint_content(painter)
            painter.end()
            if not flipping:
                self._layer = layer
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._background_layer)
        if self._old_layer is not None:
            painter.setOpacity(1 - self._blend)
            painter.drawPixmap(0, 0, self._old_layer)
        painter.setOpacity(1.0 if flipping else self._blend)
        painter.drawPixmap(0, 0, layer)
        painter.end()
