# -*- coding: utf-8 -*-
"""Asynchronous PCM WAV feedback using Windows' bundled waveOut API.

The release intentionally excludes Qt Multimedia. Each native voice owns its
header and sample buffer until Windows returns them; gain only changes our PCM
samples and never the device's or another application's volume.
"""

from __future__ import annotations

from array import array
import atexit
from collections import OrderedDict
from contextlib import suppress
import ctypes
from dataclasses import dataclass
import logging
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
import wave

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 25 * 1024 * 1024
_MAX_CACHE_BYTES = 64 * 1024 * 1024
_MAX_GAIN_CACHE_BYTES = 32 * 1024 * 1024
_MAX_NATIVE_VOICES = 32
_WHDR_DONE = 0x00000001
_WAVE_MAPPER = 0xFFFFFFFF
# Failed drivers must not leave Python freeing memory still owned by Windows.
_RETAINED_VOICES: list = []


class _WaveFormat(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("wFormatTag", ctypes.c_uint16),
        ("nChannels", ctypes.c_uint16),
        ("nSamplesPerSec", ctypes.c_uint32),
        ("nAvgBytesPerSec", ctypes.c_uint32),
        ("nBlockAlign", ctypes.c_uint16),
        ("wBitsPerSample", ctypes.c_uint16),
        ("cbSize", ctypes.c_uint16),
    ]


class _WaveHeader(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint32),
        ("dwBytesRecorded", ctypes.c_uint32),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", ctypes.c_uint32),
        ("dwLoops", ctypes.c_uint32),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


@dataclass(frozen=True, slots=True)
class _PcmWave:
    channels: int
    width: int
    rate: int
    frames: bytes

    def format(self) -> _WaveFormat:
        block = self.channels * self.width
        return _WaveFormat(1, self.channels, self.rate, self.rate * block, block, self.width * 8, 0)


def _load_wave(path: str) -> _PcmWave:
    """Bound user-file allocation and accept ordinary mono/stereo integer PCM."""
    with open(path, "rb") as source:
        if os.fstat(source.fileno()).st_size > _MAX_FILE_BYTES:
            raise ValueError("WAV exceeds the 25 MB sound limit")
        with wave.open(source, "rb") as audio:
            channels, width, rate, count = (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
                audio.getnframes(),
            )
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 1 <= rate <= 384000:
                raise ValueError("Sound requires 8/16/24/32-bit mono/stereo PCM WAV")
            expected = count * channels * width
            if audio.getcomptype() != "NONE" or not 0 < expected <= _MAX_FILE_BYTES:
                raise ValueError("Sound requires nonempty uncompressed PCM WAV")
            frames = audio.readframes(count)
            if len(frames) != expected:
                raise ValueError("WAV sample data is truncated")
            return _PcmWave(channels, width, rate, frames)


def _apply_gain(frames: bytes, width: int, gain: float) -> bytes:
    """WAV 8-bit samples are unsigned; wider integer samples are signed LE."""
    gain = min(1.0, max(0.0, gain))
    if gain == 1.0:
        return frames
    if width == 1:
        table = bytes(round((value - 128) * gain) + 128 for value in range(256))
        return frames.translate(table)
    if width in (2, 4):
        values = array("h" if width == 2 else "i")
        values.frombytes(frames)
        if sys.byteorder != "little":
            values.byteswap()
        if width == 2 and len(frames) >= 128 * 1024:
            # A C-level array lookup avoids millions of Python slice/int/bytes
            # operations for a large custom WAV. Tiny clicks skip the LUT cost.
            unsigned = array("H")
            unsigned.frombytes(frames)
            if sys.byteorder != "little":
                unsigned.byteswap()
            table = array(
                "h",
                (
                    round((value if value < 32768 else value - 65536) * gain)
                    for value in range(65536)
                ),
            )
            output = array("h", map(table.__getitem__, unsigned))
        else:
            output = array(values.typecode, (round(value * gain) for value in values))
        if sys.byteorder != "little":
            output.byteswap()
        return output.tobytes()
    output = bytearray(len(frames))
    for offset in range(0, len(frames), width):
        value = int.from_bytes(frames[offset : offset + width], "little", signed=True)
        output[offset : offset + width] = round(value * gain).to_bytes(width, "little", signed=True)
    return bytes(output)


class _WinMM:
    """The DLL and signatures are created only on the playback worker."""

    def __init__(self):
        if os.name != "nt":
            raise OSError("Native KeyDeck sound requires Windows")
        self.dll = ctypes.WinDLL("winmm.dll")
        declarations = {
            "waveOutOpen": [
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_uint32,
                ctypes.POINTER(_WaveFormat),
                ctypes.c_size_t,
                ctypes.c_size_t,
                ctypes.c_uint32,
            ],
            "waveOutPrepareHeader": [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint32],
            "waveOutWrite": [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint32],
            "waveOutUnprepareHeader": [
                ctypes.c_void_p,
                ctypes.POINTER(_WaveHeader),
                ctypes.c_uint32,
            ],
            "waveOutReset": [ctypes.c_void_p],
            "waveOutClose": [ctypes.c_void_p],
        }
        for name, arguments in declarations.items():
            function = getattr(self.dll, name)
            function.argtypes = arguments
            function.restype = ctypes.c_uint32
            setattr(self, name, function)


