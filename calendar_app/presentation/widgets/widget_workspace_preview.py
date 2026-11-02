# -*- coding: utf-8 -*-
"""Bounded native snapshots and read-only widget health, with no new data requests."""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime

from PyQt6.QtCore import QBuffer, QIODevice, QPoint, QRectF, QSize
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import QWidget

from calendar_app.infrastructure.i18n import t


def widget_health(widget, kind, *, now=None):
    """Return a small status from existing data, never trigger a refresh."""
    if kind == "weather":
        data = getattr(widget, "_weather_data", {})
        error = str(data.get("error") or "")
        if error:
            return (
                "delayed",
                t("widget_studio.health_delayed", "데이터 지연"),
                str(getattr(widget, "_status_text", error)),
            )
        stamp = data.get("fetched_at")
        if stamp:
            try:
                fetched = datetime.fromisoformat(str(stamp))
                fetched = fetched.replace(tzinfo=UTC) if fetched.tzinfo is None else fetched
                if ((now or datetime.now(UTC)) - fetched).total_seconds() > 7200:
                    return (
                        "delayed",
                        t("widget_studio.health_delayed", "데이터 지연"),
                        t("widget_studio.weather_old", "마지막 날씨 갱신이 2시간 이전입니다"),
                    )
            except (ValueError, TypeError):
                pass
        if data.get("temp") in {None, "--"}:
            return (
                "normal",
                t("widget_studio.health_waiting", "날씨 대기"),
                str(getattr(widget, "_status_text", "")),
            )
        return (
            "normal",
            t("widget_studio.health_normal", "정상"),
            str(getattr(widget, "_status_text", "")),
        )
    if kind == "countdown" and hasattr(widget, "_cd_target_dt") and widget._cd_target_dt() is None:
        return (
            "setup",
            t("widget_studio.health_setup", "설정 필요"),
            t("widget_studio.countdown_setup", "설정에서 목표 시간을 지정하세요"),
        )
    if kind == "dday" and hasattr(widget, "_dd_target_date") and widget._dd_target_date() is None:
        return (
            "setup",
            t("widget_studio.health_setup", "설정 필요"),
            t("widget_studio.dday_setup", "설정에서 목표 날짜를 지정하세요"),
        )
    return "normal", t("widget_studio.health_normal", "정상"), ""


def native_thumbnail(widget, size=QSize(280, 160), *, opacity=None, frame_size=None):
    """Render into a fixed pixel budget without showing or resizing the source window."""
    size = QSize(max(80, min(640, size.width())), max(60, min(400, size.height())))
    dpr = min(2.0, widget.devicePixelRatioF())
    canvas = QPixmap(round(size.width() * dpr), round(size.height() * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(QColor("#152534"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size.width(), size.height())
    gradient.setColorAt(0, QColor("#304a61"))
    gradient.setColorAt(1, QColor("#162534"))
    painter.fillRect(QRectF(0, 0, size.width(), size.height()), gradient)
    source = widget.size()
    source = QSize(max(1, source.width()), max(1, source.height()))
    target = frame_size or source
    scale = min(
        (size.width() - 16) / max(1, target.width()), (size.height() - 16) / max(1, target.height())
    )
    frame = QRectF(
        (size.width() - target.width() * scale) / 2,
        (size.height() - target.height() * scale) / 2,
        target.width() * scale,
        target.height() * scale,
    )
    if frame_size is not None:
        painter.setPen(QColor("#91baff"))
        painter.drawRoundedRect(frame, 5, 5)
    render_scale = min(frame.width() / source.width(), frame.height() / source.height())
    painter.translate(
        frame.center().x() - source.width() * render_scale / 2,
        frame.center().y() - source.height() * render_scale / 2,
    )
    painter.scale(render_scale, render_scale)
    alpha = widget.windowOpacity() if opacity is None else max(0.1, min(1.0, opacity / 100))
    painter.setOpacity(alpha)
    try:
        widget.render(
            painter,
            QPoint(),
            QRegion(),
            QWidget.RenderFlag.DrawWindowBackground | QWidget.RenderFlag.DrawChildren,
        )
    finally:
        painter.end()
    return canvas


class ThumbnailCache:
    def __init__(self):
        self.items = OrderedDict()

    def get(self, iid, widget, *, fresh=False):
        key = (iid, widget.width(), widget.height())
        if fresh or key not in self.items:
            for previous in [item for item in self.items if item[0] == iid]:
                self.items.pop(previous)
            self.items[key] = native_thumbnail(widget)
            while len(self.items) > 48:
                self.items.popitem(last=False)
        self.items.move_to_end(key)
        return self.items[key]

    def clear(self):
        self.items.clear()


def thumbnail_icon(pixmap):
    """Selection is conveyed by the card border, preserving the actual widget colours."""
    result = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
        for state in (QIcon.State.On, QIcon.State.Off):
            result.addPixmap(pixmap, mode, state)
    return result


def workspace_thumbnail(manager):
    canvas = QPixmap(440, 220)
    canvas.fill(QColor("#172738"))
    rows = [row for row in manager.all_instances() if row[3].is_enabled()]
    if not rows:
        return ""
    bounds = rows[0][3].geometry()
    for row in rows[1:]:
        bounds = bounds.united(row[3].geometry())
    scale = min(420 / max(1, bounds.width()), 200 / max(1, bounds.height()))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for _, _, _, widget in rows[:32]:
        rect = widget.geometry()
        target = QRectF(
            10 + (rect.x() - bounds.x()) * scale,
            10 + (rect.y() - bounds.y()) * scale,
            max(4, rect.width() * scale),
            max(4, rect.height() * scale),
        )
        thumbnail = native_thumbnail(widget)
        painter.drawPixmap(target, thumbnail, QRectF(thumbnail.rect()))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    canvas.save(buffer, "JPG", 85)
    return bytes(buffer.data().toBase64()).decode("utf-8", errors="strict")
