# -*- coding: utf-8 -*-
"""Approved audio decisions (2026-11-13).

KeyDeck holds its output device while a deck is visible; the loop mixer waits on a
driver event, opens the microphone off the audio thread, keeps a take on device
errors, records hits where they were heard, decodes custom WAVs off the audio thread
and survives a system sleep. Device-free: fakes stand in for every driver call.
"""

from array import array
from collections import OrderedDict
import ctypes
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.domain import loop_mixer as domain
from calendar_app.domain.loop_mixer import BLOCK_FRAMES, pcm_bytes, pcm_samples
from calendar_app.infrastructure.runtime import keydeck_audio
from calendar_app.infrastructure.runtime import loop_mixer_audio as audio
from calendar_app.presentation.widgets.keydeck import model, resources
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from tests.test_keydeck_native_audio import FakeWinMM as DeckWinMM
from tests.test_keydeck_native_audio import _wav as deck_wav
from tests.test_loop_mixer_audio import FakeWinMM, no_physical_devices, wav  # noqa: F401

_REAL_WINMM = audio._winmm  # captured before the autouse fixture forbids it
_APP = QApplication.instance() or QApplication([])


def _until(condition, timeout=2.0):
    # perf_counter: several tests replace time.monotonic with a fake clock.
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if condition():
            return True
        time.sleep(0.005)
    return bool(condition())


@pytest.fixture(autouse=True)
def forget_keydeck_sounds():
    yield
    audio._KEYDECK_SOUNDS.clear()


# -- 1. KeyDeck output device held while a deck is visible -------------------------


@pytest.fixture
def deck_api(monkeypatch):
    api = DeckWinMM()
    monkeypatch.setattr(keydeck_audio, "_WinMM", lambda: api)
    return api


def test_bank_keeps_the_device_open_only_while_a_deck_holds_it(deck_api, tmp_path):
    path = deck_wav(tmp_path / "pad.wav")
    primed = keydeck_audio._PRIMED_VOICES
    bank = keydeck_audio.NativeSoundBank()
    try:
        bank.preload([path])
        bank.hold_output(1, True)
        bank.hold_output(2, True)
        assert _until(lambda: deck_api.calls.count("open") == primed)
        assert bank.play(path, 0.6)
        assert _until(lambda: "write" in deck_api.calls)
        # The first hit used a voice opened while the deck appeared.
        assert deck_api.calls.count("open") == primed
        bank.hold_output(1, False)
        time.sleep(0.1)
        assert "close" not in deck_api.calls  # another visible deck still holds it
        bank.hold_output(2, False)
        assert _until(lambda: deck_api.calls.count("close") == primed - 1)
        for header in list(deck_api.headers.values()):
            header.dwFlags |= keydeck_audio._WHDR_DONE
        # The sounding voice closes once Windows hands its buffer back.
        assert _until(lambda: deck_api.calls.count("close") == primed)
    finally:
        bank._shutdown()


def test_releasing_a_hold_never_starts_the_audio_worker(deck_api):
    bank = keydeck_audio.NativeSoundBank()
    bank.hold_output(1, False)
    assert bank._thread is None
    bank.close()


def test_preload_prepares_a_custom_pad_at_its_volume(deck_api, tmp_path, monkeypatch):
    calls = []
    original = keydeck_audio._apply_gain

    def counted(*args):
        calls.append(args[2])
        return original(*args)

    monkeypatch.setattr(keydeck_audio, "_apply_gain", counted)
    player = keydeck_audio._Player()
    path = deck_wav(tmp_path / "pad.wav")
    try:
        player.preload([path], volume=0.6)
        assert calls == [0.6] and deck_api.calls == []
        player.play(path, 0.6)
        assert calls == [0.6]  # the first hit reused the prepared samples
    finally:
        player.close()


@pytest.fixture
def deck_canvas(monkeypatch):
    app = _APP
    bank = Mock()
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: bank)
    canvas = KeyDeckCanvas()
    canvas.set_deck(model.build_template_deck("beatmaker_4x4"))
    canvas.resize(canvas.sizeHint())
    yield canvas, bank, app
    canvas.close()
    canvas.deleteLater()
    app.processEvents()


