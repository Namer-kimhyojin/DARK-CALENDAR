# -*- coding: utf-8 -*-
"""Audio lifetimes (2026-11-13).

A KeyDeck that disappears without a hide event still lets go of the output device,
a loaded loop session decodes its decks' sounds before Play, and the per-block
microphone call keeps the GIL. Device-free: a recorder stands in for the KeyDeck
output and WinMM is forbidden by the shared loop-mixer fixture.
"""

import ctypes
import gc
import os
import threading
import time

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
import pytest

from calendar_app.domain.loop_mixer import pcm_samples
from calendar_app.infrastructure.runtime import loop_mixer_audio as audio
from calendar_app.presentation.widgets.keydeck import model, resources
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY
from tests.test_loop_mixer_audio import no_physical_devices, wav  # noqa: F401

_REAL_WINMM = audio._winmm  # captured before the autouse fixture forbids it
_APP = QApplication.instance() or QApplication([])


# -- 1. A deck deleted while shown releases the output -----------------------------


class _Output:
    """Native output stand-in: the decks that currently keep the device open."""

    def __init__(self):
        self.holders = set()

    def hold_output(self, token, held):
        if held:
            self.holders.add(token)
        else:
            self.holders.discard(token)

    def preload(self, *_args, **_kwargs):
        pass

    def play(self, *_args, **_kwargs):
        return True

    def stop_all(self):
        pass


@pytest.fixture
def output(monkeypatch):
    # The packaged build: no Qt Multimedia, so decks hold the native WinMM output.
    device = _Output()
    monkeypatch.setattr(resources, "QSoundEffect", None)
    monkeypatch.setattr(resources, "NativeSoundBank", lambda: device)
    monkeypatch.setattr(resources, "_SOUND_BANK", None)
    previous = _APP.property(EXITING_PROPERTY)
    _APP.setProperty(EXITING_PROPERTY, False)
    yield device
    _settle()
    _APP.setProperty(EXITING_PROPERTY, previous)


def _settle():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.processEvents()


def _deck_in_window():
    window = QWidget()
    container = QWidget(window)
    QVBoxLayout(window).addWidget(container)
    canvas = KeyDeckCanvas(container)
    QVBoxLayout(container).addWidget(canvas)
    canvas.set_deck(model.build_template_deck("beatmaker_4x4"))
    window.show()
    _APP.processEvents()
    assert canvas.isVisible()
    return window, container, canvas


@pytest.mark.parametrize("deleted", ["canvas", "container", "window"])
def test_deck_deleted_while_shown_lets_go_of_the_output(output, deleted):
    window, container, canvas = _deck_in_window()
    assert output.holders == {canvas._audio_token}
    # A deleted window hides its children first; the canvas's own deleteLater() and a
    # deleted parent inside the window delete it while it still counts as shown.
    {"canvas": canvas, "container": container, "window": window}[deleted].deleteLater()
    _settle()
    assert sip.isdeleted(canvas)
    assert output.holders == set()
    if not sip.isdeleted(window):
        window.deleteLater()


def test_releasing_a_deleted_deck_keeps_another_shown_deck_holding(output):
    first_window, _container, first = _deck_in_window()
    second_window, _container, second = _deck_in_window()
    assert output.holders == {first._audio_token, second._audio_token}
    first.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(first)
    # The deletion itself runs no Python; the check follows on the next event-loop turn.
    assert first._audio_token in output.holders
    _APP.processEvents()
    assert output.holders == {second._audio_token}
    first_window.deleteLater()
    second_window.deleteLater()


def test_shown_deck_freed_by_cyclic_garbage_collection_lets_go_of_the_output(output):
    canvas = KeyDeckCanvas()
    canvas.set_deck(model.build_template_deck("beatmaker_4x4"))
    canvas.show()
    _APP.processEvents()
    assert output.holders
    canvas.cycle = canvas  # only the cyclic collector can free it
    del canvas
    gc.collect()
    _settle()
    assert output.holders == set()


