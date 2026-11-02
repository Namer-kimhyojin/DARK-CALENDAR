# -*- coding: utf-8 -*-
"""Real widget thumbnails with one staged, optionally animated inspector."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.widget_management_ui import hub_button, hub_label
from calendar_app.presentation.widgets.widget_workspace_preview import (
    ThumbnailCache,
    native_thumbnail,
    thumbnail_icon,
    widget_health,
)


class WidgetGallery(QWidget):
    def __init__(self, dialog, service):
        super().__init__(dialog)
        self.dialog, self.service, self.manager = dialog, service, dialog._mgr
        self.cache = ThumbnailCache()
        self.current_id = None
        self.items = {}
        self._loading = False
        self._draft_origin = None
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        left = QVBoxLayout()
        toolbar = QHBoxLayout()
        toolbar.addWidget(
            hub_button(
                t("widget_studio.refresh_preview", "미리보기 새로고침"), self.refresh_previews
            )
        )
        toolbar.addWidget(
            hub_button(
                t("widget_studio.create_stack", "선택 위젯 스택 만들기"), dialog._create_stack
            )
        )
        left.addLayout(toolbar)
        self.list = QListWidget()
        self.list.setObjectName("studioGallery")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(210, 120))
        self.list.setGridSize(QSize(230, 185))
        self.list.setWordWrap(True)
        self.list.setSpacing(5)
        self.list.setAccessibleName(t("widget_studio.gallery", "위젯 미리보기 갤러리"))
        self.list.currentItemChanged.connect(self._selected)
        self.list.itemDoubleClicked.connect(
            lambda _: dialog._on_graphics(self.current_id) if self.current_id else None
        )
        self.list.verticalScrollBar().valueChanged.connect(lambda _: self._icon_timer.start(0))
        self.list.horizontalScrollBar().valueChanged.connect(lambda _: self._icon_timer.start(0))
        left.addWidget(self.list, 1)
        self.selection_help = hub_label(
            t("widget_studio.multi_select", "Ctrl+클릭으로 여러 위젯 선택 · 더블클릭으로 꾸미기")
        )
        left.addWidget(self.selection_help)
        root.addLayout(left, 1)
        sidebar_widget = QWidget()
        sidebar_widget.setFixedWidth(264)
        sidebar = QVBoxLayout(sidebar_widget)
        sidebar.setContentsMargins(0, 0, 0, 0)
        inspector = QScrollArea()
        inspector.setObjectName("studioInspector")
        inspector.viewport().setObjectName("studioInspectorViewport")
        inspector.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inspector.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("studioInspectorBody")
        detail = QVBoxLayout(content)
        detail.setContentsMargins(12, 8, 12, 8)
        detail.setSpacing(10)
        self.title = hub_label(t("widget_studio.choose_widget", "위젯을 선택하세요"), "hubTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(120)
        self.preview.setAccessibleName(t("widget_studio.current_preview", "현재 위젯 미리보기"))
        self.status = hub_label("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        detail.addWidget(self.title)
        detail.addWidget(self.preview)
        detail.addWidget(self.status)
        self.animate = QCheckBox(t("widget_studio.animate_preview", "선택 미리보기 움직임"))
        self.animate.toggled.connect(self._sync_timer)
        detail.addWidget(self.animate)
        form = QFormLayout()
        self.width_spin, self.height_spin, self.opacity_spin = QSpinBox(), QSpinBox(), QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(40, 8192)
        self.opacity_spin.setRange(10, 100)
        self.opacity_spin.setSuffix("%")
        for spin, key, label in (
            (self.width_spin, "width", "너비"),
            (self.height_spin, "height", "높이"),
            (self.opacity_spin, "opacity", "불투명도"),
        ):
            spin.setAccessibleName(t("widget_studio." + key, label))
            form.addRow(t("widget_studio." + key, label), spin)
        detail.addLayout(form)
        detail.addWidget(hub_label(t("widget_studio.draft_ratio", "크기 비율·투명도 미리보기")))
        self.expected = QLabel()
        self.expected.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.expected.setMinimumHeight(100)
        detail.addWidget(self.expected)
        detail.addWidget(
            hub_label(
                t(
                    "widget_studio.size_help",
                    "크기 변경 후 내용 배치는 실제 위젯에 맞춰 조정됩니다. 잠긴 위젯은 잠금을 해제한 뒤 편집하세요.",
                )
            )
        )
        row = QHBoxLayout()
        self.apply_button = hub_button(t("common.apply", "적용"), self.apply_draft, primary=True)
        row.addWidget(self.apply_button)
        row.addWidget(hub_button(t("common.cancel", "취소"), self.reset_draft))
        sidebar.addWidget(inspector, 1)
        sidebar.addLayout(row)
        detail.addWidget(
            hub_button(t("widget_hub.decorate", "꾸미기"), lambda: self._route("graphics"))
        )
        detail.addWidget(
            hub_button(t("widget_manager.btn_settings", "설정"), lambda: self._route("settings"))
        )
        self.retry_button = hub_button(
            t("widget_studio.retry_weather", "날씨 다시 확인"), self._retry
        )
        detail.addWidget(self.retry_button)
        detail.addStretch()
        inspector.setWidget(content)
        root.addWidget(sidebar_widget)
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(120)
        self._draft_timer.timeout.connect(self._update_expected)
        for spin in (self.width_spin, self.height_spin, self.opacity_spin):
            spin.valueChanged.connect(
                lambda _: self._draft_timer.start() if not self._loading else None
            )
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._preview_tick)
        self._icon_timer = QTimer(self)
        self._icon_timer.setSingleShot(True)
        self._icon_timer.timeout.connect(self._fill_visible_icons)
        self.service.changed.connect(self._service_changed)

    def selected_ids(self):
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list.selectedItems()
            if not item.isHidden()
        ]

    def populate(self, rows, matches):
        existing = {row[0] for row in rows}
        for iid in set(self.items) - existing:
            self.list.takeItem(self.list.row(self.items.pop(iid)))
        for iid, name, kind, widget in rows:
            item = self.items.get(iid)
            if item is None:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, iid)
                item.setSizeHint(self.list.gridSize())
                self.items[iid] = item
                self.list.addItem(item)
            item.setHidden(iid not in matches)
            state = (
                t("widget_hub.shown", "표시 중")
                if widget.is_enabled()
                else t("widget_hub.hidden", "숨김")
            )
            _, health, hint = widget_health(widget, kind)
            group = self.service.stacks.group_for(iid)
            if widget.is_enabled() and group and group["members"][group["index"]] != iid:
                state = t("widget_studio.stack_waiting", "스택 대기")
            suffix = f" · {group['name']}" if group else ""
            item.setText(f"{name}\n{state} · {health}{suffix}")
            item.setToolTip(hint or name)
        if self.current_id not in matches:
            self.list.setCurrentItem(
                next((item for iid, item in self.items.items() if iid in matches), None)
            )
        elif self.current_id is not None:
            widget = self.manager.get_widget(self.current_id)
            origin = (widget.width(), widget.height(), int(widget._get("widget_opacity", 100)))
            if origin != self._draft_origin:
                self.reset_draft()
        self._icon_timer.start(0)
        self._sync_timer()

    def _fill_visible_icons(self):
        if not self.isVisible():
            return
        viewport = self.list.viewport().rect().adjusted(0, -185, 0, 185)
        for iid, item in self.items.items():
            if not item.isHidden() and self.list.visualItemRect(item).intersects(viewport):
                widget = self.manager.get_widget(iid)
                if widget is not None:
                    item.setIcon(thumbnail_icon(self.cache.get(iid, widget)))
            elif not item.icon().isNull():
                item.setIcon(QIcon())

    def _service_changed(self):
        self.cache.clear()
        if self.isVisible():
            self._icon_timer.start(0)
        self._sync_timer()

    def _selected(self, current, previous=None):
        self.current_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.reset_draft()
        self._sync_timer()

    def reset_draft(self):
        self._draft_timer.stop()
        widget = self.manager.get_widget(self.current_id) if self.current_id else None
        if widget is None:
            self.title.setText(t("widget_studio.choose_widget", "위젯을 선택하세요"))
            self.apply_button.setEnabled(False)
            self.preview.clear()
            self.expected.clear()
            self.status.clear()
            return
        row = next(row for row in self.manager.all_instances() if row[0] == self.current_id)
        self.title.setText(row[1])
        self._loading = True
        self.width_spin.setValue(widget.width())
        self.height_spin.setValue(widget.height())
        self.opacity_spin.setValue(
            int(getattr(widget, "_get", lambda *a, **k: 100)("widget_opacity", 100))
        )
        self._loading = False
        self._draft_origin = (widget.width(), widget.height(), self.opacity_spin.value())
        self.apply_button.setEnabled(not widget.placement_is_locked())
        self.retry_button.setVisible(row[2] == "weather")
        self._preview_tick()
        self._update_expected()

    def _preview_tick(self):
        widget = self.manager.get_widget(self.current_id) if self.current_id else None
        if widget is None:
            self._preview_timer.stop()
            return
        pixmap = self.cache.get(self.current_id, widget, fresh=True)
        self.preview.setPixmap(
            pixmap.scaled(
                round(228 * pixmap.devicePixelRatio()),
                round(130 * pixmap.devicePixelRatio()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.items[self.current_id].setIcon(thumbnail_icon(pixmap))
        kind = next(row[2] for row in self.manager.all_instances() if row[0] == self.current_id)
        _, label, hint = widget_health(widget, kind)
        self.status.setText(label + ("\n" + hint if hint else ""))

    def _update_expected(self):
        widget = self.manager.get_widget(self.current_id) if self.current_id else None
        if widget is not None:
            self.expected.setPixmap(
                native_thumbnail(
                    widget,
                    QSize(228, 110),
                    opacity=self.opacity_spin.value(),
                    frame_size=QSize(self.width_spin.value(), self.height_spin.value()),
                )
            )

    def apply_draft(self):
        widget = self.manager.get_widget(self.current_id) if self.current_id else None
        if widget is None:
            return
        raw = [widget.x(), widget.y(), self.width_spin.value(), self.height_spin.value()]
        self.service.apply_geometry({self.current_id: raw}, opacity=self.opacity_spin.value())
        self.refresh_previews()

    def refresh_previews(self):
        self.cache.clear()
        self.dialog._apply_filters()
        self.reset_draft()

    def _route(self, kind):
        if self.current_id:
            (self.dialog._on_graphics if kind == "graphics" else self.dialog._on_settings)(
                self.current_id
            )
            self.refresh_previews()

    def _retry(self):
        widget = self.manager.get_widget(self.current_id) if self.current_id else None
        if widget is not None and hasattr(widget, "request_update"):
            widget.request_update()
            self._preview_tick()

    def _sync_timer(self, *_):
        allowed = (
            self.isVisible()
            and self.current_id is not None
            and self.animate.isChecked()
            and self.service.state["options"]["motion"] != "static"
            and not self.service._paused
        )
        self._preview_timer.start() if allowed else self._preview_timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.dialog._apply_filters()
        self._sync_timer()

    def hideEvent(self, event):
        self._icon_timer.stop()
        self._preview_timer.stop()
        self._draft_timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.height() < 300
        self.selection_help.setVisible(not compact)
        self.list.setIconSize(QSize(160, 90) if compact else QSize(210, 120))
        self.list.setGridSize(QSize(180, 145) if compact else QSize(230, 185))
        for item in self.items.values():
            item.setSizeHint(self.list.gridSize())
        if hasattr(self, "_icon_timer"):
            self._icon_timer.start(0)
