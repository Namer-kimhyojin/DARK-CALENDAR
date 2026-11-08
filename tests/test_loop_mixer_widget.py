# -*- coding: utf-8 -*-
"""Real mixer UI/domain with temporary settings and an unopened device boundary."""

import json
from pathlib import Path
import threading
from types import SimpleNamespace

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRect, QSettings, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.infrastructure.runtime import loop_mixer_audio
from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY
from calendar_app.shared.typography import get_typography_scale

_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def mixer(tmp_path, monkeypatch):
    opened_devices = []

    class ForbiddenDevice:
        def __init__(self, *_args, **_kwargs):
            opened_devices.append("device")
            raise AssertionError("A widget regression must not open an audio device")

    base = loop_mixer_audio.LoopMixer

    class DeviceFreeMixer(base):
        def __init__(self):
            super().__init__(backend_factory=ForbiddenDevice, threaded=False)

    monkeypatch.setattr(loop_mixer_audio, "LoopMixer", DeviceFreeMixer)
    # Responsive 1120px layout tests explicitly model a desktop-sized work area;
    # the offscreen plugin's default 800px screen is not that test scenario.
    desktop = SimpleNamespace(
        geometry=lambda: QRect(0, 0, 1920, 1080),
        availableGeometry=lambda: QRect(0, 0, 1920, 1080),
    )
    monkeypatch.setattr(OverlayLoopDeckWidget, "screen", lambda self: desktop)
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [desktop]))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    previous = _APP.property(EXITING_PROPERTY)
    _APP.setProperty(EXITING_PROPERTY, False)
    host = QWidget()
    host.resize(1200, 900)
    host.settings = QSettings(str(tmp_path / "mixer.ini"), QSettings.Format.IniFormat)
    manager = OverlayWidgetManager(host)
    host.overlay_manager = manager
    iid = manager.add_instance("loop_deck", "Mixer")
    widget = manager.get_widget(iid)
    assert isinstance(widget, OverlayLoopDeckWidget)
    yield host, manager, iid, widget, opened_devices
    manager.shutdown()
    for _, _, _, item in manager.all_instances():
        item.deleteLater()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.setProperty(EXITING_PROPERTY, previous)
    assert opened_devices == []


def _settle_save(widget):
    widget._save.stop()
    widget._autosave()
    widget._refresh_face()


def test_construct_show_hide_and_settings_use_one_registered_idle_widget(mixer):
    _, manager, iid, widget, devices = mixer
    assert not widget.isVisible() and not widget.is_enabled()
    assert widget._mixer.snapshot()["mode"] == "idle"
    assert not widget._poll.isActive() and devices == []
    manager.show_instance(iid)
    _APP.processEvents()
    assert widget.isVisible() and widget._poll.isActive()
    manager.hide_instance(iid)
    assert not widget.isVisible() and not widget._poll.isActive()
    assert widget._mixer.snapshot()["mode"] == "idle"
    widget._open_settings()
    assert widget.isVisible() and widget.is_enabled()
    assert manager._meta[iid]["enabled"]


@pytest.mark.parametrize("width,columns", [(1120, 3), (820, 2), (520, 1)])
def test_responsive_columns_keep_the_same_six_track_controls(mixer, width, columns):
    _, _, _, widget, _ = mixer
    cards = list(widget.cards)
    widget.resize(width, 820)
    widget._reflow_for_width()
    assert widget._columns == columns and widget.cards == cards
    assert widget.grid.count() == 6
    assert all(card.arm.minimumHeight() >= 44 for card in cards)
    assert all(card.volume.minimumHeight() >= 44 for card in cards)


def test_track_buttons_and_direct_slider_changes_do_not_drag_the_window(mixer):
    _, manager, iid, widget, _ = mixer
    manager.show_instance(iid)
    _APP.processEvents()
    before = widget.pos()
    card = widget.cards[0]
    QTest.mouseClick(card.mute, Qt.MouseButton.LeftButton)
    assert widget._mixer.snapshot()["tracks"][0]["muted"] is True
    card.volume.resize(240, 44)
    QTest.mousePress(card.volume, Qt.MouseButton.LeftButton, pos=QPoint(25, 22))
    QTest.mouseMove(card.volume, QPoint(210, 22))
    QTest.mouseRelease(card.volume, Qt.MouseButton.LeftButton, pos=QPoint(210, 22))
    assert widget._mixer.snapshot()["tracks"][0]["volume"] >= 80
    assert widget.pos() == before
    assert widget._placement_origin is None


