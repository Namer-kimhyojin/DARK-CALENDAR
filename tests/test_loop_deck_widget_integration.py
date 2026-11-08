# -*- coding: utf-8 -*-
"""Loop Deck registration uses existing instance ownership without audio devices."""

import json
import sys
from types import ModuleType
from unittest.mock import Mock

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_manager import (
    _WIDGET_TYPES,
    OverlayWidgetManager,
    widget_type_label,
)
from calendar_app.presentation.widgets.widget_graphic_catalog import (
    COLLECTIONS,
    DESIGNS_BY_KIND,
    collection_for_kind,
    graphic_collections,
)
from calendar_app.presentation.widgets.widget_management_ui import WidgetAddDialog
from calendar_app.presentation.widgets.widget_workspace_gallery import WidgetGallery
from calendar_app.presentation.widgets.widget_workspace_runtime import WidgetWorkspaceService
from tests.test_widget_management_hub import SampleWidget, hub  # noqa: F401


class _LoopWidgetFixture(QWidget):
    """Real Qt lifetime/settings boundary; device transport is deliberately synthetic."""

    prefix = "overlay_loop_deck"

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.active = False
        self.transport_stop = Mock()
        self.transport_shutdown = Mock()
        self._open_settings = Mock()
        self._open_graphic_collections = Mock()
        self.apply_graphic_collection = Mock()
        self.cloned_source = None

    def clone_project_from(self, source):
        self.cloned_source = source
        assert self._get("project_path", "") == ""
        self._set("project", source._get("project"))
        self._set("project_path", f"{self.owner._prefix}/session.airloop")
        return True

    def shutdown(self):
        self.transport_shutdown()

    def _get(self, key, default=None, type_=None):
        name = f"{self.prefix}_{key}"
        return (
            self.owner.settings.value(name, default, type=type_)
            if type_ is not None
            else self.owner.settings.value(name, default)
        )

    def _set(self, key, value):
        self.owner.settings.setValue(f"{self.prefix}_{key}", value)

    def _setting_exists(self, key):
        marker = object()
        return self._get(key, marker) is not marker

    def apply_initial_settings(self):
        self.resize(1020, 760)

    def restore_position(self, offset):
        self.move(QPoint(int(self._get("pos_x", offset.x())), int(self._get("pos_y", offset.y()))))

    def save_position(self):
        self._set("pos_x", self.x())
        self._set("pos_y", self.y())

    def is_enabled(self):
        return self._get("enabled", False, type_=bool)

    def set_enabled(self, enabled):
        self._set("enabled", enabled)
        self._set_runtime_active(enabled)
        if enabled:
            self.show()
        else:
            self.hide()
        callback = getattr(self, "_overlay_manager_sync", None)
        if callback is not None:
            callback()

    def _set_runtime_active(self, active):
        self.active = active
        if not active:
            self.transport_stop()
            self.transport_shutdown()

    def placement_is_locked(self):
        return False


class _LegacyDeckFixture(_LoopWidgetFixture):
    prefix = "overlay_launcher_deck"


@pytest.fixture
def manager(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "loop-instances.ini"), QSettings.Format.IniFormat)
    module = ModuleType("calendar_app.presentation.widgets.overlay_widgets")
    for kind, record in _WIDGET_TYPES.items():
        setattr(
            module,
            record["class"],
            _LegacyDeckFixture if kind == "launcher_deck" else _LoopWidgetFixture,
        )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    instance = OverlayWidgetManager(host)
    yield instance
    for _, _, _, widget in instance.all_instances():
        widget._set_runtime_active(False)
        widget.deleteLater()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_loop_type_uses_its_own_factory_and_allows_independent_instances(manager):
    first = manager.add_instance("loop_deck", "드럼 루프")
    second = manager.add_instance("loop_deck", "보컬 루프")
    assert (first, second) == ("loop_deck_0", "loop_deck_1")
    assert len(manager.instances_of("loop_deck")) == 2
    assert isinstance(manager.get_widget(first), _LoopWidgetFixture)
    manager.get_widget(first)._set("project", "one")
    manager.get_widget(second)._set("project", "two")
    assert manager._settings().value("oi_loop_deck_0_overlay_loop_deck_project") == "one"
    assert manager._settings().value("oi_loop_deck_1_overlay_loop_deck_project") == "two"


