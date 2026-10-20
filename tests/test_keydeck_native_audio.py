# -*- coding: utf-8 -*-
"""Native WAV playback: real PCM, independent gain and driver buffer lifetime."""

import ctypes
import queue
import struct
import threading
import wave

import pytest

from calendar_app.infrastructure.runtime import keydeck_audio as audio


def _wav(path, samples=(12000, -12000, 0, 3000), *, width=2, channels=1, rate=44100):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        if width == 1:
            frames = bytes(samples)
        else:
            frames = b"".join(value.to_bytes(width, "little", signed=True) for value in samples)
        output.writeframes(frames)
    return str(path)


class FakeWinMM:
    def __init__(self):
        self.next_handle = 1
        self.headers = {}
        self.calls = []
        self.written = []
        self.open_error = self.prepare_error = self.write_error = self.unprepare_error = 0

    def waveOutOpen(self, handle, device, fmt, callback, instance, flags):
        self.calls.append("open")
        if self.open_error:
            return self.open_error
        ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = self.next_handle
        self.next_handle += 1
        assert device == 0xFFFFFFFF and callback == instance == flags == 0
        return 0

    def waveOutPrepareHeader(self, handle, header, size):
        self.calls.append("prepare")
        if self.prepare_error:
            return self.prepare_error
        value = ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents
        value.dwFlags |= 2
        self.headers[handle.value] = value
        assert size == ctypes.sizeof(audio._WaveHeader)
        return 0

    def waveOutWrite(self, handle, header, size):
        self.calls.append("write")
        if self.write_error:
            return self.write_error
        value = ctypes.cast(header, ctypes.POINTER(audio._WaveHeader)).contents
        value.dwFlags &= ~audio._WHDR_DONE
        self.written.append(ctypes.string_at(value.lpData, value.dwBufferLength))
        return 0

    def waveOutUnprepareHeader(self, handle, header, size):
        self.calls.append("unprepare")
        if self.unprepare_error:
            return self.unprepare_error
        self.headers.pop(handle.value, None)
        return 0

    def waveOutReset(self, handle):
        self.calls.append("reset")
        if handle.value in self.headers:
            self.headers[handle.value].dwFlags |= audio._WHDR_DONE
        return 0

    def waveOutClose(self, handle):
        self.calls.append("close")
        assert handle.value not in self.headers
        return 0


@pytest.fixture
def player(monkeypatch):
    api = FakeWinMM()
    monkeypatch.setattr(audio, "_WinMM", lambda: api)
    value = audio._Player()
    yield value, api
    api.unprepare_error = 0
    value.close()


def test_native_abi_uses_fixed_width_windows_fields():
    assert ctypes.sizeof(audio._WaveFormat) == 18
    assert ctypes.sizeof(audio._WaveHeader) == (48 if ctypes.sizeof(ctypes.c_void_p) == 8 else 32)


@pytest.mark.parametrize(
    "width,samples,expected",
    [
        (1, [0, 128, 255], [64, 128, 192]),
        (2, [-32768, 0, 32766], [-16384, 0, 16383]),
        (3, [-8388608, 0, 8388606], [-4194304, 0, 4194303]),
        (4, [-2147483648, 0, 2147483646], [-1073741824, 0, 1073741823]),
    ],
)
def test_gain_handles_unsigned_8_bit_and_signed_wider_pcm(width, samples, expected):
    if width == 1:
        assert list(audio._apply_gain(bytes(samples), width, 0.5)) == expected
    else:
        frames = b"".join(value.to_bytes(width, "little", signed=True) for value in samples)
        actual = audio._apply_gain(frames, width, 0.5)
        assert [
            int.from_bytes(actual[index : index + width], "little", signed=True)
            for index in range(0, len(actual), width)
        ] == expected


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_custom_stereo_integer_pcm_is_preserved(tmp_path, width):
    samples = (128, 200, 100, 128) if width == 1 else (1200, -3000, 100, -100)
    path = _wav(tmp_path / "custom.wav", samples, width=width, channels=2, rate=48000)
    pcm = audio._load_wave(path)
    assert (pcm.channels, pcm.width, pcm.rate) == (2, width, 48000)
    assert len(pcm.frames) == width * len(samples)


def test_corrupt_and_truncated_wav_are_rejected(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"this is not WAV audio")
    with pytest.raises(wave.Error):
        audio._load_wave(str(bad))
    valid = tmp_path / "cut.wav"
    _wav(valid)
    valid.write_bytes(valid.read_bytes()[:-2])
    with pytest.raises(ValueError, match="truncated"):
        audio._load_wave(str(valid))


