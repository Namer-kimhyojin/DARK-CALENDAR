# -*- coding: utf-8 -*-
"""Opt-in six-track mixer with bounded WinMM streaming and local WAV projects.

Constructing this QObject never opens an audio device. Microphone capture is
opened only by an explicit record request with a microphone track armed.
"""

from array import array
import atexit
from collections import OrderedDict
from contextlib import suppress
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import tempfile
import threading
import time
from types import SimpleNamespace
import wave
import weakref

from PyQt6.QtCore import QCoreApplication, QObject

from calendar_app.domain.loop_mixer import (
    BLOCK_FRAMES,
    SAMPLE_RATE,
    TRACK_COUNT,
    LoopMixerState,
    convert_pcm,
    pcm_bytes,
)
from calendar_app.infrastructure.runtime.keydeck_audio import _WaveFormat, _WaveHeader
from calendar_app.shared.qt_lifetime import call_when_destroyed

# A live pad hit older than this is dropped (e.g. after suspend) instead of replayed.
# 100 ms also dropped real taps whenever the UI briefly held the GIL.
_LIVE_HIT_MAX_AGE_S = 0.25
_LEASE_LOCK = threading.RLock()
_ACTIVE = None
_MIXERS = weakref.WeakSet()
_RETAINED = []
_DRIVER_UNSAFE = threading.Event()
_MAX_WAV_BYTES = 25 * 1024 * 1024
_MAX_PROJECT_BYTES = 64 * 1024
_MAX_ASSET_CACHE = 32 * 1024 * 1024
_WHDR_DONE = 1
_MAPPER = 0xFFFFFFFF
_CALLBACK_EVENT = 0x00050000
_TIME_SAMPLES, _TIME_BYTES = 2, 4
_OUTPUT_BUFFERS = 3
_OUTPUT_WAIT_MS = 20
_OUTPUT_STALL_S = 1.0
# The stall deadline counts time spent waiting for the device. monotonic() keeps
# running through a system sleep, so one step longer than this means the thread did
# not run at all: the deadline starts over instead of reporting a stalled device.
_CLOCK_JUMP_S = 0.25
_MIC_OPEN_JOIN_S = 2.0
# Header, write and position calls return at once and never call back into Python:
# they keep the GIL, so a busy UI thread cannot hold the audio thread back for a
# whole switch interval after each one. Open, reset and close may block in the driver.
_GIL_KEPT = frozenset(
    {
        "waveOutPrepareHeader",
        "waveOutUnprepareHeader",
        "waveOutWrite",
        "waveOutGetPosition",
        "waveInAddBuffer",  # re-queues a capture buffer on every block while recording
    }
)
# Source id -> WAVs that KeyDeck can play (reported by the deck when its sounds change).
_KEYDECK_SOUNDS = {}


class _InputCaps(ctypes.Structure):
    _fields_ = [
        ("manufacturer", ctypes.c_uint16),
        ("product", ctypes.c_uint16),
        ("version", ctypes.c_uint32),
        ("name", ctypes.c_wchar * 32),
        ("formats", ctypes.c_uint32),
        ("channels", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16),
    ]


class _MMTime(ctypes.Structure):
    # MMTIME: a UINT type and an 8-byte union (only the DWORD sample/byte count is used).
    _fields_ = [("wType", ctypes.c_uint32), ("value", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


def _winmm():
    if os.name != "nt":
        raise OSError("windows_audio_required")
    dll = ctypes.WinDLL("winmm.dll")
    # x64 and ARM64 have a single calling convention, so PyDLL's cdecl is WINAPI there.
    fast = ctypes.PyDLL("winmm.dll") if ctypes.sizeof(ctypes.c_void_p) == 8 else dll
    signatures = {
        "waveOutOpen": [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint32,
            ctypes.POINTER(_WaveFormat),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint32,
        ],
        "waveInOpen": [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint32,
            ctypes.POINTER(_WaveFormat),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint32,
        ],
        "waveInGetNumDevs": [],
        "waveInGetDevCapsW": [ctypes.c_size_t, ctypes.POINTER(_InputCaps), ctypes.c_uint32],
    }
    for family in ("waveOut", "waveIn"):
        for operation in ("PrepareHeader", "UnprepareHeader"):
            signatures[family + operation] = [
                ctypes.c_void_p,
                ctypes.POINTER(_WaveHeader),
                ctypes.c_uint32,
            ]
        for operation in ("Reset", "Close"):
            signatures[family + operation] = [ctypes.c_void_p]
    signatures["waveOutWrite"] = [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint32]
    signatures["waveOutGetPosition"] = [ctypes.c_void_p, ctypes.POINTER(_MMTime), ctypes.c_uint32]
    signatures["waveInAddBuffer"] = [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint32]
    signatures["waveInStart"] = [ctypes.c_void_p]
    api = SimpleNamespace()
    for name, arguments in signatures.items():
        function = getattr(fast if name in _GIL_KEPT else dll, name)
        function.argtypes = arguments
        function.restype = ctypes.c_uint32
        setattr(api, name, function)
    return api


def _check(code, operation):
    if code:
        raise OSError(f"{operation}: WinMM {code}")


def _devices(api):
    rows, occurrences = [], {}
    for index in range(min(64, api.waveInGetNumDevs())):
        caps = _InputCaps()
        if api.waveInGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps)):
            continue
        label = str(caps.name).strip() or f"Microphone {index + 1}"
        identity = f"{caps.manufacturer}:{caps.product}:{label}"
        key = hashlib.sha256(identity.encode("utf-8", errors="strict")).hexdigest()[:24]
        ordinal = occurrences.get(key, 0)
        occurrences[key] = ordinal + 1
        rows.append((f"winmm:{key}:{ordinal}", label, index))
    return rows


