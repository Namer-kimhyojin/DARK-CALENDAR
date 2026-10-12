# -*- coding: utf-8 -*-
"""Quiet placement controls shared by desktop widgets and the unified window."""

import math

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QRegion
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFontComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.widget_mode_geometry import clamp_rect


def drag_distance_reached(origin: QPoint, current: QPoint) -> bool:
    """Use the OS drag threshold so clicking never becomes an accidental edit."""
    return (current - origin).manhattanLength() >= QApplication.startDragDistance()


def proportional_size(width: int, height: int, original: tuple[int, int]) -> tuple[int, int]:
    """Follow the dimension changed most, preserving the opening aspect ratio."""
    ow, oh = original
    if ow <= 0 or oh <= 0:
        return width, height
    scale_w, scale_h = width / ow, height / oh
    scale = scale_w if abs(scale_w - 1) >= abs(scale_h - 1) else scale_h
    scale = max(scale, 80 / ow, 40 / oh)
    return round(ow * scale), round(oh * scale)


_RESIZE_REGIONS = frozenset(
    {
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "left",
        "right",
        "top",
        "bottom",
    }
)


def resize_region_at(
    point: QPoint,
    rect: QRect,
    shape: str = "card",
    corner_size: int = 30,
    edge_width: int = 12,
) -> str | None:
    """Find an accessible resize border without consuming the widget's center.

    Round windows use the same pixel mask as the overlay, with diagonal grips
    on the curved outline instead of the unreachable rectangular corners.
    """
    if rect.isEmpty() or not rect.contains(point):
        return None
    width, height = rect.width(), rect.height()
    corner = max(1.0, min(float(corner_size), width / 3.0, height / 3.0))
    edge = max(1.0, min(float(edge_width), width / 6.0, height / 6.0))
    x, y = point.x() - rect.x(), point.y() - rect.y()
    if shape not in {"circle", "capsule"}:
        near_left, near_right = x < corner, width - 1 - x < corner
        near_top, near_bottom = y < corner, height - 1 - y < corner
        if near_top and near_left:
            return "top_left"
        if near_top and near_right:
            return "top_right"
        if near_bottom and near_left:
            return "bottom_left"
        if near_bottom and near_right:
            return "bottom_right"
        distances = ((y, "top"), (height - 1 - y, "bottom"), (x, "left"), (width - 1 - x, "right"))
        distance, region = min(distances)
        return region if distance < edge else None

    outline = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    if outline.isEmpty():
        return None
    path = QPainterPath()
    if shape == "circle":
        path.addEllipse(outline)
    else:
        radius = min(outline.width(), outline.height()) / 2.0
        path.addRoundedRect(outline, radius, radius)
    if not QRegion(path.toFillPolygon().toPolygon()).contains(point):
        return None

    cx, cy = outline.center().x(), outline.center().y()
    dx, dy = point.x() - cx, point.y() - cy
    if abs(dx) < width / 6.0 and abs(dy) < height / 6.0:
        return None
    if shape == "circle":
        rx, ry = outline.width() / 2.0, outline.height() / 2.0
        nx, ny = dx / rx, dy / ry
        normalized_distance = math.hypot(nx, ny)
        if normalized_distance == 0:
            return None
        depth = math.hypot(dx, dy) * (1.0 / normalized_distance - 1.0)
    else:
        radius = min(outline.width(), outline.height()) / 2.0
        if outline.width() >= outline.height():
            nearest_x = max(outline.left() + radius, min(point.x(), outline.right() - radius))
            dx = point.x() - nearest_x
        else:
            nearest_y = max(outline.top() + radius, min(point.y(), outline.bottom() - radius))
            dy = point.y() - nearest_y
        normalized_distance = math.hypot(dx, dy)
        if normalized_distance == 0:
            return None
        nx, ny = dx / normalized_distance, dy / normalized_distance
        depth = radius - normalized_distance

    # The 22.5–67.5 degree sections make diagonal controls easy to reach while
    # keeping each cardinal direction available on the middle of its edge.
    diagonal = math.sin(math.pi / 8.0)
    direction_length = math.hypot(nx, ny)
    diagonal_region = min(abs(nx), abs(ny)) / direction_length >= diagonal
    if diagonal_region:
        if depth > corner:
            return None
        return ("top" if ny < 0 else "bottom") + ("_left" if nx < 0 else "_right")
    if depth > edge:
        return None
    if abs(nx) > abs(ny):
        return "left" if nx < 0 else "right"
    return "top" if ny < 0 else "bottom"


