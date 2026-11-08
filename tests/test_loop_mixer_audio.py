# -*- coding: utf-8 -*-
"""Fake WinMM and disposable projects only; physical capture is forbidden."""

from array import array
import ctypes
import hashlib
import json
from pathlib import Path
import threading
import time
import wave

from PyQt6 import sip
import pytest

from calendar_app.domain.loop_mixer import BLOCK_FRAMES, SAMPLE_RATE, pcm_bytes, pcm_samples
from calendar_app.infrastructure.runtime import loop_mixer_audio as audio


def wav(path, value=1000, frames=32, *, rate=SAMPLE_RATE):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm_bytes(array("h", [value, value]) * frames))
    return path


@pytest.fixture(autouse=True)
def no_physical_devices(monkeypatch):
    def forbidden():
        raise AssertionError("Physical WinMM access is forbidden in isolated tests")

    monkeypatch.setattr(audio, "_winmm", forbidden)
    yield
    for mixer in list(audio._MIXERS):
        mixer.shutdown()
    audio._DRIVER_UNSAFE.clear()
    audio._RETAINED.clear()


@pytest.fixture
def mixer():
    value = audio.LoopMixer(threaded=False)
    yield value
    value.shutdown()


class FakeWinMM:
    def __init__(self):
        self.calls = []
        self.inputs = []
        self.outputs = []
        self.fail = ""
        self.labels = ["Input A", "Input B"]

    def _call(self, name):
        self.calls.append(name)
        return 1 if self.fail == name else 0

    def waveOutOpen(self, handle, _device, _fmt, _callback, _instance, _flags):
        result = self._call("out_open")
        if not result:
            ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = 1
        return result

    def waveOutPrepareHeader(self, _handle, header, _size):
        result = self._call("out_prepare")
        if not result:
            self.outputs.append(ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents)
        return result

    def waveOutWrite(self, _handle, header, _size):
        result = self._call("out_write")
        if not result:
            ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents.dwFlags |= 1
        return result

    def waveOutUnprepareHeader(self, _handle, _header, _size):
        return self._call("out_unprepare")

    def waveOutReset(self, _handle):
        for header in self.outputs:
            header.dwFlags |= 1
        return self._call("out_reset")

    def waveOutClose(self, _handle):
        return self._call("out_close")

    def waveInOpen(self, handle, _device, _fmt, _callback, _instance, flags):
        result = self._call("in_query" if flags == 1 else "in_open")
        if not flags and not result:
            ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = 2
        return result

    def waveInPrepareHeader(self, _handle, header, _size):
        result = self._call("in_prepare")
        if not result:
            self.inputs.append(ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents)
        return result

    def waveInAddBuffer(self, _handle, header, _size):
        ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents.dwFlags &= ~1
        return self._call("in_add")

    def waveInStart(self, _handle):
        for header in self.inputs:
            data = array("h", [1234]) * (header.dwBufferLength // 2)
            ctypes.memmove(header.lpData, data.tobytes(), len(data) * 2)
            header.dwBytesRecorded = header.dwBufferLength
            header.dwFlags |= 1
        return self._call("in_start")

    def waveInReset(self, _handle):
        for header in self.inputs:
            header.dwFlags |= 1
        return self._call("in_reset")

    def waveInUnprepareHeader(self, _handle, _header, _size):
        return self._call("in_unprepare")

    def waveInClose(self, _handle):
        return self._call("in_close")

    def waveInGetNumDevs(self):
        return len(self.labels)

    def waveInGetDevCapsW(self, index, pointer, _size):
        caps = ctypes.cast(pointer, ctypes.POINTER(audio._InputCaps)).contents
        caps.manufacturer, caps.product, caps.name = 1, 2, self.labels[index]
        return 0


def test_construct_snapshot_clone_never_open_devices(mixer):
    snapshot = mixer.snapshot()
    assert snapshot["mode"] == "idle" and len(snapshot["tracks"]) == 6
    assert set(snapshot) >= {
        "bpm",
        "bars",
        "master_volume",
        "operation_id",
        "completed_operation_id",
        "operation_success",
        "error",
        "error_code",
    }
    assert all(
        set(track)
        >= {"name", "source", "armed", "muted", "solo", "volume", "pan", "has_audio", "peaks"}
        for track in snapshot["tracks"]
    )
    other = audio.LoopMixer(threaded=False)
    assert other.clone_from(mixer)
    assert other.snapshot()["mode"] == "idle"


def test_native_stream_has_one_output_handle_and_bounded_prepared_blocks():
    api = FakeWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    backend.open_output()
    for _ in range(10):
        assert backend.write_output(bytes(BLOCK_FRAMES * 4))
        assert len(backend.outputs) <= 3
    assert api.calls.count("out_open") == 1 and "in_open" not in api.calls
    backend.close()
    assert api.calls[-3:] == ["out_reset", "out_unprepare", "out_close"]


def test_input_query_open_prepare_start_read_reset_unprepare_close_are_ordered():
    api = FakeWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    assert not api.calls
    backend.open_output()
    backend.open_input("default")
    assert api.calls.count("in_open") == 1 and len(backend.inputs) == 4
    result = pcm_samples(backend.read_input(10))
    assert len(result) == 20 and set(result) == {1234}
    assert len(backend.fifo) <= BLOCK_FRAMES * 4 * 8
    backend.close()
    assert (
        api.calls.index("in_reset")
        < api.calls.index("in_unprepare")
        < api.calls.index("in_close")
        < api.calls.index("out_reset")
    )


@pytest.mark.parametrize(
    "failure",
    ["out_open", "out_prepare", "out_write", "in_open", "in_prepare", "in_add", "in_start"],
)
def test_device_partial_failures_cleanup_without_losing_owned_headers(failure):
    api = FakeWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    api.fail = failure
    with pytest.raises(OSError):
        backend.open_output()
        if failure.startswith("out_"):
            backend.write_output(bytes(40))
        else:
            backend.open_input("default")
    api.fail = ""
    backend.close()
    assert not backend.outputs and not backend.inputs


def test_driver_cleanup_failure_retains_buffers_and_blocks_unbounded_retries():
    api = FakeWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    backend.open_output()
    backend.write_output(bytes(40))
    api.fail = "out_unprepare"
    with pytest.raises(OSError):
        backend.close()
    assert [backend] == audio._RETAINED and backend.outputs[0][1] is not None
    with pytest.raises(OSError, match="restart_required"):
        audio.WinMMLoopBackend(threading.Event(), api=api)
    api.fail = ""
    backend.close()


def test_output_stall_has_a_deadline_instead_of_extending_capture_forever(monkeypatch):
    api = FakeWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    backend.open_output()

    def queued(_handle, pointer, _size):
        ctypes.cast(pointer, ctypes.POINTER(audio._WaveHeader)).contents.dwFlags &= ~1
        return 0

    api.waveOutWrite = queued
    for _ in range(3):
        assert backend.write_output(bytes(40))
    times = iter([0, 2])
    monkeypatch.setattr(audio.time, "monotonic", lambda: next(times))
    with pytest.raises(OSError, match="output_device_stalled"):
        backend.write_output(bytes(40))
    backend.close()


def test_thread_start_failure_reports_error_and_releases_lease(tmp_path, monkeypatch):
    class FailedThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("cannot_start_thread")

        def is_alive(self):
            return False

        def join(self, **_kwargs):
            pass

    monkeypatch.setattr(audio.threading, "Thread", FailedThread)
    value = audio.LoopMixer()
    assert not value.play() and value.snapshot()["mode"] == "idle"
    assert audio._active() is None
    assert not value.save_project(tmp_path / "save.json")
    snapshot = value.snapshot()
    assert not snapshot["busy"] and not snapshot["operation_success"]
    assert snapshot["completed_operation_id"] == snapshot["operation_id"] == 1


def test_microphone_ids_survive_device_enumeration_reordering():
    api = FakeWinMM()
    first = {label: identity for identity, label, _index in audio._devices(api)}
    api.labels.reverse()
    second = {label: identity for identity, label, _index in audio._devices(api)}
    assert first == second and len(first) == 2
    assert not any(call.startswith("in_open") for call in api.calls)


def test_transport_lease_and_muted_source_interception_are_explicit(mixer, tmp_path):
    path = wav(tmp_path / "pad.wav")
    assert mixer.set_track(0, source="launcher_deck_0", muted=True)
    assert not audio.route_keydeck_sound("launcher_deck_0", path, 1)
    assert mixer.play()
    other = audio.LoopMixer(threaded=False)
    assert not other.play() and other.snapshot()["error_code"] == "another_mixer_is_playing"
    assert audio.route_keydeck_sound("launcher_deck_0", path, 1)
    assert not audio.route_keydeck_sound("launcher_deck_1", path, 1)
    assert not any(mixer._process_block(frames=8))
    mixer.stop()
    assert other.play()


def test_source_stop_removes_only_that_live_source_and_keeps_transport_and_clip(mixer, tmp_path):
    path = wav(tmp_path / "pad.wav")
    mixer._state.load_audio(2, array("h", [500, 500]) * 32)
    mixer.set_track(0, source="launcher_deck_0")
    mixer.set_track(1, source="launcher_deck_1")
    mixer.set_master_volume(100)
    mixer.play()
    assert audio.route_keydeck_sound("launcher_deck_0", path, 1)
    assert audio.route_keydeck_sound("launcher_deck_1", path, 1)
    assert audio.stop_keydeck_source("launcher_deck_0")
    assert not audio.stop_keydeck_source("launcher_deck_9")
    assert list(pcm_samples(mixer._process_block(frames=1))) == [1500, 1500]
    assert mixer.snapshot()["mode"] == "playing" and mixer.snapshot()["tracks"][2]["has_audio"]


def test_stale_live_hits_are_discarded_after_suspend_instead_of_burst_replayed(
    mixer, tmp_path, monkeypatch
):
    mixer.set_track(0, source="launcher_deck_0")
    mixer.play()
    monkeypatch.setattr(audio.time, "monotonic", lambda: 0)
    audio.route_keydeck_sound("launcher_deck_0", wav(tmp_path / "pad.wav"), 1)
    monkeypatch.setattr(audio.time, "monotonic", lambda: 1000000)
    assert not any(mixer._process_block(frames=1))
    assert mixer.snapshot()["dropped_hits"] == 1


def test_pending_source_stop_also_cancels_an_inflight_asset_load(mixer, tmp_path, monkeypatch):
    mixer.set_track(0, source="launcher_deck_0")
    mixer.play()
    audio.route_keydeck_sound("launcher_deck_0", wav(tmp_path / "pad.wav"), 1)
    original = mixer._asset

    def load(path):
        assert audio.stop_keydeck_source("launcher_deck_0")
        return original(path)

    monkeypatch.setattr(mixer, "_asset", load)
    assert not any(mixer._process_block(frames=1))


def test_threaded_play_never_opens_mic_and_record_while_playing_uses_same_worker():
    entered = threading.Event()
    captured = threading.Event()
    instances = []

    class FakeBackend:
        def __init__(self, stop):
            self.stop = stop
            self.open_inputs = 0
            instances.append(self)

        def open_output(self):
            entered.set()

        def open_input(self, _device):
            self.open_inputs += 1
            captured.set()

        def close_input(self):
            pass

        def read_input(self, frames):
            return bytes(frames * 4)

        def write_output(self, _data):
            self.stop.wait(0.005)
            return not self.stop.is_set()

        def close(self):
            pass

    value = audio.LoopMixer(backend_factory=FakeBackend)
    value.set_track(0, source="mic", armed=True)
    assert value.play() and entered.wait(1)
    assert instances[0].open_inputs == 0
    assert value.record() and captured.wait(1)
    assert len(instances) == 1
    value.shutdown()
    assert not value._thread.is_alive()


def test_auto_commit_closes_input_before_output_can_wait_or_stall(monkeypatch):
    from calendar_app.domain import loop_mixer

    monkeypatch.setattr(loop_mixer, "loop_length", lambda _bpm, _bars: 16)
    order = []

    class FakeBackend:
        def __init__(self, stop):
            self.stop = stop

        def open_output(self):
            order.append("output_open")

        def open_input(self, _device):
            order.append("input_open")

        def read_input(self, frames):
            order.append("input_read")
            return pcm_bytes(array("h", [123, 123]) * frames)

        def close_input(self):
            order.append("input_close")

        def write_output(self, _data):
            assert order[-1] == "input_close"
            assert value.snapshot()["mode"] == "playing"
            order.append("write_output")
            self.stop.set()
            return False

        def close(self):
            order.append("close")

    value = audio.LoopMixer(backend_factory=FakeBackend, threaded=False)
    value.set_track(0, source="mic", armed=True)
    assert value.record()
    value._run()
    assert order == [
        "output_open",
        "input_open",
        "input_read",
        "input_close",
        "write_output",
        "close",
    ]


def test_fifo_overrun_and_command_queue_are_bounded_without_fallback_leak(mixer, tmp_path):
    api = FakeWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    backend.open_input("default")
    for _ in range(8):
        api.waveInStart(backend.input)
        backend.read_input(1)
    assert backend.dropped_input_frames > 0
    assert len(backend.fifo) <= BLOCK_FRAMES * 4 * 8
    backend.close()
    mixer.set_track(0, source="launcher_deck_0", muted=True)
    mixer.play()
    path = wav(tmp_path / "tap.wav")
    for _ in range(100):
        assert audio.route_keydeck_sound("launcher_deck_0", path, 1)
    assert mixer._commands.qsize() == 64 and mixer.snapshot()["dropped_hits"] == 36


def test_file_jobs_have_ids_and_project_roundtrip_is_device_free(mixer, tmp_path):
    source = wav(tmp_path / "source.wav", value=3000)
    assert mixer.load_wav(0, source)
    first = mixer.snapshot()
    assert first["operation_id"] == first["completed_operation_id"] == 1
    assert first["operation_success"] and first["tracks"][0]["source"] == "file"
    assert mixer.configure(240, 1)
    assert mixer.set_track(0, name="My take", muted=True, solo=True, volume=63, pan=-32)
    project = tmp_path / "set.airloop.json"
    assert mixer.save_project(project)
    assert mixer.snapshot()["operation_success"]
    restored = audio.LoopMixer(threaded=False)
    assert restored.load_project(project) and restored.snapshot()["operation_success"]
    assert restored._state.tracks[0].audio == mixer._state.tracks[0].audio
    assert restored.snapshot()["tracks"] == mixer.snapshot()["tracks"]
    assert restored.snapshot()["mode"] == "idle"
    assert len(list(tmp_path.glob("set.airloop.assets/*.wav"))) == 1


@pytest.mark.parametrize(
    "bad_reference",
    [
        "../outside.wav",
        "C:/private.wav",
        "/private.wav",
        "set.assets/../outside.wav",
        "set.assets/wrong.wav",
    ],
)
def test_project_path_escape_rejects_without_replacing_current_audio(
    mixer, tmp_path, bad_reference
):
    mixer.load_wav(0, wav(tmp_path / "source.wav"))
    project = tmp_path / "set.json"
    mixer.save_project(project)
    original = array("h", mixer._state.tracks[0].audio)
    document = json.loads(project.read_text(encoding="utf-8", errors="strict"))
    document["tracks"][0]["audio"] = bad_reference
    project.write_text(json.dumps(document), encoding="utf-8", errors="strict")
    assert mixer.load_project(project)
    assert not mixer.snapshot()["operation_success"]
    assert mixer._state.tracks[0].audio == original


def test_corrupt_asset_hash_and_future_project_preserve_current_state(mixer, tmp_path):
    mixer.load_wav(0, wav(tmp_path / "source.wav"))
    project = tmp_path / "set.json"
    mixer.save_project(project)
    original = mixer._copy_project().snapshot()
    document = json.loads(project.read_text(encoding="utf-8", errors="strict"))
    asset = tmp_path / document["tracks"][0]["audio"]
    wav(asset, value=999)
    mixer.load_project(project)
    assert not mixer.snapshot()["operation_success"] and mixer._state.snapshot() == original
    document["version"] = 99
    project.write_text(json.dumps(document), encoding="utf-8", errors="strict")
    mixer.load_project(project)
    assert not mixer.snapshot()["operation_success"] and mixer._state.snapshot() == original


def test_save_replace_failure_preserves_previous_json_and_cleans_temporary_files(
    mixer, tmp_path, monkeypatch
):
    mixer.load_wav(0, wav(tmp_path / "source.wav"))
    project = tmp_path / "set.json"
    previous = b"previous project bytes"
    project.write_bytes(previous)
    monkeypatch.setattr(audio.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk_full")))
    mixer.save_project(project)
    assert not mixer.snapshot()["operation_success"] and project.read_bytes() == previous
    assert not list(tmp_path.rglob(".loop-*"))


def test_export_is_exact_one_loop_with_mix_controls_and_no_device(mixer, tmp_path):
    mixer.configure(240, 1)
    mixer.load_wav(0, wav(tmp_path / "source.wav", value=1000))
    mixer.set_master_volume(50)
    mixer.set_track(0, pan=-100)
    target = tmp_path / "mix.wav"
    mixer.export_wav(target)
    assert mixer.snapshot()["operation_success"]
    with wave.open(str(target), "rb") as exported:
        assert (
            exported.getframerate(),
            exported.getnchannels(),
            exported.getsampwidth(),
            exported.getnframes(),
        ) == (SAMPLE_RATE, 2, 2, SAMPLE_RATE)
        assert list(pcm_samples(exported.readframes(1))) == [500, 0]
    assert mixer.snapshot()["mode"] == "idle"


def test_clone_copies_committed_audio_without_live_pending_or_mutable_sharing(mixer, tmp_path):
    mixer.load_wav(0, wav(tmp_path / "source.wav"))
    mixer.set_track(0, source="mic", armed=True)
    mixer.record()
    mixer._process_block(pcm_bytes(array("h", [9000, 9000])), frames=1)
    clone = audio.LoopMixer(threaded=False)
    assert clone.clone_from(mixer)
    assert clone.snapshot()["mode"] == "idle" and not clone._state._pending
    assert clone._state.tracks[0].audio[0] == 1000
    clone._state.tracks[0].audio[0] = -100
    assert mixer._state.tracks[0].audio[0] == 1000
    assert clone._microphone_device == "default"


def test_accepted_async_save_completes_after_qobject_destruction(tmp_path, monkeypatch):
    value = audio.LoopMixer(threaded=True)
    value._state.load_audio(0, array("h", [123, 123]) * 16)
    entered, release = threading.Event(), threading.Event()
    original = audio._write_wav

    def slow_write(path, samples):
        entered.set()
        assert release.wait(2)
        original(path, samples)

    monkeypatch.setattr(audio, "_write_wav", slow_write)
    target = tmp_path / "saved.json"
    assert value.save_project(target) and entered.wait(1)
    start = time.monotonic()
    value.shutdown()
    assert time.monotonic() - start < 1
    sip.delete(value)
    release.set()
    value._io_thread.join(timeout=2)
    assert not value._io_thread.is_alive()
    assert target.is_file() and value.snapshot()["operation_success"]
    document = json.loads(target.read_text(encoding="utf-8", errors="strict"))
    data = audio._read_wav(tmp_path / document["tracks"][0]["audio"])
    assert hashlib.sha256(pcm_bytes(data)).hexdigest() == document["tracks"][0]["pcm_sha256"]


def test_io_busy_rejects_overlapping_requests_and_completion_is_correlated(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    value = audio.LoopMixer()
    original = audio._read_wav

    def slow_read(path, **kwargs):
        entered.set()
        assert release.wait(2)
        return original(path, **kwargs)

    monkeypatch.setattr(audio, "_read_wav", slow_read)
    assert value.load_wav(0, wav(tmp_path / "source.wav")) and entered.wait(1)
    accepted = value.snapshot()["operation_id"]
    assert value.snapshot()["busy"] and not value.load_project(tmp_path / "other.json")
    assert value.snapshot()["operation_id"] == accepted
    release.set()
    value._io_thread.join(timeout=2)
    result = value.snapshot()
    assert (
        not result["busy"]
        and result["completed_operation_id"] == accepted
        and result["operation_success"]
    )


def test_wav_duration_and_invalid_track_fail_without_mutation(mixer, tmp_path, monkeypatch):
    path = wav(tmp_path / "source.wav")
    monkeypatch.setattr(audio, "_MAX_WAV_BYTES", 1)
    mixer.load_wav(0, path)
    assert (
        not mixer.snapshot()["operation_success"] and not mixer.snapshot()["tracks"][0]["has_audio"]
    )
    assert not mixer.set_track(99, muted=True)
