# -*- coding: utf-8 -*-
"""Only live widget sources enter the independent mixer; opening it preserves decks."""

from copy import deepcopy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.widgets.keydeck import model
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.overlay_launcher_deck import (
    OverlayLauncherDeckWidget,
    open_loop_mixer_widget,
)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(monkeypatch):
    backend = SimpleNamespace(
        route_keydeck_sound=Mock(return_value=True),
        stop_keydeck_source=Mock(return_value=True),
        set_keydeck_sounds=Mock(),
    )
    monkeypatch.setitem(
        sys.modules, "calendar_app.infrastructure.runtime.loop_mixer_audio", backend
    )
    return backend


@pytest.fixture
def surface(app, monkeypatch):
    bank = Mock()
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: bank)
    surface = KeyDeckCanvas()
    surface.set_deck(model.build_template_deck("beatmaker_4x4"))
    yield surface, bank
    surface.close()
    surface.deleteLater()
    app.processEvents()


def test_live_source_routes_custom_wav_actual_gain_once_without_duplicate_bank(surface, backend):
    canvas, bank = surface
    canvas.audio_source_id = "launcher_deck_42"
    canvas.deck["sound_volume"] = 40
    canvas._play("C:/custom/live.wav", 0.25)
    backend.route_keydeck_sound.assert_called_once_with(
        "launcher_deck_42", "C:/custom/live.wav", 0.1
    )
    bank.play.assert_not_called()


def test_unconnected_source_falls_back_and_preview_stays_out_of_bus(surface, backend):
    canvas, bank = surface
    assert canvas.audio_source_id == ""
    canvas._play("preview.wav")
    backend.route_keydeck_sound.assert_not_called()
    assert bank.play.call_count == 1
    canvas.audio_source_id = "live"
    backend.route_keydeck_sound.return_value = False
    canvas._play("unconnected.wav", 0.5, voices=1)
    assert bank.play.call_count == 2
    backend.route_keydeck_sound.reset_mock()
    canvas._sound_preview_queue = [(0.0, "audition.wav", 0.7)]
    canvas._advance_sound_preview()
    backend.route_keydeck_sound.assert_not_called()
    assert bank.play.call_args.args == ("audition.wav", 0.7)


def test_mute_and_empty_paths_never_reach_bus_and_stop_is_source_owned(surface, backend):
    canvas, bank = surface
    canvas.audio_source_id = "live"
    canvas.deck["sound_enabled"] = False
    canvas._play("muted.wav")
    canvas._play("")
    backend.route_keydeck_sound.assert_not_called()
    canvas.stop_sounds()
    backend.stop_keydeck_source.assert_called_once_with("live")
    bank.stop_all.assert_not_called()
    backend.stop_keydeck_source.return_value = False
    canvas.stop_sounds()
    bank.stop_all.assert_called_once()


def test_open_reuses_mixer_or_adds_one_then_shows_and_raises(app):
    mixer = Mock()
    manager = Mock()
    manager.instances_of.return_value = []
    manager.add_instance.return_value = "loop_deck_1"
    manager.get_widget.return_value = mixer
    context = SimpleNamespace(overlay_manager=manager)
    assert open_loop_mixer_widget(context) is mixer
    manager.add_instance.assert_called_once_with("loop_deck")
    manager.show_instance.assert_called_once_with("loop_deck_1")
    mixer.raise_.assert_called_once()
    manager.instances_of.return_value = [("loop_deck_1", "My mixer", mixer)]
    assert open_loop_mixer_widget(context) is mixer
    assert manager.add_instance.call_count == 1


def test_instance_id_is_bound_after_manager_attach_and_old_entries_preserve_data(
    app, backend, tmp_path, monkeypatch
):
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", Mock())
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "sources.ini"), QSettings.Format.IniFormat)
    owner.overlay_manager = Mock()
    owner.overlay_manager.instances_of.return_value = [("loop_deck_1", "Mixer", Mock())]
    widget = OverlayLauncherDeckWidget(owner)
    try:
        assert widget._canvas.audio_source_id == ""
        widget._overlay_inst_id = "launcher_deck_88"
        widget._set_runtime_active(True)
        assert widget._canvas.audio_source_id == "launcher_deck_88"
        before = deepcopy(widget.deck())
        widget._open_beatmaker_performance()
        widget._open_beatmaker_looper()
        assert widget.deck() == before
        assert owner.overlay_manager.show_instance.call_count == 2
    finally:
        widget.close()
        widget.deleteLater()
        owner.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("choice", ["apply", "discard", "keep", "clean"])
def test_studio_mixer_handoff_waits_for_save_discard_or_cancel(app, tmp_path, monkeypatch, choice):
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", Mock())
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "handoff.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    widget._apply_deck(model.build_template_deck("beatmaker_4x4"))
    original = widget.deck()["pages"][0]["keys"][0]["label"]
    calls, observed, errors = [], {}, []

    def opened(context):
        calls.append(
            {
                "context": context,
                "active_modal": QApplication.activeModalWidget(),
                "saved_label": widget.deck()["pages"][0]["keys"][0]["label"],
            }
        )

    monkeypatch.setattr(
        "calendar_app.presentation.widgets.overlay_launcher_deck.open_loop_mixer_widget", opened
    )

    def request():
        studio = widget._studio
        try:
            if choice != "clean":
                studio.deck["pages"][0]["keys"][0]["label"] = "Edited draft"
                studio._mark_dirty()
            studio._ask_unsaved_changes = Mock(return_value=choice)
            studio.open_loop_mixer()
            observed["visible"] = studio.isVisible()
            observed["immediate_calls"] = len(calls)
            if choice == "keep":
                observed["draft_label"] = studio.deck["pages"][0]["keys"][0]["label"]
                studio.force_close()
        except BaseException as error:
            errors.append(error)
            studio.force_close()

    try:
        QTimer.singleShot(0, request)
        widget._open_settings()
        app.processEvents()
        assert not errors
        assert observed["immediate_calls"] == 0
        if choice == "keep":
            assert observed["visible"]
            assert observed["draft_label"] == "Edited draft"
            assert not calls
        else:
            assert not observed["visible"]
            assert len(calls) == 1
            assert calls[0]["context"] is widget
            assert calls[0]["active_modal"] is None
            assert calls[0]["saved_label"] == ("Edited draft" if choice == "apply" else original)
        assert widget._load_deck()["pages"][0]["keys"][0]["label"] == (
            "Edited draft" if choice == "apply" else original
        )
    finally:
        widget.close()
        widget.deleteLater()
        owner.deleteLater()
        app.processEvents()