def resize_cursor(region: str | None) -> Qt.CursorShape:
    """Return the common cursor for a resize edge or diagonal."""
    if region in {"top_left", "bottom_right"}:
        return Qt.CursorShape.SizeFDiagCursor
    if region in {"top_right", "bottom_left"}:
        return Qt.CursorShape.SizeBDiagCursor
    if region in {"left", "right"}:
        return Qt.CursorShape.SizeHorCursor
    if region in {"top", "bottom"}:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.ArrowCursor


def anchor_resize_rect(
    origin: QRect,
    size: tuple[int, int] | QSize,
    region: str | None,
) -> QRect:
    """Retain the opening anchor after content fitting changes the final size."""
    if isinstance(size, QSize):
        width, height = size.width(), size.height()
    else:
        width, height = size
    width, height = max(1, int(width)), max(1, int(height))
    x, y = origin.x(), origin.y()
    if region in {"left", "top_left", "bottom_left"}:
        x = origin.right() - width + 1
    if region in {"top", "top_left", "top_right"}:
        y = origin.bottom() - height + 1
    if region in {"left", "right"}:
        center_y = origin.center().y()
        y = center_y - (height - 1) // 2
        # QRect.center() truncates a negative midpoint toward zero, rather
        # than flooring it. Compensate when an even length straddles pixels.
        if center_y < 0 and height % 2 == 0:
            y -= 1
    elif region in {"top", "bottom"}:
        center_x = origin.center().x()
        x = center_x - (width - 1) // 2
        if center_x < 0 and width % 2 == 0:
            x -= 1
    return QRect(x, y, width, height)


def resize_rect(
    origin: QRect,
    delta: QPoint,
    region: str,
    *,
    proportional: bool = False,
    min_size: tuple[int, int] = (80, 40),
    max_size: tuple[int, int] | None = None,
) -> QRect:
    """Resize from the opening geometry, retaining the opposite anchor.

    A proportional side drag retains the opposite edge's center. Size limits
    constrain one shared scale, avoiding aspect distortion at a limit. Minimum
    dimensions take precedence when a caller supplies contradictory limits.
    """
    if region not in _RESIZE_REGIONS or origin.isEmpty():
        return QRect(origin)
    left = region in {"left", "top_left", "bottom_left"}
    right = region in {"right", "top_right", "bottom_right"}
    top = region in {"top", "top_left", "top_right"}
    bottom = region in {"bottom", "bottom_left", "bottom_right"}
    ow, oh = origin.width(), origin.height()
    width = ow + (delta.x() if right else -delta.x() if left else 0)
    height = oh + (delta.y() if bottom else -delta.y() if top else 0)
    min_width, min_height = max(1, int(min_size[0])), max(1, int(min_size[1]))
    max_width = max(min_width, int(max_size[0])) if max_size else None
    max_height = max(min_height, int(max_size[1])) if max_size else None
    if proportional:
        scale_w, scale_h = width / ow, height / oh
        if (left or right) and (top or bottom):
            scale = scale_w if abs(scale_w - 1) >= abs(scale_h - 1) else scale_h
        else:
            scale = scale_w if left or right else scale_h
        minimum_scale = max(min_width / ow, min_height / oh)
        scale = max(minimum_scale, scale)
        if max_width is not None and max_height is not None:
            maximum_scale = max(minimum_scale, min(max_width / ow, max_height / oh))
            scale = min(scale, maximum_scale)
        width, height = round(ow * scale), round(oh * scale)
    else:
        width, height = max(min_width, width), max(min_height, height)
        if max_width is not None and max_height is not None:
            width, height = min(width, max_width), min(height, max_height)
    return anchor_resize_rect(origin, (width, height), region)


