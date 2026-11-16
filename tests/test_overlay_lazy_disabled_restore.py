# -*- coding: utf-8 -*-
"""A saved disabled overlay instance is built when it is first needed, not at start.

A hidden loop mixer alone cost 0.15-0.22 s of every start. Start-up and background
paths (menu, stacks, workspace runtime, Text template refresh, first-run check,
away-lock unlock, shutdown) must not build hidden widgets; anything that needs the
widget gets it from get_widget() or all_instances(), which build it on first use.
"""

import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QSettings
from PyQt6.QtWidgets import QApplication, QMenu, QWidget
import pytest

from calendar_app.presentation.widgets.overlay_manager import _WIDGET_TYPES, OverlayWidgetManager

SHIM_NAME = "calendar_app.presentation.widgets.overlay_widgets"


class _Widget(QWidget):
    built: list = []
    fail_types: set = set()

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.locked = False
        self.registry_seen = None

    def _get(self, key, default=None, type_=None):
        name = f"x_{key}"
        if type_ is not None:
            return self.owner.settings.value(name, default, type=type_)
        return self.owner.settings.value(name, default)

    def _set(self, key, value):
        self.owner.settings.setValue(f"x_{key}", value)

    def apply_initial_settings(self):
        kind = self.owner._prefix.removeprefix("oi_").rsplit("_", 1)[0]
        if kind in self.fail_types:
            raise RuntimeError("synthetic build failure")
        self.built.append(self.owner._prefix.removeprefix("oi_"))

    def restore_position(self, offset):
        self.move(offset)

    def save_position(self):
        pass

    def is_enabled(self):
        return self._get("enabled", False, type_=bool)

    def set_enabled(self, value):
        self._set("enabled", bool(value))
        self.setVisible(bool(value))
        sync = getattr(self, "_overlay_manager_sync", None)
        if callable(sync):
            sync()

    def _set_runtime_active(self, _active):
        pass

    def set_interaction_locked(self, locked):
        self.locked = locked

    def placement_is_locked(self):
        return False

    # Text / template-source surface used by refresh_all_texts().
    def refresh_tier(self):
        return "med"

    def refresh_template(self, _countdown, _stopwatch, _app_data, registry):
        self.registry_seen = list(registry)

    def get_elapsed_text(self):
        return "00:01.0"

    def get_dday_text(self):
        return "D-3"


@pytest.fixture
def make(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])  # held: an unreferenced app is destroyed
    stub = ModuleType(SHIM_NAME)
    for record in _WIDGET_TYPES.values():
        setattr(stub, record["class"], _Widget)
    monkeypatch.setitem(sys.modules, SHIM_NAME, stub)
    _Widget.built = []
    _Widget.fail_types = set()
    hosts = []

    def factory(records, *, with_manager=True, **settings):
        host = QWidget()
        host.settings = QSettings(str(tmp_path / "lazy.ini"), QSettings.Format.IniFormat)
        host.settings.setValue("overlay_instances", json.dumps(records))
        for key, value in settings.items():
            host.settings.setValue(key, value)
        # init_overlay_manager() creates the manager itself when with_manager is False.
        host.overlay_manager = OverlayWidgetManager(host) if with_manager else None
        hosts.append(host)
        return host, host.overlay_manager

    yield factory
    for host in hosts:
        manager = host.overlay_manager
        if manager is not None:
            manager._closed = True
            for _, _, _, widget in manager.live_instances():
                widget.deleteLater()
        host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del app


def _record(iid, enabled):
    return {"id": iid, "type": iid.rsplit("_", 1)[0], "name": iid.upper(), "enabled": enabled}


def test_disabled_instances_are_listed_saved_and_built_only_when_needed(make):
    records = [_record("clock_0", True), _record("loop_deck_0", False), _record("clock_1", False)]
    host, manager = make(records)
    manager.restore_all()
    assert _Widget.built == ["clock_0"]
    assert manager.instance_records() == [
        ("clock_0", "CLOCK_0", "clock", True),
        ("loop_deck_0", "LOOP_DECK_0", "loop_deck", False),
        ("clock_1", "CLOCK_1", "clock", False),
    ]
    assert [row[0] for row in manager.live_instances()] == ["clock_0"]

    menu = QMenu()
    manager.build_widgets_menu(menu, "")
    checks = {a.text(): a.isChecked() for a in menu.actions() if a.isCheckable()}
    assert checks == {"CLOCK_0": True, "LOOP_DECK_0": False, "CLOCK_1": False}
    manager.save_all()
    assert json.loads(host.settings.value("overlay_instances")) == records
    assert _Widget.built == ["clock_0"]

    second = manager.get_widget("clock_1")
    assert _Widget.built == ["clock_0", "clock_1"]
    assert not second.is_enabled() and not second.isVisible()
    # The default offset keeps the saved order: the second clock is one step (80 px) lower.
    assert second.pos() == QPoint(-230, 40 + 80)
    manager.toggle_instance("loop_deck_0")
    assert manager.get_widget("loop_deck_0").is_enabled()
    assert json.loads(host.settings.value("overlay_instances"))[1]["enabled"] is True


