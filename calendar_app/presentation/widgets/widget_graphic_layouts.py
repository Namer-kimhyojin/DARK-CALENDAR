# -*- coding: utf-8 -*-
"""Native painter compositions shared by the per-widget graphic design catalog."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPen, QRadialGradient

from calendar_app.presentation.widgets.widget_graphic_catalog import graphic_collection


def paint_design_decoration(surface, painter):
    design = graphic_collection(surface.collection_id)
    if design is None or not design.widget_kind:
        return
    w, h = surface.width(), surface.height()
    _, _, accent = surface._palette()
    painter.save()
    painter.setOpacity(surface.background_alpha)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(2, 2, w - 4, h - 4), 22, 22)
    painter.setClipPath(clip)
    painter.setPen(QPen(surface._ink(accent, 0.17), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    layout = design.layout
    if layout == "flip":
        painter.fillRect(QRectF(w * 0.07, h * 0.25, w * 0.86, h * 0.48), surface._ink(accent, 0.06))
        painter.drawLine(QPointF(w * 0.07, h * 0.49), QPointF(w * 0.93, h * 0.49))
        painter.drawLine(QPointF(w * 0.5, h * 0.25), QPointF(w * 0.5, h * 0.73))
    elif layout == "orbit":
        painter.drawEllipse(QRectF(w * 0.08, h * 0.22, h * 0.56, h * 0.56))
        painter.setPen(QPen(surface._ink(accent, 0.08), 10))
        painter.drawEllipse(QRectF(w * 0.08 + 8, h * 0.22 + 8, h * 0.56 - 16, h * 0.56 - 16))
    elif layout == "split":
        painter.fillRect(QRectF(w * 0.61, 0, w * 0.39, h), surface._ink(accent, 0.08))
        painter.drawLine(QPointF(w * 0.61, h * 0.1), QPointF(w * 0.61, h * 0.9))
    elif layout == "ribbon":
        painter.fillRect(QRectF(0, 0, w, h * 0.25), surface._ink(accent, 0.14))
        painter.fillRect(QRectF(0, h * 0.25, w, 2), surface._ink(accent, 0.5))
    elif layout == "glass":
        glow = QRadialGradient(QPointF(w * 0.81, h * 0.22), max(w, h) * 0.7)
        glow.setColorAt(0, surface._ink("#ffffff", 0.65))
        glow.setColorAt(1, surface._ink(accent, 0.02))
        painter.fillRect(QRectF(0, 0, w, h), glow)
        painter.drawRoundedRect(QRectF(7, 7, w - 14, h - 14), 18, 18)
    elif layout == "terminal":
        painter.setPen(QPen(surface._ink(accent, 0.07), 1))
        for x in range(18, w, 18):
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        for y in range(18, h, 18):
            painter.drawLine(QPointF(0, y), QPointF(w, y))
        painter.setPen(QPen(surface._ink(accent, 0.4), 2))
        painter.drawLine(QPointF(18, h - 26), QPointF(w - 18, h - 26))
    elif layout == "editorial":
        painter.fillRect(QRectF(0, 0, 6, h), surface._ink(accent, 0.85))
        painter.drawLine(QPointF(24, h * 0.72), QPointF(w - 24, h * 0.72))
    elif layout == "ticket":
        painter.setPen(QPen(surface._ink(accent, 0.45), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(w * 0.76, 12), QPointF(w * 0.76, h - 12))
        for y in (2, h - 2):
            painter.drawEllipse(QPointF(w * 0.76, y), 7, 7)
    elif layout == "arch":
        painter.setPen(QPen(surface._ink(accent, 0.2), 12))
        painter.drawArc(QRectF(w * 0.17, h * 0.13, w * 0.66, h * 1.1), 0, 180 * 16)
    else:
        painter.fillRect(QRectF(0, h * 0.76, w, h * 0.24), surface._ink(accent, 0.09))
        painter.setPen(QPen(surface._ink(accent, 0.6), 2))
        painter.drawLine(QPointF(18, 18), QPointF(42, 18))
        painter.drawLine(QPointF(w - 18, h - 18), QPointF(w - 42, h - 18))
    painter.restore()


def paint_design_content(surface, painter):
    """Return the weather artwork slot; ordinary faces draw their own optional art."""
    design = graphic_collection(surface.collection_id)
    w, h = surface.width(), surface.height()
    pad = max(10, min(26, w * 0.065))
    inner = QRectF(pad, pad, max(1, w - pad * 2), max(1, h - pad * 2))
    scale = min(1.5, max(0.6, min(w / 320, h / 220)))
    compact = w < 220 or h < 135
    kind, data = surface.kind, surface.data
    layout = design.layout
    fg, muted, accent = surface._palette()
    surface._text_bounds = []
    title = str(data.get("title", ""))
    main = str(data.get("main", "--"))
    minor = str(data.get("minor", ""))
    detail = str(data.get("detail", ""))
    title_box = QRectF(inner.left(), inner.top(), inner.width(), 24 * scale)
    hero = QRectF(
        inner.left(), inner.top() + 28 * scale, inner.width(), max(20, inner.height() - 66 * scale)
    )
    footer = QRectF(inner.left(), inner.bottom() - 24 * scale, inner.width(), 24 * scale)
    side = QRectF()
    art = QRectF()
    align = {
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
    }.get(data.get("alignment"), Qt.AlignmentFlag.AlignLeft)

    if compact:
        if kind == "weather":
            size = min(inner.height() * 0.6, inner.width() * 0.34)
            art = QRectF(inner.right() - size, hero.top(), size, size)
            hero.setWidth(max(25, inner.width() - size - 4))
        surface._label(painter, title, title_box, 12 * scale, muted, align=align)
        if kind == "text":
            surface._label(
                painter,
                str(data.get("body", "")),
                hero,
                13 * scale,
                fg,
                wrap=bool(data.get("wrap", True)),
                align=align,
            )
        else:
            surface._number(painter, main, minor, hero, 65 * scale, fg)
        return art

    if layout == "orbit":
        size = min(inner.height() - 30 * scale, inner.width() * 0.47)
        orbit = QRectF(inner.left(), inner.top() + 27 * scale, size, size)
        side = QRectF(
            orbit.right() + 16 * scale,
            hero.top(),
            inner.right() - orbit.right() - 16 * scale,
            hero.height(),
        )
        if kind in {"clock", "stopwatch", "countdown"}:
            surface._dial(
                painter,
                orbit,
                accent,
                hour=data.get("hour") if kind == "clock" else None,
                minute=data.get("minute") if kind == "clock" else None,
                seconds=data.get("second") if kind != "countdown" else None,
                progress=data.get("progress") if kind == "countdown" else None,
            )
            hero = QRectF(side)
        elif kind == "weather":
            art, hero = orbit, QRectF(side)
        elif kind != "text":
            hero = orbit.adjusted(8 * scale, 8 * scale, -8 * scale, -8 * scale)
    elif layout == "split":
        split = w * 0.61
        hero.setWidth(max(30, split - pad - 12 * scale))
        side = QRectF(
            split + 12 * scale, hero.top(), max(20, w - split - pad - 12 * scale), hero.height()
        )
    elif layout == "ticket":
        hero.setWidth(inner.width() * 0.75 - 8 * scale)
        side = QRectF(w * 0.78, hero.top(), max(20, w * 0.22 - pad), hero.height())
    elif layout == "ribbon":
        hero.translate(0, 10 * scale)
        hero.setHeight(max(20, hero.height() - 10 * scale))
    elif layout == "editorial":
        hero.setTop(inner.top() + 32 * scale)
        hero.setBottom(h * 0.70)
    elif layout == "arch":
        hero.adjust(18 * scale, 12 * scale, -18 * scale, -8 * scale)
    elif layout == "compact":
        hero.setTop(inner.top() + 20 * scale)
        hero.setBottom(h * 0.73)

    if kind == "text":
        body = str(data.get("body", ""))[:8192]
        if layout == "split":
            title_box = QRectF(hero)
            body_box = QRectF(side)
        else:
            title_box.setHeight(42 * scale)
            body_box = QRectF(
                inner.left(),
                title_box.bottom() + 16 * scale,
                inner.width(),
                max(18, inner.bottom() - title_box.bottom() - 16 * scale),
            )
            if layout == "ticket":
                title_box.setWidth(hero.width())
                body_box.setWidth(hero.width())
        surface._label(
            painter, title, title_box, (25 if body else 36) * scale, fg, bold=True, align=align
        )
        if body:
            surface._label(
                painter,
                body,
                body_box,
                15 * scale,
                muted,
                wrap=bool(data.get("wrap", True)),
                align=align,
            )
        return art

    surface._label(painter, title, title_box, 13 * scale, muted)
    if kind == "weather":
        if art.isEmpty():
            size = min(
                inner.height() * 0.66, inner.width() * (0.30 if layout == "ticket" else 0.39)
            )
            art = QRectF(inner.right() - size, hero.top(), size, size)
            if not side.isEmpty():
                size = min(size, side.width(), side.height())
                art = QRectF(side.center().x() - size / 2, side.center().y() - size / 2, size, size)
            else:
                hero.setWidth(max(30, inner.width() - size - 12 * scale))
        surface._number(painter, main, minor, hero, 68 * scale, fg)
        description = QRectF(footer)
        description.translate(0, -25 * scale)
        surface._label(painter, detail, description, 13 * scale, fg)
        surface._label(painter, str(data.get("metrics", "")), footer, 11 * scale, muted)
        return art

    if kind in {"date_card", "dday"} and layout in {"glass", "ribbon", "split", "ticket"}:
        size = min(inner.height() * 0.62, inner.width() * 0.35)
        art = QRectF(inner.right() - size, hero.top(), size, size)
        if not side.isEmpty():
            size = min(side.width(), side.height())
            art = QRectF(side.center().x() - size / 2, side.center().y() - size / 2, size, size)
        else:
            hero.setWidth(max(35, inner.width() - size - 12 * scale))
        surface._paint_design_moment(painter, art)
    number_color = accent if data.get("urgent") else fg
    surface._number(
        painter, main, minor, hero, (82 if kind == "date_card" else 64) * scale, number_color
    )
    if kind == "dday":
        target_box = QRectF(footer)
        target_box.translate(0, -22 * scale)
        surface._label(painter, detail, target_box, 13 * scale, fg, bold=True)
        surface._label(painter, str(data.get("date", "")), footer, 11 * scale, muted)
    elif kind in {"clock", "stopwatch", "countdown"} and layout in {"split", "ticket"}:
        surface._label(
            painter, detail, side, (12 if layout == "split" else 10) * scale, muted, wrap=True
        )
    else:
        surface._label(painter, detail, footer, 11 * scale, muted)
    return art
