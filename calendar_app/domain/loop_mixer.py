# -*- coding: utf-8 -*-
"""Bounded PCM loop mixer, independent of devices, Qt and persistence."""

from array import array
from dataclasses import dataclass, field
import math
import sys

SAMPLE_RATE = 22050
CHANNELS = 2
SAMPLE_WIDTH = 2
TRACK_COUNT = 6
MAX_SECONDS = 48
MAX_FRAMES = SAMPLE_RATE * MAX_SECONDS
MAX_PCM_BYTES = MAX_FRAMES * CHANNELS * SAMPLE_WIDTH
MAX_VOICES = 32
MAX_VOICE_BYTES = 16 * 1024 * 1024
BLOCK_FRAMES = 441


def clamp_sample(value):
    return min(32767, max(-32768, round(value)))


def pcm_samples(data):
    if not isinstance(data, bytes | bytearray) or len(data) % 4 or len(data) > MAX_PCM_BYTES:
        raise ValueError("invalid_pcm")
    result = array("h")
    result.frombytes(data)
    if sys.byteorder != "little":
        result.byteswap()
    return result


def pcm_bytes(samples):
    result = array("h", samples)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def convert_pcm(data, channels, width, rate):
    """Convert bounded integer PCM with linear resampling, never device I/O."""
    if (
        channels not in (1, 2)
        or width not in (1, 2, 3, 4)
        or type(rate) is not int
        or not 8000 <= rate <= 192000
        or not isinstance(data, bytes)
        or not data
        or len(data) % (channels * width)
    ):
        raise ValueError("unsupported_wav")
    count = len(data) // (channels * width)
    if count > MAX_SECONDS * rate:
        raise ValueError("clip_too_long")
    if channels == 2 and width == 2 and rate == SAMPLE_RATE:
        return pcm_samples(data)
    if width == 2 and rate in (SAMPLE_RATE, SAMPLE_RATE * 2):
        original = array("h")
        original.frombytes(data)
        if sys.byteorder != "little":
            original.byteswap()
        step = rate // SAMPLE_RATE
        if channels == 1:
            return array("h", (value for sample in original[::step] for value in (sample, sample)))
        return array(
            "h",
            (
                value
                for pair in zip(original[:: step * 2], original[1 :: step * 2], strict=True)
                for value in pair
            ),
        )
    original = array("h")
    for offset in range(0, len(data), channels * width):
        for channel in range(2):
            start = offset + min(channel, channels - 1) * width
            value = (
                (data[start] - 128) * 256
                if width == 1
                else int.from_bytes(data[start : start + width], "little", signed=True)
                / (256 ** (width - 2))
            )
            original.append(clamp_sample(value))
    frames = min(MAX_FRAMES, max(1, round(count * SAMPLE_RATE / rate)))
    result = array("h")
    for frame in range(frames):
        numerator = frame * rate
        first, fraction = divmod(numerator, SAMPLE_RATE)
        first = min(count - 1, first)
        second = min(count - 1, first + 1)
        for channel in range(2):
            low, high = original[first * 2 + channel], original[second * 2 + channel]
            result.append(clamp_sample(low + (high - low) * fraction / SAMPLE_RATE))
    return result


def loop_length(bpm, bars):
    if (
        type(bpm) is not int
        or not 40 <= bpm <= 240
        or type(bars) is not int
        or bars not in (1, 2, 4, 8)
    ):
        raise ValueError("invalid_tempo")
    return round(SAMPLE_RATE * 60 * bars * 4 / bpm)


def valid_source(source):
    return isinstance(source, str) and (
        source in ("none", "mic", "file")
        or (source.startswith("launcher_deck_") and source[14:].isdigit() and len(source) <= 80)
    )