class _Win32Event:
    """Auto-reset event the driver signals whenever an output buffer completes.

    Waiting on it releases the GIL and wakes the audio thread as soon as a buffer is
    free. Polling every 2 ms (about 10 ms in practice) delivered only 36-56% of real
    time while another thread kept the GIL busy.
    """

    def __init__(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateEventW
        create.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        create.restype = ctypes.c_void_p
        self._wait = kernel32.WaitForSingleObject
        self._wait.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._wait.restype = ctypes.c_uint32
        self._signal = kernel32.SetEvent
        self._close = kernel32.CloseHandle
        for function in (self._signal, self._close):
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_int
        self._lock = threading.Lock()
        self.handle = create(None, False, False, None)
        if not self.handle:
            raise OSError(f"CreateEventW: Win32 {ctypes.get_last_error()}")

    def wait(self, milliseconds):
        self._wait(self.handle, milliseconds)

    def wake(self):
        with self._lock:
            if self.handle:
                self._signal(self.handle)

    def close(self):
        with self._lock:
            handle, self.handle = self.handle, None
        if handle:
            self._close(handle)


class _ThreadEvent:
    """Portable stand-in used with injected test APIs; only ``wake`` signals it."""

    handle = 0

    def __init__(self):
        self._event = threading.Event()

    def wait(self, milliseconds):
        if self._event.wait(milliseconds / 1000):
            self._event.clear()

    def wake(self):
        self._event.set()

    def close(self):
        pass


class WinMMLoopBackend:
    """One worker owns all headers, buffers and input/output native handles."""

    def __init__(self, stop_event, *, api=None, events=None):
        if _DRIVER_UNSAFE.is_set():
            raise OSError("audio_driver_cleanup_failed_restart_required")
        self.api = api if api is not None else _winmm()
        self._new_event = events or (_Win32Event if api is None else _ThreadEvent)
        self.event = None
        self.stop_event = stop_event
        self.submitted_frames = 0
        self.output = ctypes.c_void_p()
        self.input = ctypes.c_void_p()
        self.outputs = []
        self.inputs = []
        self._input_cursor = 0
        self.input_channels = 1
        self.fifo = bytearray()
        self.dropped_input_frames = 0

    def open_output(self):
        fmt = _WaveFormat(1, 2, SAMPLE_RATE, SAMPLE_RATE * 4, 4, 16, 0)
        event = self._new_event()
        code = self.api.waveOutOpen(
            ctypes.byref(self.output), _MAPPER, ctypes.byref(fmt), event.handle, 0, _CALLBACK_EVENT
        )
        if code:
            event.close()  # the device never opened, so nothing can signal it
            _check(code, "waveOutOpen")
        self.event = event

    def wake(self):
        """Another thread is stopping playback: end the current buffer wait now."""
        event = self.event
        if event is not None:
            event.wake()

    def _release_outputs(self):
        remaining = []
        for header, buffer in self.outputs:
            if header.dwFlags & _WHDR_DONE:
                _check(
                    self.api.waveOutUnprepareHeader(
                        self.output, ctypes.byref(header), ctypes.sizeof(header)
                    ),
                    "waveOutUnprepareHeader",
                )
            else:
                remaining.append((header, buffer))
        self.outputs = remaining

    def wait_output(self):
        """Block until the device frees a buffer; False once stopping."""
        waited, last = 0.0, time.monotonic()
        while not self.stop_event.is_set():
            self._release_outputs()
            if len(self.outputs) < _OUTPUT_BUFFERS:
                return True
            now = time.monotonic()
            step, last = now - last, now
            waited = waited + step if step < _CLOCK_JUMP_S else 0.0
            if waited >= _OUTPUT_STALL_S:
                raise OSError("output_device_stalled")
            self.event.wait(_OUTPUT_WAIT_MS)
        return False

    def write_output(self, data):
        if not self.wait_output():
            return False
        buffer = ctypes.create_string_buffer(data, len(data))
        header = _WaveHeader()
        header.lpData, header.dwBufferLength = ctypes.addressof(buffer), len(data)
        _check(
            self.api.waveOutPrepareHeader(self.output, ctypes.byref(header), ctypes.sizeof(header)),
            "waveOutPrepareHeader",
        )
        self.outputs.append((header, buffer))
        _check(
            self.api.waveOutWrite(self.output, ctypes.byref(header), ctypes.sizeof(header)),
            "waveOutWrite",
        )
        self.submitted_frames += len(data) // 4
        return True

    def latency_frames(self):
        """(output, input) frames between the speaker/microphone and the next block."""
        output = 0
        if self.output.value:
            output = (
                sum(
                    header.dwBufferLength
                    for header, _buffer in self.outputs
                    if not header.dwFlags & _WHDR_DONE
                )
                // 4
            )
            position = _MMTime(_TIME_SAMPLES, 0, 0)
            unit = None
            if not self.api.waveOutGetPosition(
                self.output, ctypes.byref(position), ctypes.sizeof(position)
            ):
                unit = {_TIME_SAMPLES: 1, _TIME_BYTES: 4}.get(position.wType)
            if unit:
                # The device position also counts what the audio engine still holds.
                ahead = ((self.submitted_frames * unit - position.value) % (1 << 32)) // unit
                if ahead <= output + SAMPLE_RATE // 5:
                    output = ahead
        # Captured audio waits in the FIFO, plus about one capture buffer before it.
        microphone = len(self.fifo) // 4 + BLOCK_FRAMES if self.input.value else 0
        return output, microphone

    def open_input(self, device_id):
        if self.input.value:
            return
        if not self.api.waveInGetNumDevs():
            raise OSError("microphone_device_missing")
        selected = _MAPPER
        if device_id != "default":
            matches = [row for row in _devices(self.api) if row[0] == device_id]
            if not matches:
                raise OSError("microphone_device_missing")
            selected = matches[0][2]
        # Ask without opening first. The mapper may adapt a supported PCM format.
        for channels in (1, 2):
            fmt = _WaveFormat(
                1, channels, SAMPLE_RATE, SAMPLE_RATE * channels * 2, channels * 2, 16, 0
            )
            if not self.api.waveInOpen(None, selected, ctypes.byref(fmt), 0, 0, 1):
                break
        else:
            raise OSError("microphone_format_unavailable")
        self.input_channels = channels
        _check(
            self.api.waveInOpen(ctypes.byref(self.input), selected, ctypes.byref(fmt), 0, 0, 0),
            "waveInOpen",
        )
        self._input_cursor = 0
        for _ in range(4):
            buffer = ctypes.create_string_buffer(BLOCK_FRAMES * channels * 2)
            header = _WaveHeader()
            header.lpData, header.dwBufferLength = ctypes.addressof(buffer), len(buffer)
            _check(
                self.api.waveInPrepareHeader(
                    self.input, ctypes.byref(header), ctypes.sizeof(header)
                ),
                "waveInPrepareHeader",
            )
            self.inputs.append((header, buffer))
            _check(
                self.api.waveInAddBuffer(self.input, ctypes.byref(header), ctypes.sizeof(header)),
                "waveInAddBuffer",
            )
        _check(self.api.waveInStart(self.input), "waveInStart")

    def read_input(self, frames):
        # Recycled buffers return in submission order, not fixed header-index
        # order. A delayed poll may see a rotated ring entirely marked DONE.
        for _ in range(len(self.inputs)):
            header, _buffer = self.inputs[self._input_cursor]
            if header.dwFlags & _WHDR_DONE:
                count = min(header.dwBytesRecorded, header.dwBufferLength)
                count -= count % (self.input_channels * 2)
                raw = ctypes.string_at(header.lpData, count)
                if self.input_channels == 1:
                    mono = array("h")
                    mono.frombytes(raw)
                    raw = pcm_bytes(
                        array("h", (value for sample in mono for value in (sample, sample)))
                    )
                if len(self.fifo) + len(raw) > BLOCK_FRAMES * 4 * 8:
                    self.dropped_input_frames += len(raw) // 4
                else:
                    self.fifo.extend(raw)
                header.dwBytesRecorded = 0
                _check(
                    self.api.waveInAddBuffer(
                        self.input, ctypes.byref(header), ctypes.sizeof(header)
                    ),
                    "waveInAddBuffer",
                )
                self._input_cursor = (self._input_cursor + 1) % len(self.inputs)
            else:
                break  # Keep later completed blocks behind their earlier input.
        size = frames * 4
        result = bytes(self.fifo[:size])
        del self.fifo[:size]
        return result + bytes(size - len(result))

    def close_input(self):
        if not self.input.value:
            return
        _check(self.api.waveInReset(self.input), "waveInReset")
        for header, _buffer in self.inputs:
            _check(
                self.api.waveInUnprepareHeader(
                    self.input, ctypes.byref(header), ctypes.sizeof(header)
                ),
                "waveInUnprepareHeader",
            )
        _check(self.api.waveInClose(self.input), "waveInClose")
        self.inputs.clear()
        self._input_cursor = 0
        self.input = ctypes.c_void_p()
        self.fifo.clear()

    def close(self):
        try:
            self.close_input()
            if self.output.value:
                _check(self.api.waveOutReset(self.output), "waveOutReset")
                for header, _buffer in self.outputs:
                    _check(
                        self.api.waveOutUnprepareHeader(
                            self.output, ctypes.byref(header), ctypes.sizeof(header)
                        ),
                        "waveOutUnprepareHeader",
                    )
                _check(self.api.waveOutClose(self.output), "waveOutClose")
                self.outputs.clear()
                self.output = ctypes.c_void_p()
            if self.event is not None:
                # Only now: the driver may signal the event until waveOutClose returns.
                event, self.event = self.event, None
                event.close()
        except OSError:
            # Preserve native-owned allocations; prevent repeated failed sessions
            # from creating an unbounded retained-buffer collection.
            _DRIVER_UNSAFE.set()
            if self not in _RETAINED:
                _RETAINED.append(self)
            raise


def _read_wav(path, *, canonical=False):
    path = Path(path)
    if path.suffix.lower() != ".wav" or path.stat().st_size > _MAX_WAV_BYTES:
        raise ValueError("unsupported_wav")
    with wave.open(str(path), "rb") as source:
        channels, width, rate, frames = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getnframes(),
        )
        expected = channels * width * frames
        if source.getcomptype() != "NONE" or not 0 < expected <= _MAX_WAV_BYTES:
            raise ValueError("unsupported_wav")
        if canonical and (channels, width, rate) != (2, 2, SAMPLE_RATE):
            raise ValueError("invalid_project_audio")
        data = source.readframes(frames)
        if len(data) != expected:
            raise ValueError("truncated_wav")
    return convert_pcm(data, channels, width, rate)


