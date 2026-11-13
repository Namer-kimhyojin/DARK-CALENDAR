# -*- coding: utf-8 -*-
"""A fake queued WinMM capture device proves PCM chronology without hardware."""

from array import array
from collections import deque
import ctypes
import threading

import pytest

from calendar_app.domain import loop_mixer as domain
from calendar_app.infrastructure.runtime import loop_mixer_audio as audio
from tests.test_loop_mixer_audio import FakeWinMM, no_physical_devices  # noqa: F401


class InputRingWinMM(FakeWinMM):
    """Complete buffers in their real submission order, across ring rotations."""

    def __init__(self, channels=1):
        super().__init__()
        self.channels = channels
        self.pending = deque()
        self.completions = []
        self.backend = None
        self.cleanup_buffer_counts = []

    def waveInOpen(self, handle, device, fmt, callback, instance, flags):
        if (
            flags == 1
            and ctypes.cast(fmt, ctypes.POINTER(audio._WaveFormat)).contents.nChannels
            != self.channels
        ):
            return 1
        return super().waveInOpen(handle, device, fmt, callback, instance, flags)

    def waveInAddBuffer(self, handle, header, size):
        result = super().waveInAddBuffer(handle, header, size)
        if not result:
            self.pending.append(
                ctypes.addressof(ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents)
            )
        return result

    def waveInStart(self, _handle):
        return self._call("in_start")  # Completion happens only through complete().

    def complete(self, values):
        for value in values:
            address = self.pending.popleft()
            header = ctypes.cast(address, ctypes.POINTER(audio._WaveHeader)).contents
            frame = (value,) if self.channels == 1 else (value, -value)
            raw = domain.pcm_bytes(array("h", frame) * domain.BLOCK_FRAMES)
            assert len(raw) == header.dwBufferLength
            ctypes.memmove(header.lpData, raw, len(raw))
            header.dwBytesRecorded = len(raw)
            header.dwFlags |= audio._WHDR_DONE
            self.completions.append((address, value))

    def waveInReset(self, handle):
        self.pending.clear()
        return super().waveInReset(handle)

    def waveInUnprepareHeader(self, handle, header, size):
        if self.backend is not None:
            self.cleanup_buffer_counts.append(len(self.backend.inputs))
            assert any(
                ctypes.addressof(item)
                == ctypes.addressof(ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents)
                for item, _buffer in self.backend.inputs
            )
        return super().waveInUnprepareHeader(handle, header, size)

    def waveInClose(self, handle):
        if self.backend is not None:
            self.cleanup_buffer_counts.append(len(self.backend.inputs))
        return super().waveInClose(handle)


def _expected(values, channels):
    return b"".join(
        domain.pcm_bytes(
            array("h", [value, value if channels == 1 else -value]) * domain.BLOCK_FRAMES
        )
        for value in values
    )


@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize("initial_completed", [1, 2, 3])
def test_rotated_completed_ring_preserves_submission_order_for_mono_and_stereo(
    channels, initial_completed
):
    api = InputRingWinMM(channels)
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    backend.open_input("default")
    try:
        initial = list(range(100, 100 + initial_completed))
        api.complete(initial)
        assert backend.read_input(domain.BLOCK_FRAMES * len(initial)) == _expected(
            initial, channels
        )
        # After partial recycling the device FIFO is rotated, e.g. [2,3,0,1].
        backlog = [300, 400, 500, 600]
        api.complete(backlog)
        assert backend.read_input(domain.BLOCK_FRAMES * 4) == _expected(backlog, channels)
        assert backend.dropped_input_frames == 0
    finally:
        backend.close()


