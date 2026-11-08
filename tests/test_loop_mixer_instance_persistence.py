# -*- coding: utf-8 -*-
"""The real loop widget persists through the manager; no audio device is opened."""

import json
from types import SimpleNamespace

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QSettings
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget
import pytest

from calendar_app.infrastructure.runtime import loop_mixer_audio
from calendar_app.presentation.widgets.overlay_launcher_deck import open_loop_mixer_widget
from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager, _SettingsProxy
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY


@pytest.fixture
def session(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    previous = app.property(EXITING_PROPERTY)
    app.setProperty(EXITING_PROPERTY, False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    # This scenario persists a 960x760 window. Supply a work area that can fit
    # it; small-screen clamping is exercised by test_loop_mixer_geometry.py.
    desktop = SimpleNamespace(
        geometry=lambda: QRect(0, 0, 1920, 1080),
        availableGeometry=lambda: QRect(0, 0, 1920, 1080),
    )
    monkeypatch.setattr(OverlayLoopDeckWidget, "screen", lambda self: desktop)
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [desktop]))
    device_attempts = []

    class ForbiddenDevice:
        def __init__(self, *_args, **_kwargs):
            device_attempts.append(True)
            raise AssertionError("Persistence tests cannot open an audio device")

    base_mixer = loop_mixer_audio.LoopMixer

    class DeviceFreeMixer(base_mixer):
        def __init__(self):
            super().__init__(backend_factory=ForbiddenDevice, threaded=False)

    monkeypatch.setattr(loop_mixer_audio, "LoopMixer", DeviceFreeMixer)
    settings_path = tmp_path / "session.ini"
    hosts = []

    def make_host():
        host = QWidget()
        host.resize(1200, 900)
        host.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        host.overlay_manager = OverlayWidgetManager(host)
        hosts.append(host)
        return host

    yield SimpleNamespace(app=app, make_host=make_host, path=settings_path, hosts=hosts)
    for host in hosts:
        host.overlay_manager.shutdown()
        for _, _, _, widget in host.overlay_manager.all_instances():
            widget.deleteLater()
        host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.setProperty(EXITING_PROPERTY, previous)
    assert device_attempts == []


def _records(settings):
    return json.loads(settings.value("overlay_instances", "[]"))


def _disk_records(session):
    settings = QSettings(str(session.path), QSettings.Format.IniFormat)
    settings.sync()
    assert settings.status() == QSettings.Status.NoError
    return _records(settings)


def test_direct_entry_saves_enabled_identity_before_return_and_shutdown_restores_it(session):
    host = session.make_host()
    host.settings.setValue("unrelated_user_setting", "preserve exactly")
    widget = open_loop_mixer_widget(host)
    assert isinstance(widget, OverlayLoopDeckWidget)
    assert widget._overlay_inst_id == "loop_deck_0"
    expected = [
        {
            "id": "loop_deck_0",
            "type": "loop_deck",
            "name": host.overlay_manager._meta["loop_deck_0"]["name"],
            "enabled": True,
        }
    ]
    assert _records(host.settings) == expected
    assert host.settings.value("oi_loop_deck_0_overlay_loop_deck_enabled", type=bool)
    # Commit a user resize through the placement hook. QWidget.resize alone
    # also represents a platform DPI suggestion and must not overwrite intent.
    widget._fit_font_to_size(960, 760)
    widget.move(QPoint(35, 45))
    host.overlay_manager.shutdown()
    assert _disk_records(session) == expected
    assert host.settings.value("oi_loop_deck_0_overlay_loop_deck_fixed_w", type=int) == 960
    assert host.settings.value("oi_loop_deck_0_overlay_loop_deck_fixed_h", type=int) == 760
    host_restored = session.make_host()
    host_restored.overlay_manager.restore_all()
    restored = host_restored.overlay_manager.get_widget("loop_deck_0")
    assert isinstance(restored, OverlayLoopDeckWidget)
    assert restored.is_enabled() and restored.isVisible()
    assert restored.size() == widget.size()
    assert host_restored.settings.value("oi_loop_deck_0_overlay_loop_deck_pos_x", type=int) == 35
    assert host_restored.settings.value("oi_loop_deck_0_overlay_loop_deck_pos_y", type=int) == 45
    assert restored.pos() == restored._clamp_restored_position(QPoint(35, 45))
    assert host_restored.settings.value("unrelated_user_setting") == "preserve exactly"