def _write_wav(path, samples):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm_bytes(samples))


class _MicrophoneOpener:
    """Opens the microphone on a helper thread while the audio loop keeps playing.

    waveInOpen and buffer setup can take tens of milliseconds; on the audio thread
    they emptied the output queue when a recording started over a playing loop.
    """

    def __init__(self, backend, device):
        self.error = None
        self.thread = threading.Thread(
            target=self._open, args=(backend, device), name="LoopMixerMicrophone", daemon=True
        )
        self.thread.start()

    def _open(self, backend, device):
        try:
            backend.open_input(device)
        except Exception as error:  # reported on the audio thread
            self.error = error

    def finished(self):
        return not self.thread.is_alive()

    def raise_error(self):
        if self.error is not None:
            raise self.error

    def join(self, timeout):
        self.thread.join(timeout)
        return not self.thread.is_alive()


def _active():
    with _LEASE_LOCK:
        return _ACTIVE() if _ACTIVE is not None else None


def route_keydeck_sound(source_id, path, gain):
    mixer = _active()
    return mixer._route(source_id, path, gain) if mixer is not None else False


def stop_keydeck_source(source_id):
    mixer = _active()
    return mixer._stop_source(source_id) if mixer is not None else False


def set_keydeck_sounds(source_id, paths):
    """A KeyDeck lists the WAVs it can play; mixers it feeds decode them right away."""
    source_id = str(source_id)
    paths = tuple(dict.fromkeys(str(path) for path in paths if path))[:256]
    with _LEASE_LOCK:
        _KEYDECK_SOUNDS[source_id] = paths
        mixers = list(_MIXERS)
    for mixer in mixers:
        mixer._warm_source(source_id)


