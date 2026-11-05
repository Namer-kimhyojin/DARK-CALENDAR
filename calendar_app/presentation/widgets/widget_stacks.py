# -*- coding: utf-8 -*-
"""Stacks switch existing top-level overlays without reparenting or changing content."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QPushButton, QWidget

from calendar_app.domain.widget_workspace import validate_stacks, validate_state
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style


class StackBar(QWidget):
    def __init__(self, controller, group):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setProperty("dcWheelValueControl", True)
        self.controller, self.group = controller, group
        self.setWindowTitle(group["name"] or t("widget_studio.stack", "위젯 스택"))
        from calendar_app.presentation.widgets.overlay_manager_dialog import _load_tokens

        tokens = _load_tokens(controller.service.settings)
        self.setObjectName("studioStackBar")
        apply_common_dialog_style(
            self,
            minimum_width=360,
            size=(400, 44),
            extra_stylesheet=f"""
            QWidget#studioStackBar {{ background: {tokens["bg_main"]}; color: {tokens["text_primary"]}; }}
            QPushButton#studioStackArrow {{ min-width: 24px; max-width: 28px; padding: 0; }}
            QPushButton#studioStackAction {{ min-width: 36px; max-width: 48px; padding: 0 4px; }}
            QComboBox#studioStackCombo {{ min-width: 110px; padding: 0 6px; }}
        """,
        )
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)
        previous = QPushButton("‹")
        previous.setObjectName("studioStackArrow")
        previous.setAccessibleName(t("widget_studio.previous", "이전 위젯"))
        previous.setFixedWidth(28)
        previous.clicked.connect(lambda: controller.advance(group["id"], -1))
        self.combo = QComboBox()
        self.combo.setObjectName("studioStackCombo")
        self.combo.setAccessibleName(t("widget_studio.stack_page", "스택의 표시 위젯"))
        self.combo.activated.connect(lambda index: controller.select(group["id"], index))
        next_button = QPushButton("›")
        next_button.setObjectName("studioStackArrow")
        next_button.setAccessibleName(t("widget_studio.next", "다음 위젯"))
        next_button.setFixedWidth(28)
        next_button.clicked.connect(lambda: controller.advance(group["id"], 1))
        self.rotate_button = QPushButton(t("widget_studio.rotate", "자동"))
        self.rotate_button.setObjectName("studioStackAction")
        self.rotate_button.setCheckable(True)
        self.rotate_button.setChecked(group["rotate"])
        self.rotate_button.toggled.connect(
            lambda checked: controller.set_rotation(group["id"], checked)
        )
        self.rotate_button.setToolTip(
            t("widget_studio.rotate_help", "10초마다 전환 · 조작 중에는 대기")
        )
        dissolve = QPushButton(t("widget_studio.ungroup", "해제"))
        dissolve.setObjectName("studioStackAction")
        dissolve.clicked.connect(lambda: controller.remove(group["id"]))
        for button in (previous, self.combo, next_button, self.rotate_button, dissolve):
            layout.addWidget(button, 1 if button is self.combo else 0)

    def wheelEvent(self, event):
        self.controller.advance(self.group["id"], -1 if event.angleDelta().y() > 0 else 1)
        event.accept()


class WidgetStackController(QObject):
    def __init__(self, service):
        super().__init__(service)
        self.service, self.manager = service, service.manager
        self.groups = []
        self.bars = {}
        self._updating = False
        self._last_rotate = {}
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(150)
        self._save_timer.timeout.connect(self.service._write)

    def _save(self):
        self.service.state["stacks"] = deepcopy(self.groups)
        self._save_timer.start()

    def restore(self, groups):
        self._save_timer.stop()
        self.clear(restore=False)
        existing = {row[0] for row in self.manager.all_instances()}
        for raw in validate_stacks(groups):
            group = deepcopy(raw)
            group["members"] = [iid for iid in group["members"] if iid in existing]
            if len(group["members"]) >= 2:
                group["index"] %= len(group["members"])
                self.groups.append(group)
        self.refresh()

    def create(self, ids, name):
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2 or any(self.group_for(iid) for iid in ids):
            raise ValueError("select two ungrouped widgets")
        originals = {}
        for iid in ids:
            widget = self.manager.get_widget(iid)
            if widget is None or widget.placement_is_locked():
                raise ValueError("unlock widgets before grouping")
            r = widget.geometry()
            originals[iid] = {
                "rect": [r.x(), r.y(), r.width(), r.height()],
                "enabled": widget.is_enabled(),
            }
        group = {
            "id": uuid4().hex,
            "name": str(name).strip() or t("widget_studio.stack", "위젯 스택"),
            "members": ids,
            "index": 0,
            "rotate": False,
            "originals": originals,
        }
        draft = deepcopy(self.service.state)
        draft["stacks"] = self.groups + [group]
        validate_state(draft)
        self.service._undo = (self.service.capture(), self.service.state["active"])
        self.service._busy = True
        try:
            for iid in ids:
                self.manager.show_instance(iid)
            self.groups.append(group)
            self.refresh()
        finally:
            self.service._busy = False
        self._save()
        self.manager._notify_listeners()
        return group["id"]

    def group_for(self, iid):
        return next((g for g in self.groups if iid in g["members"]), None)

    def refresh(self):
        if self._updating:
            return
        self._updating = True
        try:
            for group in list(self.groups):
                group["members"] = [
                    iid for iid in group["members"] if self.manager.get_widget(iid) is not None
                ]
                if len(group["members"]) < 2:
                    self.remove(group["id"])
                    continue
                group["index"] %= len(group["members"])
                bar = self.bars.get(group["id"])
                if bar is None:
                    bar = self.bars[group["id"]] = StackBar(self, group)
                enabled = [
                    iid for iid in group["members"] if self.manager.get_widget(iid).is_enabled()
                ]
                active = group["members"][group["index"]]
                if enabled and active not in enabled:
                    active = enabled[0]
                    group["index"] = group["members"].index(active)
                names = {row[0]: row[1] for row in self.manager.all_instances()}
                bar.combo.blockSignals(True)
                bar.combo.clear()
                for index, iid in enumerate(group["members"]):
                    bar.combo.addItem(
                        f"{index + 1}/{len(group['members'])} · {names.get(iid, iid)}", iid
                    )
                bar.combo.setCurrentIndex(group["index"])
                bar.combo.blockSignals(False)
                for iid in group["members"]:
                    widget = self.manager.get_widget(iid)
                    widget.installEventFilter(self)
                    if iid == active and enabled:
                        if widget.isHidden():
                            widget._show_with_correct_size() if hasattr(
                                widget, "_show_with_correct_size"
                            ) else widget.show()
                    elif not widget.isHidden():
                        widget.hide()
                if enabled:
                    self._position_bar(group)
                    bar.show()
                else:
                    bar.hide()
        finally:
            self._updating = False

    def _position_bar(self, group):
        widget = self.manager.get_widget(group["members"][group["index"]])
        bar = self.bars.get(group["id"])
        if widget is None or bar is None:
            return
        screen = widget.screen()
        available = screen.availableGeometry() if screen else widget.geometry()
        x = max(available.left(), min(widget.x(), available.right() - bar.width() + 1))
        y = widget.y() - bar.height() - 4
        if y < available.top():
            y = min(available.bottom() - bar.height() + 1, widget.y() + widget.height() + 4)
        bar.move(x, y)

    def select(self, group_id, index):
        group = next(g for g in self.groups if g["id"] == group_id)
        index %= len(group["members"])
        target = self.manager.get_widget(group["members"][index])
        if target is None or not target.is_enabled():
            return
        old = self.manager.get_widget(group["members"][group["index"]])
        point = old.pos() if old is not None else target.pos()
        self._updating = True
        try:
            from calendar_app.presentation.widgets.widget_workspace_runtime import fit_rect

            target.move(fit_rect([point.x(), point.y(), target.width(), target.height()]).topLeft())
            target.save_position()
            group["index"] = index
        finally:
            self._updating = False
        self.refresh()
        self._last_rotate[group_id] = datetime.now()
        self._save()
        self.manager._notify_listeners()

    def advance(self, group_id, step):
        group = next(g for g in self.groups if g["id"] == group_id)
        for offset in range(1, len(group["members"]) + 1):
            index = (group["index"] + step * offset) % len(group["members"])
            widget = self.manager.get_widget(group["members"][index])
            if widget is not None and widget.is_enabled():
                self.select(group_id, index)
                break

    def set_rotation(self, group_id, enabled):
        next(g for g in self.groups if g["id"] == group_id)["rotate"] = bool(enabled)
        self._save()
        self.service._refresh_runtime()

    def rotate(self, now, *, paused=False):
        for group in self.groups:
            if paused or not group["rotate"] or QApplication.activeModalWidget() is not None:
                continue
            widget = self.manager.get_widget(group["members"][group["index"]])
            bar = self.bars.get(group["id"])
            if (
                widget is None
                or widget.isHidden()
                or widget.underMouse()
                or (bar and (bar.underMouse() or bar.isActiveWindow()))
                or QApplication.activePopupWidget() is not None
                or widget.isActiveWindow()
            ):
                self._last_rotate[group["id"]] = now
                continue
            last = self._last_rotate.setdefault(group["id"], now)
            if (now - last).total_seconds() >= 10:
                self.advance(group["id"], 1)
                self._last_rotate[group["id"]] = now

    def eventFilter(self, watched, event):
        if not self._updating and event.type() in {QEvent.Type.Move, QEvent.Type.Resize}:
            group = self.group_for(getattr(watched, "_overlay_inst_id", ""))
            if group and watched is self.manager.get_widget(group["members"][group["index"]]):
                self._position_bar(group)
        return False

    def remove(self, group_id, *, restore=True):
        group = next((g for g in self.groups if g["id"] == group_id), None)
        if group is None:
            return
        self.groups.remove(group)
        bar = self.bars.pop(group_id, None)
        if bar is not None:
            bar.hide()
            bar.deleteLater()
        from calendar_app.presentation.widgets.widget_workspace_runtime import (
            fit_rect,
            set_widget_rect,
        )

        for iid in group["members"]:
            widget = self.manager.get_widget(iid)
            if widget is None:
                continue
            widget.removeEventFilter(self)
            original = group["originals"].get(iid)
            if restore and original:
                set_widget_rect(widget, fit_rect(original["rect"]), resize=False)
                self.manager.show_instance(iid) if original[
                    "enabled"
                ] else self.manager.hide_instance(iid)
            elif restore and widget.is_enabled():
                widget.show()
        if restore:
            self._save()
            self.manager._notify_listeners()

    def clear(self, *, restore=True):
        for group in list(self.groups):
            self.remove(group["id"], restore=restore)

    def shutdown(self):
        if self._save_timer.isActive():
            self.service._write()
        self._save_timer.stop()
        self.clear(restore=False)
