# -*- coding: utf-8 -*-
"""Logical canvas geometry and isolated editing gestures for widget configurations."""

from copy import deepcopy
import math

from PyQt6.QtCore import QDate, QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.widget_free_layout import (
    BLOCK_MINIMUM_SIZES,
    validate_free_layout,
)


def _block_labels():
    return {
        "date": t("widget_mode.free_block_date", "날짜"),
        "clock": t("widget_mode.free_block_clock", "시계"),
        "calendar": t("widget_mode.free_block_calendar", "달력"),
        "filters": t("widget_mode.free_block_filters", "통합 목록 필터"),
        "agenda": t("widget_mode.free_block_agenda", "통합 목록"),
        "schedule": t("widget_mode.filter_schedule", "일정"),
        "work": t("widget_mode.filter_work", "업무"),
        "directive": t("widget_mode.filter_directive", "지시"),
    }


def _selected_blocks(data, ids, *, unlocked=False):
    selected = set(ids)
    return [
        block
        for block in data["blocks"]
        if block["id"] in selected
        and block["enabled"]
        and (not unlocked or not block.get("locked", False))
    ]


def selection_bounds(data, ids):
    rects = [QRect(*block["rect"]) for block in _selected_blocks(data, ids)]
    if not rects:
        return None
    result = rects[0]
    for rect in rects[1:]:
        result = result.united(rect)
    return result


def align_selection(data, ids, kind):
    """Align editable elements to the selection, or to the canvas for a single one."""
    result = deepcopy(data)
    blocks = _selected_blocks(result, ids, unlocked=True)
    selected = _selected_blocks(result, ids)
    bounds = selection_bounds(result, ids) if len(selected) > 1 else QRect(0, 0, *result["canvas"])
    if not blocks or bounds is None:
        return result
    aliases = {
        "hcenter": "center_x",
        "horizontal_center": "center_x",
        "center": "center_x",
        "vcenter": "center_y",
        "vertical_center": "center_y",
        "middle": "center_y",
    }
    kind = aliases.get(kind, kind)
    if kind not in {"left", "right", "top", "bottom", "center_x", "center_y"}:
        raise ValueError("Unknown alignment")
    for block in blocks:
        x, y, width, height = block["rect"]
        if kind == "left":
            x = bounds.x()
        elif kind == "right":
            x = bounds.x() + bounds.width() - width
        elif kind == "center_x":
            x = round(bounds.x() + (bounds.width() - width) / 2)
        elif kind == "top":
            y = bounds.y()
        elif kind == "bottom":
            y = bounds.y() + bounds.height() - height
        else:
            y = round(bounds.y() + (bounds.height() - height) / 2)
        block["rect"] = [x, y, width, height]
    return validate_free_layout(result)


def distribute_selection(data, ids, axis):
    """Keep the outer editable elements fixed while equalizing the intervening gaps."""
    result = deepcopy(data)
    blocks = _selected_blocks(result, ids, unlocked=True)
    if axis not in {"x", "y", "horizontal", "vertical"}:
        raise ValueError("Unknown distribution axis")
    if len(blocks) < 3:
        return result
    index = 0 if axis in {"x", "horizontal"} else 1
    size_index = index + 2
    blocks.sort(key=lambda block: block["rect"][index])
    first = blocks[0]["rect"][index]
    end = blocks[-1]["rect"][index] + blocks[-1]["rect"][size_index]
    gap = (end - first - sum(block["rect"][size_index] for block in blocks)) / (len(blocks) - 1)
    position = float(first)
    for block in blocks[1:-1]:
        previous = blocks[blocks.index(block) - 1]
        position += previous["rect"][size_index] + gap
        block["rect"][index] = round(position)
    return validate_free_layout(result)


def overlap_pairs(data):
    blocks = [block for block in data["blocks"] if block["enabled"]]
    return [
        (first["id"], second["id"])
        for index, first in enumerate(blocks)
        for second in blocks[index + 1 :]
        if QRect(*first["rect"]).intersects(QRect(*second["rect"]))
    ]


