# -*- coding: utf-8 -*-
"""Paint a live split-flap clock with independent, hinged digit cards."""

from functools import lru_cache
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFontMetricsF,
    QImageReader,
    QLinearGradient,
    QPainterPath,
    QPen,
    QPixmap,
)

from calendar_app.app_paths import get_resource_path
from calendar_app.presentation.widgets.widget_graphic_catalog import graphic_collection


def clock_flip_text(data: dict) -> str:
    return f"{data.get('main', '')}{data.get('minor', '')}"


@lru_cache(maxsize=3)
def _sticker_frames(sticker: str) -> tuple[QPixmap, ...]:
    """Decode a bounded set of bundled GIF frames shared by all clocks."""
    reader = QImageReader(get_resource_path("flipbook", f"{sticker}.gif"))
    size = reader.size()
    if not size.isValid() or max(size.width(), size.height()) > 144:
        return ()
    frames = []
    for _ in range(min(16, reader.imageCount())):
        frame = reader.read()
        if frame.isNull():
            break
        frames.append(QPixmap.fromImage(frame))
    return tuple(frames)


def _paint_half(painter, rect, path, char, font, ink, color, *, top, scale=1.0, shade=0.0):
    if scale <= 0.005:
        return
    hinge = rect.center().y()
    half = QRectF(rect)
    if top:
        half.setBottom(hinge)
    else:
        half.setTop(hinge)
    painter.save()
    painter.translate(0, hinge)
    painter.scale(1, scale)
    painter.translate(0, -hinge)
    painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
    painter.setClipRect(half, Qt.ClipOperation.IntersectClip)
    gradient = QLinearGradient(half.topLeft(), half.bottomLeft())
    gradient.setColorAt(0, color.lighter(105))
    gradient.setColorAt(1, color)
    painter.fillRect(half, gradient)
    painter.setFont(font)
    painter.setPen(ink)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, char)
    if shade > 0:
        painter.fillRect(half, QColor(0, 0, 0, round(shade * 255)))
    painter.restore()


def _paint_digit(surface, painter, rect, current, previous, font, ink, upper, lower):
    radius = min(10.0, rect.width() * 0.17)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    phase = surface._blend
    flipping = previous != current and phase < 1.0

    shadow = QColor(13, 26, 43, round(surface.background_alpha * 42))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shadow)
    painter.drawRoundedRect(rect.translated(0, 2), radius, radius)
    _paint_half(painter, rect, path, current, font, ink, upper, top=True)
    _paint_half(painter, rect, path, previous if flipping else current, font, ink, lower, top=False)
    if flipping:
        fold = math.cos(math.pi * phase)
        front = fold > 0
        _paint_half(
            painter,
            rect,
            path,
            previous if front else current,
            font,
            ink,
            upper if front else lower,
            top=front,
            scale=abs(fold),
            shade=(1 - abs(fold)) * 0.24,
        )

    center = rect.center().y()
    painter.setPen(QPen(QColor(17, 25, 38, round(surface.background_alpha * 110)), 1))
    painter.drawLine(QPointF(rect.left() + 1, center), QPointF(rect.right() - 1, center))


def _chip(painter, box, background, alpha):
    fill = QColor(background)
    fill.setAlphaF(alpha)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    radius = min(8, box.height() / 2)
    painter.drawRoundedRect(box, radius, radius)