def test_restore_duplicate_and_remove_preserve_legacy_and_other_loop_projects(manager):
    settings = manager._settings()
    legacy = '{"version":4,"beatmaker_looper":{"version":1},"custom":"keep raw"}'
    settings.setValue("oi_launcher_deck_0_overlay_launcher_deck_keydeck_data", legacy)
    settings.setValue(
        "overlay_instances",
        json.dumps(
            [{"id": "launcher_deck_0", "type": "launcher_deck", "name": "old", "enabled": True}]
        ),
    )
    manager.restore_all()
    first = manager.add_instance("loop_deck", "new")
    widget = manager.get_widget(first)
    widget._set("project", '{"sources":["deck-a","microphone"]}')
    widget._set("project_path", "original/session.airloop")
    manager.show_instance(first)
    copy_id = manager.duplicate_instance(first)
    assert copy_id == "loop_deck_1"
    assert manager.get_widget(copy_id)._get("project") == widget._get("project")
    assert manager.get_widget(copy_id).cloned_source is widget
    assert manager.get_widget(copy_id)._get("project_path") == "oi_loop_deck_1/session.airloop"
    assert widget._get("project_path") == "original/session.airloop"
    manager.remove_instance(first)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(widget)
    widget.transport_shutdown.assert_called()
    assert not any(key.startswith("oi_loop_deck_0_") for key in settings.allKeys())
    assert settings.value("oi_launcher_deck_0_overlay_launcher_deck_keydeck_data") == legacy
    assert manager.get_widget(copy_id)._get("project") == '{"sources":["deck-a","microphone"]}'
    restored = OverlayWidgetManager(manager._owner)
    restored.restore_all()
    try:
        assert [row[0] for row in restored.all_instances()] == ["launcher_deck_0", copy_id]
        assert restored.get_widget(copy_id).is_enabled()
        assert settings.value("oi_launcher_deck_0_overlay_launcher_deck_keydeck_data") == legacy
    finally:
        for _, _, _, item in restored.all_instances():
            item.deleteLater()


def test_hide_and_shutdown_use_existing_runtime_hook_without_disabling_saved_instance(manager):
    iid = manager.add_instance("loop_deck")
    widget = manager.get_widget(iid)
    widget._set("project", "saved project")
    manager.show_instance(iid)
    manager.hide_instance(iid)
    assert not widget.active and not widget.isVisible()
    widget.transport_stop.assert_called()
    widget.transport_shutdown.assert_called()
    manager.show_instance(iid)
    manager.shutdown()
    assert widget.is_enabled() and not widget.active and not widget.isVisible()
    assert widget._get("project") == "saved project"
    records = json.loads(manager._settings().value("overlay_instances"))
    assert records == [
        {"id": iid, "type": "loop_deck", "name": widget_type_label("loop_deck"), "enabled": True}
    ]


def test_loop_is_not_a_text_or_keycap_collection_target(manager):
    assert graphic_collections("loop_deck") == ()
    assert collection_for_kind(COLLECTIONS[0].collection_id, "loop_deck") is None
    assert len(DESIGNS_BY_KIND) == 8
    loop_id = manager.add_instance("loop_deck")
    legacy_id = manager.add_instance("launcher_deck")
    manager.show_all()
    manager.apply_graphic_collection(legacy_id, COLLECTIONS[0].collection_id)
    manager.get_widget(loop_id).apply_graphic_collection.assert_not_called()
    manager.get_widget(legacy_id).apply_graphic_collection.assert_called_once()


def test_workspace_snapshot_keeps_loop_appearance_without_copying_project_or_runtime(manager):
    iid = manager.add_instance("loop_deck")
    widget = manager.get_widget(iid)
    widget._set("project", '{"sources":["private-wave.wav","microphone"]}')
    widget._set("widget_opacity", 73)
    widget._set("recording_active", True)
    service = WidgetWorkspaceService(manager)
    try:
        snapshot = service.capture()
        entry = snapshot["widgets"][0]
        assert entry["id"] == iid and entry["type"] == "loop_deck"
        assert entry["style"] == {"widget_opacity": 73}
        assert "deck_visual" not in entry
        assert "private-wave" not in json.dumps(snapshot)
        assert "microphone" not in json.dumps(snapshot)
        assert "recording_active" not in json.dumps(snapshot)
    finally:
        service.shutdown()
        service.deleteLater()


def test_workspace_gallery_labels_loop_as_open_not_generic_decoration(manager):
    iid = manager.add_instance("loop_deck")
    parent = QWidget()
    parent._mgr = manager
    parent._create_stack = Mock()
    parent._on_graphics = Mock()
    parent._on_settings = Mock()
    parent._apply_filters = Mock()
    service = WidgetWorkspaceService(manager)
    gallery = WidgetGallery(parent, service)
    try:
        gallery.populate(manager.all_instances(), {iid})
        assert gallery.decorate_button.text() == t("loopdeck.open", "루프 믹서 열기")
        gallery.decorate_button.click()
        parent._on_graphics.assert_called_once_with(iid)
    finally:
        service.shutdown()
        gallery.deleteLater()
        service.deleteLater()
        parent.deleteLater()