def _check(code: int, operation: str) -> None:
    if code:
        raise OSError(f"{operation} failed (WinMM {code})")


class _Voice:
    def __init__(self, api, path: str, pcm: _PcmWave):
        self.api, self.path = api, path
        self.format_key = (pcm.channels, pcm.width, pcm.rate)
        self.handle = ctypes.c_void_p()
        self.header: _WaveHeader | None = None
        self.buffer = None
        self.prepared = False
        self.used_at = time.monotonic()
        fmt = pcm.format()
        _check(
            api.waveOutOpen(ctypes.byref(self.handle), _WAVE_MAPPER, ctypes.byref(fmt), 0, 0, 0),
            "waveOutOpen",
        )

    @property
    def busy(self) -> bool:
        return self.header is not None

    def finish(self, *, stop: bool = False) -> bool:
        if self.header is None:
            return True
        if stop:
            _check(self.api.waveOutReset(self.handle), "waveOutReset")
        elif not self.header.dwFlags & _WHDR_DONE:
            return False
        if self.prepared:
            _check(
                self.api.waveOutUnprepareHeader(
                    self.handle, ctypes.byref(self.header), ctypes.sizeof(_WaveHeader)
                ),
                "waveOutUnprepareHeader",
            )
        self.prepared = False
        self.header = None
        self.buffer = None
        return True

    def play(self, pcm: _PcmWave, gain: float, *, samples: bytes | None = None) -> None:
        self.finish(stop=self.busy)
        data = samples if samples is not None else _apply_gain(pcm.frames, pcm.width, gain)
        self.buffer = ctypes.create_string_buffer(data, len(data))
        self.header = _WaveHeader()
        self.header.lpData = ctypes.addressof(self.buffer)
        self.header.dwBufferLength = len(data)
        try:
            _check(
                self.api.waveOutPrepareHeader(
                    self.handle, ctypes.byref(self.header), ctypes.sizeof(_WaveHeader)
                ),
                "waveOutPrepareHeader",
            )
            self.prepared = True
            _check(
                self.api.waveOutWrite(
                    self.handle, ctypes.byref(self.header), ctypes.sizeof(_WaveHeader)
                ),
                "waveOutWrite",
            )
        except OSError:
            self.finish(stop=True)
            raise
        self.used_at = time.monotonic()

    def close(self) -> None:
        self.finish(stop=self.busy)
        if self.handle.value:
            _check(self.api.waveOutClose(self.handle), "waveOutClose")
            self.handle = ctypes.c_void_p()


class _Player:
    """Single-thread-owned WAV cache, bounded voices and native lifetime."""

    def __init__(self):
        self.api = _WinMM()
        self.assets: OrderedDict[str, tuple[tuple[int, int], _PcmWave]] = OrderedDict()
        self.voices: list[_Voice] = []
        self.cache_bytes = 0
        self.gains: OrderedDict[tuple, bytes] = OrderedDict()
        self.gain_cache_bytes = 0

    def preload(self, paths, voices: int | None = None) -> None:
        for path in paths:
            self._asset(path)

    def _asset(self, path: str) -> _PcmWave:
        stamp_info = Path(path).stat()
        stamp = (stamp_info.st_mtime_ns, stamp_info.st_size)
        cached = self.assets.get(path)
        if cached is not None and cached[0] == stamp:
            self.assets.move_to_end(path)
            return cached[1]
        pcm = _load_wave(path)
        if cached is not None:
            self.cache_bytes -= len(cached[1].frames)
        self.assets[path] = (stamp, pcm)
        self.cache_bytes += len(pcm.frames)
        self.assets.move_to_end(path)
        while self.cache_bytes > _MAX_CACHE_BYTES:
            _old_path, (_old_stamp, old_pcm) = self.assets.popitem(last=False)
            self.cache_bytes -= len(old_pcm.frames)
        return pcm

    def _samples(self, path: str, pcm: _PcmWave, volume: float) -> bytes:
        if volume >= 1.0:
            return pcm.frames
        stamp = self.assets[path][0]
        identity = (path, stamp, volume)
        cached = self.gains.get(identity)
        if cached is not None:
            self.gains.move_to_end(identity)
            return cached
        samples = _apply_gain(pcm.frames, pcm.width, volume)
        self.gains[identity] = samples
        self.gain_cache_bytes += len(samples)
        while self.gain_cache_bytes > _MAX_GAIN_CACHE_BYTES or len(self.gains) > 64:
            _identity, oldest = self.gains.popitem(last=False)
            self.gain_cache_bytes -= len(oldest)
        return samples

    def reap(self) -> None:
        for voice in self.voices:
            voice.finish()

    def stop_all(self) -> None:
        for voice in self.voices:
            try:
                voice.finish(stop=True)
            except OSError:
                logger.warning("Could not stop native KeyDeck audio voice", exc_info=True)

    def play(self, path: str, volume: float, voices: int | None = None) -> None:
        pcm = self._asset(path)
        self.reap()
        matching = [
            voice
            for voice in self.voices
            if voice.path == path and voice.format_key == (pcm.channels, pcm.width, pcm.rate)
        ]
        voice = next((item for item in matching if not item.busy), None)
        if voice is None and len(matching) >= max(1, min(8, voices or 2)):
            voice = min(matching, key=lambda item: item.used_at)
        if voice is None:
            if len(self.voices) >= _MAX_NATIVE_VOICES:
                idle = [item for item in self.voices if not item.busy]
                if not idle:
                    return
                oldest = min(idle, key=lambda item: item.used_at)
                oldest.close()
                self.voices.remove(oldest)
            voice = _Voice(self.api, path, pcm)
            self.voices.append(voice)
        voice.play(pcm, volume, samples=self._samples(path, pcm, volume))

    def close(self) -> None:
        for voice in self.voices:
            try:
                voice.close()
            except OSError:
                logger.warning("Could not release native KeyDeck audio voice", exc_info=True)
                _RETAINED_VOICES.append(voice)
        self.voices.clear()
        self.assets.clear()
        self.cache_bytes = 0
        self.gains.clear()
        self.gain_cache_bytes = 0