@dataclass
class MixerTrack:
    name: str
    source: str = "none"
    armed: bool = False
    muted: bool = False
    solo: bool = False
    volume: int = 100
    pan: int = 0
    audio: array = field(default_factory=lambda: array("h"))
    peaks: list = field(default_factory=list)

    def refresh_peaks(self):
        # A bounded overview is cached when audio changes, never scanned at UI rate.
        stride = max(2, math.ceil(len(self.audio) / 64 / 2) * 2)
        self.peaks = [
            max(
                (
                    abs(value)
                    for value in self.audio[offset : offset + stride : max(1, stride // 128)]
                ),
                default=0,
            )
            / 32768
            for offset in range(0, len(self.audio), stride)
        ]

    def metadata(self):
        return {
            "name": self.name,
            "source": self.source,
            "armed": self.armed,
            "muted": self.muted,
            "solo": self.solo,
            "volume": self.volume,
            "pan": self.pan,
        }


@dataclass
class _Voice:
    source: str
    audio: array
    gain: float
    position: int = 0


class LoopMixerState:
    """One frame clock for live inputs, transactional takes and all six layers."""

    def __init__(self):
        self.bpm, self.bars = 120, 1
        self.master_volume = 80
        self.tracks = [MixerTrack(f"Track {index + 1}") for index in range(TRACK_COUNT)]
        self.mode = "idle"
        self.position_frames = 0
        self.input_level = 0.0
        self.output_levels = (0.0, 0.0)
        self._voices = []
        self._pending = {}
        self._recorded = 0
        self._overdub = False

    @property
    def loop_frames(self):
        return loop_length(self.bpm, self.bars)

    def configure(self, bpm, bars):
        loop_length(bpm, bars)
        if self.mode != "idle":
            raise ValueError("transport_busy")
        self.bpm, self.bars = bpm, bars
        self.position_frames = 0

    def set_track(self, index, **changes):
        if type(index) is not int or not 0 <= index < TRACK_COUNT:
            raise ValueError("invalid_track")
        track = self.tracks[index]
        if set(changes) - {"name", "source", "armed", "muted", "solo", "volume", "pan"}:
            raise ValueError("invalid_track_setting")
        for key, value in changes.items():
            if key == "name" and (not isinstance(value, str) or not 1 <= len(value.strip()) <= 80):
                raise ValueError("invalid_name")
            if key == "source" and not valid_source(value):
                raise ValueError("invalid_source")
            if key in ("armed", "muted", "solo") and type(value) is not bool:
                raise ValueError("invalid_track_setting")
            if key in ("volume", "pan") and (
                type(value) is not int or not (-100 if key == "pan" else 0) <= value <= 100
            ):
                raise ValueError("invalid_track_setting")
            if self.mode == "recording" and key in ("source", "armed"):
                raise ValueError("recording_busy")
        for key, value in changes.items():
            setattr(track, key, value.strip() if key == "name" else value)

    def load_audio(self, index, samples):
        if self.mode != "idle":
            raise ValueError("transport_busy")
        if type(index) is not int or not 0 <= index < TRACK_COUNT:
            raise ValueError("invalid_track")
        if not isinstance(samples, array) or samples.typecode != "h" or len(samples) % 2:
            raise ValueError("invalid_pcm")
        if len(samples) > MAX_FRAMES * 2:
            raise ValueError("clip_too_long")
        self.tracks[index].audio = array("h", samples)
        self.tracks[index].refresh_peaks()

    def play(self):
        if self.mode == "recording":
            raise ValueError("recording_busy")
        self.mode = "playing"

    def record(self, overdub=False):
        if type(overdub) is not bool:
            raise ValueError("invalid_record_mode")
        if self.mode == "recording":
            raise ValueError("recording_busy")
        armed = [
            index
            for index, track in enumerate(self.tracks)
            # Backing WAVs are committed playback, never a live recording input.
            if track.armed and track.source not in ("none", "file")
        ]
        if not armed:
            raise ValueError("no_armed_tracks")
        if self.mode == "idle":
            self.position_frames = 0
        self._recorded = 0
        self._overdub = overdub
        sample_count = self.loop_frames * 2
        pending = {}
        for index in armed:
            # An early Stop commits the whole pending loop. Keep untouched audio
            # in overdub mode, including when a take wraps around the loop end.
            samples = array("h", self.tracks[index].audio[:sample_count]) if overdub else array("h")
            samples.extend(array("h", [0]) * (sample_count - len(samples)))
            pending[index] = samples
        self._pending = pending
        self.mode = "recording"

    def _commit(self):
        if self._recorded:
            for index, pending in self._pending.items():
                self.tracks[index].audio = pending
                self.tracks[index].refresh_peaks()
        self._pending = {}
        self._recorded = 0
        self.mode = "playing"

    def stop(self, *, commit=True):
        if self.mode == "recording" and commit:
            self._commit()
        self._pending = {}
        self.mode = "idle"
        self.position_frames = 0
        self._voices.clear()
        self.input_level = 0.0
        self.output_levels = (0.0, 0.0)

    def clear_track(self, index):
        if self.mode == "recording":
            raise ValueError("recording_busy")
        if type(index) is not int or not 0 <= index < TRACK_COUNT:
            raise ValueError("invalid_track")
        self.tracks[index].audio = array("h")
        self.tracks[index].peaks = []

    def sources(self):
        return {track.source for track in self.tracks if track.source.startswith("launcher_deck_")}

    def add_voice(self, source, samples, gain):
        if source not in self.sources() or self.mode == "idle":
            return False
        if not math.isfinite(gain) or not 0 <= gain <= 1 or len(samples) > MAX_FRAMES * 2:
            return False
        while self._voices and (
            len(self._voices) >= MAX_VOICES
            or sum(
                len(value) * 2
                for value in {id(voice.audio): voice.audio for voice in self._voices}.values()
            )
            + len(samples) * 2
            > MAX_VOICE_BYTES
        ):
            self._voices.pop(0)
        self._voices.append(_Voice(source, samples, gain))
        return True

    def stop_source(self, source):
        self._voices = [voice for voice in self._voices if voice.source != source]

    def _live(self, frames):
        buffers = {}
        for voice in self._voices:
            target = buffers.setdefault(voice.source, [0] * (frames * 2))
            count = min(frames * 2, len(voice.audio) - voice.position)
            for offset in range(count):
                target[offset] += round(voice.audio[voice.position + offset] * voice.gain)
            voice.position += count
        self._voices = [voice for voice in self._voices if voice.position < len(voice.audio)]
        return buffers

    def render(self, frames, microphone=b""):
        if type(frames) is not int or not 1 <= frames <= BLOCK_FRAMES:
            raise ValueError("invalid_block")
        if self.mode == "idle":
            return bytes(frames * 4)
        mic = pcm_samples(microphone) if microphone else array("h")
        if len(mic) > frames * 2:
            raise ValueError("invalid_input_block")
        self.input_level = max((abs(value) for value in mic), default=0) / 32768
        live = self._live(frames)
        output = [0] * (frames * 2)
        solo = any(track.solo for track in self.tracks)
        frame = 0
        loop_frames = self.loop_frames
        while frame < frames:
            position = self.position_frames
            count = min(frames - frame, loop_frames - position)
            if self.mode == "recording":
                count = min(count, loop_frames - self._recorded)
            size, base = count * 2, frame * 2
            for index, track in enumerate(self.tracks):
                sample_at = position * 2
                previous = track.audio[sample_at : sample_at + size]
                if len(previous) < size:
                    previous.extend([0] * (size - len(previous)))
                source = mic if track.source == "mic" else live.get(track.source, ())
                incoming = previous if track.source == "file" else source[base : base + size]
                if len(incoming) < size:
                    incoming = list(incoming) + [0] * (size - len(incoming))
                capturing = self.mode == "recording" and index in self._pending
                if capturing:
                    recorded = array(
                        "h",
                        (
                            clamp_sample(
                                incoming[offset] + (previous[offset] if self._overdub else 0)
                            )
                            for offset in range(size)
                        ),
                    )
                    self._pending[index][sample_at : sample_at + size] = recorded
                if (
                    track.muted
                    or (solo and not track.solo)
                    or not track.volume
                    or not self.master_volume
                ):
                    continue
                heard = [0] * size if capturing and not self._overdub else previous
                if track.source not in ("mic", "file"):
                    heard = [left + right for left, right in zip(heard, incoming, strict=True)]
                elif track.source == "file" and capturing and not self._overdub:
                    heard = incoming
                gains = (
                    track.volume * self.master_volume * (100 - max(0, track.pan)) / 1000000,
                    track.volume * self.master_volume * (100 - max(0, -track.pan)) / 1000000,
                )
                for channel, gain in enumerate(gains):
                    if gain:
                        for offset in range(channel, size, 2):
                            output[base + offset] += round(heard[offset] * gain)
            frame += count
            self.position_frames = (position + count) % loop_frames
            if self.mode == "recording":
                self._recorded += count
                if self._recorded == loop_frames:
                    self._commit()
        samples = array("h", (clamp_sample(value) for value in output))
        self.output_levels = tuple(
            max((abs(value) for value in samples[channel::2]), default=0) / 32768
            for channel in range(2)
        )
        return pcm_bytes(samples)

    def snapshot(self):
        result = []
        for track in self.tracks:
            result.append(
                {
                    **track.metadata(),
                    "has_audio": bool(track.audio),
                    "audio_frames": len(track.audio) // 2,
                    "peaks": list(track.peaks),
                }
            )
        return {
            "mode": self.mode,
            "bpm": self.bpm,
            "bars": self.bars,
            "position_frames": self.position_frames,
            "loop_frames": self.loop_frames,
            "sample_rate": SAMPLE_RATE,
            "master_volume": self.master_volume,
            "tracks": result,
            "input_level": self.input_level,
            "output_levels": list(self.output_levels),
            "error": "",
        }
