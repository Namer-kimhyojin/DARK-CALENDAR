# -*- coding: utf-8 -*-
"""Task drag/drop compatibility helpers."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QDataStream, QIODevice, QMimeData, QPoint, QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QPixmap

from calendar_app.infrastructure import task_drop_service
from calendar_app.infrastructure.db import task_repo


def _safe_task_ids(widget, task_id):
    app = widget.window() if widget is not None else None
    selected = list(getattr(app, "selected_task_ids", []) or [])
    if task_id not in selected:
        selected = [task_id]
    return sorted(int(tid) for tid in selected)


def _write_int_list(task_ids):
    data = QByteArray()
    stream = QDataStream(data, QIODevice.OpenModeFlag.WriteOnly)
    stream.writeInt32(len(task_ids))
    for tid in task_ids:
        stream.writeInt32(int(tid))
    return data


def _span_days_for_task(task):
    try:
        st = (task or {}).get("deadline")
        et = (task or {}).get("end_date")
        if not st or not et:
            return 1
        from datetime import datetime

        d1 = datetime.fromisoformat(str(st).replace(" ", "T")).date()
        d2 = datetime.fromisoformat(str(et).replace(" ", "T")).date()
        return max(1, (d2 - d1).days + 1)
    except Exception:
        return 1


def _drag_color(tokens, key, fallback, alpha=None):
    color = QColor(tokens.get(key, fallback))
    if not color.isValid():
        color = QColor(fallback)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def build_task_drag_pixmap(task_ids, task_map=None):
    """Build the themed drag ghost shown while moving calendar tasks."""
    from calendar_app.infrastructure.i18n import t
    from calendar_app.shared.icon_map import ICON
    from calendar_app.shared.icon_map import icon as _ic
    from calendar_app.shared.ui_tokens import get_ui_tokens

    ids = list(task_ids or [])
    tasks = task_map or {}
    tokens = get_ui_tokens()
    count = max(1, len(ids))

    width, height = 252, 86
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    bg = _drag_color(tokens, "bg_alt", "#171c27", 246)
    surface = _drag_color(tokens, "bg_item", "#232a39", 238)
    accent = _drag_color(tokens, "accent", "#4da6ff", 255)
    text_primary = _drag_color(tokens, "text_primary", "#f4f7ff", 255)
    text_secondary = _drag_color(tokens, "text_secondary", "#a9b5c7", 255)

    # Soft shadow and offset sheets make multi-selection feel like a stack.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(0, 0, 0, 72)))
    painter.drawRoundedRect(QRect(8, 10, width - 14, height - 12), 14, 14)
    if count > 1:
        stacked = QColor(surface)
        stacked.setAlpha(116)
        painter.setBrush(QBrush(stacked))
        painter.drawRoundedRect(QRect(15, 2, width - 28, height - 12), 13, 13)
        stacked.setAlpha(170)
        painter.setBrush(QBrush(stacked))
        painter.drawRoundedRect(QRect(10, 5, width - 20, height - 12), 13, 13)

    card_rect = QRect(4, 8, width - 12, height - 14)
    border = QColor(accent)
    border.setAlpha(145)
    painter.setBrush(QBrush(bg))
    painter.setPen(QPen(border, 1.4))
    painter.drawRoundedRect(card_rect, 14, 14)

    # Accent rail and icon tile provide a strong grab-point silhouette.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(accent))
    painter.drawRoundedRect(QRect(4, 8, 5, height - 14), 3, 3)

    tile_fill = QColor(accent)
    tile_fill.setAlpha(42)
    tile_border = QColor(accent)
    tile_border.setAlpha(115)
    tile_rect = QRect(17, 20, 42, 42)
    painter.setBrush(QBrush(tile_fill))
    painter.setPen(QPen(tile_border, 1.2))
    painter.drawRoundedRect(tile_rect, 12, 12)
    _ic(ICON.CALENDAR, color=accent.name()).paint(painter, QRect(27, 30, 22, 22))

    first_task = tasks.get(ids[0], {}) if ids else {}
    if count == 1:
        title = str(first_task.get("name") or "").strip() or "1개 일정"
    else:
        title = f"{count}개 일정"

    title_font = QFont("Malgun Gothic", 11, QFont.Weight.DemiBold)
    title_metrics = QFontMetrics(title_font)
    title = title_metrics.elidedText(title, Qt.TextElideMode.ElideRight, 142)
    painter.setFont(title_font)
    painter.setPen(text_primary)
    painter.drawText(
        QRect(72, 18, 148, 25),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        title,
    )

    hint_text = t("drag.hint_copy", "Ctrl: 복사  /  기본: 이동")
    hint_font = QFont("Malgun Gothic", 8)
    painter.setFont(hint_font)
    painter.setPen(text_secondary)
    _ic(ICON.NAV_NEXT, color=text_secondary.name()).paint(painter, QRect(72, 49, 12, 12))
    painter.drawText(
        QRect(89, 44, 137, 22),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        hint_text,
    )

    if count > 1:
        badge_rect = QRect(width - 39, 17, 24, 24)
        painter.setBrush(QBrush(accent))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(badge_rect)
        badge_font = QFont("Malgun Gothic", 9, QFont.Weight.Bold)
        painter.setFont(badge_font)
        painter.setPen(_drag_color(tokens, "text_inverse", "#ffffff", 255))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, str(count))

    painter.end()
    return pixmap


def start_task_drag(widget, _event, task_id):
    task_ids = _safe_task_ids(widget, task_id)
    task_map = {tid: task_repo.get_unified_task(tid) or {} for tid in task_ids}

    mime = QMimeData()
    mime.setData("application/x-task-item", _write_int_list(task_ids))

    # Used by calendar cells for range preview while dragging.
    span_data = QByteArray()
    span_stream = QDataStream(span_data, QIODevice.OpenModeFlag.WriteOnly)
    spans = [_span_days_for_task(task_map.get(tid)) for tid in task_ids]
    span = max(spans, default=1)
    span_stream.writeInt32(int(span))
    mime.setData("application/x-task-span-days", span_data)

    app = widget.window() if widget is not None else None
    if app is not None:
        app._is_dragging = True
    widget.setProperty("dragging", True)
    widget.style().unpolish(widget)
    widget.style().polish(widget)

    drag = QDrag(widget)
    drag.setMimeData(mime)

    # ---- 드래그 픽맵: 테마 기반 스택 카드 ----
    try:
        pixmap = build_task_drag_pixmap(task_ids, task_map)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(21, pixmap.height() // 2))
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to create drag pixmap: {e}")

    action = Qt.DropAction.IgnoreAction
    try:
        action = drag.exec(
            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.MoveAction
        )
    finally:
        widget.setProperty("dragging", False)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        if app is not None:
            task_drop_service.finalize_task_drag(app, changed=0)

    return action


def handle_task_drop(app, task_id_list, target_date, target_time, action):
    return task_drop_service.handle_task_drop(app, task_id_list, target_date, target_time, action)
