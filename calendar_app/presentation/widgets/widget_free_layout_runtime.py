# -*- coding: utf-8 -*-
"""Independent content blocks inside the unified widget's free-layout canvas."""

from collections import Counter

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t


def item_matches_block(item, block_id):
    """Split work never also includes directive rows, even when both are tasks."""
    if item.get("is_section"):
        return False
    if block_id == "directive":
        return item.get("source") == "directive"
    if block_id == "work":
        return item.get("item_kind") == "work" and item.get("source") != "directive"
    return item.get("item_kind") == "schedule" and item.get("source") != "directive"


class FreeAgendaPanel(QFrame):
    """A local list projection with the shared controller's original item actions."""

    def __init__(self, window, block_id, parent=None):
        super().__init__(parent)
        self.window = window
        self.block_id = block_id
        self.rows = []
        self._signature = None
        self._revision = 0
        self._context = None
        self.setObjectName("unified_agenda_section")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        self.heading = QLabel(self)
        self.heading.setObjectName("unified_section")
        self.heading.setText(window._filter_labels()[block_id])
        root.addWidget(self.heading)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("unified_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setObjectName("unified_scroll_viewport")
        self.content = QWidget(self.scroll)
        self.content.setObjectName("unified_scroll_content")
        self.list_layout = QVBoxLayout(self.content)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    def update_items(self, items, *, data_state="ready"):
        from calendar_app.presentation.widgets.unified_widget_mode import AgendaItemWidget
        from calendar_app.presentation.widgets.widget_mode_density import read_widget_density

        selected = [dict(item) for item in items if item_matches_block(item, self.block_id)]
        context = self.window.controller._current_date().toJulianDay()
        signature = (selected, self.window._style_signature, data_state, context)
        if signature == self._signature:
            return
        self._signature = signature
        focused = QApplication.focusWidget()
        focus_row = next((row for row in self.rows if focused and row.isAncestorOf(focused)), None)
        old_order = [row.item_key for row in self.rows]
        anchor = next(
            (
                row
                for row in self.rows
                if row.mapTo(self.scroll.viewport(), QPoint()).y() + row.height() > 0
            ),
            None,
        )
        anchor_key = anchor.item_key if anchor else None
        offset = anchor.mapTo(self.scroll.viewport(), QPoint()).y() if anchor else 0
        focus_key = focus_row.item_key if focus_row else None
        focus_role = focused.objectName() if focus_row else None
        same_context = context == self._context
        self._context = context
        old = {row.item_key: row for row in self.rows}
        old_counts = Counter(old_order)
        new_counts = Counter((item.get("source"), item.get("item_id")) for item in selected)
        retained = {}
        for item in selected:
            key = (item.get("source"), item.get("item_id"))
            row = old.get(key)
            row_signature = (item, self.window._style_signature)
            if (
                all(key)
                and old_counts[key] == new_counts[key] == 1
                and row
                and row.item_signature == row_signature
            ):
                retained[key] = row
        kept_widgets = set(retained.values())
        while self.list_layout.count() > 1:
            widget = self.list_layout.takeAt(0).widget()
            if widget is not None and widget not in kept_widgets:
                widget.hide()
                widget.deleteLater()
        self.rows = []
        self.list_layout.setSpacing(
            read_widget_density(self.window.controller.main_window.settings).row_spacing
        )
        self.heading.setText(self.window._filter_labels()[self.block_id])
        count = t("widget_mode.item_count_chip", "{count}개", count=len(selected))
        self.heading.setAccessibleDescription(count)
        if data_state != "ready":
            label = QLabel(
                t("widget_mode.loading", "일정을 불러오는 중…")
                if data_state == "loading"
                else t(
                    "widget_mode.load_delayed",
                    "일정을 아직 불러오지 못했습니다. 다시 시도해 주세요.",
                ),
                self.content,
            )
            label.setObjectName("unified_hint")
            label.setWordWrap(True)
            self.list_layout.insertWidget(self.list_layout.count() - 1, label)
            if data_state == "delayed":
                retry = QToolButton(self.content)
                retry.setObjectName("unified_action_btn")
                retry.setText(t("widget_mode.retry", "다시 시도"))
                retry.clicked.connect(self.window.controller.retry_refresh)
                self.list_layout.insertWidget(self.list_layout.count() - 1, retry)
        if not selected and data_state == "ready":
            key = {
                "schedule": "empty_schedule_filter",
                "work": "empty_work_filter",
                "directive": "empty_directive_filter",
            }[self.block_id]
            label = QLabel(t(f"widget_mode.{key}", "이 날짜에 항목이 없습니다."), self.content)
            label.setObjectName("unified_empty")
            label.setWordWrap(True)
            self.list_layout.insertWidget(0, label)
        for item in selected:
            key = (item.get("source"), item.get("item_id"))
            row = retained.get(key)
            if row is None:
                row = AgendaItemWidget(
                    str(item.get("title") or t("widget_mode.untitled", "제목 없음")),
                    str(item.get("time") or ""),
                    is_task=bool(item.get("is_task")),
                    item=item,
                    controller=self.window.controller,
                    parent=self.content,
                )
                row.item_signature = (dict(item), self.window._style_signature)
            check = row.findChild(QCheckBox, "agenda_complete")
            if check:
                blocked = check.blockSignals(True)
                check.setChecked(bool(item.get("completed")))
                check.blockSignals(blocked)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self.rows.append(row)
        self._revision += 1
        revision = self._revision
        expected_focus = QApplication.focusWidget()

        def restore():
            if sip.isdeleted(self) or revision != self._revision:
                return
            rows = {row.item_key: row for row in self.rows}

            def neighbor(key):
                if key in rows:
                    return rows[key]
                if key in old_order:
                    index = old_order.index(key)
                    for candidate in old_order[index + 1 :] + list(reversed(old_order[:index])):
                        if candidate in rows:
                            return rows[candidate]
                return self.rows[0] if self.rows else None

            if focus_key and QApplication.focusWidget() is expected_focus:
                row = neighbor(focus_key) if same_context else (self.rows[0] if self.rows else None)
                control = row.findChild(QWidget, focus_role) if row else self.window.add_btn
                if control is not None:
                    control.setFocus(Qt.FocusReason.OtherFocusReason)
            self.list_layout.activate()
            row = neighbor(anchor_key) if same_context else None
            self.scroll.verticalScrollBar().setValue(row.y() - offset if row else 0)

        QTimer.singleShot(0, restore)


class FreeLayoutCanvas(QWidget):
    """Render saved proportions without imposing editor snap or a runtime grid."""

    def __init__(self, window):
        super().__init__(window.container)
        self.window = window
        self.setObjectName("unified_free_canvas")
        self.data = None
        self.frames = {}
        self.panels = {}
        self.previous_minimums = {}
        self.previous_backgrounds = {}
        self.previous_styles = {}
        self.date_button = QToolButton(self)
        self.date_button.setObjectName("unified_action_btn")
        self.date_button.clicked.connect(window._pick_date)
        self.date_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.date_button.setMinimumHeight(32)
        self.contents = {
            "date": self.date_button,
            "clock": window.clock_label,
            "calendar": window.cal_grid,
            "filters": window.filter_section,
            "agenda": window.agenda_section,
        }
        for kind in ("schedule", "work", "directive"):
            panel = FreeAgendaPanel(window, kind, self)
            self.panels[kind] = panel
            self.contents[kind] = panel
        for block_id, content in self.contents.items():
            frame = QFrame(self)
            frame.setObjectName("unified_free_block")
            frame.setProperty("blockId", block_id)
            layout = QVBoxLayout(frame)
            layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            layout.setContentsMargins(0, 0, 0, 0)
            if block_id == "filters":
                heading = QLabel(t("widget_mode.free_filter_heading", "통합 목록 필터"), frame)
                heading.setObjectName("unified_section")
                heading.setToolTip(heading.text())
                heading.setAccessibleName(heading.text())
                heading.setMinimumWidth(0)
                heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                layout.addWidget(heading)
            viewport = QScrollArea(frame)
            viewport.setObjectName("unified_scroll")
            viewport.viewport().setObjectName("unified_scroll_viewport")
            viewport.setFrameShape(QFrame.Shape.NoFrame)
            viewport.setWidgetResizable(True)
            self.previous_minimums[block_id] = content.minimumSize()
            self.previous_backgrounds[block_id] = content.autoFillBackground()
            self.previous_styles[block_id] = content.styleSheet()
            from calendar_app.presentation.widgets.widget_free_layout import BLOCK_MINIMUM_SIZES

            content.setMinimumSize(*BLOCK_MINIMUM_SIZES[block_id])
            if block_id in {"date", "clock"}:
                content.setMinimumSize(0, 0)
                content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
                content.setParent(frame)
                layout.addWidget(content)
                viewport.deleteLater()
                frame.content_viewport = None
            else:
                viewport.setWidget(content)
                content.setAutoFillBackground(False)
                viewport.viewport().setAutoFillBackground(False)
                layout.addWidget(viewport)
                frame.content_viewport = viewport
            self.frames[block_id] = frame

    def enabled_block_ids(self):
        return {block["id"] for block in (self.data or {}).get("blocks", ()) if block["enabled"]}

    def apply_data(self, data):
        self.data = data
        for block_id, frame in self.frames.items():
            frame.setVisible(block_id in self.enabled_block_ids())
            self.contents[block_id].setVisible(block_id in self.enabled_block_ids())
        for block_id in data.get("order", self.frames):
            self.frames[block_id].raise_()
        self.update_date()
        self.layout_blocks()

    def update_date(self):
        label = self.window.date_picker_btn.text()
        self.date_button.setText(label)
        self.date_button.setToolTip(self.window.date_picker_btn.accessibleName())
        self.date_button.setAccessibleName(self.date_button.toolTip())
        self.layout_blocks()

    def update_items(self, items):
        enabled = self.enabled_block_ids()
        for kind, panel in self.panels.items():
            if kind in enabled:
                panel.update_items(items, data_state=self.window._data_state)

    def restore_item_check(self, item):
        for panel in self.panels.values():
            for row in panel.rows:
                if row.item_key == (item.get("source"), item.get("item_id")):
                    check = row.findChild(QCheckBox, "agenda_complete")
                    if check is not None:
                        blocked = check.blockSignals(True)
                        check.setChecked(bool(item.get("completed")))
                        check.blockSignals(blocked)

    def layout_blocks(self):
        if not self.data or self.width() < 1 or self.height() < 1:
            return
        canvas_w, canvas_h = self.data["canvas"]
        from calendar_app.presentation.widgets.widget_free_layout import BLOCK_MINIMUM_SIZES

        for block in self.data["blocks"]:
            frame = self.frames.get(block["id"])
            if frame is None or not block["enabled"]:
                continue
            x, y, width, height = block["rect"]
            min_width, min_height = BLOCK_MINIMUM_SIZES[block["id"]]
            width = min(
                self.width(),
                max(
                    1,
                    round(min_width * self.width() / canvas_w),
                    round(width * self.width() / canvas_w),
                ),
            )
            height = min(
                self.height(),
                max(
                    1,
                    round(min_height * self.height() / canvas_h),
                    round(height * self.height() / canvas_h),
                ),
            )
            x = max(0, min(self.width() - width, round(x * self.width() / canvas_w)))
            y = max(0, min(self.height() - height, round(y * self.height() / canvas_h)))
            frame.setGeometry(QRect(x, y, width, height))
            if block["id"] in {"date", "clock"}:
                self._fit_readout(block["id"], width, height)
        if "filters" in self.enabled_block_ids():
            self.window._apply_filter_responsive_layout(self.window.filter_section.width())

    def _fit_readout(self, block_id, width, height):
        from calendar_app.presentation.widgets.widget_mode_typography import read_widget_typography

        content = self.contents[block_id]
        typography = read_widget_typography(self.window.controller.main_window.settings)
        points = typography.date if block_id == "date" else typography.control
        font = QFont(self.window.font())
        text = content.text()
        while points > 6:
            font.setPointSizeF(points)
            metrics = QFontMetrics(font)
            if metrics.horizontalAdvance(text) <= max(1, width - 8) and metrics.height() <= max(
                1, height - 4
            ):
                break
            points = max(6, points - 0.5)
        content.setStyleSheet(f"font-size: {points:.1f}pt;")
        if block_id == "clock":
            content.setToolTip(text)
            content.setAccessibleName(text)

    def detach_existing(self):
        """Return borrowed widgets to their original containers before presets resume."""
        for block_id in ("calendar", "filters", "agenda"):
            content = self.contents[block_id]
            self.frames[block_id].content_viewport.takeWidget()
            content.setMinimumSize(self.previous_minimums[block_id])
            content.setAutoFillBackground(self.previous_backgrounds[block_id])
            content.setParent(self.window.container)
        clock = self.contents["clock"]
        self.frames["clock"].layout().removeWidget(clock)
        clock.setMinimumSize(self.previous_minimums["clock"])
        clock.setAutoFillBackground(self.previous_backgrounds["clock"])
        clock.setStyleSheet(self.previous_styles["clock"])
        clock.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        clock.setParent(self.window)
        self.window.footer_layout.insertWidget(self.window.footer_layout.count() - 1, clock)
        self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_blocks()