def _holds(bank):
    return [call.args[1] for call in bank.hold_output.call_args_list]


def test_visible_active_deck_holds_the_output_and_hiding_releases_it(deck_canvas):
    canvas, bank, app = deck_canvas
    assert _holds(bank) == []
    canvas.show()
    app.processEvents()
    assert _holds(bank) == [True]
    canvas.set_runtime_active(False)
    assert _holds(bank) == [True, False]
    bank.reset_mock()
    canvas.set_runtime_active(True)
    names = [name for name, _args, _kwargs in bank.method_calls]
    # The device is primed after this deck's sounds were queued for loading.
    assert names.index("hold_output") > max(i for i, n in enumerate(names) if n == "preload")
    canvas.hide()
    app.processEvents()
    assert _holds(bank) == [True, False]
    assert len({call.args[0] for call in bank.hold_output.call_args_list}) == 1
    canvas.deck["sound_enabled"] = False
    canvas.show()
    app.processEvents()
    assert _holds(bank) == [True, False]  # a muted deck never opens the device


def test_packaged_sound_bank_forwards_holds_to_the_native_device(monkeypatch):
    native = Mock()
    monkeypatch.setattr(resources, "QSoundEffect", None)
    monkeypatch.setattr(resources, "NativeSoundBank", lambda: native)
    bank = resources.SoundBank()
    bank.hold_output(3, False)
    native.hold_output.assert_not_called()
    bank.hold_output(3, True)
    native.hold_output.assert_called_once_with(3, True)


def test_canvas_preloads_custom_pads_at_their_playing_volume(deck_canvas, tmp_path):
    canvas, bank, _app = deck_canvas
    path = deck_wav(tmp_path / "custom.wav")
    deck = model.build_template_deck("macro_3x3")
    deck.update(sound="custom", sound_path=path, sound_volume=50)
    deck["pages"][0]["keys"][0]["sound_volume"] = 40
    bank.preload.reset_mock()
    canvas.set_deck(deck)
    volumes = {
        call.kwargs.get("volume") for call in bank.preload.call_args_list if path in call.args[0]
    }
    assert volumes == {0.5, 0.2}


# -- 2. Loop mixer output waits on a driver event ----------------------------------


class FakeEvent:
    """Stand-in for the driver-signalled event: records waits and never blocks."""

    handle = 0x5150

    def __init__(self, on_wait=None, log=None):
        self.waits, self.wakes, self.closed = [], 0, False
        self.on_wait, self.log = on_wait, log

    def wait(self, milliseconds):
        self.waits.append(milliseconds)
        if self.on_wait is not None:
            self.on_wait()

    def wake(self):
        self.wakes += 1

    def close(self):
        self.closed = True
        if self.log is not None:
            self.log.append("event_close")


class QueuedWinMM(FakeWinMM):
    """Written buffers stay queued until the test completes them, like a real device."""

    def __init__(self):
        super().__init__()
        self.opened_with = None
        self.queued = []

    def waveOutOpen(self, handle, device, fmt, callback, instance, flags):  # noqa: N802
        self.opened_with = (callback, flags)
        return super().waveOutOpen(handle, device, fmt, callback, instance, flags)

    def waveOutWrite(self, _handle, header, _size):  # noqa: N802
        result = self._call("out_write")
        if not result:
            self.queued.append(ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents)
        return result

    def complete_one(self):
        if self.queued:
            self.queued.pop(0).dwFlags |= 1


def test_output_waits_on_the_driver_event_and_closes_it_after_the_device():
    api = QueuedWinMM()
    events = []

    def new_event():
        events.append(FakeEvent(on_wait=api.complete_one, log=api.calls))
        return events[-1]

    backend = audio.WinMMLoopBackend(threading.Event(), api=api, events=new_event)
    backend.open_output()
    assert api.opened_with == (FakeEvent.handle, audio._CALLBACK_EVENT)
    for _ in range(4):
        assert backend.write_output(bytes(BLOCK_FRAMES * 4))
    # Only the fourth block had to wait, once, for the device to free a buffer.
    assert events[0].waits == [audio._OUTPUT_WAIT_MS]
    backend.close()
    assert api.calls[-2:] == ["out_close", "event_close"]


