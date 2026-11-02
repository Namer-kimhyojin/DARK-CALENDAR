# -*- coding: utf-8 -*-
"""Local workspaces: scoped snapshots, reversible apply and opt-in runtime policies."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
import logging
import os
import sys
from uuid import uuid4

from PyQt6.QtCore import QObject, QPoint, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from calendar_app.domain.widget_workspace import (
    STATE_KEY,
    STYLE_KEYS,
    default_state,
    load_state,
    matching_rule,
    mode_setting_allowed,
    validate_snapshot,
    validate_state,
)

logger = logging.getLogger(__name__)
_KEEP_SCOPE = object()


def encode_setting(value):
    if isinstance(value, QSize):
        return {"qt_size": [value.width(), value.height()]}
    if isinstance(value, QPoint):
        return {"qt_point": [value.x(), value.y()]}
    if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
        return deepcopy(value)
    raise ValueError("setting cannot be saved in a workspace")


def decode_setting(value):
    if isinstance(value, dict) and set(value) == {"qt_size"}:
        return QSize(*[int(v) for v in value["qt_size"]])
    if isinstance(value, dict) and set(value) == {"qt_point"}:
        return QPoint(*[int(v) for v in value["qt_point"]])
    return value


def other_app_is_fullscreen():
    """Read foreground geometry on Windows; no hooks, input or window changes."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        hwnd = user32.GetForegroundWindow()
        if not hwnd or user32.IsIconic(hwnd):
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        # Qt screens use logical coordinates; Win32 foreground rectangles are physical.
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        monitor = user32.MonitorFromWindow(hwnd, 2)

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("monitor", wintypes.RECT),
                ("work", wintypes.RECT),
                ("flags", wintypes.DWORD),
            ]

        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        m = info.monitor
        return (
            rect.left <= m.left + 2
            and rect.top <= m.top + 2
            and rect.right >= m.right - 2
            and rect.bottom >= m.bottom - 2
        )
    except (AttributeError, OSError, ValueError):
        return False


def fit_rect(raw, screen_name="", old_available=None):
    rect = QRect(*raw)
    screens = QApplication.screens()
    screen = next((screen for screen in screens if screen.name() == screen_name), None)
    screen = screen or QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
    if screen is None:
        return rect
    available = screen.availableGeometry()
    if old_available and list(old_available) != [
        available.x(),
        available.y(),
        available.width(),
        available.height(),
    ]:
        old = QRect(*old_available)
        x = (rect.x() - old.x()) / max(1, old.width() - rect.width())
        y = (rect.y() - old.y()) / max(1, old.height() - rect.height())
        rect.moveTopLeft(
            QPoint(
                available.x() + round(x * max(0, available.width() - rect.width())),
                available.y() + round(y * max(0, available.height() - rect.height())),
            )
        )
    rect.setSize(
        QSize(min(rect.width(), available.width()), min(rect.height(), available.height()))
    )
    rect.moveLeft(max(available.left(), min(rect.left(), available.right() - rect.width() + 1)))
    rect.moveTop(max(available.top(), min(rect.top(), available.bottom() - rect.height() + 1)))
    return rect


def set_widget_rect(widget, rect, *, resize=True):
    deck = getattr(widget, "_deck_data", None)
    if resize and isinstance(deck, dict) and hasattr(widget, "_set_scale"):
        factor = min(rect.width() / max(1, widget.width()), rect.height() / max(1, widget.height()))
        widget._set_scale(round(deck["scale"] * factor))
        widget._apply_appearance()
    elif resize and hasattr(widget, "_set"):
        width, height = widget._constrain_shape_size(rect.width(), rect.height())
        widget._set("fixed_w", width)
        widget._set("fixed_h", height)
        widget._apply_and_resize()
    elif resize:
        widget.resize(rect.size())
    widget.move(rect.topLeft())
    widget.save_position()