def test_repeat_direct_entry_reuses_identity_and_does_not_overwrite_another_instances_data(session):
    host = session.make_host()
    untouched = '{"version":4,"beatmaker_looper":{"version":1},"custom":"원본"}'
    key = "oi_launcher_deck_5_overlay_launcher_deck_keydeck_data"
    host.settings.setValue(key, untouched)
    first = open_loop_mixer_widget(host)
    before = host.settings.value("overlay_audio_instance_counters")
    host.overlay_manager.hide_instance("loop_deck_0")
    assert _records(host.settings)[0]["enabled"] is False
    second = open_loop_mixer_widget(host)
    assert second is first and len(host.overlay_manager.all_instances()) == 1
    assert _records(host.settings)[0]["enabled"] is True
    assert host.settings.value("overlay_audio_instance_counters") == before
    assert host.settings.value(key) == untouched
    host.overlay_manager.save_all()
    assert _disk_records(session) == _records(host.settings)


def test_header_hide_retains_a_disabled_registered_instance_instead_of_deleting_it(session):
    host = session.make_host()
    widget = open_loop_mixer_widget(host)
    close = widget.header.findChild(QPushButton)
    assert close is not None
    close.click()
    records = _records(host.settings)
    assert len(records) == 1 and records[0]["id"] == "loop_deck_0"
    assert records[0]["enabled"] is False
    assert host.overlay_manager.get_widget("loop_deck_0") is widget
    host.overlay_manager.save_all()
    assert _disk_records(session) == records


def test_old_disabled_launcher_metadata_and_raw_data_survive_direct_loop_creation(
    session, monkeypatch
):
    host = session.make_host()
    old = {"id": "launcher_deck_5", "type": "launcher_deck", "name": "Old deck", "enabled": False}
    raw_key = "oi_launcher_deck_5_overlay_launcher_deck_keydeck_data"
    raw_data = '{"version":4,"beatmaker_recording":{"keep":"raw bytes"}}'
    host.settings.setValue("overlay_instances", json.dumps([old]))
    host.settings.setValue(raw_key, raw_data)

    class DormantLegacyWidget(QWidget):
        def __init__(self, owner):
            super().__init__()
            self.owner = owner
            self.enabled = False

        def apply_initial_settings(self):
            pass

        def restore_position(self, _offset):
            pass

        def save_position(self):
            pass

        def is_enabled(self):
            return self.enabled

        def set_enabled(self, value):
            self.enabled = value

        def _set_runtime_active(self, _active):
            pass

    original_factory = host.overlay_manager._create_widget
    monkeypatch.setattr(
        host.overlay_manager,
        "_create_widget",
        lambda kind, identity: (
            DormantLegacyWidget(_SettingsProxy(host, f"oi_{identity}"))
            if kind == "launcher_deck"
            else original_factory(kind, identity)
        ),
    )
    host.overlay_manager.restore_all()
    loop = open_loop_mixer_widget(host)
    assert isinstance(loop, OverlayLoopDeckWidget)
    host.overlay_manager.save_all()
    records = _disk_records(session)
    assert records[0] == old
    assert records[1]["id"] == "loop_deck_0" and records[1]["enabled"] is True
    assert host.settings.value(raw_key) == raw_data


def test_failed_initialization_can_leave_instance_settings_before_metadata_registration(
    session, monkeypatch
):
    """Characterize failure ordering; do not treat orphan settings as saved metadata."""
    host = session.make_host()
    open_loop_mixer_widget(host)
    before = _records(host.settings)
    created = []

    class FailedInitialization(QWidget):
        def __init__(self, owner):
            super().__init__()
            self.owner = owner
            created.append(self)

        def apply_initial_settings(self):
            self.owner.settings.setValue("overlay_loop_deck_fixed_w", 960)
            raise RuntimeError("Synthetic initialization failure before registration")

    monkeypatch.setattr(
        host.overlay_manager,
        "_create_widget",
        lambda _kind, identity: FailedInitialization(_SettingsProxy(host, f"oi_{identity}")),
    )
    try:
        with pytest.raises(RuntimeError, match="before registration"):
            host.overlay_manager.add_instance("loop_deck")
        assert host.settings.value("oi_loop_deck_1_overlay_loop_deck_fixed_w", type=int) == 960
        assert _records(host.settings) == before
        assert len(host.overlay_manager.all_instances()) == 1
    finally:
        for widget in created:
            widget.deleteLater()
