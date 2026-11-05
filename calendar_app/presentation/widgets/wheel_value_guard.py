# -*- coding: utf-8 -*-
"""Keep mouse-wheel scrolling from changing values anywhere in the application."""

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QScrollBar,
    QTabBar,
    QWidget,
)


def _changes_value(widget: QWidget) -> bool:
    ancestors = []
    while isinstance(widget, QWidget) and not sip.isdeleted(widget):
        ancestors.append(widget)
        widget = widget.parentWidget()

    # Scrollbars and open item lists scroll content; they do not commit values.
    if any(isinstance(item, QScrollBar) for item in ancestors):
        return False
    # A calendar's table viewport changes the displayed month on wheel input.
    if any(isinstance(item, QCalendarWidget) for item in ancestors):
        return True
    for item in ancestors:
        if isinstance(item, (QAbstractSpinBox, QComboBox, QAbstractSlider, QTabBar)) or (
            item.property("dcWheelValueControl") is True
        ):
            return True
        if isinstance(item, QAbstractItemView):
            return False
    return False


def _scroll_container(widget: QWidget, event: QWheelEvent) -> bool:
    window = widget.window()
    parent = widget.parentWidget()
    while parent is not None and parent.window() is window:
        if isinstance(parent, QAbstractScrollArea) and not _changes_value(parent.viewport()):
            viewport = parent.viewport()
            forwarded = QWheelEvent(
                QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                event.globalPosition(),
                event.pixelDelta(),
                event.angleDelta(),
                event.buttons(),
                event.modifiers(),
                event.phase(),
                event.inverted(),
                Qt.MouseEventSource.MouseEventSynthesizedByApplication,
                event.pointingDevice(),
            )
            QApplication.sendEvent(viewport, forwarded)
            return True
        parent = parent.parentWidget()
    return False


class _WheelValueGuard(QObject):
    def eventFilter(self, watched, event):
        if (
            event.type() != QEvent.Type.Wheel
            or QApplication.closingDown()
            or not isinstance(watched, QWidget)
            or sip.isdeleted(watched)
        ):
            return False
        if _changes_value(watched):
            # Forward once to a scroll viewport, never back to another editor.
            # Accept the original after forwarding so Qt cannot scroll twice.
            if _scroll_container(watched, event):
                event.accept()
            else:
                event.ignore()
            return True
        return False


def install_wheel_value_guard(app: QApplication | None = None) -> QObject | None:
    """Install one guard for present/future windows, including focused controls."""
    app = app or QApplication.instance()
    if app is None or QApplication.closingDown():
        return None
    guard = getattr(app, "_dc_wheel_value_guard", None)
    if guard is None or sip.isdeleted(guard):
        guard = _WheelValueGuard(app)
        app._dc_wheel_value_guard = guard
        app.installEventFilter(guard)
    return guard