class _IgnoreWheelMixin:
    def wheelEvent(self, event):
        # Scrolling the page must not move a widget or change its dimensions.
        event.ignore()


class NoWheelComboBox(_IgnoreWheelMixin, QComboBox):
    pass


class NoWheelFontComboBox(_IgnoreWheelMixin, QFontComboBox):
    pass


class NoWheelSlider(_IgnoreWheelMixin, QSlider):
    pass


class NoWheelSpinBox(_IgnoreWheelMixin, QSpinBox):
    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and event.key() in (
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            self.setValue(self.value() + (10 if event.key() == Qt.Key.Key_Up else -10))
            event.accept()
            return
        super().keyPressEvent(event)


class WidgetPlacementDialog(QDialog):
    """Stage precise geometry; cancellation never changes the actual widget."""

    def __init__(self, widget, *, locked=False, snap=True, proportional=False):
        super().__init__(widget)
        self._opening = QRect(widget.geometry())
        self._widget_minimum = widget.minimumSize()
        self._proportional = proportional
        apply_dialog_title(self, t("widget.placement.title", "위치·크기 조정"))
        apply_common_dialog_style(self, minimum_width=460)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        title = QLabel(t("widget.placement.heading", "편한 자리에, 원하는 크기로"))
        title.setObjectName("dialog_title")
        title.setProperty("role", "dialogTitle")
        root.addWidget(title)
        help_label = QLabel(
            t(
                "widget.placement.help",
                "드래그로 자유롭게 조정하거나 아래에 정확한 값을 입력하세요. 적용할 때 저장됩니다.",
            )
        )
        help_label.setWordWrap(True)
        root.addWidget(help_label)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.fields = {}
        labels = (
            ("x", t("widget.placement.x", "가로 위치")),
            ("y", t("widget.placement.y", "세로 위치")),
            ("width", t("widget.placement.width", "너비")),
            ("height", t("widget.placement.height", "높이")),
        )
        for index, (key, label) in enumerate(labels):
            field = NoWheelSpinBox(self)
            field.setObjectName("placement_" + key)
            field.setRange(-100000, 100000) if index < 2 else field.setRange(
                max(80 if key == "width" else 40, getattr(self._widget_minimum, key)()), 16384
            )
            field.setSuffix(" px")
            field.setAccessibleName(label)
            field.setToolTip(t("widget.placement.step_help", "방향키: 1px · Shift+방향키: 10px"))
            label_widget = QLabel(label)
            label_widget.setBuddy(field)
            column, row = index % 2, (index // 2) * 2
            grid.addWidget(label_widget, row, column)
            grid.addWidget(field, row + 1, column)
            self.fields[key] = field
        root.addLayout(grid)
        self.aspect = QCheckBox(t("widget.placement.aspect", "가로·세로 비율 유지"))
        self.aspect.setChecked(proportional)
        self.aspect.setEnabled(not proportional)
        root.addWidget(self.aspect)
        if proportional:
            note = QLabel(
                t("widget.placement.keydeck_note", "키덱은 키 모양을 유지하며 확대·축소합니다.")
            )
            note.setWordWrap(True)
            root.addWidget(note)
        self.lock = QCheckBox(t("widget.placement.lock", "위치·크기 고정"))
        self.lock.setChecked(locked)
        self.lock.setToolTip(
            t(
                "widget.placement.lock_help",
                "이동과 크기 조절만 잠급니다. 위젯의 버튼과 내용은 계속 사용할 수 있습니다.",
            )
        )
        root.addWidget(self.lock)
        self.snap = QCheckBox(t("widget.placement.snap", "가까운 경계에 자동 맞춤"))
        self.snap.setChecked(snap)
        root.addWidget(self.snap)
        hint = QLabel(
            t(
                "widget.placement.gesture_help",
                "Shift: 비율 유지 · Alt: 자동 맞춤 해제 · 우클릭: 최근 배치 되돌리기",
            )
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        actions = QHBoxLayout()
        self.revert_btn = QPushButton(t("widget.placement.revert", "처음 값으로"))
        self.revert_btn.setObjectName("ghost_btn")
        self.revert_btn.setAutoDefault(False)
        self.revert_btn.clicked.connect(lambda: self._set_rect(self._opening))
        actions.addWidget(self.revert_btn)
        self.screen_btn = QPushButton(t("widget.placement.screen", "화면 안에 맞추기"))
        self.screen_btn.setObjectName("ghost_btn")
        self.screen_btn.setAutoDefault(False)
        self.screen_btn.clicked.connect(self._fit_to_screen)
        actions.addWidget(self.screen_btn)
        root.addLayout(actions)
        footer, self.apply_btn, self.cancel_btn = build_dialog_footer(
            t("btn.apply", "적용"), t("btn.cancel", "취소")
        )
        root.addLayout(footer)
        self.apply_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self._set_rect(self._opening)
        self.fields["width"].valueChanged.connect(lambda value: self._keep_ratio("width", value))
        self.fields["height"].valueChanged.connect(lambda value: self._keep_ratio("height", value))
        self.fields["x"].setFocus()

    def _set_rect(self, rect):
        values = dict(zip(("x", "y", "width", "height"), rect.getRect(), strict=True))
        for key, field in self.fields.items():
            was_blocked = field.blockSignals(True)
            field.setValue(values[key])
            field.blockSignals(was_blocked)

    def _keep_ratio(self, key, value):
        if not self.aspect.isChecked():
            return
        other = "height" if key == "width" else "width"
        ratio = self._opening.height() / max(1, self._opening.width())
        field = self.fields[other]
        was_blocked = field.blockSignals(True)
        field.setValue(round(value * ratio if key == "width" else value / max(0.001, ratio)))
        field.blockSignals(was_blocked)

    def _fit_to_screen(self):
        rect = self.placement_rect()
        screen = QApplication.screenAt(rect.center()) or self.parentWidget().screen()
        if screen is not None:
            self._set_rect(clamp_rect(rect, screen.availableGeometry()))

    def placement_rect(self):
        return QRect(*(self.fields[key].value() for key in ("x", "y", "width", "height")))


class PlacementSizeGrip(QSizeGrip):
    """Corner resizing with a deliberate drag start and no native resize shortcut."""

    editStarted = pyqtSignal()
    editFinished = pyqtSignal()
    editCanceled = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self._origin = None
        self._rect_origin = None
        self._active = False
        self.setFixedSize(22, 22)
        self.setAccessibleName(t("widget.placement.resize", "크기 조절"))
        self.setToolTip(t("widget.placement.resize_help", "모서리를 끌어 크기를 조절하세요."))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.globalPosition().toPoint()
            self._rect_origin = QRect(self.window().geometry())
            self._active = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._origin is None:
            super().mouseMoveEvent(event)
            return
        if not event.buttons() & Qt.MouseButton.LeftButton:
            self.cancel_edit()
            self.editCanceled.emit()
            return
        if self._origin is not None and not self._active:
            if not drag_distance_reached(self._origin, event.globalPosition().toPoint()):
                event.accept()
                return
            self.editStarted.emit()
            self._active = True
        delta = event.globalPosition().toPoint() - self._origin
        rect = self._rect_origin
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        width = max(80, rect.width() + (-delta.x() if rtl else delta.x()))
        height = max(40, rect.height() + delta.y())
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            width, height = proportional_size(
                width,
                height,
                (rect.width(), rect.height()),
            )
            minimum = self.window().minimumSize()
            scale = max(1, minimum.width() / width, minimum.height() / height)
            width, height = round(width * scale), round(height * scale)
        self.window().resize(width, height)
        if rtl:
            self.window().move(rect.right() - self.window().width() + 1, rect.top())
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            active = self._active
            self._active = False
            self._origin = None
            if active:
                self.editFinished.emit()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def cancel_edit(self):
        self._active = False
        self._origin = None
        self._rect_origin = None
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        if not self.isEnabled() or not (self.underMouse() or self._active):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().highlight().color(), 1.5))
        for offset in (5, 10):
            painter.drawLine(
                self.width() - offset - 3,
                self.height() - 3,
                self.width() - 3,
                self.height() - offset - 3,
            )