@pytest.mark.parametrize("failure", ["out_open", "out_close"])
def test_event_lives_exactly_as_long_as_the_driver_may_signal_it(failure):
    api = QueuedWinMM()
    events = []
    backend = audio.WinMMLoopBackend(
        threading.Event(),
        api=api,
        events=lambda: events.append(FakeEvent(log=api.calls)) or events[-1],
    )
    if failure == "out_open":
        api.fail = "out_open"
        with pytest.raises(OSError):
            backend.open_output()
        assert events[0].closed  # the device never opened, so nothing can signal it
        backend.close()
        return
    backend.open_output()
    assert backend.write_output(bytes(40))
    api.fail = "out_close"
    with pytest.raises(OSError):
        backend.close()
    # The driver may still signal a handle it was never told to release.
    assert not events[0].closed and backend in audio._RETAINED
    api.fail = ""
    backend.close()
    assert events[0].closed


class BlockingEvent:
    handle = 1

    def __init__(self):
        self.signal, self.waiting = threading.Event(), threading.Event()

    def wait(self, _milliseconds):
        self.waiting.set()
        self.signal.wait(5)
        self.signal.clear()

    def wake(self):
        self.signal.set()

    def close(self):
        pass


def test_stop_wakes_the_audio_thread_out_of_its_buffer_wait():
    api = QueuedWinMM()
    events = []

    def factory(stop):
        return audio.WinMMLoopBackend(
            stop, api=api, events=lambda: events.append(BlockingEvent()) or events[-1]
        )

    value = audio.LoopMixer(backend_factory=factory)
    assert value.play()
    assert _until(lambda: bool(events) and events[0].waiting.is_set())
    started = time.perf_counter()
    value.stop()
    assert time.perf_counter() - started < 0.25
    assert not value._thread.is_alive() and audio._active() is None


@pytest.mark.skipif(os.name != "nt", reason="WinMM exists only on Windows")
def test_buffer_calls_keep_the_gil_and_device_calls_release_it():
    api = _REAL_WINMM()  # loads the DLL only; no device is opened

    def keeps_gil(function):
        return bool(function._flags_ & ctypes._FUNCFLAG_PYTHONAPI)

    assert all(
        keeps_gil(getattr(api, name))
        for name in (
            "waveOutPrepareHeader",
            "waveOutUnprepareHeader",
            "waveOutWrite",
            "waveOutGetPosition",
        )
    )
    assert not any(
        keeps_gil(getattr(api, name))
        for name in ("waveOutOpen", "waveOutReset", "waveOutClose", "waveInOpen", "waveInStart")
    )


# -- 3. Recording ------------------------------------------------------------------


def test_microphone_opens_on_a_helper_thread_while_the_loop_keeps_playing():
    release, opening = threading.Event(), threading.Event()
    writes, reads, threads = [], [], {}

    class Backend:
        def __init__(self, stop):
            self.stop = stop

        def open_output(self):
            threads["audio"] = threading.current_thread()

        def open_input(self, _device):
            threads["microphone"] = threading.current_thread()
            opening.set()
            release.wait(2)

        def read_input(self, frames):
            reads.append(frames)
            return bytes(frames * 4)

        def close_input(self):
            pass

        def wait_output(self):
            return not self.stop.is_set()

        def write_output(self, _data):
            writes.append(1)
            self.stop.wait(0.005)
            return not self.stop.is_set()

        def close(self):
            pass

    value = audio.LoopMixer(backend_factory=Backend)
    try:
        assert value.set_track(0, source="mic", armed=True)
        assert value.play() and _until(lambda: len(writes) > 2)
        assert value.record() and opening.wait(1)
        before = len(writes)
        time.sleep(0.1)
        assert len(writes) > before + 3  # the loop kept playing while the mic opened
        assert threads["microphone"] is not threads["audio"]
        assert not reads  # nothing is read before the device is ready
        release.set()
        assert _until(lambda: bool(reads))
    finally:
        release.set()
        value.shutdown()