def test_preload_reads_assets_without_opening_audio_device(player, tmp_path):
    instance, api = player
    path = _wav(tmp_path / "click.wav")
    instance.preload([path], voices=2)
    assert path in instance.assets
    assert api.calls == []


def test_overlapping_voices_keep_samples_alive_and_gain_is_per_play(player, tmp_path):
    instance, api = player
    path = _wav(tmp_path / "click.wav")
    instance.play(path, 0.5)
    instance.play(path, 1.0)
    assert len(instance.voices) == 2
    assert all(voice.busy and voice.buffer is not None for voice in instance.voices)
    assert struct.unpack("<4h", api.written[0]) == (6000, -6000, 0, 1500)
    assert struct.unpack("<4h", api.written[1]) == (12000, -12000, 0, 3000)
    instance.reap()
    assert all(voice.busy for voice in instance.voices)
    first = instance.voices[0]
    first.header.dwFlags |= audio._WHDR_DONE
    instance.reap()
    assert first.buffer is None and first.header is None
    assert instance.voices[1].busy
    instance.play(path, 0.25)
    assert len(instance.voices) == 2
    assert api.calls.count("open") == 2


def test_reusing_busy_voice_resets_before_replacing_its_buffer(player, tmp_path):
    instance, api = player
    path = _wav(tmp_path / "click.wav")
    instance.play(path, 1.0, voices=1)
    first_buffer = instance.voices[0].buffer
    instance.play(path, 0.5, voices=1)
    assert len(instance.voices) == 1
    assert instance.voices[0].buffer is not first_buffer
    assert api.calls == ["open", "prepare", "write", "reset", "unprepare", "prepare", "write"]


def test_shutdown_resets_then_unprepares_then_closes(player, tmp_path):
    instance, api = player
    instance.play(_wav(tmp_path / "click.wav"), 1.0)
    instance.close()
    assert api.calls[-3:] == ["reset", "unprepare", "close"]
    assert instance.voices == [] and not instance.assets
    instance.close()


def test_driver_unprepare_failure_retains_live_buffer_until_retry(player, tmp_path):
    instance, api = player
    instance.play(_wav(tmp_path / "click.wav"), 1.0)
    voice = instance.voices[0]
    original = voice.buffer
    voice.header.dwFlags |= audio._WHDR_DONE
    api.unprepare_error = 33
    with pytest.raises(OSError, match="WinMM 33"):
        instance.reap()
    assert voice.buffer is original and voice.prepared
    api.unprepare_error = 0
    instance.reap()
    assert voice.buffer is None and not voice.prepared


@pytest.mark.parametrize("operation", ["prepare_error", "write_error"])
def test_playback_failure_releases_owned_buffer_and_can_retry(player, tmp_path, operation):
    instance, api = player
    path = _wav(tmp_path / "click.wav")
    setattr(api, operation, 5)
    with pytest.raises(OSError, match="WinMM 5"):
        instance.play(path, 0.5)
    assert instance.voices[0].buffer is None
    setattr(api, operation, 0)
    instance.play(path, 0.5)
    assert instance.voices[0].busy


def test_missing_audio_device_raises_without_creating_voice(player, tmp_path):
    instance, api = player
    api.open_error = 2
    with pytest.raises(OSError, match="waveOutOpen"):
        instance.play(_wav(tmp_path / "click.wav"), 0.5)
    assert instance.voices == []


def test_native_bank_never_waits_for_file_or_driver_on_caller(monkeypatch):
    entered, release, cleaned = threading.Event(), threading.Event(), threading.Event()

    class BlockingPlayer:
        voices = []

        def play(self, *args):
            entered.set()
            assert release.wait(timeout=3)

        def close(self):
            cleaned.set()

    monkeypatch.setattr(audio, "_Player", BlockingPlayer)
    bank = audio.NativeSoundBank()
    assert bank._thread is None
    try:
        assert bank.play("unopened.wav", 0.5)
        assert entered.wait(timeout=2)
        bank.close()
        assert not cleaned.is_set()
        assert not bank.play("after-close.wav", 1.0)
    finally:
        release.set()
        bank._shutdown()
    assert cleaned.is_set()