def _keydeck_sounds(source_id):
    with _LEASE_LOCK:
        return _KEYDECK_SOUNDS.get(source_id, ())


def _shutdown_if_alive(ref):
    mixer = ref()
    if mixer is not None:
        mixer.shutdown()


class LoopMixer(QObject):
    """UI facade; transport, device I/O and file work never run on the UI thread."""

    def __init__(self, parent=None, *, backend_factory=None, threaded=True):
        super().__init__(parent)
        self._state = LoopMixerState()
        self._lock = threading.RLock()
        self._backend_factory = backend_factory or WinMMLoopBackend
        self._threaded = threaded
        self._thread = self._io_thread = None
        self._stop_event = threading.Event()
        self._cancel_io = threading.Event()
        self._commands = queue.Queue(maxsize=64)
        self._closed = False
        self._error = self._error_code = ""
        self._busy = False
        self._last_operation = ""
        self._operation_id = self._completed_operation_id = 0
        self._operation_success = False
        self._microphone_device = "default"
        self._backend = None
        self._cache = OrderedDict()
        self._cache_bytes = self._dropped_hits = 0
        self._decode_errors = OrderedDict()
        self._warm_queue = OrderedDict()
        self._warm_thread = None
        self._awaiting = []
        self._source_epoch = {}
        _MIXERS.add(self)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        call_when_destroyed(self, _shutdown_if_alive, weakref.ref(self))

    def _fail(self, error, code=None):
        self._error = str(error)
        self._error_code = code or str(error).split(":", 1)[0]
        return False

    def _edit(self, operation):
        with self._lock:
            if self._closed or self._busy:
                return self._fail("mixer_closed" if self._closed else "file_operation_busy")
            try:
                operation()
                self._error = self._error_code = ""
                return True
            except (ValueError, TypeError, IndexError) as error:
                return self._fail(error)

    def configure(self, bpm, bars):
        return self._edit(lambda: self._state.configure(bpm, bars))

    def set_track(self, index, **settings):
        changed = self._edit(lambda: self._state.set_track(index, **settings))
        source = settings.get("source")
        if changed and isinstance(source, str) and source.startswith("launcher_deck_"):
            # Decode the deck's sounds before its first hit reaches the audio thread.
            self._warm(_keydeck_sounds(source))
        return changed

    def set_master_volume(self, value):
        def update():
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("invalid_volume")
            self._state.master_volume = value

        return self._edit(update)

    def clear_track(self, index):
        return self._edit(lambda: self._state.clear_track(index))

    def set_microphone_device(self, device_id):
        def update():
            if self._state.mode != "idle":
                raise ValueError("transport_busy")
            if not isinstance(device_id, str) or not (
                device_id == "default" or re.fullmatch(r"winmm:[a-f0-9]{24}:\d{1,2}", device_id)
            ):
                raise ValueError("invalid_microphone_device")
            self._microphone_device = device_id

        return self._edit(update)

    def microphone_devices(self):
        if self._closed:
            return []
        try:
            return [
                ("default", "Windows default microphone"),
                *[(key, label) for key, label, _index in _devices(_winmm())],
            ]
        except OSError as error:
            with self._lock:
                self._fail(error, "microphone_unavailable")
            return []

    def _claim(self):
        global _ACTIVE
        with _LEASE_LOCK:
            owner = _ACTIVE() if _ACTIVE is not None else None
            if owner is not None and owner is not self:
                return False
            _ACTIVE = weakref.ref(self)
            return True

    def _release(self):
        global _ACTIVE
        with _LEASE_LOCK:
            if _ACTIVE is not None and _ACTIVE() is self:
                _ACTIVE = None

    def _start(self, *, recording=False, overdub=False):
        with self._lock:
            if self._closed or self._busy:
                return self._fail("mixer_closed" if self._closed else "file_operation_busy")
            already_running = self._state.mode != "idle" and (
                not self._threaded or (self._thread is not None and self._thread.is_alive())
            )
            if already_running:
                try:
                    self._state.record(overdub) if recording else self._state.play()
                    self._error = self._error_code = ""
                    return True
                except (ValueError, TypeError) as error:
                    return self._fail(error)
            if self._thread is not None and self._thread.is_alive():
                return self._fail("audio_device_stopping")
        if not self._claim():
            with self._lock:
                return self._fail("another_mixer_is_playing")
        with self._lock:
            try:
                self._state.record(overdub) if recording else self._state.play()
                self._error = self._error_code = ""
                self._stop_event = threading.Event()
                if self._threaded:
                    self._thread = threading.Thread(
                        target=self._run, name="LoopMixerAudio", daemon=True
                    )
                    self._thread.start()
                sources = self._state.sources()
            except (ValueError, TypeError, RuntimeError) as error:
                self._state.stop(commit=False)
                self._release()
                return self._fail(error)
        # A restored session or project connects KeyDecks without set_track().
        for source in sources:
            self._warm(_keydeck_sounds(source))
        return True

    def play(self):
        return self._start()

    def record(self, overdub=False):
        return self._start(recording=True, overdub=overdub)

    def _drain_commands(self):
        while True:
            try:
                self._commands.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        self._stop_event.set()
        with self._lock:
            backend = self._backend
            self._state.stop()
            self._drain_commands()
            self._awaiting.clear()
        wake = getattr(backend, "wake", None)  # test backends may omit it
        if wake is not None:
            wake()  # the audio thread may be waiting up to 20 ms for a buffer
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.3)
        # Keep the lease until the output handle is released if a driver stalls.
        if thread is None or not thread.is_alive():
            self._release()
        return True

    def shutdown(self):
        with self._lock:
            self._closed = True
            # A previously accepted save must survive its Qt parent's destruction.
            # Its worker owns only Python snapshots and atomic local file handles.
            if not (self._busy and self._last_operation == "save_project"):
                self._cancel_io.set()
        self.stop()
        thread = self._io_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.3)
        with self._lock:
            self._cache.clear()
            self._cache_bytes = 0
            self._decode_errors.clear()
            self._warm_queue.clear()

    def _route(self, source_id, path, gain):
        with self._lock:
            if self._closed or self._state.mode == "idle" or source_id not in self._state.sources():
                return False
            try:
                volume = float(gain)
                if not math.isfinite(volume) or not 0 <= volume <= 1 or not path:
                    return True
                self._commands.put_nowait(
                    (
                        source_id,
                        str(path),
                        volume,
                        time.monotonic(),
                        self._source_epoch.get(source_id, 0),
                    )
                )
            except (TypeError, ValueError, OverflowError, queue.Full):
                self._dropped_hits += 1
            return True

    def _stop_source(self, source_id):
        with self._lock:
            if self._state.mode == "idle" or source_id not in self._state.sources():
                return False
            self._source_epoch[source_id] = self._source_epoch.get(source_id, 0) + 1
            retained = []
            while True:
                try:
                    command = self._commands.get_nowait()
                except queue.Empty:
                    break
                if command[0] != source_id:
                    retained.append(command)
            for command in retained:
                self._commands.put_nowait(command)
            self._state.stop_source(source_id)
            return True

    @staticmethod
    def _identity(path):
        stamp = Path(path).stat()
        return (path, stamp.st_mtime_ns, stamp.st_size)

    def _cached(self, path):
        """Decoded samples, or None until a decoder thread has them. Never decodes."""
        identity = self._identity(path)
        with self._lock:
            samples = self._cache.get(identity)
            if samples is not None:
                self._cache.move_to_end(identity)
                return samples
            error = self._decode_errors.get(identity)
        if error is not None:
            raise error
        return None

    def _asset(self, path):
        """Decoded samples, decoding now when needed (decoder thread or tests only)."""
        samples = self._cached(path)
        if samples is not None:
            return samples
        identity = self._identity(path)
        try:
            samples = _read_wav(path)
        except (OSError, ValueError, EOFError, wave.Error) as error:
            with self._lock:
                self._decode_errors[identity] = error
                while len(self._decode_errors) > 64:
                    self._decode_errors.popitem(last=False)
            raise
        with self._lock:
            if not self._closed and identity not in self._cache:
                self._cache[identity] = samples
                self._cache_bytes += len(samples) * 2
                while self._cache_bytes > _MAX_ASSET_CACHE or len(self._cache) > 64:
                    _old_key, old = self._cache.popitem(last=False)
                    self._cache_bytes -= len(old) * 2
        return samples

    def _warm(self, paths):
        """Decode KeyDeck sounds on a helper thread so the audio thread never has to."""
        with self._lock:
            if self._closed:
                return
            for path in paths:
                self._warm_queue[str(path)] = None
                self._warm_queue.move_to_end(str(path))
            while len(self._warm_queue) > 256:
                self._warm_queue.popitem(last=False)
            if not self._warm_queue or self._warm_thread is not None:
                return
            thread = None
            if self._threaded:
                thread = self._warm_thread = threading.Thread(
                    target=self._decode_pending, name="LoopMixerDecode", daemon=True
                )
        if thread is None:
            self._decode_pending()
            return
        try:
            thread.start()
        except RuntimeError:
            with self._lock:
                self._warm_thread = None

    def _warm_source(self, source):
        with self._lock:
            connected = source in self._state.sources()
        if connected:
            self._warm(_keydeck_sounds(source))

    def _decode_pending(self):
        while True:
            with self._lock:
                if self._closed or not self._warm_queue:
                    self._warm_queue.clear()
                    self._warm_thread = None
                    return
                path, _value = self._warm_queue.popitem(last=False)
            # A failure is kept for the hit that needs this sound; it reports it.
            with suppress(OSError, ValueError, EOFError, wave.Error):
                self._asset(path)

    def _process_block(self, microphone=b"", frames=BLOCK_FRAMES, *, latency=0, input_latency=0):
        # Also used by deterministic tests with threaded=False; never device I/O.
        with self._lock:
            commands, self._awaiting = self._awaiting, []
        for _ in range(64):
            try:
                commands.append(self._commands.get_nowait())
            except queue.Empty:
                break
        for command in commands:
            source, path, gain, created, epoch = command
            if time.monotonic() - created > _LIVE_HIT_MAX_AGE_S:
                with self._lock:
                    self._dropped_hits += 1
                continue
            try:
                # The audio thread never decodes: a 1 s 48 kHz 24-bit WAV took ~95 ms
                # and cut the loop. Its hit waits here until a decoder thread is done.
                samples = self._cached(path) if self._threaded else self._asset(path)
            except (OSError, ValueError, EOFError, wave.Error) as error:
                with self._lock:
                    self._fail(error, "sound_unavailable")
                continue
            if samples is None:
                with self._lock:
                    if len(self._awaiting) < 64:
                        self._awaiting.append(command)
                    else:
                        self._dropped_hits += 1
                self._warm((path,))
                continue
            with self._lock:
                if (
                    epoch == self._source_epoch.get(source, 0)
                    and time.monotonic() - created <= _LIVE_HIT_MAX_AGE_S
                ):
                    self._state.add_voice(source, samples, gain)
                else:
                    self._dropped_hits += 1
        with self._lock:
            return self._state.render(
                frames, microphone, latency=latency, input_latency=input_latency
            )

    def _run(self):
        backend = opener = None
        try:
            backend = self._backend_factory(self._stop_event)
            with self._lock:
                self._backend = backend
            backend.open_output()
            latency = getattr(backend, "latency_frames", None)  # test backends may omit it
            input_open = False
            # Render only once the device has a free buffer: a block rendered before
            # that wait would hold back hits pressed meanwhile by one block (~20 ms).
            while backend.wait_output():
                with self._lock:
                    needs_input = self._state.mode == "recording" and any(
                        self._state.tracks[index].source == "mic" for index in self._state._pending
                    )
                    device = self._microphone_device
                if needs_input and not input_open:
                    if not self._threaded:
                        backend.open_input(device)
                        input_open = True
                    elif opener is None:
                        opener = _MicrophoneOpener(backend, device)
                    elif opener.finished():
                        opener, ready = None, opener
                        ready.raise_error()
                        input_open = True
                elif not needs_input and (input_open or (opener is not None and opener.finished())):
                    opener = None
                    backend.close_input()
                    input_open = False
                microphone = backend.read_input(BLOCK_FRAMES) if input_open else b""
                output_latency, input_latency = latency() if latency is not None else (0, 0)
                data = self._process_block(
                    microphone, latency=output_latency, input_latency=input_latency
                )
                # Auto-commit ends capture before waiting for output buffers. A
                # stalled output device must never extend a completed mic take.
                with self._lock:
                    capture_finished = self._state.mode != "recording"
                if input_open and capture_finished:
                    backend.close_input()
                    input_open = False
                if not backend.write_output(data):
                    break
        except Exception as error:
            # After a failed native cleanup only an app restart helps (see close()).
            code = "audio_cleanup_failed" if _DRIVER_UNSAFE.is_set() else "audio_device_error"
            with self._lock:
                # Like pressing Stop: the part of a take recorded before the error stays.
                if self._state.stop() and code == "audio_device_error":
                    code = "audio_device_error_take_saved"
                self._fail(error, code)
        finally:
            with self._lock:
                self._backend = None
            if backend is not None:
                if opener is not None and not opener.join(_MIC_OPEN_JOIN_S):
                    # The helper still owns a half-open microphone. Freeing the backend
                    # now could race the driver, so keep it until the process ends.
                    _DRIVER_UNSAFE.set()
                    _RETAINED.append(backend)
                    with self._lock:
                        self._fail("microphone_open_timeout", "audio_cleanup_failed")
                else:
                    try:
                        backend.close()
                    except OSError as error:
                        with self._lock:
                            self._fail(error, "audio_cleanup_failed")
            self._release()
            with self._lock:
                if self._closed:
                    self._cache.clear()
                    self._cache_bytes = 0

    def snapshot(self):
        with self._lock:
            return {
                **self._state.snapshot(),
                "error": self._error,
                "error_code": self._error_code,
                "busy": self._busy,
                "last_operation": self._last_operation,
                "operation_id": self._operation_id,
                "completed_operation_id": self._completed_operation_id,
                "operation_success": self._operation_success,
                "microphone_device": self._microphone_device,
                "dropped_hits": self._dropped_hits,
            }

    def _file_job(self, name, operation, *, require_idle=False):
        with self._lock:
            if self._closed or self._busy or (require_idle and self._state.mode != "idle"):
                return self._fail("file_operation_busy")
            self._busy = True
            self._last_operation = name
            self._operation_id += 1
            operation_id = self._operation_id
            self._error = self._error_code = ""

        def run():
            success = False
            try:
                operation()
                success = True
            except Exception as error:
                with self._lock:
                    self._fail(error, name + "_failed")
            finally:
                with self._lock:
                    self._busy = False
                    self._completed_operation_id = operation_id
                    self._operation_success = success

        if self._threaded:
            self._io_thread = threading.Thread(target=run, name="LoopMixerFile", daemon=True)
            try:
                self._io_thread.start()
            except RuntimeError as error:
                with self._lock:
                    self._busy = False
                    self._completed_operation_id = operation_id
                    self._operation_success = False
                    return self._fail(error, name + "_failed")
        else:
            run()
        return True

    def _check_cancel(self):
        if self._cancel_io.is_set():
            raise ValueError("operation_cancelled")

    def load_wav(self, index, path):
        def load():
            samples = _read_wav(path)
            self._check_cancel()
            with self._lock:
                self._state.load_audio(index, samples)
                self._state.set_track(index, source="file")

        return self._file_job("load_wav", load, require_idle=True)

    def _copy_project(self):
        with self._lock:
            result = LoopMixerState()
            result.configure(self._state.bpm, self._state.bars)
            result.master_volume = self._state.master_volume
            for index, track in enumerate(self._state.tracks):
                result.set_track(index, **track.metadata())
                result.load_audio(index, track.audio)
            return result

    def clone_from(self, other_mixer):
        if not isinstance(other_mixer, LoopMixer) or other_mixer is self:
            with self._lock:
                return self._fail("invalid_mixer_source")
        state = other_mixer._copy_project()
        with self._lock:
            if self._closed or self._busy or self._state.mode != "idle":
                return self._fail("transport_busy")
            self._state = state
            self._error = self._error_code = ""
            return True

    @staticmethod
    def _safe_destination(path):
        target = Path(path).absolute()
        if (
            not target.parent.is_dir()
            or target.is_symlink()
            or target.parent.resolve() != target.parent
        ):
            raise ValueError("unsafe_project_path")
        return target

    def _atomic_wav(self, target, state):
        descriptor, temporary = tempfile.mkstemp(
            prefix=".loop-mix-", suffix=".wav", dir=target.parent
        )
        os.close(descriptor)
        try:
            state.play()
            remaining = state.loop_frames
            with wave.open(temporary, "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(SAMPLE_RATE)
                while remaining:
                    self._check_cancel()
                    count = min(BLOCK_FRAMES, remaining)
                    output.writeframesraw(state.render(count))
                    remaining -= count
            self._check_cancel()
            os.replace(temporary, target)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary)

    def export_wav(self, path):
        def export():
            target = self._safe_destination(path)
            if target.suffix.lower() != ".wav":
                raise ValueError("wav_extension_required")
            self._atomic_wav(target, self._copy_project())

        return self._file_job("export_wav", export)

    def save_project(self, path):
        def save():
            target = self._safe_destination(path)
            state = self._copy_project()
            assets = target.with_name(target.stem + ".assets")
            if assets.is_symlink() or (
                assets.exists() and (not assets.is_dir() or assets.resolve() != assets)
            ):
                raise ValueError("unsafe_project_path")
            assets.mkdir(exist_ok=True)
            existing = list(assets.iterdir())
            if (
                len(existing) > 128
                or sum(item.stat().st_size for item in existing if item.is_file())
                > 512 * 1024 * 1024
            ):
                raise ValueError("project_asset_limit")
            rows = []
            for track in state.tracks:
                self._check_cancel()
                row = track.metadata()
                if track.audio:
                    digest = hashlib.sha256(pcm_bytes(track.audio)).hexdigest()
                    asset = assets / (digest + ".wav")
                    if asset.is_symlink():
                        raise ValueError("unsafe_project_audio")
                    if not asset.exists():
                        descriptor, temporary = tempfile.mkstemp(
                            prefix=".loop-clip-", suffix=".wav", dir=assets
                        )
                        os.close(descriptor)
                        try:
                            _write_wav(temporary, track.audio)
                            self._check_cancel()
                            os.link(temporary, asset)
                        finally:
                            with suppress(FileNotFoundError):
                                os.unlink(temporary)
                    if (
                        hashlib.sha256(pcm_bytes(_read_wav(asset, canonical=True))).hexdigest()
                        != digest
                    ):
                        raise ValueError("project_audio_hash_mismatch")
                    row["audio"] = assets.name + "/" + asset.name
                    row["pcm_sha256"] = digest
                rows.append(row)
            document = {
                "version": 1,
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "sample_width": 2,
                "bpm": state.bpm,
                "bars": state.bars,
                "master_volume": state.master_volume,
                "tracks": rows,
            }
            data = json.dumps(document, ensure_ascii=False, indent=2).encode(
                "utf-8", errors="strict"
            )
            descriptor, temporary = tempfile.mkstemp(
                prefix=".loop-project-", suffix=".json", dir=target.parent
            )
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                self._check_cancel()
                os.replace(temporary, target)
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(temporary)
            # Every take adds a clip; drop the ones this save no longer references so
            # the folder never reaches the asset limit. Only digest names written above.
            referenced = {row["pcm_sha256"] + ".wav" for row in rows if "pcm_sha256" in row}
            # "X.airloop" and "X.json" share "X.assets": keep the other project's clips.
            for sibling in target.parent.iterdir():
                if sibling.stem != target.stem or sibling == target or not sibling.is_file():
                    continue
                try:
                    other = json.loads(sibling.read_text(encoding="utf-8", errors="strict"))
                    tracks = other.get("tracks", []) if isinstance(other, dict) else []
                    referenced |= {
                        str(track["pcm_sha256"]) + ".wav"
                        for track in tracks
                        if isinstance(track, dict) and "pcm_sha256" in track
                    }
                except ValueError:
                    continue  # not a project file
                except OSError:
                    return  # cannot tell what it uses; keep every clip
            for item in assets.iterdir():
                if (
                    re.fullmatch(r"[a-f0-9]{64}\.wav", item.name)
                    and item.name not in referenced
                    and item.is_file()
                    and not item.is_symlink()
                ):
                    with suppress(OSError):
                        item.unlink()

        return self._file_job("save_project", save)

    def load_project(self, path):
        def load():
            target = self._safe_destination(path)
            if target.stat().st_size > _MAX_PROJECT_BYTES:
                raise ValueError("project_too_large")
            document = json.loads(target.read_text(encoding="utf-8", errors="strict"))
            if (
                not isinstance(document, dict)
                or type(document.get("version")) is not int
                or document.get("version") != 1
                or any(
                    document.get(key) != value
                    for key, value in (
                        ("sample_rate", SAMPLE_RATE),
                        ("channels", 2),
                        ("sample_width", 2),
                    )
                )
            ):
                raise ValueError("unsupported_project")
            rows = document.get("tracks")
            if not isinstance(rows, list) or len(rows) != TRACK_COUNT:
                raise ValueError("invalid_project_tracks")
            state = LoopMixerState()
            state.configure(document["bpm"], document["bars"])
            volume = document["master_volume"]
            if type(volume) is not int or not 0 <= volume <= 100:
                raise ValueError("invalid_volume")
            state.master_volume = volume
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise ValueError("invalid_project_tracks")
                state.set_track(
                    index,
                    **{
                        key: row[key]
                        for key in ("name", "source", "armed", "muted", "solo", "volume", "pan")
                    },
                )
                if "audio" in row:
                    relative = row["audio"]
                    digest = row.get("pcm_sha256", "")
                    if (
                        not isinstance(relative, str)
                        or re.fullmatch(r"[a-f0-9]{64}", digest) is None
                        or relative != target.stem + ".assets/" + digest + ".wav"
                    ):
                        raise ValueError("unsafe_project_audio")
                    asset = target.parent / relative
                    if (
                        asset.is_symlink()
                        or asset.parent.is_symlink()
                        or not asset.resolve().is_relative_to(target.parent)
                    ):
                        raise ValueError("unsafe_project_audio")
                    samples = _read_wav(asset, canonical=True)
                    if hashlib.sha256(pcm_bytes(samples)).hexdigest() != digest:
                        raise ValueError("project_audio_hash_mismatch")
                    state.load_audio(index, samples)
                self._check_cancel()
            with self._lock:
                self._state = state
            # Decks that reported their sounds before this session connected them are
            # decoded now, not by the first hits after Play.
            for source in state.sources():
                self._warm(_keydeck_sounds(source))

        return self._file_job("load_project", load, require_idle=True)


def _shutdown_mixers():
    for mixer in list(_MIXERS):
        mixer.shutdown()


atexit.register(_shutdown_mixers)

__all__ = ["LoopMixer", "route_keydeck_sound", "set_keydeck_sounds", "stop_keydeck_source"]
