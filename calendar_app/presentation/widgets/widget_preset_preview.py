# -*- coding: utf-8 -*-
"""Native, read-only thumbnails for overlay content presets."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap, QTextDocument
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from calendar_app.presentation.widgets.widget_shapes import get_widget_shape


def template_preview_pixmap(
    html: str,
    size: QSize,
    *,
    font: QFont,
    margins: list[int],
    shape_id: str,
    face_style,
    dpr: float = 1.0,
) -> QPixmap:
    """Fit an independently rendered face into a thumbnail without settings writes."""
    frame = QFrame()
    frame.setObjectName("presetPreviewFace")
    frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    frame.setStyleSheet(face_style(None))
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(0)
    label = QLabel(frame)
    label.setFont(font)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(False)
    label.setStyleSheet("background: transparent; border: none; padding: 0;")
    label.setText(html)
    layout.addWidget(label)
    frame.ensurePolished()
    label.ensurePolished()
    document = QTextDocument()
    document.setDefaultFont(font)
    document.setDocumentMargin(0)
    document.setHtml(html)
    content = label.sizeHint().expandedTo(document.size().toSize())
    insets = frame.contentsMargins()
    width = max(80, content.width() + margins[0] + margins[2] + insets.left() + insets.right() + 8)
    height = max(
        40, content.height() + margins[1] + margins[3] + insets.top() + insets.bottom() + 8
    )
    shape = get_widget_shape(shape_id)
    if shape_id == "circle":
        width = height = max(120, width + 104, height + 104)
    elif shape_id == "capsule":
        width = max(width, height * 2)
    elif shape_id == "poster":
        height = max(height, round(width / float(shape.aspect_ratio or 0.72)))
    # Custom templates can contain unusually large text. Keep preview allocation bounded.
    width, height = min(2048, width), min(2048, height)
    frame.setFixedSize(width, height)
    layout.activate()
    if shape_id in {"circle", "capsule"}:
        frame.setStyleSheet(face_style(min(width, height) // 2))
        frame.ensurePolished()
        layout.activate()
    canvas = QPixmap(round(size.width() * dpr), round(size.height() * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(QColor("#14212e"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scale = min(max(1, size.width() - 10) / width, max(1, size.height() - 10) / height)
    painter.translate((size.width() - width * scale) / 2, (size.height() - height * scale) / 2)
    painter.scale(scale, scale)
    if shape_id in {"circle", "capsule"}:
        path = QPainterPath()
        rect = QRectF(0, 0, width, height)
        if shape_id == "circle":
            path.addEllipse(rect)
        else:
            radius = min(width, height) / 2
            path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)
    frame.render(painter, QPoint())
    painter.end()
    frame.deleteLater()
    return canvas