def test_rotated_input_pcm_remains_exact_through_record_project_save_and_restore(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: domain.BLOCK_FRAMES * 6)
    api = InputRingWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    backend.open_input("default")
    mixer, restored = audio.LoopMixer(threaded=False), audio.LoopMixer(threaded=False)
    try:
        api.complete([100, 200])
        captured = backend.read_input(domain.BLOCK_FRAMES * 2)
        api.complete([300, 400, 500, 600])
        captured += backend.read_input(domain.BLOCK_FRAMES * 4)
        expected = _expected([100, 200, 300, 400, 500, 600], 1)
        assert captured == expected
        assert mixer.set_track(0, source="mic", armed=True)
        assert mixer.record()
        for offset in range(0, len(captured), domain.BLOCK_FRAMES * 4):
            mixer._process_block(captured[offset : offset + domain.BLOCK_FRAMES * 4])
        assert mixer.snapshot()["mode"] == "playing"
        assert domain.pcm_bytes(mixer._state.tracks[0].audio) == expected
        mixer.stop()
        project = tmp_path / "ordered.airloop"
        assert mixer.save_project(project) and mixer.snapshot()["operation_success"]
        assert restored.load_project(project) and restored.snapshot()["operation_success"]
        assert domain.pcm_bytes(restored._state.tracks[0].audio) == expected
        assert restored.snapshot()["mode"] == "idle"
    finally:
        mixer.shutdown()
        restored.shutdown()
        backend.close()


def test_close_preserves_owned_headers_until_reset_unprepare_close_and_reopen_starts_fresh():
    api = InputRingWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    api.backend = backend
    backend.open_input("default")
    api.complete([100, 200, 300])
    assert backend.read_input(domain.BLOCK_FRAMES * 3) == _expected([100, 200, 300], 1)
    backend.close_input()
    assert api.cleanup_buffer_counts == [4, 4, 4, 4, 4]
    assert api.calls[-6:] == [
        "in_reset",
        "in_unprepare",
        "in_unprepare",
        "in_unprepare",
        "in_unprepare",
        "in_close",
    ]
    assert backend.inputs == [] and backend.fifo == b"" and not backend.input.value
    backend.open_input("default")
    try:
        api.complete([900, 1000, 1100, 1200])
        assert backend.read_input(domain.BLOCK_FRAMES * 4) == _expected([900, 1000, 1100, 1200], 1)
    finally:
        backend.close()


def test_requeue_error_does_not_release_prepared_input_buffers_before_native_cleanup():
    api = InputRingWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    api.backend = backend
    backend.open_input("default")
    api.complete([123])
    api.fail = "in_add"
    try:
        with pytest.raises(OSError, match="waveInAddBuffer"):
            backend.read_input(domain.BLOCK_FRAMES)
        assert len(backend.inputs) == 4
    finally:
        api.fail = ""
        backend.close()
    assert api.cleanup_buffer_counts == [4, 4, 4, 4, 4]
    assert not backend.inputs


def test_cleanup_error_retains_driver_owned_input_memory_instead_of_freeing_it():
    api = InputRingWinMM()
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    api.backend = backend
    backend.open_input("default")
    api.complete([456])
    api.fail = "in_unprepare"
    try:
        with pytest.raises(OSError, match="waveInUnprepareHeader"):
            backend.close()
        assert backend in audio._RETAINED and len(backend.inputs) == 4
        assert audio._DRIVER_UNSAFE.is_set()
        assert ctypes.string_at(backend.inputs[0][0].lpData, 2) == domain.pcm_bytes(
            array("h", [456])
        )
    finally:
        api.fail = ""
        backend.close()


def test_no_input_devices_reports_missing_microphone_before_querying_a_format():
    api = InputRingWinMM()
    api.labels = []
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    with pytest.raises(OSError, match="microphone_device_missing"):
        backend.open_input("default")
    assert api.calls == [] and not backend.input.value and not backend.inputs
    backend.close()


def test_present_device_with_unsupported_pcm_keeps_the_distinct_format_error():
    api = InputRingWinMM()
    api.channels = 0
    backend = audio.WinMMLoopBackend(threading.Event(), api=api)
    with pytest.raises(OSError, match="microphone_format_unavailable"):
        backend.open_input("default")
    assert not backend.input.value and not backend.inputs
    backend.close()
