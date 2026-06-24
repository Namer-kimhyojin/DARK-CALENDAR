"""OverlayWidgetManager — manages multiple instances of each overlay widget type.

Each widget type can have N simultaneous instances.  Instance metadata (id, name,
enabled state, position, settings-prefix) is persisted to QSettings as a JSON list
under the key  "overlay_instances".

Instance ID format:  "<type>_<n>"   e.g.  "clock_0", "clock_1", "text_2"
Settings prefix:     "oi_<id>"       e.g.  "oi_clock_0"

Public API (called from MainWindowUiActionsMixin / menus):
    manager.add_instance(widget_type)   → id str
    manager.remove_instance(inst_id)
    manager.rename_instance(inst_id, new_name)
    manager.show_instance(inst_id)
    manager.hide_instance(inst_id)
    manager.toggle_instance(inst_id)
    manager.instances_of(widget_type)  → list of (id, name, widget)
    manager.all_instances()            → list of (id, name, widget_type, widget)
    manager.build_widgets_menu(parent_menu, menu_style) — rebuilds the Widgets submenu
    manager.restore_all()              — called at startup
    manager.save_all()                 — called at shutdown (also auto-called on changes)
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
from typing import TYPE_CHECKING
import weakref

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QInputDialog, QMenu, QMessageBox

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_base import _overlay_menu_style
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget as _QWidget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Widget type registry
# ---------------------------------------------------------------------------

_WIDGET_TYPES: dict[str, dict] = {
    "clock": {
        "label_key": "menu.widget_clock",
        "label_default": "Digital Clock",
        "class": "OverlayClockWidget",
        "icon": ICON.WIDGET_CLOCK,
        "default_offset": QPoint(-230, 40),
        "init_method": "_init_clock_instance",
    },
    "weather": {
        "label_key": "menu.widget_weather",
        "label_default": "Weather Info",
        "class": "OverlayWeatherWidget",
        "icon": ICON.WIDGET_WEATHER,
        "default_offset": QPoint(-230, 160),
        "init_method": "_init_weather_instance",
    },
    "stopwatch": {
        "label_key": "menu.widget_stopwatch",
        "label_default": "Stopwatch",
        "class": "OverlayStopwatchWidget",
        "icon": ICON.WIDGET_STOPWATCH,
        "default_offset": QPoint(-230, 240),
        "init_method": "_init_stopwatch_instance",
    },
    "date_card": {
        "label_key": "menu.widget_date_card",
        "label_default": "Date Card",
        "class": "OverlayDateCardWidget",
        "icon": ICON.WIDGET_DATECARD,
        "default_offset": QPoint(-200, 320),
        "init_method": "_init_date_card_instance",
    },
    "countdown": {
        "label_key": "menu.widget_countdown",
        "label_default": "Countdown",
        "class": "OverlayCountdownWidget",
        "icon": ICON.WIDGET_COUNTDOWN,
        "default_offset": QPoint(-230, 400),
        "init_method": "_init_countdown_instance",
    },
    "dday": {
        "label_key": "menu.widget_dday",
        "label_default": "D-Day",
        "class": "OverlayDDayWidget",
        "icon": ICON.WIDGET_DDAY,
        "default_offset": QPoint(-230, 480),
        "init_method": "_init_dday_instance",
    },
    "text": {
        "label_key": "menu.widget_text",
        "label_default": "Text Label",
        "class": "OverlayTextWidget",
        "icon": ICON.WIDGET_TEXT,
        "default_offset": QPoint(-230, 560),
        "init_method": "_init_text_instance",
    },
}

_SETTINGS_KEY = "overlay_instances"


def widget_type_label(widget_type: str) -> str:
    info = _WIDGET_TYPES.get(widget_type, {})
    return t(info.get("label_key", ""), info.get("label_default", widget_type))


class OverlayWidgetManager:
    """Manages a collection of overlay widget instances across all types."""

    def __init__(self, owner):
        """
        owner: the main window (has .settings QSettings, .frameGeometry(), etc.)
        """
        self._owner = owner
        # id → widget instance
        self._widgets: dict[str, _QWidget] = {}
        # id → { "type": str, "name": str, "enabled": bool }
        self._meta: dict[str, dict] = {}
        # counters per type for id generation
        self._counters: dict[str, int] = {}
        self._id_lock = threading.Lock()
        self._listeners: list = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _settings(self):
        return self._owner.settings

    def _gen_id(self, widget_type: str) -> str:
        """Generate a unique id for a new instance of widget_type."""
        with self._id_lock:
            used = {m["_id"] for m in self._meta.values()} if self._meta else set()
            n = self._counters.get(widget_type, 0)
            while f"{widget_type}_{n}" in used:
                n += 1
            self._counters[widget_type] = n + 1
            return f"{widget_type}_{n}"

    def _settings_prefix(self, inst_id: str) -> str:
        return f"oi_{inst_id}"

    def _create_widget(self, widget_type: str, inst_id: str):
        """Instantiate and return the widget for the given type/id."""
        from calendar_app.presentation.widgets.overlay_widgets import (
            OverlayClockWidget,
            OverlayCountdownWidget,
            OverlayDateCardWidget,
            OverlayDDayWidget,
            OverlayStopwatchWidget,
            OverlayTextWidget,
            OverlayWeatherWidget,
        )

        cls_map = {
            "clock": OverlayClockWidget,
            "stopwatch": OverlayStopwatchWidget,
            "date_card": OverlayDateCardWidget,
            "countdown": OverlayCountdownWidget,
            "dday": OverlayDDayWidget,
            "text": OverlayTextWidget,
            "weather": OverlayWeatherWidget,
        }
        cls = cls_map.get(widget_type)
        if cls is None:
            raise ValueError(f"Unknown widget type: {widget_type!r}")

        # Create a lightweight settings proxy so each instance has its own prefix
        widget = cls(_SettingsProxy(self._owner, self._settings_prefix(inst_id)))
        return widget

    def _default_offset_for_type(self, widget_type: str, index: int) -> QPoint:
        base = _WIDGET_TYPES[widget_type]["default_offset"]
        # Stack instances 80px apart vertically
        return QPoint(base.x(), base.y() + index * 80)

    def _instance_count_of(self, widget_type: str) -> int:
        return sum(1 for m in self._meta.values() if m["type"] == widget_type)

    def _notify_listeners(self):
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.exception("Overlay manager listener failed")

    def _sync_widget_enabled(self, inst_id: str):
        widget = self._widgets.get(inst_id)
        if widget is None or inst_id not in self._meta:
            return
        self._meta[inst_id]["enabled"] = bool(widget.is_enabled())
        self._save()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_instance(self, widget_type: str, name: str | None = None) -> str:
        """Create a new instance. Returns the new instance id."""
        if widget_type not in _WIDGET_TYPES:
            raise ValueError(f"Unknown widget type: {widget_type!r}")

        inst_id = self._gen_id(widget_type)
        idx = self._instance_count_of(widget_type)
        if name is None:
            type_label = widget_type_label(widget_type)
            name = f"{type_label} {idx + 1}" if idx > 0 else type_label

        widget = self._create_widget(widget_type, inst_id)
        _mgr_ref = weakref.ref(self)
        widget._overlay_manager_sync = lambda iid=inst_id, _r=_mgr_ref: (
            m := _r()
        ) and m._sync_widget_enabled(iid)
        widget._overlay_manager_remove = lambda iid=inst_id, _r=_mgr_ref: (
            m := _r()
        ) and m._ui_remove_with_confirm(iid, parent_widget=None)
        widget._overlay_inst_id = inst_id
        widget.restore_position(self._default_offset_for_type(widget_type, idx))
        widget.apply_initial_settings()

        self._widgets[inst_id] = widget
        self._meta[inst_id] = {"_id": inst_id, "type": widget_type, "name": name, "enabled": False}
        self._save()
        self._notify_listeners()
        return inst_id

    def remove_instance(self, inst_id: str):
        """Hide and destroy the instance."""
        widget = self._widgets.pop(inst_id, None)
        if widget is not None:
            widget.hide()
            widget.deleteLater()
        self._meta.pop(inst_id, None)
        self._save()
        self._notify_listeners()

    def rename_instance(self, inst_id: str, new_name: str):
        if inst_id in self._meta:
            self._meta[inst_id]["name"] = new_name
            self._save()
            self._notify_listeners()

    def show_instance(self, inst_id: str):
        widget = self._widgets.get(inst_id)
        if widget:
            widget.set_enabled(True)
        if inst_id in self._meta:
            self._meta[inst_id]["enabled"] = True
        self._save()
        self._notify_listeners()

    def hide_instance(self, inst_id: str):
        widget = self._widgets.get(inst_id)
        if widget:
            widget.set_enabled(False)
        if inst_id in self._meta:
            self._meta[inst_id]["enabled"] = False
        self._save()
        self._notify_listeners()

    def show_all(self):
        """Show every registered instance."""
        for iid in list(self._meta):
            self.show_instance(iid)

    def hide_all(self):
        """Hide every registered instance."""
        for iid in list(self._meta):
            self.hide_instance(iid)

    def remove_all(self):
        """Permanently destroy every instance (no confirmation)."""
        for iid in list(self._meta):
            self.remove_instance(iid)

    @staticmethod
    def _make_topmost_msgbox(parent_widget=None) -> QMessageBox:
        """QMessageBox that always appears above overlay widgets."""
        from PyQt6.QtCore import Qt as _Qt

        box = QMessageBox(parent_widget)
        box.setWindowFlag(_Qt.WindowType.WindowStaysOnTopHint, True)
        return box

    def _ui_remove_with_confirm(self, inst_id: str, parent_widget=None):
        """Show confirmation dialog then remove. Safe to call from widget context menu."""
        meta = self._meta.get(inst_id)
        name = meta["name"] if meta else inst_id
        box = self._make_topmost_msgbox(parent_widget)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(t("widget_manager.confirm_delete_title", "위젯 삭제"))
        box.setText(
            t("widget_manager.confirm_delete_msg", "'{name}' 위젯을 삭제할까요?", name=name)
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.remove_instance(inst_id)
            self._rebuild_widgets_menu()

    def _ui_remove_all_with_confirm(self, parent_widget=None):
        """Show confirmation then destroy all instances."""
        count = len(self._meta)
        if count == 0:
            return
        box = self._make_topmost_msgbox(parent_widget)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(t("widget_manager.confirm_delete_all_title", "전체 위젯 삭제"))
        box.setText(
            t(
                "widget_manager.confirm_delete_all_msg",
                "위젯 {count}개를 모두 삭제할까요? 되돌릴 수 없습니다.",
                count=count,
            )
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.remove_all()
            self._rebuild_widgets_menu()

    def toggle_instance(self, inst_id: str):
        widget = self._widgets.get(inst_id)
        if widget is None:
            return
        enabled = not widget.is_enabled()
        widget.set_enabled(enabled)
        if inst_id in self._meta:
            self._meta[inst_id]["enabled"] = enabled
        self._save()
        self._notify_listeners()

    def instances_of(self, widget_type: str) -> list[tuple[str, str, object]]:
        """Return [(id, name, widget), ...] for the given type."""
        return [
            (iid, m["name"], self._widgets[iid])
            for iid, m in self._meta.items()
            if m["type"] == widget_type and iid in self._widgets
        ]

    def all_instances(self) -> list[tuple[str, str, str, object]]:
        """Return [(id, name, widget_type, widget), ...] in insertion order."""
        return [
            (iid, m["name"], m["type"], self._widgets[iid])
            for iid, m in self._meta.items()
            if iid in self._widgets
        ]

    def get_widget(self, inst_id: str):
        return self._widgets.get(inst_id)

    def get_widgets_of_type(self, widget_type: str) -> list:
        return [
            self._widgets[iid]
            for iid, m in self._meta.items()
            if m["type"] == widget_type and iid in self._widgets
        ]

    # ------------------------------------------------------------------
    # Widget registry — id → widget (for cross-widget template references)
    # ------------------------------------------------------------------

    def widget_registry(self) -> dict:
        """Return a snapshot dict of {inst_id: widget} for all live instances."""
        return dict(self._widgets)

    # ------------------------------------------------------------------
    # App data provider (optional callback for {task_count} etc.)
    # ------------------------------------------------------------------

    def set_app_data_provider(self, callback):
        """Register a zero-argument callable that returns a dict with app data.

        Expected keys (all optional):
            task_count       int   — number of today's tasks
            directive_count  int   — number of active directives
            next_event       str   — next scheduled event summary
            custom_var       str   — user-defined value
        """
        self._app_data_provider = callback

    def _get_app_data(self) -> dict:
        provider = getattr(self, "_app_data_provider", None)
        if callable(provider):
            try:
                return provider() or {}
            except Exception:
                pass
        return {}

    # ------------------------------------------------------------------
    # Tiered text refresh
    # ------------------------------------------------------------------

    def refresh_all_texts(
        self,
        countdown_remaining: str = "",
        stopwatch_text: str = "",
        tier: str = "fast",
        app_data: dict | None = None,
    ):
        """Push live data into text widgets that need a refresh at the given tier.

        tier values (from fastest to slowest):
            'fast'  — refresh widgets that use {stopwatch} or {time} (100 ms)
            'med'   — refresh widgets that use {countdown} or faster  (1 s)
            'slow'  — refresh all widgets that have any template var  (60 s)
        """
        _tier_rank = {"fast": 3, "med": 2, "slow": 1}
        caller_rank = _tier_rank.get(tier, 1)

        _ad = app_data if app_data is not None else (self._get_app_data() if tier == "slow" else {})
        # Build registry once per refresh call — all live instances by id
        registry = self.widget_registry()

        for w in self.get_widgets_of_type("text"):
            if not (hasattr(w, "refresh_template") and w.is_enabled()):
                continue
            if not hasattr(w, "refresh_tier"):
                # Fallback: always refresh
                w.refresh_template(countdown_remaining, stopwatch_text, _ad, registry)
                continue
            widget_tier = w.refresh_tier()
            widget_rank = _tier_rank.get(widget_tier, 0)
            # Refresh widget if caller tier is at least as frequent as widget's needs
            # e.g. caller=fast(3) refreshes fast(3), med(2), slow(1) widgets
            # e.g. caller=med(2) refreshes med(2) and slow(1) but NOT fast(3)
            if widget_rank > 0 and caller_rank >= widget_rank:
                w.refresh_template(countdown_remaining, stopwatch_text, _ad, registry)

    # ------------------------------------------------------------------
    # Dynamic menu builder
    # ------------------------------------------------------------------

    def build_widgets_menu(self, parent_menu: QMenu, menu_style: str = ""):
        """Rebuild the Widgets submenu in-place."""
        if menu_style:
            parent_menu.setStyleSheet(menu_style)
        parent_menu.clear()
        locked = bool(getattr(self._owner, "is_locked", False))

        # ── 위젯 관리자 (고정) ────────────────────────────────────────
        act_mgr = parent_menu.addAction(
            _se(t("widget_manager.open_manager", "위젯 관리자...")),
            lambda: self._open_manager_dialog(),
        )
        act_mgr.setIcon(_ic(ICON.WIDGET_MGR))
        act_mgr.setEnabled(not locked)

        # ── 기존 인스턴스 목록 ────────────────────────────────────────
        instances = self.all_instances()
        if instances:
            parent_menu.addSeparator()
            for iid, name, wtype, widget in instances:
                info = _WIDGET_TYPES.get(wtype, {})
                display = name or _se(widget_type_label(wtype))
                act_inst = parent_menu.addAction(display)
                if "icon" in info:
                    act_inst.setIcon(_ic(info["icon"]))
                act_inst.setCheckable(True)
                act_inst.setChecked(widget.is_enabled())
                act_inst.setEnabled(not locked)
                act_inst.triggered.connect(lambda checked, iid=iid: self.toggle_instance(iid))

        # ── 전체 제어 ─────────────────────────────────────────────────
        any_instances = bool(instances)
        parent_menu.addSeparator()
        act_show_all = parent_menu.addAction(
            _se(t("widget_manager.menu_show_all", "모두 표시")),
            self.show_all,
        )
        act_show_all.setIcon(_ic(ICON.SHOW))
        act_show_all.setEnabled(not locked and any_instances)

        act_hide_all = parent_menu.addAction(
            _se(t("widget_manager.menu_hide_all", "모두 숨김")),
            self.hide_all,
        )
        act_hide_all.setIcon(_ic(ICON.HIDE))
        act_hide_all.setEnabled(not locked and any_instances)

        act_del_all = parent_menu.addAction(
            _se(t("widget_manager.menu_delete_all", "모두 삭제...")),
            lambda: self._ui_remove_all_with_confirm(),
        )
        act_del_all.setIcon(_ic(ICON.DELETE))
        act_del_all.setEnabled(not locked and any_instances)

        # ── 위젯 추가 ─────────────────────────────────────────────────
        parent_menu.addSeparator()
        for wtype, info in _WIDGET_TYPES.items():
            type_label = _se(widget_type_label(wtype))
            act = parent_menu.addAction(
                t("widget_manager.add_widget_menu", "{label} 추가", label=type_label),
                lambda *_, wt=wtype: self._ui_add_instance(wt),
            )
            if "icon" in info:
                act.setIcon(_ic(info["icon"]))
            act.setEnabled(not locked)

    def _ui_add_instance(self, widget_type: str):
        """Ask for a name and create a new instance."""
        type_label = widget_type_label(widget_type)
        idx = self._instance_count_of(widget_type)
        default_name = f"{type_label} {idx + 1}" if idx > 0 else type_label
        name, ok = QInputDialog.getText(
            None,
            t("widget_manager.add_widget_title", "Add {label}", label=type_label),
            t("widget_manager.widget_name", "Widget name:"),
            text=default_name,
        )
        if not ok:
            return
        inst_id = self.add_instance(widget_type, name.strip() or default_name)
        # Show immediately after adding
        self.show_instance(inst_id)
        self._rebuild_widgets_menu()

    def _ui_rename(self, inst_id: str):
        meta = self._meta.get(inst_id)
        if meta is None:
            return
        name, ok = QInputDialog.getText(
            None,
            t("widget_manager.rename_title", "Rename"),
            t("widget_manager.new_name", "New name:"),
            text=meta["name"],
        )
        if ok and name.strip():
            self.rename_instance(inst_id, name.strip())
            self._rebuild_widgets_menu()

    def _ui_remove(self, inst_id: str):
        self.remove_instance(inst_id)
        self._rebuild_widgets_menu()

    def _open_manager_dialog(self):
        """위젯 관리자 다이얼로그 열기 — owner의 open_widget_manager() 위임."""
        if hasattr(self._owner, "open_widget_manager"):
            self._owner.open_widget_manager()

    def _rebuild_widgets_menu(self):
        """Re-populate the widgets submenu if accessible from owner."""
        widgets_menu = getattr(self._owner, "widgets_menu", None)
        if widgets_menu is not None:
            style = (
                getattr(self._owner, "_last_menu_style", "")
                or widgets_menu.styleSheet()
                or _default_menu_style()
            )
            self.build_widgets_menu(widgets_menu, style)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        """Persist instance list to QSettings."""
        data = []
        for iid, m in self._meta.items():
            widget = self._widgets.get(iid)
            data.append(
                {
                    "id": iid,
                    "type": m["type"],
                    "name": m["name"],
                    "enabled": widget.is_enabled() if widget else m.get("enabled", False),
                }
            )
        self._settings().setValue(_SETTINGS_KEY, json.dumps(data))

    def restore_all(self):
        """Restore all instances from QSettings at startup."""
        raw = self._settings().value(_SETTINGS_KEY, None)
        # _had_saved_instances=True 이면 key가 존재 → 사용자가 의도적으로 비운 것
        self._had_saved_instances = raw is not None
        if raw is None:
            return  # 진짜 첫 실행 — 키가 없음
        try:
            items: list[dict] = json.loads(str(raw))
        except Exception:
            items = []

        # Determine highest counter per type from saved ids
        for item in items:
            iid = item.get("id", "")
            parts = iid.rsplit("_", 1)
            if len(parts) == 2:
                wtype, num_str = parts
                with contextlib.suppress(ValueError):
                    self._counters[wtype] = max(self._counters.get(wtype, 0), int(num_str) + 1)

        for item in items:
            iid = item.get("id", "")
            wtype = item.get("type", "")
            name = item.get("name", iid)
            enabled = item.get("enabled", False)

            if wtype not in _WIDGET_TYPES:
                logger.warning("Unknown overlay widget type %r in saved data, skipping", wtype)
                continue

            try:
                widget = self._create_widget(wtype, iid)
                _mgr_ref = weakref.ref(self)
                widget._overlay_manager_sync = lambda iid=iid, _r=_mgr_ref: (
                    m := _r()
                ) and m._sync_widget_enabled(iid)
                idx = self._instance_count_of(wtype)
                widget.restore_position(self._default_offset_for_type(wtype, idx))
                widget.apply_initial_settings()
                if enabled:
                    widget.set_enabled(True)

                self._widgets[iid] = widget
                self._meta[iid] = {"_id": iid, "type": wtype, "name": name, "enabled": enabled}
            except Exception:
                logger.exception("Failed to restore overlay instance %r", iid)
        self._notify_listeners()

    def save_all(self):
        """Explicit save (call at shutdown)."""
        self._save()

    def set_all_interaction_locked(self, locked: bool):
        """고정 모드 시 모든 위젯의 드래그/리사이즈를 잠금/해제."""
        for widget in self._widgets.values():
            if hasattr(widget, "set_interaction_locked"):
                widget.set_interaction_locked(locked)

    def add_listener(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        with contextlib.suppress(ValueError):
            self._listeners.remove(callback)


# ---------------------------------------------------------------------------
# _SettingsProxy — gives each widget instance its own prefix namespace
# ---------------------------------------------------------------------------


class _SettingsProxy:
    """Wraps the real QSettings but prepends `prefix_` to all keys.

    This makes each widget instance store its data under e.g. "oi_clock_1_font_size"
    while the widget only sees "font_size".

    The proxy also exposes `.settings` so that owner.settings still works when
    accessed from within widget code that does `self.owner.settings`.
    """

    def __init__(self, real_owner, prefix: str):
        self._real = real_owner
        self._prefix = prefix

    # --- QSettings forwarding ---

    @property
    def settings(self):
        return self  # widgets do owner.settings.value(…) — return self

    def value(self, key, default=None, type=None):  # noqa: A002
        full = f"{self._prefix}_{key}"
        if type is not None:
            return self._real.settings.value(full, default, type=type)
        return self._real.settings.value(full, default)

    def setValue(self, key, value):
        self._real.settings.setValue(f"{self._prefix}_{key}", value)

    def remove(self, key):
        self._real.settings.remove(f"{self._prefix}_{key}")

    # --- Proxy all other owner attributes transparently ---

    def __getattr__(self, name):
        return getattr(self._real, name)

    def frameGeometry(self):
        return self._real.frameGeometry()


def _default_menu_style() -> str:
    return _overlay_menu_style()