class WidgetWorkspaceService(QObject):
    changed = pyqtSignal()

    def __init__(self, manager):
        owner = manager._owner
        super().__init__(owner if isinstance(owner, QObject) else None)
        self.manager, self.owner, self.settings = manager, owner, manager._settings()
        self.load_error = False
        try:
            self.state = load_state(self.settings.value(STATE_KEY, ""))
        except (ValueError, TypeError, AttributeError, OverflowError):
            logger.exception(
                "Invalid widget workspace settings; keeping original settings for recovery"
            )
            self.state, self.load_error = default_state(), True
        self._busy = False
        self._started = False
        self._undo = None
        self._manual_until = None
        self._last_rule = None
        self._paused = False
        self.last_error = ""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self._refresh = QTimer(self)
        self._refresh.setSingleShot(True)
        self._refresh.timeout.connect(self._refresh_runtime)
        from calendar_app.presentation.widgets.widget_stacks import WidgetStackController

        self.stacks = WidgetStackController(self)

    def start(self):
        if self._started:
            return
        self._started = True
        self.manager.add_listener(self._manager_changed)
        self.stacks.restore(self.state["stacks"])
        self._refresh_runtime()
        if self.state["options"]["automatic"] and self.state["rules"]:
            self.timer.start(0)

    def _manager_changed(self):
        if not self._busy and not self._refresh.isActive():
            self._refresh.start(0)

    def _write(self):
        self.state = validate_state(self.state)
        self.settings.setValue(STATE_KEY, json.dumps(self.state, ensure_ascii=False))
        self.load_error = False
        self.changed.emit()

    def capture(self):
        widgets = []
        for iid, name, kind, widget in self.manager.all_instances():
            style = {
                key: encode_setting(widget._get(key))
                for key in STYLE_KEYS
                if widget._setting_exists(key)
            }
            screen = widget.screen()
            rect = widget.geometry()
            item = {
                "id": iid,
                "name": name,
                "type": kind,
                "enabled": widget.is_enabled(),
                "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
                "style": style,
                "screen": screen.name() if screen else "",
            }
            if screen:
                a = screen.availableGeometry()
                item["available"] = [a.x(), a.y(), a.width(), a.height()]
            if kind == "launcher_deck" and isinstance(getattr(widget, "_deck_data", None), dict):
                from calendar_app.presentation.widgets.widget_graphics import keydeck_visual_values

                item["deck_visual"] = keydeck_visual_values(widget._deck_data)
                item["deck_visual"]["scale"] = widget._deck_data["scale"]
            widgets.append(item)
        mode = {}
        for key in self.settings.allKeys():
            if mode_setting_allowed(str(key)):
                try:
                    mode[str(key)] = encode_setting(self.settings.value(key))
                except ValueError:
                    continue
        coordinator = getattr(self.owner, "_widget_mode_coordinator", None)
        from calendar_app.presentation.widgets.widget_mode_coordinator import _resume_requested

        mode_active = bool(
            coordinator
            and (
                coordinator.is_widget_mode_active()
                or (_resume_requested(self.settings) and not self.owner.isVisible())
            )
        )
        if coordinator is not None and coordinator.controller.widget is not None:
            from calendar_app.presentation.widgets.widget_mode_geometry import (
                geometry_key,
                serialize_geometry,
            )

            controller, window = coordinator.controller, coordinator.controller.widget
            screen = window.screen()
            if screen:
                layout = window.active_layout_id()
                key = geometry_key(
                    controller._geometry_layout_id(
                        layout, controller._calendar_visible_for_layout(layout)
                    )
                )
                mode[key] = serialize_geometry(
                    window.geometry(), screen.availableGeometry(), screen.name()
                )
        return validate_snapshot(
            {
                "widgets": widgets,
                "mode": mode,
                "mode_active": mode_active,
                "stacks": deepcopy(self.stacks.groups),
            }
        )

    def save_profile(self, name, *, profile_id=None, calendar_ids=_KEEP_SCOPE, thumbnail=""):
        name = str(name).strip()
        if not name or len(name) > 80:
            raise ValueError("invalid workspace name")
        if any(
            p["name"].casefold() == name.casefold() and p["id"] != profile_id
            for p in self.state["profiles"]
        ):
            raise ValueError("workspace name already exists")
        profile = {
            "id": profile_id or uuid4().hex,
            "name": name,
            "snapshot": self.capture(),
            "thumbnail": thumbnail,
        }
        if calendar_ids is not _KEEP_SCOPE:
            from calendar_app.domain.widget_workspace import CALENDAR_SCOPE_KEY

            profile["snapshot"]["mode"][CALENDAR_SCOPE_KEY] = json.dumps(calendar_ids)
        index = next(
            (i for i, p in enumerate(self.state["profiles"]) if p["id"] == profile_id), None
        )
        draft = deepcopy(self.state)
        if index is None:
            draft["profiles"].append(profile)
        else:
            draft["profiles"][index] = profile
        self.state = validate_state(draft)
        self._write()
        return profile["id"]

    def remove_profile(self, profile_id):
        self.state["profiles"] = [p for p in self.state["profiles"] if p["id"] != profile_id]
        self.state["rules"] = [r for r in self.state["rules"] if r["profile"] != profile_id]
        self._write()
        self._refresh_runtime()

    def _restore_mode(self, mode):
        for key in list(self.settings.allKeys()):
            if mode_setting_allowed(str(key)) and key not in mode:
                self.settings.remove(key)
        for key, value in mode.items():
            self.settings.setValue(key, decode_setting(value))
        coordinator = getattr(self.owner, "_widget_mode_coordinator", None)
        controller = coordinator.controller if coordinator is not None else None
        if controller is not None and controller.widget is not None:
            window = controller.widget
            controller._restoring_geometry = True
            try:
                window.apply_selected_layout(force=True)
                window._style_signature = None
                window.apply_theme()
                window.set_filter(str(self.settings.value("widget_mode_filter", "all")))
            finally:
                controller._restoring_geometry = False
            controller._restore_geometry()
            controller.set_always_top(
                self.settings.value("widget_mode_always_top", True, type=bool), persist=False
            )
            controller.force_refresh()

    def restore_snapshot(self, snapshot):
        snapshot = validate_snapshot(snapshot)
        self._busy = True
        missing = []
        try:
            self.stacks.clear(restore=False)
            entries = {entry["id"]: entry for entry in snapshot["widgets"]}
            for iid, _, _, widget in self.manager.all_instances():
                item = entries.get(iid)
                if item is None:
                    self.manager.hide_instance(iid)
                    continue
                for key in STYLE_KEYS:
                    if key in item["style"]:
                        widget._set(key, decode_setting(item["style"][key]))
                    else:
                        widget._s().remove(f"{widget._pref()}_{key}")
                if "deck_visual" in item:
                    self._restore_deck_visual(widget, item["deck_visual"])
                widget._apply_and_resize()
                self.manager.show_instance(iid) if item["enabled"] else self.manager.hide_instance(
                    iid
                )
                rect = fit_rect(item["rect"], item["screen"], item.get("available"))
                set_widget_rect(
                    widget, rect, resize="fixed_w" in item["style"] and "fixed_h" in item["style"]
                )
            missing = [iid for iid in entries if self.manager.get_widget(iid) is None]
            self._restore_mode(snapshot["mode"])
            self.stacks.restore(snapshot["stacks"])
            self.state["stacks"] = deepcopy(self.stacks.groups)
        finally:
            self._busy = False
            self._refresh_runtime()
            self.manager._notify_listeners()
        return missing

    @staticmethod
    def _restore_deck_visual(widget, visual):
        if not isinstance(getattr(widget, "_deck_data", None), dict):
            return
        from calendar_app.presentation.widgets.keydeck.model import beatmaker_state

        deck = widget._deck_data
        deck["case"].update(visual["case"])
        deck["scale"] = visual["scale"]
        for page in deck["pages"]:
            performance = beatmaker_state(page) is not None
            for key in page["keys"]:
                if performance and key.get("action", {}).get("type") == "sound":
                    continue
                for group, values in visual["keys"].get(key["id"], {}).items():
                    if group != "insert" or key["insert"]["kind"] not in {"image", "panorama"}:
                        key[group].update(values)
        widget._canvas.refresh()
        widget._apply_appearance()
        widget._fit_window()
        widget._schedule_save()

    def apply_profile(self, profile_id, *, open_mode=False, automatic=False):
        profile = next(p for p in self.state["profiles"] if p["id"] == profile_id)
        before = self.capture()
        old_active = self.state["active"]
        try:
            missing = self.restore_snapshot(profile["snapshot"])
        except Exception:
            logger.exception("Workspace apply failed; restoring previous workspace")
            self.restore_snapshot(before)
            raise
        self._undo = (before, old_active)
        self.state["active"] = profile_id
        if not automatic:
            self._manual_until = datetime.now() + timedelta(hours=1)
            self._last_rule = None
        self._write()
        if open_mode:
            ensure = getattr(self.owner, "_ensure_widget_mode_coordinator", None)
            coordinator = (
                ensure()
                if callable(ensure)
                else getattr(self.owner, "_widget_mode_coordinator", None)
            )
            if coordinator is not None:
                coordinator.enter() if profile["snapshot"][
                    "mode_active"
                ] else coordinator.return_to_main()
        return missing

    def apply_geometry(self, rectangles, *, opacity=None):
        from calendar_app.domain.widget_workspace import valid_rect

        targets = {iid: fit_rect(valid_rect(raw)) for iid, raw in rectangles.items()}
        before = self.capture()
        try:
            for iid, rect in targets.items():
                widget = self.manager.get_widget(iid)
                if widget is None or widget.placement_is_locked():
                    continue
                if opacity is not None:
                    widget._set("widget_opacity", max(10, min(100, int(opacity))))
                set_widget_rect(widget, rect)
        except Exception:
            self.restore_snapshot(before)
            raise
        self._undo = (before, self.state["active"])
        self.manager._notify_listeners()
        self.changed.emit()

    def undo(self):
        if self._undo is None:
            return
        snapshot, active = self._undo
        self.restore_snapshot(snapshot)
        self._undo = None
        self.state["active"] = active
        self._manual_until = datetime.now() + timedelta(hours=1)
        self._last_rule = None
        self._write()

    def configure(self, options, rules):
        draft = deepcopy(self.state)
        draft.update(options=options, rules=rules)
        self.state = validate_state(draft)
        self._manual_until, self._last_rule = None, None
        self._write()
        self._refresh_runtime()
        self.tick()

    def _refresh_runtime(self):
        self.stacks.refresh()
        options = self.state["options"]
        previously_paused = self._paused
        self._paused = options["pause_fullscreen"] and other_app_is_fullscreen()
        from calendar_app.presentation.widgets.weather_scene import system_allows_weather_motion

        motion = options["motion"] if system_allows_weather_motion() else "static"
        for _, _, _, widget in self.manager.all_instances():
            for surface in widget.findChildren(QObject):
                setter = getattr(surface, "set_motion_policy", None)
                if callable(setter):
                    setter(motion, self._paused)
        interval = (
            1000
            if options["pause_fullscreen"]
            else 10_000
            if any(g["rotate"] for g in self.stacks.groups)
            else 30_000
            if options["automatic"] and self.state["rules"]
            else 60_000
            if any(
                kind == "launcher_deck" and widget.isVisible()
                for _, _, kind, widget in self.manager.all_instances()
            )
            else 0
        )
        if interval:
            self.timer.start(
                interval
            ) if self.timer.interval() != interval or not self.timer.isActive() else None
        else:
            self.timer.stop()
        if self._paused != previously_paused:
            self.changed.emit()

    def tick(self, now=None):
        now = now or datetime.now()
        self._refresh_runtime()
        self.stacks.rotate(now, paused=self._paused)
        if not self.state["options"]["automatic"] or (
            self._manual_until and now < self._manual_until
        ):
            return
        if QApplication.activeModalWidget() is not None:
            return
        match = matching_rule(self.state["rules"], now)
        key = (now.date(), match)
        if match and key != self._last_rule:
            previous_error = self.last_error
            try:
                self.apply_profile(match[1], automatic=True)
                self.last_error = ""
            except Exception:
                self.last_error = "automation_failed"
                logger.exception("Automatic workspace switch failed")
            if previous_error != self.last_error:
                self.changed.emit()
        self._last_rule = key

    def shutdown(self):
        self.timer.stop()
        self._refresh.stop()
        self.stacks.shutdown()
        if self._started:
            self.manager.remove_listener(self._manager_changed)
        self._started = False