def test_idle_worker_waits_without_polling_and_close_sentinel_wakes_it(monkeypatch):
    loaded, waiting, cleaned = threading.Event(), threading.Event(), threading.Event()

    class IdlePlayer:
        voices = []

        def preload(self, *args):
            loaded.set()

        def close(self):
            cleaned.set()

    class RecordingQueue(queue.Queue):
        def get(self, block=True, timeout=None):
            if loaded.is_set():
                assert timeout is None
                waiting.set()
            return super().get(block=block, timeout=timeout)

    monkeypatch.setattr(audio, "_Player", IdlePlayer)
    bank = audio.NativeSoundBank()
    bank._queue = RecordingQueue(maxsize=64)
    try:
        bank.preload(["sound.wav"])
        assert waiting.wait(timeout=2)
        assert not cleaned.is_set()
    finally:
        bank._shutdown()
    assert cleaned.is_set() and not bank._thread.is_alive()


def test_repeated_gain_is_cached_and_random_gains_stay_bounded(player, tmp_path, monkeypatch):
    instance, api = player
    path = _wav(tmp_path / "click.wav")
    pcm = instance._asset(path)
    first = instance._samples(path, pcm, 0.5)
    assert instance._samples(path, pcm, 0.5) is first
    monkeypatch.setattr(audio, "_MAX_GAIN_CACHE_BYTES", len(first) * 3)
    for value in range(1, 100):
        instance._samples(path, pcm, value / 100)
    assert instance.gain_cache_bytes <= len(first) * 3
    assert len(instance.gains) <= 3


def test_large_16_bit_fast_path_matches_sample_gain():
    frames = struct.pack("<4h", -32768, 32766, -7, 9) * (128 * 1024 // 8)
    samples = audio._apply_gain(frames, 2, 0.5)
    assert samples == struct.pack("<4h", -16384, 16383, -4, 4) * (128 * 1024 // 8)


def test_repeated_refresh_preloads_are_deduplicated_and_leave_room_for_play(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    class LoadingPlayer:
        voices = []

        def preload(self, *args):
            entered.set()
            assert release.wait(timeout=3)

        def close(self):
            pass

    monkeypatch.setattr(audio, "_Player", LoadingPlayer)
    bank = audio.NativeSoundBank()
    paths = [f"switch-{index}.wav" for index in range(28)]
    try:
        bank.preload(paths)
        assert entered.wait(timeout=2)
        for _ in range(100):
            bank.preload(paths)
        assert len(bank._pending_preloads) == len(paths)
        assert bank._queue.qsize() == len(paths) - 1
        assert bank.play("click.wav", 0.6)
    finally:
        bank.close()
        release.set()
        bank._shutdown()


def test_silent_or_invalid_gain_does_not_start_native_worker():
    bank = audio.NativeSoundBank()
    for volume in (0, -1, float("nan"), float("inf"), None, "invalid"):
        assert not bank.play("click.wav", volume)
    assert not bank.play("", 1.0)
    assert bank._thread is None
    bank.close()


def test_stop_all_releases_native_buffers_and_keeps_cache(player, tmp_path):
    instance, api = player
    path = _wav(tmp_path / "pad.wav")
    instance.play(path, 0.6)
    instance.play(path, 0.5)
    instance.stop_all()
    assert all(not voice.busy for voice in instance.voices)
    assert not api.headers
    assert len(instance.voices) == 2 and path in instance.assets
    instance.play(path, 0.6)
    assert len(instance.voices) == 2
    assert instance.voices[0].busy


def test_stop_all_discards_pending_hits_before_next_performance(monkeypatch):
    entered, release, silenced = threading.Event(), threading.Event(), threading.Event()
    fresh_played = threading.Event()
    played = []

    class SlowPlayer:
        voices = []

        def play(self, path, *args):
            played.append(path)
            entered.set()
            assert release.wait(timeout=3)
            if path == "fresh.wav":
                fresh_played.set()

        def stop_all(self):
            silenced.set()

        def close(self):
            pass

    monkeypatch.setattr(audio, "_Player", SlowPlayer)
    bank = audio.NativeSoundBank()
    bank.stop_all()
    assert bank._thread is None
    try:
        bank.play("first.wav", 0.5)
        assert entered.wait(timeout=2)
        for _ in range(64):
            bank.play("stale.wav", 0.5)
        bank.stop_all()
        release.set()
        assert silenced.wait(timeout=2)
        assert played == ["first.wav"]
        bank.play("fresh.wav", 0.5)
        assert fresh_played.wait(timeout=2)
        assert played == ["first.wav", "fresh.wav"]
    finally:
        release.set()
        bank._shutdown()
