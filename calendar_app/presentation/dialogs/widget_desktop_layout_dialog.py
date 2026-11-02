# -*- coding: utf-8 -*-
"""Draft-only monitor canvas for arranging existing desktop widgets."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from calendar_app.domain.widget_workspace import arrange_rectangles
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    build_dialog_footer,
)
from calendar_app.presentation.widgets.widget_management_ui import (
    apply_hub_dialog_style,
    hub_button,
    hub_label,
)
from calendar_app.presentation.widgets.widget_workspace_preview import native_thumbnail
from calendar_app.shared.theme_snapshot import _css_to_qcolor as token_color


class DesktopWidgetItem(QGraphicsRectItem):
    def __init__(self, iid, name, widget, editor, thumbnail=True):
        rect = widget.geometry()
        super().__init__(0, 0, rect.width(), rect.height())
        self.iid, self.name, self.editor = iid, name, editor
        self.locked = widget.placement_is_locked()
        self.preview = native_thumbnail(widget) if thumbnail else None
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        if not self.locked:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setPos(rect.x(), rect.y())
        self.setZValue(2)
        self.setToolTip(
            name + (" · " + t("widget_studio.locked", "배치 잠김") if self.locked else "")
        )

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = token_color(
            self.editor.tokens["accent"]
            if self.isSelected()
            else self.editor.tokens["border_strong"]
        )
        painter.setPen(QPen(color, 4 if self.isSelected() else 2))
        painter.setBrush(token_color(self.editor.tokens["bg_item"]))
        painter.drawRoundedRect(self.rect(), 8, 8)
        if self.preview is not None:
            painter.drawPixmap(
                self.rect().adjusted(4, 4, -4, -4), self.preview, QRectF(self.preview.rect())
            )
        caption = self.rect().adjusted(4, 4, -4, -4)
        caption.setHeight(min(42, self.rect().height() / 3))
        painter.fillRect(caption, token_color(self.editor.tokens["bg_main"]))
        painter.setPen(token_color(self.editor.tokens["text_primary"]))
        font = QFont()
        font.setPixelSize(max(12, min(24, round(self.rect().width() / 14))))
        painter.setFont(font)
        painter.drawText(caption, Qt.AlignmentFlag.AlignCenter, self.name)

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and hasattr(self, "editor")
            and not self.editor._building
            and self.editor.snap.isChecked()
        ):
            return QPointF(round(value.x() / 10) * 10, round(value.y() / 10) * 10)
        return super().itemChange(change, value)


class WidgetDesktopLayoutDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle(t("widget_studio.layout_editor", "바탕화면 배치 편집"))
        apply_hub_dialog_style(self, parent, minimum_width=720, size=(1000, 700))
        from calendar_app.presentation.widgets.overlay_manager_dialog import _load_tokens

        self.tokens = getattr(parent, "_tok", None) or _load_tokens()
        self._building = True
        root = QVBoxLayout(self)
        root.addWidget(
            hub_label(
                t(
                    "widget_studio.layout_help",
                    "드래그로 이동하고 Ctrl+클릭으로 여러 위젯을 선택하세요. 잠긴 위젯은 유지하며, 적용 전까지 실제 배치는 바뀌지 않습니다.",
                )
            )
        )
        tools = QHBoxLayout()
        self.snap = QCheckBox(t("widget_studio.grid_snap", "격자에 맞춤"))
        self.snap.setChecked(True)
        tools.addWidget(self.snap)
        for action, key, fallback in (
            ("left", "align_left", "왼쪽 정렬"),
            ("top", "align_top", "위쪽 정렬"),
            ("horizontal", "space_h", "가로 간격"),
            ("vertical", "space_v", "세로 간격"),
        ):
            tools.addWidget(
                hub_button(
                    t("widget_studio." + key, fallback),
                    lambda _=False, action=action: self.arrange(action),
                )
            )
        tools.addStretch()
        root.addLayout(tools)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setBackgroundBrush(token_color(self.tokens["bg_alt"]))
        self.items_by_id = {}
        self.originals = {}
        bounds = QRectF()
        for screen in QApplication.screens():
            rect = QRectF(screen.availableGeometry())
            monitor = self.scene.addRect(
                rect,
                QPen(token_color(self.tokens["border_strong"]), 4),
                token_color(self.tokens["bg_main"]),
            )
            monitor.setZValue(-2)
            text = self.scene.addText(screen.name())
            text.setDefaultTextColor(token_color(self.tokens["text_muted"]))
            text.setPos(rect.x() + 12, rect.y() + 6)
            text.setScale(2)
            bounds = bounds.united(rect)
        for index, (iid, name, _, widget) in enumerate(service.manager.all_instances()):
            item = DesktopWidgetItem(iid, name, widget, self, thumbnail=index < 32)
            self.items_by_id[iid] = item
            r = widget.geometry()
            self.originals[iid] = [r.x(), r.y(), r.width(), r.height()]
            self.scene.addItem(item)
        self._building = False
        self.scene.setSceneRect(bounds.adjusted(-30, -30, 30, 30))
        self.scene.selectionChanged.connect(self._selection_changed)
        root.addWidget(self.view, 1)
        fields = QHBoxLayout()
        self.monitor_combo = QComboBox()
        self.monitor_combo.setAccessibleName(
            t("widget_studio.move_monitor", "선택 위젯을 모니터로 이동")
        )
        self.monitor_combo.addItem(
            t("widget_studio.move_monitor", "선택 위젯을 모니터로 이동"), None
        )
        for screen in QApplication.screens():
            self.monitor_combo.addItem(screen.name(), screen.name())
        self.monitor_combo.activated.connect(self._move_monitor)
        fields.addWidget(self.monitor_combo)
        fields.addWidget(QLabel(t("widget_studio.width", "너비")))
        self.width_spin, self.height_spin = QSpinBox(), QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(40, 8192)
            spin.valueChanged.connect(self._resize_selected)
        fields.addWidget(self.width_spin)
        fields.addWidget(QLabel(t("widget_studio.height", "높이")))
        fields.addWidget(self.height_spin)
        self.width_spin.setAccessibleName(t("widget_studio.width", "너비"))
        self.height_spin.setAccessibleName(t("widget_studio.height", "높이"))
        fields.addStretch()
        root.addLayout(fields)
        self.feedback = hub_label("")
        root.addWidget(self.feedback)
        footer, self.apply_button, cancel = build_dialog_footer(
            ok_label=t("common.apply", "적용"), cancel_label=t("common.cancel", "취소")
        )
        self.apply_button.clicked.connect(self._apply)
        cancel.clicked.connect(self.reject)
        root.addLayout(footer)
        self._selection_changed()

    def _selection_changed(self):
        selected = [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, DesktopWidgetItem) and not item.locked
        ]
        for spin in (self.width_spin, self.height_spin):
            spin.setEnabled(len(selected) == 1)
        if len(selected) == 1:
            for spin, value in (
                (self.width_spin, selected[0].rect().width()),
                (self.height_spin, selected[0].rect().height()),
            ):
                spin.blockSignals(True)
                spin.setValue(round(value))
                spin.blockSignals(False)
        self.feedback.setText(
            t(
                "widget_studio.selected_count", "선택 {count}개 · 크기 변경은 한 개 선택 시 사용"
            ).format(count=len(selected))
        )

    def draft_rectangles(self, selected_only=False):
        return {
            iid: [
                round(item.x()),
                round(item.y()),
                round(item.rect().width()),
                round(item.rect().height()),
            ]
            for iid, item in self.items_by_id.items()
            if not item.locked and (not selected_only or item.isSelected())
        }

    def arrange(self, action):
        draft = arrange_rectangles(self.draft_rectangles(selected_only=True), action)
        for iid, raw in draft.items():
            self.items_by_id[iid].setPos(raw[0], raw[1])

    def _resize_selected(self):
        selected = [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, DesktopWidgetItem) and not item.locked
        ]
        if len(selected) == 1:
            selected[0].setRect(0, 0, self.width_spin.value(), self.height_spin.value())

    def _move_monitor(self, index):
        name = self.monitor_combo.itemData(index)
        screen = next((s for s in QApplication.screens() if s.name() == name), None)
        if screen is None:
            return
        selected = self.draft_rectangles(selected_only=True)
        if not selected:
            return
        left, top = min(r[0] for r in selected.values()), min(r[1] for r in selected.values())
        area = screen.availableGeometry()
        for iid, rect in selected.items():
            self.items_by_id[iid].setPos(
                area.x() + 24 + rect[0] - left, area.y() + 24 + rect[1] - top
            )

    def _apply(self):
        changed = {
            iid: rect
            for iid, rect in self.draft_rectangles().items()
            if rect != self.originals[iid]
        }
        if changed:
            self.service.apply_geometry(changed)
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "view"):
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