@pytest.fixture
def owner(tmp_path):
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "decks.ini"), QSettings.Format.IniFormat)
    yield host
    host.deleteLater()
    _settle()


def test_deck_window_deleted_while_shown_lets_go_of_the_output(output, owner):
    widget = OverlayLauncherDeckWidget(owner)
    widget.set_enabled(True)
    _APP.processEvents()
    canvas = widget._canvas
    assert canvas.isVisible() and output.holders == {canvas._audio_token}
    widget.deleteLater()
    _settle()
    assert sip.isdeleted(canvas)
    assert output.holders == set()


def test_overlay_manager_removing_a_shown_deck_lets_go_of_the_output(output, owner):
    manager = OverlayWidgetManager(owner)
    owner.overlay_manager = manager
    iid = manager.add_instance("launcher_deck", "Drums")
    manager.show_instance(iid)
    _APP.processEvents()
    canvas = manager.get_widget(iid)._canvas
    assert output.holders == {canvas._audio_token}
    manager.remove_instance(iid)
    _settle()
    assert sip.isdeleted(canvas)
    assert output.holders == set()
    manager.shutdown()


# -- 2. A loaded session decodes its decks' sounds before Play ---------------------


def _until(condition, timeout=2.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if condition():
            return True
        time.sleep(0.005)
    return bool(condition())


def test_loaded_session_plays_a_reported_deck_sound_in_the_first_block(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "_KEYDECK_SOUNDS", {})
    path = wav(tmp_path / "pad.wav")
    project = tmp_path / "session.airloop"
    author = audio.LoopMixer(threaded=False)
    assert author.set_track(0, source="launcher_deck_4") and author.save_project(project)
    # The deck reported its sounds before the session that connects it was restored.
    audio.set_keydeck_sounds("launcher_deck_4", [str(path)])
    threads = []
    original = audio._read_wav

    def read(source, **kwargs):
        threads.append(threading.current_thread())
        return original(source, **kwargs)

    monkeypatch.setattr(audio, "_read_wav", read)
    value = audio.LoopMixer()
    try:
        assert value.load_project(project)
        assert _until(lambda: value.snapshot()["completed_operation_id"] == 1)
        assert value.snapshot()["operation_success"]
        assert _until(lambda: value._cached(str(path)) is not None)
        assert threading.current_thread() not in threads
        assert value.set_master_volume(100)
        value._state.play()
        assert value._claim()
        assert audio.route_keydeck_sound("launcher_deck_4", path, 1)
        # This test thread plays the audio thread: the hit sounds in its first block.
        assert any(pcm_samples(value._process_block(frames=1)))
        assert value._awaiting == [] and value.snapshot()["dropped_hits"] == 0
    finally:
        value.shutdown()


# -- 3. The per-block microphone call keeps the GIL ---------------------------------


@pytest.mark.skipif(os.name != "nt", reason="WinMM exists only on Windows")
def test_microphone_buffer_requeue_keeps_the_gil_like_output_writes():
    api = _REAL_WINMM()  # loads the DLL only; no device is opened

    def keeps_gil(function):
        return bool(function._flags_ & ctypes._FUNCFLAG_PYTHONAPI)

    # x64 and ARM64 only: 32-bit WINAPI is stdcall, which PyDLL cannot call.
    assert keeps_gil(api.waveInAddBuffer) == (ctypes.sizeof(ctypes.c_void_p) == 8)
    assert keeps_gil(api.waveInAddBuffer) == keeps_gil(api.waveOutWrite)
    # Opening, starting, resetting and closing the microphone may block in the driver.
    assert not any(
        keeps_gil(getattr(api, name))
        for name in (
            "waveInOpen",
            "waveInStart",
            "waveInReset",
            "waveInClose",
            "waveInPrepareHeader",
            "waveInUnprepareHeader",
        )
    )