class NativeSoundBank:
    """Nonblocking SoundBank interface; all I/O and native calls run off the UI."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pending_preloads: set[str] = set()
        self._reported: set[tuple[str, str]] = set()
        atexit.register(self._shutdown)

    def _start(self) -> bool:
        with self._lock:
            if self._stop.is_set():
                return False
            if self._thread is None:
                # Called by the UI; no native work occurs while connecting shutdown.
                from PyQt6.QtCore import QCoreApplication

                app = QCoreApplication.instance()
                if app is not None:
                    app.aboutToQuit.connect(self.close)
                self._thread = threading.Thread(target=self._run, name="KeyDeckAudio", daemon=True)
                self._thread.start()
            return True

    def _submit(self, operation: str, value, volume: float = 0.0, voices=None) -> bool:
        if not self._start():
            return False
        try:
            self._queue.put_nowait((operation, value, volume, voices))
            return True
        except queue.Full:
            return False

    def preload(self, paths, voices: int | None = None) -> None:
        # Separate items keep one corrupt custom file from skipping other sounds.
        for path in paths:
            if path:
                path = str(path)
                with self._lock:
                    if path in self._pending_preloads:
                        continue
                    self._pending_preloads.add(path)
                if not self._submit("preload", path, voices=voices):
                    with self._lock:
                        self._pending_preloads.discard(path)

    def play(self, path: str, volume: float, voices: int | None = None) -> bool:
        try:
            gain = float(volume)
        except (TypeError, ValueError, OverflowError):
            return False
        if not path or not math.isfinite(gain) or gain <= 0.0:
            return False
        return self._submit("play", str(path), min(1.0, gain), voices)

    def stop_all(self) -> None:
        """Discard queued taps and stop active voices on their owning worker."""
        if self._thread is None or self._stop.is_set():
            return
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            self._pending_preloads.clear()
        self._submit("silence", "")

    def _run(self) -> None:
        player = None
        try:
            player = _Player()
            while not self._stop.is_set():
                try:
                    timeout = 0.02 if any(voice.busy for voice in player.voices) else None
                    operation, value, volume, voices = self._queue.get(timeout=timeout)
                except queue.Empty:
                    operation, value, volume, voices = "reap", "", 0.0, None
                if self._stop.is_set():
                    break
                try:
                    if operation == "play":
                        player.play(value, volume, voices)
                    elif operation == "preload":
                        player.preload([value], voices)
                    elif operation == "silence":
                        player.stop_all()
                    else:
                        player.reap()
                except (OSError, ValueError, EOFError, wave.Error) as error:
                    identity = (value, str(error))
                    if identity not in self._reported:
                        self._reported.add(identity)
                        logger.warning("KeyDeck sound unavailable: %s (%s)", value, error)
                finally:
                    if operation == "preload":
                        with self._lock:
                            self._pending_preloads.discard(value)
        except OSError as error:
            logger.warning("Native KeyDeck audio unavailable: %s", error)
        finally:
            self._stop.set()
            with self._lock:
                self._pending_preloads.clear()
            if player is not None:
                player.close()

    def close(self) -> None:
        """Signal cleanup without waiting for a driver or file read on the UI."""
        self._stop.set()
        # A full queue already wakes the worker, which checks _stop.
        with suppress(queue.Full):
            self._queue.put_nowait(("stop", "", 0.0, None))

    def _shutdown(self) -> None:
        self.close()
        if self._thread is not None and threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.5)


__all__ = ["NativeSoundBank"]