def test_wheel_never_changes_a_track_fader_or_bpm(mixer):
    _, _, _, widget, _ = mixer
    for control in (widget.cards[0].volume, widget.cards[0].pan, widget.bpm):
        previous = control.value()
        point = control.rect().center()
        event = QWheelEvent(
            QPointF(point),
            QPointF(control.mapToGlobal(point)),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QCoreApplication.sendEvent(control, event)
        assert control.value() == previous


def test_disconnected_keydeck_source_remains_identified_without_reassignment(mixer):
    _, manager, _, widget, _ = mixer
    source = QWidget()
    source_id = "launcher_deck_9"
    manager._widgets[source_id] = source
    manager._meta[source_id] = {
        "_id": source_id,
        "type": "launcher_deck",
        "name": "Drums",
        "enabled": False,
    }
    widget._edit_track(0, source=source_id)
    widget._source_options = widget._sources()
    widget._refresh_face()
    assert widget.cards[0].source.currentData() == source_id
    manager._widgets.pop(source_id)
    manager._meta.pop(source_id)
    source.deleteLater()
    widget._source_options = widget._sources()
    widget._refresh_face()
    assert widget.cards[0].source.currentData() == source_id
    assert widget._mixer.snapshot()["tracks"][0]["source"] == source_id
    assert widget.cards[0].source.currentText() != "Drums"


@pytest.mark.parametrize("body_pt", [11, 24])
def test_shared_typography_and_touch_controls_follow_saved_font_size(mixer, body_pt):
    host, manager, iid, widget, _ = mixer
    host.settings.setValue("font_size", body_pt)
    widget._apply_appearance()
    manager.show_instance(iid)
    _APP.processEvents()
    typography = get_typography_scale(host.settings)
    assert f"font-size:{typography.body_px}px" in widget.face.styleSheet()
    assert f"font-size:{typography.title_px}px" in widget.face.styleSheet()
    for button in (widget.play_button, widget.stop_button, widget.cards[0].arm):
        assert button.height() >= 44
        assert button.height() >= button.fontMetrics().height()


def test_first_autosave_creates_its_own_directory_and_restore_never_autoplays(mixer):
    host, manager, iid, widget, devices = mixer
    path = widget._session_path()
    assert not path.parent.exists()
    widget.bpm.setValue(123)
    _settle_save(widget)
    assert path.is_file(), widget._mixer.snapshot()["error"]
    assert Path(widget._get("project_path")) == path
    assert not widget._dirty
    restored = OverlayWidgetManager(host)
    restored.restore_all()
    try:
        copy = restored.get_widget(iid)
        copy._refresh_face()
        assert copy._mixer.snapshot()["bpm"] == 123
        assert copy._mixer.snapshot()["mode"] == "idle" and devices == []
    finally:
        restored.shutdown()
        for _, _, _, item in restored.all_instances():
            item.deleteLater()


def test_duplicate_has_independent_project_path_and_delete_shuts_only_its_mixer(mixer):
    _, manager, iid, widget, _ = mixer
    widget._edit_track(0, volume=37, source="mic")
    _settle_save(widget)
    original_path = widget._session_path()
    original_bytes = original_path.read_bytes()
    duplicate_id = manager.duplicate_instance(iid)
    other = manager.get_widget(duplicate_id)
    _settle_save(other)
    assert other._session_path() != original_path
    assert other._session_path().is_file()
    assert other._mixer.snapshot()["tracks"][0]["volume"] == 37
    other._edit_track(0, volume=82)
    _settle_save(other)
    assert original_path.read_bytes() == original_bytes
    assert widget._mixer.snapshot()["tracks"][0]["volume"] == 37
    backend = other._mixer
    manager.remove_instance(duplicate_id)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(other) and backend._closed
    assert not widget._mixer._closed
    assert original_path.read_bytes() == original_bytes


def test_manager_shutdown_closes_runtime_and_preserves_enabled_and_project(mixer):
    _, manager, iid, widget, _ = mixer
    manager.show_instance(iid)
    widget.bpm.setValue(124)
    _settle_save(widget)
    path = widget._session_path()
    manager.shutdown()
    assert widget._mixer._closed and not widget._poll.isActive()
    assert not widget.isVisible() and widget.is_enabled()
    assert path.is_file()


@pytest.mark.parametrize("succeeds", [True, False])
def test_async_save_commits_ui_pointer_only_on_successful_completion(
    mixer, tmp_path, monkeypatch, succeeds
):
    _, _, _, widget, devices = mixer
    from calendar_app.presentation.widgets.overlay_loop_deck import QFileDialog

    destination = tmp_path / "explicit-save.airloop"
    entered, release = threading.Event(), threading.Event()
    copy_project = widget._mixer._copy_project

    def blocked_copy():
        entered.set()
        if not release.wait(3) or not succeeds:
            raise OSError("fixture file write failed")
        return copy_project()

    widget._mixer._threaded = True
    monkeypatch.setattr(widget._mixer, "_copy_project", blocked_copy)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(destination), ""))
    widget.bpm.setValue(127)
    widget._save.stop()
    previous_pointer = widget._get("project_path", "")
    try:
        widget._save_project_as()
        assert entered.wait(1)
        assert widget._mixer.snapshot()["busy"]
        assert widget._get("project_path", "") == previous_pointer
        assert widget._dirty
    finally:
        release.set()
        if widget._mixer._io_thread is not None:
            widget._mixer._io_thread.join(3)
    widget._refresh_face()
    assert not widget._mixer.snapshot()["busy"] and devices == []
    if succeeds:
        assert widget._get("project_path") == str(destination)
        assert destination.is_file() and not widget._dirty
    else:
        assert widget._get("project_path", "") == previous_pointer
        assert widget._dirty and not destination.exists()


