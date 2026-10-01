# -*- coding: utf-8 -*-
"""Render isolated editor snapshots with the actual widget-mode components."""

from copy import deepcopy

from PyQt6 import sip
from PyQt6.QtCore import QDate, QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QAbstractScrollArea, QLayout, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.widget_customization_dialog import _DraftSettings
from calendar_app.presentation.widgets.widget_free_layout import (
    validate_free_layout,
    write_free_layout,
)


class PreviewRenderer:
    """Own a hidden renderer backed by draft settings and detached item snapshots.

    The returned pixmap has DPR 1 and the exact canvas size, so editor coordinates
    also match on fractional-DPI screens. Native control rendering is downsampled
    when needed; the editor can scale the image while retaining its proportions.
    """

    def __init__(self, settings, parent=None):
        from calendar_app.presentation.widgets.unified_widget_mode import (
            UnifiedWidgetController,
            UnifiedWidgetWindow,
        )

        self._closed = False
        self.settings = _DraftSettings(settings)
        self.settings.setValue("widget_mode_filter", "all")
        self.host = QWidget()
        self.host.hide()
        self.host.settings = self.settings
        self.host.current_date = QDate.currentDate()
        self._set_item_cache(self._example_items())
        self.host.schedule_panel_refresh = lambda **_kwargs: None
        self.controller = UnifiedWidgetController(self.host)
        self.window = UnifiedWidgetWindow(self.controller)
        self.controller.widget = self.window
        self.window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.window.setAccessibleName(t("widget_mode.free_preview", "예시 일정 미리보기"))
        self.window.setMinimumSize(0, 0)
        self.window.timer.stop()
        self.controller.prepare_shutdown()
        if parent is not None:
            parent.destroyed.connect(self.close)

    @staticmethod
    def _example_items():
        return [
            {
                "source": "task",
                "item_id": 101,
                "item_kind": "schedule",
                "is_task": False,
                "title": t("widget_mode.preview_schedule", "프로젝트 회의"),
                "time": "14:00",
            },
            {
                "source": "task",
                "item_id": 102,
                "item_kind": "work",
                "is_task": True,
                "title": t("widget_mode.preview_work", "회의 자료 정리"),
                "time": "",
                "status": "in_progress",
                "completed": False,
            },
            {
                "source": "directive",
                "item_id": 103,
                "item_kind": "work",
                "is_task": True,
                "title": t("widget_mode.preview_directive", "검토 의견 전달"),
                "time": "",
                "status": "pending",
                "completed": False,
            },
        ]

    def _set_item_cache(self, items):
        """Project this snapshot into a local date cache for native day markers.

        There is no real host cache or controller behind this projection. Items
        already represent the selected day, so no database range is requested.
        """
        date = self.host.current_date.toString("yyyy-MM-dd")
        schedules, routines, directives = [], [], []
        for item in items:
            if item.get("is_section"):
                continue
            if item.get("source") == "directive":
                directives.append(
                    (
                        item.get("item_id"),
                        item.get("title"),
                        item.get("status", "pending"),
                        "",
                        date,
                    )
                )
            elif item.get("item_kind") == "work":
                routines.append(
                    {
                        "id": item.get("item_id"),
                        "name": item.get("title"),
                        "target_date": date,
                        "status": item.get("status", "pending"),
                        "is_completed": bool(item.get("completed")),
                    }
                )
            else:
                schedules.append(
                    {
                        "id": item.get("item_id"),
                        "name": item.get("title"),
                        "deadline": f"{date} {item.get('time') or '00:00'}",
                    }
                )
        self.host._latest_calendar_range_data = {
            "range_start": self.host.current_date.addDays(-31).toString("yyyy-MM-dd"),
            "range_end": self.host.current_date.addDays(31).toString("yyyy-MM-dd"),
            "rows": schedules,
        }
        self.host._latest_directive_data = {
            "context_date": date,
            "routine_rows": routines,
            "directive_rows": directives,
        }

    def render(self, data, *, items=None, current_date=None, active_filter=None, clock_text=None):
        """Render examples, or a detached current snapshot (including []).

        Current snapshots can retain the source filter and clock label. Examples
        always show all sample items and the fixed example time, without writing
        source settings or retaining references to live item dictionaries.
        """
        if self._closed:
            raise RuntimeError("the preview renderer is closed")
        if isinstance(current_date, QDate) and current_date.isValid():
            self.host.current_date = QDate(current_date)
        examples = items is None
        items = self._example_items() if examples else deepcopy(list(items))
        self._set_item_cache(items)
        data = validate_free_layout(data)
        write_free_layout(self.settings, data)
        self.window.apply_selected_layout(force=True)
        self.window._style_signature = None
        self.window.apply_theme()
        self.window.update_header(self.host.current_date)
        target_filter = (
            "all"
            if examples
            else (
                active_filter
                if active_filter is not None
                else self.settings.source.value("widget_mode_filter", "all")
            )
        )
        # The native filter setter writes exclusively into this renderer's draft.
        self.window.set_filter(target_filter)
        self.window.clock_label.setText(
            "14:00" if examples or clock_text is None else str(clock_text)
        )
        self.window.set_data_state("ready")
        self.window.update_agenda(items)
        self.window.toolbar.hide()
        for index in range(self.window.footer_layout.count()):
            control = self.window.footer_layout.itemAt(index).widget()
            if control is not None:
                control.hide()
        self.window.feedback_label.hide()
        canvas = self.window._free_runtime
        canvas.setFixedSize(QSize(*data["canvas"]))
        self.window.resize(data["canvas"][0] + 28, data["canvas"][1] + 26)
        self.window.ensurePolished()
        # Resolve layouts locally; processing the application's event queue here
        # could dispatch unrelated real-window callbacks during an editor gesture.
        for _ in range(3):
            for layout in self.window.findChildren(QLayout):
                layout.activate()
            self.window.layout().activate()
            canvas.layout_blocks()
        # Native list refreshes preserve live scroll anchors, but this static
        # editor snapshot must show identical first rows after appearance undo.
        # Reset after sizing so every main/typed list has its final scroll range.
        for area in self.window.findChildren(QAbstractScrollArea):
            area.verticalScrollBar().setValue(0)
            area.horizontalScrollBar().setValue(0)
        crop = QRect(canvas.mapTo(self.window, QPoint()), canvas.size())
        image = self.window.grab(crop)
        image = image.scaled(
            QSize(*data["canvas"]),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        image.setDevicePixelRatio(1.0)
        self.window.timer.stop()
        self.controller.prepare_shutdown()
        return image

    def close(self):
        if self._closed:
            return
        self._closed = True
        if not sip.isdeleted(self.controller._load_timer):
            self.controller.prepare_shutdown()
        if not sip.isdeleted(self.window):
            self.window.timer.stop()
            self.window._feedback_timer.stop()
            self.window.hide()
            self.window.deleteLater()
        if not sip.isdeleted(self.host):
            self.host.deleteLater()