class LayoutEditorCanvas(QWidget):
    selectionChanged = pyqtSignal(str)
    selectionSetChanged = pyqtSignal(object)
    previewChanged = pyqtSignal(object)
    editCommitted = pyqtSignal()

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = deepcopy(data)
        self.selected_id = ""
        self.selected_ids = set()
        self.zoom = 1.0
        self.guides_enabled = True
        self.active_guides = []
        self._gesture = None
        self._marquee = None
        self._preview_image = None
        self._hovered_id = ""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(t("widget_mode.free_layout_title", "위젯 구성 편집"))
        self.setAccessibleDescription(
            t(
                "widget_mode.free_layout_snap_help",
                "8px 격자에 맞춥니다. Alt를 누르면 자유롭게 이동·크기 조절합니다. 방향키는 1px, Shift+방향키는 10px 이동합니다.",
            )
        )
        self.set_data(data)

    def set_data(self, data):
        self.data = deepcopy(data)
        self.setFixedSize(
            QSize(
                round(self.data["canvas"][0] * self.zoom), round(self.data["canvas"][1] * self.zoom)
            )
        )
        enabled = {block["id"] for block in self.data["blocks"] if block["enabled"]}
        if self._hovered_id not in enabled:
            self._hovered_id = ""
        self.set_selection(self.selected_ids & enabled, primary=self.selected_id)
        self.update()

    def set_zoom(self, scale):
        scale = float(scale)
        if not math.isfinite(scale):
            raise ValueError("Zoom must be finite")
        self.zoom = max(0.1, min(2.0, scale))
        self.set_data(self.data)

    def set_preview_image(self, pixmap):
        self._preview_image = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def logical_to_screen(self, point):
        return QPoint(round(point.x() * self.zoom), round(point.y() * self.zoom))

    def screen_to_logical(self, point):
        return QPoint(round(point.x() / self.zoom), round(point.y() / self.zoom))

    def block_rect(self, block_id):
        return QRect(
            *next(block for block in self.data["blocks"] if block["id"] == block_id)["rect"]
        )

    def set_selection(self, ids, primary=None):
        enabled = {block["id"] for block in self.data["blocks"] if block["enabled"]}
        selected = set(ids) & enabled
        primary = (
            primary
            if primary in selected
            else next((key for key in self._order() if key in selected), "")
        )
        set_changed = selected != self.selected_ids
        primary_changed = primary != self.selected_id
        self.selected_ids = selected
        self.selected_id = primary
        if primary_changed:
            self.selectionChanged.emit(primary)
        if set_changed:
            self.selectionSetChanged.emit(set(selected))
        self.update()

    def select_block(self, block_id, additive=False):
        selected = set(self.selected_ids) if additive else set()
        if additive and block_id in selected:
            selected.remove(block_id)
        elif block_id:
            selected.add(block_id)
        self.set_selection(selected, primary=block_id)

    def _order(self):
        ids = [block["id"] for block in self.data["blocks"]]
        order = [key for key in self.data.get("order", ids) if key in ids]
        return order + [key for key in ids if key not in order]

    def _sample(self, block_id):
        if block_id == "date":
            return QDate.currentDate().toString("yyyy-MM-dd")
        if block_id == "clock":
            return "14:00"
        if block_id == "calendar":
            return "1   2   3   4   5   6   7\n8   9   10   11   12   13   14"
        if block_id == "filters":
            return " · ".join(_block_labels()[key] for key in ("schedule", "work", "directive"))
        return (
            t("widget_mode.preview_schedule", "프로젝트 회의")
            if block_id == "schedule"
            else t("widget_mode.preview_work", "회의 자료 정리")
        )

    def _handles(self):
        if len(self.selected_ids) != 1:
            return {}
        block = next(block for block in self.data["blocks"] if block["id"] == self.selected_id)
        if block.get("locked", False):
            return {}
        rect = self.block_rect(self.selected_id)
        left, top, width, height = rect.getRect()
        right, bottom = left + width, top + height
        center_x, center_y = left + width / 2, top + height / 2
        return {
            "nw": QPointF(left, top),
            "n": QPointF(center_x, top),
            "ne": QPointF(right, top),
            "e": QPointF(right, center_y),
            "se": QPointF(right, bottom),
            "s": QPointF(center_x, bottom),
            "sw": QPointF(left, bottom),
            "w": QPointF(left, center_y),
        }

    def handle_rects(self):
        rect = self.block_rect(self.selected_id) if self.selected_id else QRect()
        radius = min(8 / self.zoom, rect.width() / 4, rect.height() / 4)
        return {
            key: QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
            for key, point in self._handles().items()
        }

    def _handle_hit(self, point):
        return next(
            (key for key, rect in self.handle_rects().items() if rect.contains(QPointF(point))), ""
        )

    def _hit(self, point):
        blocks = {block["id"]: block for block in self.data["blocks"]}
        return next(
            (
                key
                for key in reversed(self._order())
                if blocks[key]["enabled"] and self.block_rect(key).contains(point)
            ),
            "",
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.scale(self.zoom, self.zoom)
        if self._preview_image is not None and not self._preview_image.isNull():
            painter.drawPixmap(QRect(0, 0, *self.data["canvas"]), self._preview_image)
        if self.data["snap"]:
            color = self.palette().mid().color()
            color.setAlpha(50)
            painter.setPen(color)
            visible = self.screen_to_logical(event.rect().topLeft())
            end = self.screen_to_logical(event.rect().bottomRight())
            for x in range(visible.x() // 8 * 8, end.x() + 1, 8):
                for y in range(visible.y() // 8 * 8, end.y() + 1, 8):
                    painter.drawPoint(x, y)
        blocks = {block["id"]: block for block in self.data["blocks"]}
        labels = _block_labels()
        for key in self._order():
            block = blocks[key]
            if not block["enabled"]:
                continue
            selected = key in self.selected_ids
            hovered = key == self._hovered_id
            if self._preview_image is not None and not selected and not hovered:
                continue
            rect = QRectF(*block["rect"]).adjusted(1, 1, -1, -1)
            painter.setPen(
                QPen(
                    self.palette().highlight().color()
                    if selected or hovered
                    else self.palette().mid().color(),
                    (2 if selected else 1) / self.zoom,
                )
            )
            painter.setBrush(
                Qt.BrushStyle.NoBrush
                if self._preview_image is not None
                else self.palette().alternateBase()
            )
            painter.drawRoundedRect(rect, 6, 6)
            if self._preview_image is None:
                painter.setPen(self.palette().text().color())
                label = labels[key] + (
                    " · " + t("widget_mode.free_lock", "잠금") if block.get("locked", False) else ""
                )
                painter.drawText(
                    rect.adjusted(8, 6, -8, -6),
                    Qt.AlignmentFlag.AlignTop
                    | Qt.AlignmentFlag.AlignLeading
                    | Qt.TextFlag.TextWordWrap,
                    label + "\n" + self._sample(key),
                )
        painter.setPen(QPen(self.palette().highlight().color(), 1 / self.zoom))
        for axis, value in self.active_guides:
            if axis == "x":
                painter.drawLine(QPointF(value, 0), QPointF(value, self.data["canvas"][1]))
            else:
                painter.drawLine(QPointF(0, value), QPointF(self.data["canvas"][0], value))
        painter.setBrush(self.palette().highlight())
        rect = self.block_rect(self.selected_id) if self.selected_id else QRect()
        radius = min(4 / self.zoom, rect.width() / 4, rect.height() / 4)
        for point in self._handles().values():
            painter.drawRect(QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2))
        if self._marquee is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._marquee)
        if self._preview_image is not None:
            self._paint_selection_badges(painter)
        painter.end()

    def _paint_selection_badges(self, painter):
        painter.save()
        painter.resetTransform()
        font = QFont(self.font())
        font.setPointSizeF(9)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        labels = _block_labels()
        for block in _selected_blocks(self.data, self.selected_ids):
            label = labels[block["id"]]
            if block.get("locked", False):
                label += " · " + t("widget_mode.free_lock", "잠금")
            badge_width = min(self.width(), metrics.horizontalAdvance(label) + 12)
            badge_height = metrics.height() + 6
            point = self.logical_to_screen(QPoint(block["rect"][0], block["rect"][1]))
            x = max(0, min(self.width() - badge_width, point.x()))
            y = max(0, point.y() - badge_height)
            badge = QRect(x, y, badge_width, badge_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.palette().highlight())
            painter.drawRoundedRect(QRectF(badge), 4, 4)
            painter.setPen(self.palette().highlightedText().color())
            text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, max(1, badge_width - 10))
            painter.drawText(
                badge.adjusted(6, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeading,
                text,
            )
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        point = self.screen_to_logical(event.position())
        self._gesture = None
        self.active_guides = []
        modifiers = event.modifiers()
        additive = bool(
            modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        )
        handle = "" if additive else self._handle_hit(point)
        hit = self.selected_id if handle else self._hit(point)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if not hit:
            self._gesture = {
                "kind": "marquee",
                "origin": point,
                "selection": set(self.selected_ids) if additive else set(),
            }
            if not additive:
                self.set_selection(set())
        else:
            if additive:
                self.select_block(hit, additive=True)
            elif hit not in self.selected_ids:
                self.select_block(hit)
            else:
                self.set_selection(self.selected_ids, primary=hit)
            if not handle and not additive:
                handle = self._handle_hit(point)
            blocks = _selected_blocks(self.data, self.selected_ids, unlocked=True)
            clicked = next(block for block in self.data["blocks"] if block["id"] == hit)
            if hit in self.selected_ids and blocks and not clicked.get("locked", False):
                self._gesture = {
                    "kind": "resize" if handle else "move",
                    "handle": handle,
                    "origin": point,
                    "data": deepcopy(self.data),
                    "changed": False,
                    "ids": {block["id"] for block in blocks},
                }
        event.accept()

    def _snap_delta(self, bounds, dx, dy, modifiers):
        self.active_guides = []
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return dx, dy
        if self.data["snap"]:
            dx = round((bounds.x() + dx) / 8) * 8 - bounds.x()
            dy = round((bounds.y() + dy) / 8) * 8 - bounds.y()
        if self.guides_enabled:
            targets = {
                "x": [0, self.data["canvas"][0] / 2, self.data["canvas"][0]],
                "y": [0, self.data["canvas"][1] / 2, self.data["canvas"][1]],
            }
            for block in self.data["blocks"]:
                if block["enabled"] and block["id"] not in self.selected_ids:
                    x, y, width, height = block["rect"]
                    targets["x"].extend([x, x + width / 2, x + width])
                    targets["y"].extend([y, y + height / 2, y + height])
            for axis, position, size in (
                ("x", bounds.x() + dx, bounds.width()),
                ("y", bounds.y() + dy, bounds.height()),
            ):
                candidates = [
                    (target - source, target)
                    for source in (position, position + size / 2, position + size)
                    for target in targets[axis]
                ]
                adjustment, guide = min(candidates, key=lambda pair: abs(pair[0]))
                if abs(adjustment) <= 6 / self.zoom:
                    if axis == "x":
                        dx += round(adjustment)
                    else:
                        dy += round(adjustment)
                    self.active_guides.append((axis, guide))
        return dx, dy

    def _move(self, initial, ids, dx, dy, modifiers=Qt.KeyboardModifier.AltModifier):
        bounds = selection_bounds(initial, ids)
        if bounds is None:
            return initial
        dx, dy = self._snap_delta(bounds, dx, dy, modifiers)
        dx = max(-bounds.x(), min(initial["canvas"][0] - bounds.x() - bounds.width(), dx))
        dy = max(-bounds.y(), min(initial["canvas"][1] - bounds.y() - bounds.height(), dy))
        result = deepcopy(initial)
        for block in _selected_blocks(result, ids, unlocked=True):
            block["rect"][0] += dx
            block["rect"][1] += dy
        return validate_free_layout(result)

    def _resize(self, initial, handle, dx, dy, modifiers):
        result = deepcopy(initial)
        block = next(block for block in result["blocks"] if block["id"] == self.selected_id)
        x, y, width, height = block["rect"]
        right, bottom = x + width, y + height
        minimum_w, minimum_h = BLOCK_MINIMUM_SIZES[self.selected_id]
        bypass = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        self.active_guides = []

        def snap(value):
            return round(value / 8) * 8 if initial["snap"] and not bypass else value

        def guide(value, axis):
            if bypass or not self.guides_enabled:
                return value
            limit = initial["canvas"][0 if axis == "x" else 1]
            targets = [0, limit / 2, limit]
            for other in initial["blocks"]:
                if other["enabled"] and other["id"] != self.selected_id:
                    ox, oy, ow, oh = other["rect"]
                    targets.extend(
                        [ox, ox + ow / 2, ox + ow] if axis == "x" else [oy, oy + oh / 2, oy + oh]
                    )
            target = min(targets, key=lambda target: abs(target - value))
            if abs(target - value) <= 6 / self.zoom:
                self.active_guides.append((axis, target))
                return round(target)
            return value

        if "w" in handle:
            x = max(0, min(right - minimum_w, guide(snap(x + dx), "x")))
        if "e" in handle:
            right = max(x + minimum_w, min(initial["canvas"][0], guide(snap(right + dx), "x")))
        if "n" in handle:
            y = max(0, min(bottom - minimum_h, guide(snap(y + dy), "y")))
        if "s" in handle:
            bottom = max(y + minimum_h, min(initial["canvas"][1], guide(snap(bottom + dy), "y")))
        block["rect"] = [x, y, right - x, bottom - y]
        return validate_free_layout(result)

    def _change(self, data):
        if data == self.data:
            return False
        self.set_data(data)
        self.previewChanged.emit(deepcopy(self.data))
        return True

    def _edit_rect(self, rect):
        candidate = deepcopy(self.data)
        block = next(block for block in candidate["blocks"] if block["id"] == self.selected_id)
        if not block.get("locked", False):
            block["rect"] = list(rect.getRect())
            self._change(validate_free_layout(candidate))

    def mouseMoveEvent(self, event):
        point = self.screen_to_logical(event.position())
        if self._gesture:
            gesture = self._gesture
            if gesture["kind"] == "marquee":
                self._marquee = QRect(gesture["origin"], point).normalized()
                selected = {
                    block["id"]
                    for block in self.data["blocks"]
                    if block["enabled"] and self._marquee.intersects(QRect(*block["rect"]))
                }
                self.set_selection(gesture["selection"] | selected)
            else:
                delta = point - gesture["origin"]
                candidate = (
                    self._resize(
                        gesture["data"], gesture["handle"], delta.x(), delta.y(), event.modifiers()
                    )
                    if gesture["kind"] == "resize"
                    else self._move(
                        gesture["data"], gesture["ids"], delta.x(), delta.y(), event.modifiers()
                    )
                )
                gesture["changed"] = self._change(candidate) or gesture["changed"]
            self.update()
            event.accept()
            return
        handle = self._handle_hit(point)
        hovered = self.selected_id if handle else self._hit(point)
        if hovered != self._hovered_id:
            self._hovered_id = hovered
            self.update()
        cursors = {
            "n": Qt.CursorShape.SizeVerCursor,
            "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor,
            "w": Qt.CursorShape.SizeHorCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
        }
        self.setCursor(
            cursors.get(
                handle,
                Qt.CursorShape.SizeAllCursor if self._hit(point) else Qt.CursorShape.ArrowCursor,
            )
        )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered_id = ""
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._gesture and event.button() == Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event)
            changed = self._gesture.get("changed", False)
            self._gesture = None
            self._marquee = None
            self.active_guides = []
            if changed:
                self.editCommitted.emit()
            self.update()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._gesture and self._gesture["kind"] != "marquee":
                self._change(self._gesture["data"])
            self._gesture = None
            self._marquee = None
            self.active_guides = []
            self.set_selection(set())
            event.accept()
            return
        offsets = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        blocks = _selected_blocks(self.data, self.selected_ids, unlocked=True)
        if blocks and event.key() in offsets:
            self._gesture = None
            self._marquee = None
            amount = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx, dy = offsets[event.key()]
            if self._change(
                self._move(self.data, {block["id"] for block in blocks}, dx * amount, dy * amount)
            ):
                self.editCommitted.emit()
            event.accept()
        elif blocks and event.key() == Qt.Key.Key_Delete:
            self._gesture = None
            self._marquee = None
            candidate = deepcopy(self.data)
            for block in _selected_blocks(candidate, self.selected_ids, unlocked=True):
                block["enabled"] = False
            if self._change(validate_free_layout(candidate)):
                self.editCommitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
