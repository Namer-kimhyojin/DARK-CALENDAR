# -*- coding: utf-8 -*-
"""Editing surface of KeyDeck Studio (WYSIWYG: it uses the runtime renderer)."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.keydeck.model import (
    GRID_STEP,
    MAX_GRID_H,
    MAX_GRID_W,
    MAX_KEY_H,
    MAX_KEY_W,
    MIN_KEY_U,
    boxes_overlap,
    key_box,
    layout_bounds,
    normalize_origin,
    settle_layout,
    snap_u,
)

SELECTION_COLOR = "#3aa0ff"
_HANDLE = 8.0
_DRAG_THRESHOLD = 4.0
_MAX_EDIT_SCALE = 1.75


class StudioCanvas(KeyDeckCanvas):
    """Adds selection, move/resize with 0.25u snapping and a live press preview mode."""

    selectionChanged = pyqtSignal()
    editStarted = pyqtSignal()
    layoutEdited = pyqtSignal()
    keyDoubleClicked = pyqtSignal(str)
    contextRequested = pyqtSignal(str, QPoint)
    deleteRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview_mode = False
        self.selection: list[str] = []
        self._drag: dict | None = None
        self._band: QRectF | None = None
        self._edit_hover = ""
        self.close_control_enabled = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(420, 280)
        self.renderer.empty_hint = str(
            t(
                "widget.launcher.studio.empty_page",
                "키가 없습니다. '+ 키 추가'를 누르거나 앱·파일·링크를 끌어다 놓으세요",
            )
        )

    # -- deck & fitting --------------------------------------------------------------

    def set_deck(self, deck: dict, *, animate: bool = False) -> None:
        super().set_deck(deck, animate=animate)
        self.selection = [key_id for key_id in self.selection if self._key_by_id(key_id)]
        self.refit()

    def refresh(self, key_ids: set[str] | None = None) -> None:
        super().refresh(key_ids)
        self.refit()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(680, 440)

    def refit(self) -> None:
        deck = self.deck
        if deck is None or self._drag is not None:
            return
        keys = deck["pages"][deck["page"]]["keys"]
        _min_x, _min_y, max_x, max_y = layout_bounds(keys)
        args: dict = {"fixed_origin": True}
        if not self.preview_mode:
            # 편집 중에는 오른쪽·아래로 1u 여유 공간을 두어 키를 끌어다 놓을 수 있게 한다.
            args["grid_min"] = (
                min(MAX_GRID_W, max(max_x, 1.0) + 1.0),
                min(MAX_GRID_H, max(max_y, 1.0) + 1.0),
            )
        scale = self.fitted_scale_for(args)
        args["scale"] = scale
        self.set_geometry_overrides(**args)

    def fitted_scale_for(self, args: dict) -> float:
        from calendar_app.presentation.widgets.keydeck.renderer import fit_scale

        deck = self.deck
        width = max(120, self.width() - 36)
        height = max(90, self.height() - 36)
        return min(_MAX_EDIT_SCALE, fit_scale(deck, deck["page"], width, height, **args))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refit()

    def set_preview_mode(self, enabled: bool) -> None:
        self.preview_mode = bool(enabled)
        self._drag = None
        self._band = None
        self._edit_hover = ""
        self.unsetCursor()
        self.refit()
        self.update()

    def select(self, key_ids: list[str]) -> None:
        cleaned = [key_id for key_id in key_ids if self._key_by_id(key_id) is not None]
        if cleaned == self.selection:
            return
        self.selection = cleaned
        self.update()
        self.selectionChanged.emit()

    def selected_keys(self) -> list[dict]:
        return [key for key_id in self.selection if (key := self._key_by_id(key_id)) is not None]

    # -- overlay painting ------------------------------------------------------------

    def paint_overlay(self, painter: QPainter) -> None:
        if self.preview_mode:
            self._paint_preview_banner(painter)
            return
        geometry = self.renderer.geometry
        if geometry is None:
            return
        accent = QColor(SELECTION_COLOR)
        radius = max(4.0, geometry.unit * 0.16)
        if self._drag is not None and self._drag.get("moved") and self._drag["mode"] != "band":
            grid_pen = QPen(QColor(255, 255, 255, 26), 1.0)
            painter.setPen(grid_pen)
            rect = geometry.keys_rect
            columns = int(geometry.grid_u[0])
            rows = int(geometry.grid_u[1])
            for column in range(columns + 1):
                x = rect.left() + column * geometry.unit
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            for row in range(rows + 1):
                y = rect.top() + row * geometry.unit
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            conflicts = self._conflicting_ids()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#ff5d6c"), 2.0, Qt.PenStyle.DashLine))
            for key in geometry.keys:
                if key["id"] in conflicts:
                    painter.drawRoundedRect(
                        geometry.key_rect(key).adjusted(-2, -2, 2, 2), radius, radius
                    )
        if self._edit_hover and self._edit_hover not in self.selection:
            key = self._key_by_id(self._edit_hover)
            if key is not None:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 110), 1.2))
                painter.drawRoundedRect(
                    geometry.key_rect(key).adjusted(-2, -2, 2, 2), radius, radius
                )
        for key in self.selected_keys():
            rect = geometry.key_rect(key).adjusted(-3, -3, 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 120), 4.0))
            painter.drawRoundedRect(rect, radius + 2, radius + 2)
            painter.setPen(QPen(accent, 2.0))
            painter.drawRoundedRect(rect, radius + 2, radius + 2)
        if len(self.selection) == 1:
            painter.setPen(QPen(accent, 1.5))
            painter.setBrush(QColor(255, 255, 255))
            for center in self._handle_centers().values():
                painter.drawRoundedRect(
                    QRectF(center.x() - _HANDLE / 2, center.y() - _HANDLE / 2, _HANDLE, _HANDLE),
                    2,
                    2,
                )
        if self._band is not None:
            fill = QColor(accent)
            fill.setAlpha(40)
            painter.setBrush(fill)
            painter.setPen(QPen(accent, 1.0))
            painter.drawRect(self._band)

    def _conflicting_ids(self) -> set[str]:
        keys = self._page_keys()
        conflicts: set[str] = set()
        boxes = [(key["id"], key_box(key)) for key in keys]
        for index, (first_id, first) in enumerate(boxes):
            for second_id, second in boxes[index + 1 :]:
                if boxes_overlap(first, second):
                    conflicts.update((first_id, second_id))
        return conflicts

    def _handle_centers(self) -> dict[str, QPointF]:
        if len(self.selection) != 1:
            return {}
        key = self._key_by_id(self.selection[0])
        geometry = self.renderer.geometry
        if key is None or geometry is None:
            return {}
        rect = geometry.key_rect(key).adjusted(-3, -3, 3, 3)
        return {
            "e": QPointF(rect.right(), rect.center().y()),
            "s": QPointF(rect.center().x(), rect.bottom()),
            "se": QPointF(rect.right(), rect.bottom()),
        }

    def _handle_at(self, point: QPointF) -> str:
        for name in ("se", "e", "s"):
            center = self._handle_centers().get(name)
            if center is not None and QRectF(center.x() - 7, center.y() - 7, 14, 14).contains(
                point
            ):
                return name
        return ""

    # -- mouse -------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.preview_mode:
            super().mousePressEvent(event)
            if event.button() == Qt.MouseButton.LeftButton:
                # 체험 중에도 누른 키의 설정을 오른쪽에 열어 바로 바꿔 볼 수 있게 한다.
                pressed = self.key_at(event.position())
                self.select([pressed["id"]] if pressed is not None else [])
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        geometry = self.renderer.geometry
        if geometry is None:
            return
        point = self.to_canvas(event.position())
        key = geometry.hit_key(point)
        if event.button() == Qt.MouseButton.RightButton:
            if key is not None and key["id"] not in self.selection:
                self.select([key["id"]])
            self.contextRequested.emit(key["id"] if key else "", event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        additive = bool(
            event.modifiers()
            & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        )
        handle = self._handle_at(point)
        if handle:
            target = self._key_by_id(self.selection[0])
            self._drag = {
                "mode": "resize",
                "handle": handle,
                "start": point,
                "moved": False,
                "origin": {target["id"]: key_box(target)},
            }
            event.accept()
            return
        if key is not None:
            key_id = key["id"]
            if additive:
                selection = list(self.selection)
                if key_id in selection:
                    selection.remove(key_id)
                else:
                    selection.append(key_id)
                self.select(selection)
                if key_id not in self.selection:
                    event.accept()
                    return
            elif key_id not in self.selection:
                self.select([key_id])
            self._drag = {
                "mode": "move",
                "start": point,
                "moved": False,
                "origin": {item["id"]: key_box(item) for item in self.selected_keys()},
            }
        else:
            base = list(self.selection) if additive else []
            if not additive:
                self.select([])
            self._drag = {"mode": "band", "start": point, "moved": False, "base": base}
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.preview_mode:
            super().mouseMoveEvent(event)
            return
        geometry = self.renderer.geometry
        if geometry is None:
            return
        point = self.to_canvas(event.position())
        drag = self._drag
        if drag is None:
            self._update_edit_hover(point)
            return
        delta = point - drag["start"]
        if not drag["moved"]:
            if abs(delta.x()) + abs(delta.y()) < _DRAG_THRESHOLD:
                return
            drag["moved"] = True
            if drag["mode"] in {"move", "resize"}:
                self.editStarted.emit()
        unit = max(1.0, geometry.unit)
        if drag["mode"] == "move":
            boxes = list(drag["origin"].values())
            du = snap_u(delta.x() / unit)
            dv = snap_u(delta.y() / unit)
            du = max(du, -min(box[0] for box in boxes))
            dv = max(dv, -min(box[1] for box in boxes))
            du = min(du, MAX_GRID_W - max(box[0] + box[2] for box in boxes))
            dv = min(dv, MAX_GRID_H - max(box[1] + box[3] for box in boxes))
            for key_id, (x, y, _w, _h) in drag["origin"].items():
                key = self._key_by_id(key_id)
                if key is not None:
                    key["x"], key["y"] = snap_u(x + du), snap_u(y + dv)
            self._after_live_edit()
        elif drag["mode"] == "resize":
            key_id, (x, y, w, h) = next(iter(drag["origin"].items()))
            key = self._key_by_id(key_id)
            if key is not None:
                if "e" in drag["handle"]:
                    w = max(MIN_KEY_U, min(MAX_KEY_W, MAX_GRID_W - x, snap_u(w + delta.x() / unit)))
                if "s" in drag["handle"]:
                    h = max(MIN_KEY_U, min(MAX_KEY_H, MAX_GRID_H - y, snap_u(h + delta.y() / unit)))
                key["w"], key["h"] = w, h
                self._after_live_edit()
        else:
            self._band = QRectF(drag["start"], point).normalized()
            hits = [
                key["id"] for key in geometry.keys if geometry.key_rect(key).intersects(self._band)
            ]
            selection = drag["base"] + [key_id for key_id in hits if key_id not in drag["base"]]
            if selection != self.selection:
                self.selection = selection
                self.selectionChanged.emit()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.preview_mode:
            super().mouseReleaseEvent(event)
            return
        drag = self._drag
        self._drag = None
        self._band = None
        if drag is not None and drag["moved"] and drag["mode"] in {"move", "resize"}:
            keys = self._page_keys()
            anchors = set(drag["origin"])
            if drag["mode"] == "move" and len(anchors) == 1:
                self._swap_if_dropped_on_twin(next(iter(anchors)), drag["origin"])
            settle_layout(keys, anchors)
            normalize_origin(keys)
            self.layoutEdited.emit()
        self.renderer.invalidate_background()
        self.refit()
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.preview_mode:
            super().mouseDoubleClickEvent(event)
            return
        key = self.key_at(event.position())
        if key is not None:
            self.keyDoubleClicked.emit(key["id"])
        event.accept()

    def _swap_if_dropped_on_twin(self, key_id: str, origin: dict) -> None:
        moved = self._key_by_id(key_id)
        if moved is None:
            return
        box = key_box(moved)
        others = [
            key
            for key in self._page_keys()
            if key["id"] != key_id and boxes_overlap(box, key_box(key))
        ]
        if len(others) != 1:
            return
        other = others[0]
        if (other["w"], other["h"]) != (moved["w"], moved["h"]):
            return
        overlap_w = min(box[0] + box[2], other["x"] + other["w"]) - max(box[0], other["x"])
        overlap_h = min(box[1] + box[3], other["y"] + other["h"]) - max(box[1], other["y"])
        if overlap_w * overlap_h >= 0.5 * box[2] * box[3]:
            # 같은 크기 키 위에 놓으면 자리를 맞바꾼다 (실물 키캡 교체처럼).
            target_x, target_y = other["x"], other["y"]
            other["x"], other["y"] = origin[key_id][0], origin[key_id][1]
            moved["x"], moved["y"] = target_x, target_y

    def _after_live_edit(self) -> None:
        self.renderer.invalidate_background()
        self.update()

    def _update_edit_hover(self, point: QPointF) -> None:
        handle = self._handle_at(point)
        geometry = self.renderer.geometry
        key = geometry.hit_key(point) if geometry is not None and not handle else None
        hover = key["id"] if key is not None else ""
        if hover != self._edit_hover:
            self._edit_hover = hover
            self.update()
        if handle == "se":
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle == "e":
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle == "s":
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif key is not None:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()

    def _paint_preview_banner(self, painter: QPainter) -> None:
        """Pill at the top of the canvas so the try-out mode is never mistaken for editing."""
        text = str(
            t(
                "widget.launcher.studio.preview_banner",
                "누르기 체험 중 · 키를 눌러 보세요 · 끝내려면 Esc",
            )
        )
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        width = QFontMetricsF(font).horizontalAdvance(text) + 28
        pill = QRectF((self.width() - width) / 2.0, 10.0, width, 26.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(58, 160, 255, 225))
        painter.drawRoundedRect(pill, 13.0, 13.0)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._edit_hover:
            self._edit_hover = ""
            self.update()
        super().leaveEvent(event)

    # -- keyboard ------------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.preview_mode:
            super().keyPressEvent(event)
            return
        key = event.key()
        modifiers = event.modifiers()
        arrows = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if key in arrows and self.selection:
            step = 1.0 if modifiers & Qt.KeyboardModifier.ShiftModifier else GRID_STEP
            self.nudge(arrows[key][0] * step, arrows[key][1] * step)
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selection:
            self.deleteRequested.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Escape and self.selection:
            self.select([])
            event.accept()
            return
        if key == Qt.Key.Key_A and modifiers & Qt.KeyboardModifier.ControlModifier:
            self.select([item["id"] for item in self._page_keys()])
            event.accept()
            return
        super().keyPressEvent(event)

    def nudge(self, dx: float, dy: float) -> None:
        keys = self.selected_keys()
        if not keys:
            return
        dx = max(dx, -min(key["x"] for key in keys))
        dy = max(dy, -min(key["y"] for key in keys))
        dx = min(dx, MAX_GRID_W - max(key["x"] + key["w"] for key in keys))
        dy = min(dy, MAX_GRID_H - max(key["y"] + key["h"] for key in keys))
        if not dx and not dy:
            return
        self.editStarted.emit()
        for key in keys:
            key["x"], key["y"] = snap_u(key["x"] + dx), snap_u(key["y"] + dy)
        page_keys = self._page_keys()
        settle_layout(page_keys, {key["id"] for key in keys})
        normalize_origin(page_keys)
        self.layoutEdited.emit()
        self.renderer.invalidate_background()
        self.refit()
        self.update()


__all__ = ["SELECTION_COLOR", "StudioCanvas"]