def test_device_error_during_recording_keeps_the_partial_take(monkeypatch):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: BLOCK_FRAMES * 4)

    class Backend:
        def __init__(self, stop):
            self.stop, self.blocks = stop, 0

        def open_output(self):
            pass

        def open_input(self, _device):
            pass

        def read_input(self, frames):
            return pcm_bytes(array("h", [500, 500]) * frames)

        def close_input(self):
            pass

        def wait_output(self):
            return True

        def write_output(self, _data):
            self.blocks += 1
            if self.blocks == 3:
                raise OSError("waveOutWrite: WinMM 6")  # unplugged mid-take
            return True

        def close(self):
            pass

    value = audio.LoopMixer(backend_factory=Backend, threaded=False)
    assert value.set_track(0, source="mic", armed=True)
    assert value.record()
    value._run()
    snapshot = value.snapshot()
    assert snapshot["mode"] == "idle"
    assert snapshot["error_code"] == "audio_device_error_take_saved"
    take = value._state.tracks[0].audio
    # Three blocks were rendered before the failure; like Stop, they are kept.
    assert set(take[: 3 * BLOCK_FRAMES * 2]) == {500}
    assert not any(take[3 * BLOCK_FRAMES * 2 :])
    assert audio._active() is None


def test_device_error_without_a_take_keeps_the_plain_device_message():
    class Broken:
        def __init__(self, _stop):
            pass

        def open_output(self):
            raise OSError("waveOutOpen: WinMM 2")

        def close(self):
            pass

    value = audio.LoopMixer(backend_factory=Broken, threaded=False)
    assert value.play()
    value._run()
    assert value.snapshot()["error_code"] == "audio_device_error"


def test_saved_take_error_has_its_own_message():
    from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget

    message = OverlayLoopDeckWidget._error_message
    saved = message(None, {"error_code": "audio_device_error_take_saved"})
    assert saved != message(None, {"error_code": "audio_device_error"})
    assert saved != message(None, {"error_code": "unknown"})


def _pcm(value, frames):
    return pcm_bytes(array("h", [value, value]) * frames)


def test_take_is_written_where_it_was_heard_not_where_it_was_rendered(monkeypatch):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: 100)
    state = domain.LoopMixerState()
    state.set_track(0, source="launcher_deck_1", armed=True)
    state.set_track(1, source="mic", armed=True)
    state.record()
    state.render(40, latency=30, input_latency=5)  # silence: no shift is fixed yet
    state.add_voice("launcher_deck_1", array("h", [700, 700]) * 10, 1.0)
    state.render(40, _pcm(300, 40), latency=30, input_latency=5)
    # A shift fixed at the first sound stays for the whole take, so it never jitters.
    state.render(20, _pcm(300, 20), latency=55, input_latency=9)
    assert state.mode == "playing"
    pad = [state.tracks[0].audio[frame * 2] for frame in range(100)]
    mic = [state.tracks[1].audio[frame * 2] for frame in range(100)]
    # Rendered at frame 40, heard 30 frames later: recorded at frame 10.
    assert pad == [0] * 10 + [700] * 10 + [0] * 80
    # The microphone also heard the room 5 frames before it was read.
    assert mic == [0] * 5 + [300] * 60 + [0] * 35


def test_overdub_shift_wraps_and_keeps_audio_it_does_not_reach(monkeypatch):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: 10)
    state = domain.LoopMixerState()
    state.set_track(0, source="mic", armed=True)
    state.load_audio(0, array("h", [100, 100]) * 10)
    state.record(overdub=True)
    state.render(4, _pcm(5, 4), latency=2, input_latency=1)
    assert state.stop() is True  # an early stop commits the partial take
    assert [state.tracks[0].audio[frame * 2] for frame in range(10)] == [105] + [100] * 6 + [
        105
    ] * 3


