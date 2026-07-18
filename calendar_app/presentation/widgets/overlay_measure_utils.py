"""Layout measurement helpers extracted from overlay_base."""

from __future__ import annotations

import contextlib

from PyQt6.QtCore import QRect, QSize
from PyQt6.QtCore import Qt as _Qt
from PyQt6.QtGui import QFontMetrics, QTextDocument
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


def _measure_face_height(face: QWidget, avail_w: int) -> int:
    """Return natural face height when constrained to *avail_w*."""

    def _label_height(lbl: QLabel, max_w: int) -> int:
        fm = QFontMetrics(lbl.font())
        text = lbl.text()
        if not text:
            return 0
        if lbl.wordWrap() and max_w > 0:
            rect = fm.boundingRect(
                QRect(0, 0, max_w, 0),
                _Qt.TextFlag.TextWordWrap,
                text,
            )
            return rect.height()
        return fm.height()

    def _widget_height(widget: QWidget, max_w: int) -> int:
        if widget.isHidden():
            return 0
        lay = widget.layout()
        if lay is None:
            if isinstance(widget, QLabel):
                return _label_height(widget, max_w)
            return 0
        is_hbox = isinstance(lay, QHBoxLayout)
        margins = lay.contentsMargins()
        spacing = lay.spacing()
        inner_w = max(0, max_w - margins.left() - margins.right())

        if is_hbox:
            children = []
            for i in range(lay.count()):
                item = lay.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    children.append(item.widget())
            if not children:
                return margins.top() + margins.bottom()
            share_w = max(1, (inner_w - spacing * max(0, len(children) - 1)) // len(children))
            row_h = max(_widget_height(c, share_w) for c in children)
            return row_h + margins.top() + margins.bottom()

        total_h = 0
        visible = 0
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            child = item.widget()
            if child is None or child.isHidden():
                continue
            ch = _widget_height(child, inner_w)
            if ch == 0:
                continue
            total_h += ch
            visible += 1
        if visible > 1:
            total_h += spacing * (visible - 1)
        return total_h + margins.top() + margins.bottom()

    return _widget_height(face, avail_w)


def _measure_face_size(face: QWidget, avail_w: int) -> QSize:
    """Return rendered face size when laid out inside *avail_w* pixels."""
    layout = face.layout()
    old_size = face.size()
    if layout is not None:
        try:
            layout.invalidate()
            layout.setGeometry(QRect(0, 0, max(1, avail_w), 100000))
            layout.activate()
        except Exception:
            pass
    try:
        face.resize(max(1, avail_w), max(old_size.height(), 1))
        face.updateGeometry()
    except Exception:
        pass

    hint = face.sizeHint()
    measured_h = _measure_face_height(face, avail_w)
    children_rect = face.childrenRect()
    measured_w = 0
    if hint.isValid():
        measured_w = max(measured_w, hint.width())
    if children_rect.isValid():
        measured_w = max(measured_w, children_rect.width())
    measured_w = max(1, measured_w)

    with contextlib.suppress(Exception):
        face.resize(old_size)
    return QSize(measured_w, max(1, measured_h))


def _measure_face_size_precise(face: QWidget, avail_w: int) -> QSize:
    """Measure text-driven face size needed within *avail_w*."""

    def _label_size(lbl: QLabel, max_w: int) -> QSize:
        text = lbl.text() or ""
        if not text:
            return QSize(0, 0)

        margins = lbl.contentsMargins()
        inner_w = max(1, max_w - margins.left() - margins.right())
        is_rich = lbl.textFormat() == _Qt.TextFormat.RichText or ("<" in text and ">" in text)
        if is_rich:
            doc = QTextDocument()
            doc.setDefaultFont(lbl.font())
            doc.setDocumentMargin(0)
            doc.setHtml(text)
            if lbl.wordWrap():
                doc.setTextWidth(float(inner_w))
            size = doc.size().toSize()
            return QSize(
                size.width() + margins.left() + margins.right(),
                size.height() + margins.top() + margins.bottom(),
            )

        fm = QFontMetrics(lbl.font())
        if lbl.wordWrap():
            rect = fm.boundingRect(QRect(0, 0, inner_w, 0), _Qt.TextFlag.TextWordWrap, text)
            width = min(inner_w, rect.width())
            height = rect.height()
        else:
            rect = fm.boundingRect(text)
            width = rect.width()
            height = rect.height()
        return QSize(
            width + margins.left() + margins.right(),
            height + margins.top() + margins.bottom(),
        )

    def _widget_size(widget: QWidget, max_w: int, *, is_root: bool = False) -> QSize:
        if not is_root and widget.isHidden():
            return QSize(0, 0)

        lay = widget.layout()
        if lay is None:
            if isinstance(widget, QLabel):
                return _label_size(widget, max_w)
            hint = widget.sizeHint()
            return QSize(max(0, hint.width()), max(0, hint.height()))

        margins = lay.contentsMargins()
        spacing = max(0, lay.spacing())
        inner_w = max(1, max_w - margins.left() - margins.right())

        children = []
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            child = item.widget()
            if child is None or child.isHidden():
                continue
            children.append(child)

        if not children:
            return QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

        if isinstance(lay, QHBoxLayout):
            child_sizes = [_widget_size(child, inner_w, is_root=False) for child in children]
            total_w = sum(size.width() for size in child_sizes) + spacing * max(
                0, len(child_sizes) - 1
            )
            total_h = max(size.height() for size in child_sizes)
            return QSize(
                total_w + margins.left() + margins.right(),
                total_h + margins.top() + margins.bottom(),
            )

        child_sizes = [_widget_size(child, inner_w, is_root=False) for child in children]
        total_h = sum(size.height() for size in child_sizes) + spacing * max(
            0, len(child_sizes) - 1
        )
        total_w = max(size.width() for size in child_sizes)
        return QSize(
            total_w + margins.left() + margins.right(),
            total_h + margins.top() + margins.bottom(),
        )

    return _widget_size(face, max(1, avail_w), is_root=True)