def paint_flipbook_clock(surface, painter):
    width, height = surface.width(), surface.height()
    pad = min(23.0, max(7.0, width * 0.055))
    inner = QRectF(pad, pad, max(1.0, width - 2 * pad), max(1.0, height - 2 * pad))
    fg, muted, accent = surface._palette()
    design = graphic_collection(surface.collection_id)
    sticker = design.clock_sticker if design else ""
    frames = _sticker_frames(sticker) if sticker else ()
    badge_size = min(66.0, inner.width() * 0.30, inner.height() * 0.33) if frames else 0.0
    surface._text_bounds = []
    details = height >= 106 and width >= 150
    period = surface.data.get("ampm", "")
    header_height = max(21 if details and not sticker else 20 if period else 0, badge_size)
    footer_height = 24 if details else 0
    header = QRectF(inner.left(), inner.top(), inner.width(), header_height)
    if details and not sticker:
        surface._label(painter, surface.data.get("title", ""), header, 12, muted, bold=True)
    if period:
        if sticker:
            label_width = min(inner.width() - badge_size, 55.0)
            top = inner.bottom() - footer_height + 2 if details else inner.top()
            header = QRectF(inner.left(), top, label_width, 20)
            _chip(painter, header, surface.background, surface.background_alpha)
        surface._label(
            painter,
            period,
            header,
            12,
            muted,
            align=Qt.AlignmentFlag.AlignHCenter if sticker else Qt.AlignmentFlag.AlignRight,
        )
    if frames:
        frame_number = (
            min(len(frames) - 1, int(surface._blend * len(frames))) if surface._flip_from else 0
        )
        frame = frames[frame_number]
        badge = QRectF(inner.right() - badge_size, inner.top(), badge_size, badge_size)
        painter.drawPixmap(badge, frame, QRectF(frame.rect()))
    value = clock_flip_text(surface.data) or "--:--"
    previous = surface._flip_from or value
    weights = [0.42 if char == ":" else 1.0 for char in value]
    face_height = max(1.0, inner.height() - header_height - footer_height)
    stride = min(inner.width() / sum(weights), face_height * 0.72, 102.0)
    gap = min(5.0, stride * 0.13)
    tile_width = stride - gap
    tile_height = min(face_height, tile_width * 1.42)
    tile_top = inner.top() + header_height + (face_height - tile_height) / 2
    x = inner.center().x() - stride * sum(weights) / 2
    size = min(tile_height * 0.8, tile_width * 1.24)
    font = surface._font(size, True)
    while font.pixelSize() > 6:
        metrics = QFontMetricsF(font)
        if (
            metrics.height() <= tile_height
            and max(metrics.horizontalAdvance(d) for d in "0123456789") <= tile_width * 0.92
        ):
            break
        font.setPixelSize(font.pixelSize() - 1)
    dark_ink = QColor(fg).lightness() < 128
    if sticker:
        background = QColor(surface.background)
        upper, lower = background.lighter(108), background.darker(104)
    else:
        upper = QColor("#fbfcff" if dark_ink else "#344154")
        lower = QColor("#dce4ef" if dark_ink else "#202b3b")
    upper.setAlphaF(surface.background_alpha)
    lower.setAlphaF(surface.background_alpha)
    ink = surface._ink(fg)
    for index, (char, weight) in enumerate(zip(value, weights, strict=True)):
        if char == ":":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(surface._ink(accent, 0.86))
            center_x = x + stride * weight / 2
            dot = max(1.0, min(3.0, stride * 0.065))
            for offset in (0.40, 0.60):
                painter.drawEllipse(QPointF(center_x, tile_top + tile_height * offset), dot, dot)
        else:
            rect = QRectF(x + gap / 2, tile_top, tile_width, tile_height)
            prior = previous[index] if index < len(previous) else char
            _paint_digit(surface, painter, rect, char, prior, font, ink, upper, lower)
            surface._text_bounds.append(rect)
        x += stride * weight
    if details:
        footer = QRectF(inner.left(), inner.bottom() - footer_height, inner.width(), footer_height)
        detail = surface.data.get("detail", "").strip()
        if sticker and detail:
            if period:
                footer.setLeft(header.right() + 4)
            width = min(
                footer.width(), QFontMetricsF(surface._font(11)).horizontalAdvance(detail) + 18
            )
            x = footer.center().x() - width / 2
            footer = QRectF(x, footer.top() + 2, width, 20)
            _chip(painter, footer, surface.background, surface.background_alpha)
        surface._label(
            painter,
            detail,
            footer,
            11,
            muted,
            align=Qt.AlignmentFlag.AlignHCenter,
        )