def test_backend_reports_frames_queued_ahead_of_the_speaker_and_mic_backlog():
    api = QueuedWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api, events=FakeEvent)
    backend.open_output()
    for _ in range(3):
        assert backend.write_output(bytes(BLOCK_FRAMES * 4))
    api.played = 100
    assert backend.latency_frames() == (3 * BLOCK_FRAMES - 100, 0)
    api.played = None  # no position from the driver: count the buffers still queued
    assert backend.latency_frames() == (3 * BLOCK_FRAMES, 0)
    backend.open_input("default")  # the fake fills all four capture buffers at once
    backend.read_input(BLOCK_FRAMES)
    assert backend.latency_frames()[1] == 3 * BLOCK_FRAMES + BLOCK_FRAMES
    backend.close()


def test_worker_records_a_hit_shifted_by_the_backend_latency(monkeypatch, tmp_path):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: BLOCK_FRAMES * 4)
    path = wav(tmp_path / "pad.wav", value=900, frames=10)

    class Backend:
        def __init__(self, stop):
            self.stop, self.blocks = stop, 0

        def open_output(self):
            pass

        def latency_frames(self):
            return (BLOCK_FRAMES + 7, 0)

        def wait_output(self):
            return not self.stop.is_set()

        def write_output(self, _data):
            self.blocks += 1
            if self.blocks == 1:
                assert audio.route_keydeck_sound("launcher_deck_3", path, 1)
            if self.blocks == 4:
                self.stop.set()
            return not self.stop.is_set()

        def close(self):
            pass

    value = audio.LoopMixer(backend_factory=Backend, threaded=False)
    assert value.set_track(0, source="launcher_deck_3", armed=True)
    assert value.record()
    value._run()
    take = [value._state.tracks[0].audio[frame * 2] for frame in range(BLOCK_FRAMES * 4)]
    # Rendered at the second block's start; heard BLOCK_FRAMES + 7 frames later.
    assert take == [900] * 3 + [0] * (BLOCK_FRAMES * 4 - 10) + [900] * 7


# -- 4. Custom sounds decode off the audio thread ----------------------------------


def _decoded_on(monkeypatch, gate=None):
    threads = []
    original = audio._read_wav

    def read(path, **kwargs):
        threads.append(threading.current_thread())
        if gate is not None:
            gate.wait(2)
        return original(path, **kwargs)

    monkeypatch.setattr(audio, "_read_wav", read)
    return threads


def test_connecting_a_keydeck_decodes_its_sounds_off_the_audio_thread(tmp_path, monkeypatch):
    threads = _decoded_on(monkeypatch)
    path = str(wav(tmp_path / "pad.wav"))
    value = audio.LoopMixer()
    audio.set_keydeck_sounds("launcher_deck_7", [path])
    assert not threads  # nothing connected yet
    assert value.set_track(0, source="launcher_deck_7")
    assert _until(lambda: value._cached(path) is not None)
    assert threads and threading.current_thread() not in threads


def test_changed_keydeck_sounds_reach_a_connected_mixer(tmp_path, monkeypatch):
    threads = _decoded_on(monkeypatch)
    value = audio.LoopMixer()
    assert value.set_track(0, source="launcher_deck_8")
    path = str(wav(tmp_path / "new.wav"))
    audio.set_keydeck_sounds("launcher_deck_8", [path])
    assert _until(lambda: value._cached(path) is not None)
    assert threading.current_thread() not in threads


def test_audio_thread_never_decodes_and_plays_the_hit_once_ready(tmp_path, monkeypatch):
    gate = threading.Event()
    threads = _decoded_on(monkeypatch, gate)
    path = wav(tmp_path / "pad.wav")
    value = audio.LoopMixer()
    assert value.set_track(0, source="launcher_deck_7") and value.set_master_volume(100)
    value._state.play()
    assert value._claim()
    try:
        assert audio.route_keydeck_sound("launcher_deck_7", path, 1)
        # This test thread plays the audio thread: it must not decode the WAV itself.
        assert not any(pcm_samples(value._process_block(frames=1)))
        assert _until(lambda: bool(threads))
        assert threading.current_thread() not in threads
        gate.set()
        assert _until(lambda: value._cached(str(path)) is not None)
        assert any(pcm_samples(value._process_block(frames=1)))
        assert value.snapshot()["dropped_hits"] == 0
    finally:
        gate.set()