def test_show_remove_duplicate_and_type_lookup_build_only_what_they_need(make):
    records = [
        _record("clock_0", False),
        _record("text_0", False),
        _record("dday_0", False),
        _record("weather_0", False),
        _record("weather_1", False),
    ]
    host, manager = make(records)
    manager.restore_all()
    assert _Widget.built == []

    manager.remove_instance("text_0")
    assert _Widget.built == []
    assert "text_0" not in manager._pending
    assert [r["id"] for r in json.loads(host.settings.value("overlay_instances"))] == [
        "clock_0",
        "dday_0",
        "weather_0",
        "weather_1",
    ]

    manager.show_instance("clock_0")
    assert _Widget.built == ["clock_0"]
    assert manager.get_widget("clock_0").is_enabled()
    assert json.loads(host.settings.value("overlay_instances"))[0]["enabled"] is True

    assert [row[0] for row in manager.instances_of("weather")] == ["weather_0", "weather_1"]
    assert _Widget.built == ["clock_0", "weather_0", "weather_1"]

    copy_id = manager.duplicate_instance("dday_0")
    assert copy_id is not None
    assert _Widget.built[3] == "dday_0"  # the source is built before it is copied
    assert not manager.get_widget(copy_id).is_enabled()


def test_text_refresh_builds_only_hidden_template_sources_in_instance_order(make):
    records = [
        _record("stopwatch_0", False),
        _record("text_0", True),
        _record("loop_deck_0", False),
        _record("dday_0", False),
    ]
    _, manager = make(records)
    manager.restore_all()
    manager.refresh_all_texts(tier="fast")  # the Text widget is med tier: no registry
    assert _Widget.built == ["text_0"]
    manager.refresh_all_texts(tier="med")
    assert sorted(_Widget.built) == ["dday_0", "stopwatch_0", "text_0"]
    assert manager.get_widget("text_0").registry_seen == ["stopwatch_0", "text_0", "dday_0"]


def test_lock_shutdown_and_failure_paths(make):
    records = [_record("clock_0", False), _record("text_0", False), _record("date_card_0", False)]
    host, manager = make(records)
    manager.restore_all()
    notified = []
    manager.add_listener(lambda: notified.append(True))
    manager.set_all_interaction_locked(True)
    assert manager.get_widget("clock_0").locked
    assert notified == []  # a successful build changes nothing a listener shows

    _Widget.fail_types = {"text"}
    assert manager.get_widget("text_0") is None
    assert [r["id"] for r in json.loads(host.settings.value("overlay_instances"))] == [
        "clock_0",
        "date_card_0",
    ]
    # The hub and gallery drop the failed row without waiting for another change.
    assert notified == [True]
    assert [row[0] for row in manager.instance_records()] == ["clock_0", "date_card_0"]

    manager.shutdown()
    assert [row[0] for row in manager.all_instances()] == ["clock_0"]
    assert "date_card_0" not in _Widget.built
    assert json.loads(host.settings.value("overlay_instances"))[1]["id"] == "date_card_0"


def test_workspace_stack_start_builds_no_hidden_instance(make):
    from calendar_app.domain.widget_workspace import STATE_KEY, default_state, validate_state

    state = default_state()
    state["stacks"] = [{"id": "s", "name": "pair", "members": ["clock_0", "clock_1"], "index": 0}]
    records = [_record("clock_0", True), _record("clock_1", True), _record("loop_deck_0", False)]
    _, manager = make(records, **{STATE_KEY: json.dumps(validate_state(state))})
    manager.restore_all()
    try:
        assert manager._workspace_service is not None
        assert len(manager._workspace_service.stacks.groups) == 1
        manager._workspace_service._refresh_runtime()
        assert _Widget.built == ["clock_0", "clock_1"]
    finally:
        manager._workspace_service.shutdown()


def test_loop_mixer_sources_list_a_hidden_keydeck_without_building_it(make):
    from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget

    _, manager = make([_record("launcher_deck_0", False), _record("loop_deck_0", True)])
    manager.restore_all()
    label = SimpleNamespace(setText=lambda _text: None)
    fake = SimpleNamespace(_manager=lambda: manager, sources_label=label)
    options = OverlayLoopDeckWidget._sources(fake)
    assert ("LAUNCHER_DECK_0", "launcher_deck_0") in options
    assert _Widget.built == ["loop_deck_0"]


def test_first_run_check_and_away_unlock_build_no_hidden_instance(make):
    from calendar_app.presentation.main_window.away_lock_actions import AwayLockMixin
    from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin

    records = [_record("clock_0", False), _record("loop_deck_0", False)]
    host, _ = make(records, with_manager=False)
    host._get_overlay_app_data = dict
    for name in (
        "_ensure_stopwatch_timer",
        "_ensure_countdown_timer",
        "_ensure_slow_text_timer",
        "_refresh_slow_text_widgets",
    ):
        setattr(host, name, lambda: None)
    MainWindowUiActionsMixin.init_overlay_manager(host)
    manager = host.overlay_manager
    # Saved instances exist, so no first-run defaults are added, and none is built.
    assert [row[0] for row in manager.instance_records()] == ["clock_0", "loop_deck_0"]
    assert _Widget.built == []

    window = MagicMock()
    window.overlay_manager = manager
    AwayLockMixin._do_away_unlock(window)
    assert _Widget.built == []