def test_widgets_menu_contains_add_and_registered_loop_instance(manager):
    iid = manager.add_instance("loop_deck", "My loop")
    menu = QMenu()
    manager.build_widgets_menu(menu, "")
    texts = [action.text() for action in menu.actions()]
    assert "My loop" in texts
    assert (
        t("widget_manager.add_widget_menu", "{label} 추가", label=widget_type_label("loop_deck"))
        in texts
    )
    assert not manager.get_widget(iid).active


@pytest.mark.parametrize("raises", [False, True])
def test_clone_failure_removes_only_the_new_instance(manager, monkeypatch, raises):
    iid = manager.add_instance("loop_deck")
    source = manager.get_widget(iid)
    source._set("project", "original committed take")
    source._set("project_path", "keep-original.airloop")
    source.transport_shutdown.reset_mock()

    def failed_clone(_self, _source):
        if raises:
            raise ValueError("clone failed")
        return False

    monkeypatch.setattr(_LoopWidgetFixture, "clone_project_from", failed_clone)
    if raises:
        with pytest.raises(ValueError, match="clone failed"):
            manager.duplicate_instance(iid)
    else:
        assert manager.duplicate_instance(iid) is None
    assert [row[0] for row in manager.all_instances()] == [iid]
    assert source._get("project") == "original committed take"
    assert source._get("project_path") == "keep-original.airloop"
    source.transport_shutdown.assert_not_called()
    assert not any(key.startswith("oi_loop_deck_1_") for key in manager._settings().allKeys())


@pytest.mark.parametrize("kind", ["launcher_deck", "loop_deck"])
def test_audio_ids_are_not_reused_after_delete_and_manager_reconstruction(manager, kind):
    old_id = manager.add_instance(kind)
    manager.remove_instance(old_id)
    restored = OverlayWidgetManager(manager._owner)
    restored.restore_all()
    try:
        new_id = restored.add_instance(kind)
        assert old_id == f"{kind}_0" and new_id == f"{kind}_1"
        counters = json.loads(manager._settings().value("overlay_audio_instance_counters"))
        assert counters[kind] == 2
    finally:
        for _, _, _, item in restored.all_instances():
            item.deleteLater()


@pytest.mark.parametrize("kind", ["launcher_deck", "loop_deck"])
def test_legacy_audio_restore_reserves_id_before_first_new_allocation(manager, kind):
    settings = manager._settings()
    identity = f"{kind}_7"
    settings.setValue(
        "overlay_instances",
        json.dumps([{"id": identity, "type": kind, "name": "existing", "enabled": False}]),
    )
    manager.restore_all()
    assert json.loads(settings.value("overlay_audio_instance_counters"))[kind] == 8
    manager.remove_instance(identity)
    restored = OverlayWidgetManager(manager._owner)
    restored.restore_all()
    try:
        assert restored.add_instance(kind) == f"{kind}_8"
    finally:
        for _, _, _, item in restored.all_instances():
            item.deleteLater()


def test_audio_counter_parser_is_bounded_and_does_not_change_general_widget_ids(manager):
    manager._settings().setValue(
        "overlay_audio_instance_counters",
        json.dumps({"launcher_deck": 12, "loop_deck": True, "clock": 99, "unknown": -1}),
    )
    reconstructed = OverlayWidgetManager(manager._owner)
    assert reconstructed._gen_id("launcher_deck") == "launcher_deck_12"
    assert reconstructed._gen_id("loop_deck") == "loop_deck_0"
    assert reconstructed._gen_id("clock") == "clock_0"
    manager._settings().setValue(
        "overlay_audio_instance_counters", json.dumps({"launcher_deck": 2**31 - 1})
    )
    with pytest.raises(ValueError, match="exhausted"):
        reconstructed._gen_id("launcher_deck")


def test_add_gallery_exposes_loop_without_creating_instances(hub):
    dialog, manager, _, _ = hub
    before = manager.all_instances()
    gallery = WidgetAddDialog(dialog)
    assert "loop_deck" in gallery.kind_buttons
    gallery.show()
    button = gallery.kind_buttons["loop_deck"]
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    gallery.name_edit.setText(" 독립 루프 ")
    assert gallery.selection() == ("loop_deck", "독립 루프")
    gallery.reject()
    assert manager.all_instances() == before
    gallery.deleteLater()


def test_loop_card_routes_to_loop_settings_instead_of_generic_decorations(hub):
    dialog, manager, _, _ = hub
    widget = SampleWidget(False)
    manager.rows.append(("loop_deck_0", "Loop", "loop_deck", widget))
    dialog._populate()
    card = dialog._cards["loop_deck_0"]
    assert card.graphics_button.text() == t("loopdeck.open", "루프 믹서 열기")
    card.graphics_button.click()
    widget._open_settings.assert_called_once()
    widget._open_graphic_collections.assert_not_called()
    dialog._on_settings("loop_deck_0")
    assert widget._open_settings.call_count == 2