def test_deck_reports_its_sounds_to_the_mixer_it_plays_through(deck_canvas, monkeypatch, tmp_path):
    canvas, _bank, _app = deck_canvas
    reported = Mock()
    monkeypatch.setitem(
        sys.modules,
        "calendar_app.infrastructure.runtime.loop_mixer_audio",
        SimpleNamespace(
            route_keydeck_sound=Mock(return_value=False),
            stop_keydeck_source=Mock(return_value=False),
            set_keydeck_sounds=reported,
        ),
    )
    path = deck_wav(tmp_path / "custom.wav")
    deck = model.build_template_deck("macro_3x3")
    deck.update(sound="custom", sound_path=path)
    canvas.set_deck(deck)
    reported.assert_not_called()  # not connected to any mixer source
    canvas.audio_source_id = "launcher_deck_5"
    canvas.set_runtime_active(True)
    reported.assert_called_with("launcher_deck_5", [path])


# -- 5. System sleep does not fire the output stall deadline -----------------------


def _clock(monkeypatch, steps):
    now = [1000.0]
    steps = iter(steps)

    def monotonic():
        now[0] += next(steps, 0.05)
        return now[0]

    monkeypatch.setattr(audio.time, "monotonic", monotonic)


def _filled_backend(event):
    api = QueuedWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api, events=lambda: event)
    backend.open_output()
    for _ in range(3):
        assert backend.write_output(bytes(40))
    return api, backend


def test_stalled_output_still_fails_after_one_second_of_waiting(monkeypatch):
    event = FakeEvent()
    _api, backend = _filled_backend(event)
    _clock(monkeypatch, [])
    with pytest.raises(OSError, match="output_device_stalled"):
        backend.write_output(bytes(40))
    assert 18 <= len(event.waits) <= 22
    backend.close()


def test_waking_from_sleep_re_arms_the_stall_deadline(monkeypatch):
    event = FakeEvent()
    api, backend = _filled_backend(event)
    _clock(monkeypatch, [0.02, 3600.0])  # the PC slept inside one wait
    event.on_wait = lambda: len(event.waits) == 5 and api.complete_one()
    assert backend.write_output(bytes(40))
    # A device that stays silent after waking still fails one waiting second later.
    event.on_wait = None
    _clock(monkeypatch, [0.02, 3600.0])
    with pytest.raises(OSError, match="output_device_stalled"):
        backend.write_output(bytes(40))
    assert len(event.waits) >= 5 + 19
    backend.close()


# -- 6. Shared mixer state changes only under its lock -----------------------------


def test_hit_counters_and_sound_cache_change_only_under_the_mixer_lock(tmp_path, monkeypatch):
    class Checked(audio.LoopMixer):
        def __setattr__(self, name, value):
            if name in ("_dropped_hits", "_cache_bytes") and self.__dict__.get("_checked"):
                assert self._lock._is_owned(), name
            super().__setattr__(name, value)

    value = Checked(threaded=False)

    class GuardedCache(OrderedDict):
        def _owned(self):
            assert value._lock._is_owned()

        def __contains__(self, key):
            self._owned()
            return super().__contains__(key)

        def __getitem__(self, key):
            self._owned()
            return super().__getitem__(key)

        def __setitem__(self, key, item):
            self._owned()
            super().__setitem__(key, item)

        def get(self, key, default=None):
            self._owned()
            return super().get(key, default)

        def move_to_end(self, key, last=True):
            self._owned()
            super().move_to_end(key, last)

        def clear(self):
            self._owned()
            super().clear()

    value._cache = GuardedCache()
    value._checked = True
    assert value.set_track(0, source="launcher_deck_0") and value.play()
    path = wav(tmp_path / "pad.wav")
    monkeypatch.setattr(audio.time, "monotonic", lambda: 0.0)
    assert audio.route_keydeck_sound("launcher_deck_0", path, 1)
    monkeypatch.setattr(audio.time, "monotonic", lambda: 10.0)
    value._process_block(frames=1)  # stale: dropped
    assert audio.route_keydeck_sound("launcher_deck_0", path, 1)
    value._process_block(frames=1)  # decoded into the cache
    assert value.snapshot()["dropped_hits"] == 1
    value.shutdown()