def test_removed_keydeck_source_cannot_rebind_to_a_new_deck_after_restart(mixer):
    host, manager, iid, widget, devices = mixer
    source_id = manager.add_instance("launcher_deck", "Original drums")
    widget._edit_track(0, source=source_id)
    _settle_save(widget)
    manager.remove_instance(source_id)
    manager.shutdown()
    restored = OverlayWidgetManager(host)
    host.overlay_manager = restored
    restored.restore_all()
    try:
        new_id = restored.add_instance("launcher_deck", "New melody")
        assert new_id != source_id
        current = restored.get_widget(iid)
        current._source_options = current._sources()
        current._refresh_face()
        assert current._mixer.snapshot()["tracks"][0]["source"] == source_id
        assert current.cards[0].source.currentData() == source_id
        assert "New melody" not in current.cards[0].source.currentText()
        assert devices == []
    finally:
        restored.shutdown()
        for _, _, _, item in restored.all_instances():
            item.deleteLater()


def test_removed_mixer_default_project_is_not_loaded_by_a_new_instance(mixer):
    host, manager, iid, widget, devices = mixer
    widget.bpm.setValue(133)
    _settle_save(widget)
    old_path = widget._session_path()
    old_bytes = old_path.read_bytes()
    manager.remove_instance(iid)
    restored = OverlayWidgetManager(host)
    host.overlay_manager = restored
    restored.restore_all()
    try:
        new_id = restored.add_instance("loop_deck")
        current = restored.get_widget(new_id)
        assert new_id != iid and current._session_path() != old_path
        assert current._mixer.snapshot()["bpm"] == 120
        assert current._get("project_path", "") == "" and devices == []
        assert old_path.read_bytes() == old_bytes
    finally:
        restored.shutdown()
        for _, _, _, item in restored.all_instances():
            item.deleteLater()


@pytest.mark.parametrize("gesture", ["name", "fader"])
def test_autosave_waits_while_a_name_or_fader_is_being_edited(mixer, gesture):
    _, manager, iid, widget, _ = mixer
    manager.show_instance(iid)
    _APP.processEvents()
    widget._edit_track(0, volume=55)
    widget._save.stop()
    if gesture == "name":
        widget.cards[0].name.setFocus()
        _APP.processEvents()
        assert widget.cards[0].name.hasFocus()
    else:
        widget.cards[0].volume.setSliderDown(True)
    widget._autosave()
    assert widget._pending_io is None and not widget._mixer.snapshot()["busy"]
    assert widget._dirty
    widget.cards[0].name.clearFocus()
    widget.cards[0].volume.setSliderDown(False)
    _settle_save(widget)
    assert widget._session_path().is_file() and not widget._dirty


def test_hiding_commits_the_name_releases_faders_and_saves_without_losing_input(mixer):
    _, manager, iid, widget, _ = mixer
    manager.show_instance(iid)
    _APP.processEvents()
    editor = widget.cards[0].name
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "Live vocal")
    widget.cards[0].volume.setSliderDown(True)
    manager.hide_instance(iid)
    widget._refresh_face()
    assert not widget.cards[0].volume.isSliderDown()
    assert widget._mixer.snapshot()["tracks"][0]["name"] == "Live vocal"
    assert widget._session_path().is_file()
    document = json.loads(widget._session_path().read_text(encoding="utf-8", errors="strict"))
    assert document["tracks"][0]["name"] == "Live vocal"
