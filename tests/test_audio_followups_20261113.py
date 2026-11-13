# -*- coding: utf-8 -*-
"""Audio audit follow-ups (2026-11-13): clip cleanup, data folder, idle polling, frame rate.

Device-free: WinMM is forbidden by the shared fixtures and widgets use a fake backend.
"""

from array import array
import ctypes
import json
from pathlib import Path
from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from calendar_app import app_paths
from calendar_app.domain.loop_mixer import pcm_samples
from calendar_app.infrastructure.runtime import loop_mixer_audio as audio
from calendar_app.presentation.widgets.keydeck import model
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from tests.test_loop_mixer_audio import FakeWinMM, no_physical_devices, wav  # noqa: F401
from tests.test_loop_mixer_widget import mixer  # noqa: F401


def test_saving_removes_clips_the_project_no_longer_uses_so_autosave_keeps_working(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(audio.os, "fsync", lambda _descriptor: None)  # speed only
    value = audio.LoopMixer(threaded=False)
    project = tmp_path / "session.airloop"
    assets = tmp_path / "session.assets"
    assets.mkdir()
    # Only files the mixer itself names by digest may be removed.
    foreign = ["notes.txt", "drums.wav", "F" * 64 + ".wav", "0" * 63 + ".wav"]
    for name in foreign:
        (assets / name).write_bytes(b"user file")
    for take in range(1, 140):
        value._state.load_audio(0, array("h", [take, -take]) * 4)
        assert value.save_project(project)
        snapshot = value.snapshot()
        assert snapshot["operation_success"], (take, snapshot["error"])
    document = json.loads(project.read_text(encoding="utf-8", errors="strict"))
    clip = document["tracks"][0]["pcm_sha256"] + ".wav"
    assert sorted(item.name for item in assets.iterdir()) == sorted([clip, *foreign])
    restored = audio.LoopMixer(threaded=False)
    assert restored.load_project(project) and restored.snapshot()["operation_success"]
    assert restored._state.tracks[0].audio == value._state.tracks[0].audio


def test_saving_keeps_clips_of_a_project_that_shares_the_clip_folder(tmp_path, monkeypatch):
    # "X.airloop" and "X.json" both keep their clips in "X.assets".
    monkeypatch.setattr(audio.os, "fsync", lambda _descriptor: None)
    other = audio.LoopMixer(threaded=False)
    other._state.load_audio(0, array("h", [7, -7]) * 4)
    assert other.save_project(tmp_path / "X.json")
    other_clip = json.loads((tmp_path / "X.json").read_text(encoding="utf-8", errors="strict"))[
        "tracks"
    ][0]["pcm_sha256"]

    value = audio.LoopMixer(threaded=False)
    value._state.load_audio(0, array("h", [3, -3]) * 4)
    assert value.save_project(tmp_path / "X.airloop")
    assert value.snapshot()["operation_success"]

    assert (tmp_path / "X.assets" / (other_clip + ".wav")).is_file()
    restored = audio.LoopMixer(threaded=False)
    assert restored.load_project(tmp_path / "X.json")
    assert restored.snapshot()["operation_success"]


class _QueuedOutputWinMM(FakeWinMM):
    """Buffers stay queued until the test completes them, like a real device."""

    def __init__(self, stop_after):
        super().__init__()
        self.written, self.queued = [], []
        self.stop_after, self.stop = stop_after, None

    def waveOutWrite(self, _handle, header, _size):  # noqa: N802
        contents = ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents
        self.written.append(ctypes.string_at(contents.lpData, contents.dwBufferLength))
        self.queued.append(contents)
        if len(self.written) == self.stop_after:
            self.stop.set()
        return self._call("out_write")


class _HookedEvent:
    """The driver's buffer-done event; the test acts while the worker waits on it."""

    handle = 0

    def __init__(self, on_wait):
        self.on_wait = on_wait

    def wait(self, _milliseconds):
        self.on_wait()

    def wake(self):
        pass

    def close(self):
        pass


def test_hit_arriving_while_output_waits_is_in_the_next_submitted_block(tmp_path):
    api = _QueuedOutputWinMM(stop_after=4)
    path = wav(tmp_path / "pad.wav")

    def on_wait():
        # The device finishes its oldest buffer while a pad is pressed.
        assert audio.route_keydeck_sound("launcher_deck_0", path, 1)
        api.queued.pop(0).dwFlags |= 1

    def factory(stop):
        api.stop = stop
        return audio.WinMMLoopBackend(stop, api=api, events=lambda: _HookedEvent(on_wait))

    value = audio.LoopMixer(backend_factory=factory, threaded=False)
    assert value.set_track(0, source="launcher_deck_0") and value.set_master_volume(100)
    assert value.play()
    value._run()
    # Three blocks fill the device queue, then the worker waits for a free buffer. A
    # block rendered before that wait would carry no hit and add one block of delay.
    assert len(api.written) == 4
    assert not any(pcm_samples(api.written[2])) and any(pcm_samples(api.written[3]))
    assert value.snapshot()["error"] == ""


def test_play_after_a_failed_driver_cleanup_still_asks_for_an_app_restart():
    # An earlier session could not release native buffers; only a restart helps, so
    # later attempts must not send the user to check cables and microphone access.
    audio._DRIVER_UNSAFE.set()
    value = audio.LoopMixer(threaded=False)
    assert value.play()
    value._run()
    snapshot = value.snapshot()
    assert snapshot["mode"] == "idle" and snapshot["error_code"] == "audio_cleanup_failed"
    assert audio._active() is None


def test_loop_mixer_folder_is_inside_the_app_data_folder():
    assert Path(app_paths.LOOP_MIXER_DIR) == Path(app_paths.APP_DATA_DIR) / "loop-mixer"


def test_default_session_lives_in_the_app_loop_mixer_folder(mixer):  # noqa: F811
    _host, _manager, _iid, widget, _devices = mixer
    path = widget._session_path()
    assert path.name == "session.airloop"
    assert path.parent.parent == Path(app_paths.LOOP_MIXER_DIR)


def test_idle_loop_deck_does_not_poll_and_playback_starts_polling(mixer):  # noqa: F811
    _host, manager, iid, widget, devices = mixer
    manager.show_instance(iid)
    QApplication.processEvents()
    assert widget.isVisible() and widget._mixer.snapshot()["mode"] == "idle"
    assert not widget._poll.isActive()
    widget._play()
    assert widget._mixer.snapshot()["mode"] == "playing" and widget._poll.isActive()
    widget._stop()
    assert widget._mixer.snapshot()["mode"] == "idle" and not widget._poll.isActive()
    assert devices == []


def test_idle_mixer_lists_a_new_keydeck_when_the_source_list_opens(mixer):  # noqa: F811
    _host, manager, iid, widget, _devices = mixer
    manager.show_instance(iid)
    QApplication.processEvents()
    deck_id = manager.add_instance("launcher_deck", "Late drums")
    combo = widget.cards[0].source
    assert combo.findData(deck_id) < 0
    combo.showPopup()
    try:
        assert combo.findData(deck_id) >= 0
    finally:
        combo.hidePopup()


def test_keydeck_tap_repaints_at_60_fps_only_while_the_key_moves(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: Mock()
    )
    canvas = KeyDeckCanvas()
    canvas.set_deck(model.build_template_deck("macro_3x3"))
    canvas.deck["reduce_motion"] = False
    canvas.resize(canvas.sizeHint())
    canvas.show()
    app.processEvents()
    canvas._armed_at = 0.0
    try:
        key = canvas.deck["pages"][0]["keys"][0]
        assert key["led"]["mode"] == "reactive"
        center = (
            canvas.renderer.geometry.key_rect(key).center() + canvas.content_offset()
        ).toPoint()
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
        assert canvas._timer.isActive() and canvas._timer.interval() == 16
        frames = {}
        elapsed = 0.0
        while canvas._timer.isActive() and elapsed < 5.0:
            interval = canvas._timer.interval()
            canvas._last_tick -= interval / 1000.0
            canvas._tick()
            frames[interval] = frames.get(interval, 0) + 1
            elapsed += interval / 1000.0
        assert not canvas._timer.isActive()
        # The keystroke itself stays smooth; the ~1.75 s LED fade-out runs at 30 fps.
        assert frames[16] * 0.016 < 0.5, frames
        assert frames.get(33, 0) * 0.033 > 1.0, frames
    finally:
        canvas.close()
        canvas.deleteLater()
        app.processEvents()
