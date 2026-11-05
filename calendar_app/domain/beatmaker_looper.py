# -*- coding: utf-8 -*-
"""Bounded four-track sound loops driven by one absolute monotonic epoch."""

from bisect import bisect_left, bisect_right
from copy import deepcopy
import math
import time

from calendar_app.domain.beatmaker_recording import normalize_recording

TRACK_COUNT = 4
TICKS_PER_BEAT = 960
MAX_TRACK_EVENTS = 2048
MAX_LOOP_EVENTS = 8192
_BARS = (1, 2, 4, 8)
_GRID = TICKS_PER_BEAT // 4
_EPSILON = 1e-6
_STALE_SECONDS = 0.100


def default_looper() -> dict:
    return {
        "version": 1,
        "bpm": 120,
        "bars": 1,
        "quantize": "1/16",
        "tracks": [{"muted": False, "volume": 100, "events": []} for _ in range(TRACK_COUNT)],
    }


def _sound_snapshot(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    result = normalize_recording(
        {"version": 1, "duration_ms": 100, "events": [{**raw, "at_ms": 0}]}
    )
    if result is None:
        return None
    event = result["events"][0]
    return {key: event[key] for key in ("sound", "sound_path", "volume", "key_id")}


def normalize_looper(raw) -> dict | None:
    """Reject invalid projects as a whole and discard executable/unknown fields."""
    if not isinstance(raw, dict) or type(raw.get("version")) is not int or raw["version"] != 1:
        return None
    bpm, bars, quantize, tracks = (raw.get(key) for key in ("bpm", "bars", "quantize", "tracks"))
    if (
        type(bpm) is not int
        or not 40 <= bpm <= 240
        or type(bars) is not int
        or bars not in _BARS
        or quantize not in ("1/16", "off")
        or not isinstance(tracks, list)
        or len(tracks) != TRACK_COUNT
    ):
        return None
    cleaned, count = [], 0
    loop_ticks = bars * 4 * TICKS_PER_BEAT
    for track in tracks:
        if (
            not isinstance(track, dict)
            or type(track.get("muted")) is not bool
            or type(track.get("volume")) is not int
            or not 0 <= track["volume"] <= 100
            or not isinstance(track.get("events"), list)
            or len(track["events"]) > MAX_TRACK_EVENTS
        ):
            return None
        events, previous = [], -1
        for event in track["events"]:
            tick = event.get("at_tick") if isinstance(event, dict) else None
            sound = _sound_snapshot(event)
            if (
                type(tick) is not int
                or not 0 <= tick < loop_ticks
                or tick < previous
                or sound is None
            ):
                return None
            events.append({"at_tick": tick, **sound})
            previous = tick
        count += len(events)
        if count > MAX_LOOP_EVENTS:
            return None
        cleaned.append({"muted": track["muted"], "volume": track["volume"], "events": events})
    return {"version": 1, "bpm": bpm, "bars": bars, "quantize": quantize, "tracks": cleaned}


class BeatmakerLooperTimeline:
    """Four layers share one clock; pending live hits never echo during recording.

    ``data`` is the independent normalized project for serialization. Call the
    public editing methods rather than changing its containers during transport.
    A replacement is transactional until the first take is committed.
    """

    def __init__(self, raw=None, *, clock=time.monotonic):
        self._data = normalize_looper(raw) or default_looper()
        self._clock = clock
        self._mode = "idle"
        self._record_track = None
        self.limited = False
        self._epoch = None
        self._last_now = None
        self._last_absolute_tick = 0.0
        self._cursor_tick = -_EPSILON
        self._record_until = None
        self._pending = []
        self._overdub = True
        self._not_before = {}
        self._ticks = [
            [event["at_tick"] for event in track["events"]] for track in self._data["tracks"]
        ]

    @property
    def data(self):
        self._advance()
        return self._data

    @property
    def mode(self):
        self._advance()
        return self._mode

    @property
    def record_track(self):
        self._advance()
        return self._record_track

    @property
    def loop_ticks(self):
        return self._data["bars"] * 4 * TICKS_PER_BEAT

    @property
    def duration_ms(self):
        return round(self.loop_ticks * 60000 / (self._data["bpm"] * TICKS_PER_BEAT))

    @property
    def position_ticks(self):
        self._advance()
        return int(self._absolute_tick()) % self.loop_ticks if self._epoch is not None else 0

    @property
    def event_count(self):
        self._advance()
        return sum(self._projected_count(index) for index in range(TRACK_COUNT))

    def track_event_count(self, index):
        self._advance()
        return self._projected_count(index) if self._valid_track(index) else 0

    @staticmethod
    def _valid_track(index):
        return type(index) is int and 0 <= index < TRACK_COUNT

    def _now(self):
        now = float(self._clock())
        if not math.isfinite(now):
            now = self._last_now if self._last_now is not None else 0.0
        if self._last_now is not None:
            now = max(now, self._last_now)
        self._last_now = now
        return now

    def _start_epoch(self):
        self._epoch = self._now()
        self._last_absolute_tick = 0.0
        self._cursor_tick = -_EPSILON
        self._not_before.clear()

    def _absolute_tick(self):
        if self._epoch is None:
            return 0.0
        value = (self._now() - self._epoch) * self._data["bpm"] * TICKS_PER_BEAT / 60
        if not math.isfinite(value):
            return self._last_absolute_tick
        nearest = round(value)
        if abs(value - nearest) < _EPSILON:
            value = float(nearest)
        self._last_absolute_tick = max(value, self._last_absolute_tick)
        return self._last_absolute_tick

    def _advance(self):
        if (
            self._mode == "recording"
            and self._record_until is not None
            and self._absolute_tick() + _EPSILON >= self._record_until
        ):
            self._commit(self._record_until)

    def _projected_count(self, index):
        stored = len(self._data["tracks"][index]["events"])
        if self._mode == "recording" and index == self._record_track:
            return (stored if self._overdub else 0) + len(self._pending)
        return stored

    def _commit(self, when, *, live_hit=False):
        index = self._record_track
        if index is not None and self._pending:
            track = self._data["tracks"][index]
            if not self._overdub:
                for event in track["events"]:
                    self._not_before.pop(id(event), None)
            old = track["events"] if self._overdub else []
            pending = deepcopy(self._pending)
            for event in pending:
                self._not_before[id(event)] = when + (10 * _EPSILON if live_hit else 0)
            track["events"] = sorted([*old, *pending], key=lambda event: event["at_tick"])
            self._ticks[index] = [event["at_tick"] for event in track["events"]]
        self._pending = []
        self._record_track = self._record_until = None
        self._mode = "playing" if self._epoch is not None else "idle"

    def arm_recording(self, track, *, overdub=True):
        if not self._valid_track(track) or type(overdub) is not bool:
            return False
        self._advance()
        if self._mode == "recording":
            self._commit(self._absolute_tick(), live_hit=True)
        if self._epoch is None and any(item["events"] for item in self._data["tracks"]):
            self._start_epoch()
        self._record_track = track
        self._overdub = overdub
        self._pending = []
        self._record_until = None
        self.limited = False
        self._mode = "armed"
        return True

    def append(self, sound_snapshot):
        self._advance()
        if self._mode not in ("armed", "recording"):
            return False
        sound = _sound_snapshot(sound_snapshot)
        if sound is None:
            return False
        if self._epoch is None:
            self._start_epoch()
        absolute = self._absolute_tick()
        if self._mode == "armed":
            self._mode = "recording"
            self._record_until = absolute + self.loop_ticks
        count = self._projected_count(self._record_track)
        total = sum(self._projected_count(index) for index in range(TRACK_COUNT))
        if count >= MAX_TRACK_EVENTS or total >= MAX_LOOP_EVENTS:
            self.limited = True
            self._commit(absolute, live_hit=True)
            return False
        tick = (
            math.floor(absolute / _GRID + 0.5) * _GRID
            if self._data["quantize"] == "1/16"
            else math.floor(absolute + _EPSILON)
        ) % self.loop_ticks
        self._pending.append({"at_tick": int(tick), **sound})
        if count + 1 >= MAX_TRACK_EVENTS or total + 1 >= MAX_LOOP_EVENTS:
            self.limited = True
            self._commit(absolute, live_hit=True)
        return True

    def play(self):
        self.stop()
        if not any(track["events"] for track in self._data["tracks"]):
            return False
        self._start_epoch()
        self._mode = "playing"
        self.limited = False
        return True

    def stop(self):
        self._advance()
        if self._mode == "recording":
            self._commit(self._absolute_tick(), live_hit=True)
        self._mode = "idle"
        self._epoch = None
        self._record_track = self._record_until = None
        self._pending = []
        self._not_before.clear()

    def due_events(self):
        self._advance()
        if self._epoch is None or self._mode == "idle":
            return []
        now = self._absolute_tick()
        rate = self._data["bpm"] * TICKS_PER_BEAT / 60
        lower = max(self._cursor_tick + _EPSILON, now - rate * _STALE_SECONDS)
        first_cycle = max(0, math.floor(lower / self.loop_ticks))
        last_cycle = max(0, math.floor(now / self.loop_ticks))
        due = []
        # At most two cycles intersect the 100 ms freshness window, even after sleep.
        for cycle in range(first_cycle, last_cycle + 1):
            base = cycle * self.loop_ticks
            for index, track in enumerate(self._data["tracks"]):
                if track["muted"] or (
                    self._mode == "recording" and index == self._record_track and not self._overdub
                ):
                    continue
                ticks = self._ticks[index]
                left, right = bisect_left(ticks, lower - base), bisect_right(ticks, now - base)
                for offset in range(left, right):
                    event = track["events"][offset]
                    when = base + event["at_tick"]
                    if when <= self._cursor_tick:
                        continue
                    if when + _EPSILON < self._not_before.get(id(event), 0):
                        continue
                    volume = math.floor(event["volume"] * track["volume"] / 100 + 0.5)
                    if volume:
                        sound = {
                            key: event[key] for key in ("at_tick", "sound", "sound_path", "key_id")
                        }
                        due.append(
                            (when, index, offset, {**sound, "volume": volume, "track": index})
                        )
        self._cursor_tick = max(self._cursor_tick, now)
        due.sort(key=lambda item: item[:3])
        return [item[3] for item in due]

    def set_track_muted(self, index, muted):
        if not self._valid_track(index) or type(muted) is not bool:
            return False
        self._data["tracks"][index]["muted"] = muted
        return True

    def set_track_volume(self, index, volume):
        if not self._valid_track(index) or type(volume) is not int or not 0 <= volume <= 100:
            return False
        self._data["tracks"][index]["volume"] = volume
        return True

    def clear_track(self, index):
        self._advance()
        if not self._valid_track(index) or self._mode in ("armed", "recording"):
            return False
        for event in self._data["tracks"][index]["events"]:
            self._not_before.pop(id(event), None)
        self._data["tracks"][index]["events"] = []
        self._ticks[index] = []
        return True

    def configure(self, *, bpm=None, bars=None, quantize=None, truncate=False):
        self._advance()
        if self._mode != "idle" or type(truncate) is not bool:
            return False
        bpm = self._data["bpm"] if bpm is None else bpm
        bars = self._data["bars"] if bars is None else bars
        quantize = self._data["quantize"] if quantize is None else quantize
        if (
            type(bpm) is not int
            or not 40 <= bpm <= 240
            or type(bars) is not int
            or bars not in _BARS
            or quantize not in ("1/16", "off")
        ):
            return False
        maximum = bars * 4 * TICKS_PER_BEAT
        cutting = any(
            event["at_tick"] >= maximum
            for track in self._data["tracks"]
            for event in track["events"]
        )
        if cutting and not truncate:
            return False
        self._data.update(bpm=bpm, bars=bars, quantize=quantize)
        if cutting:
            for index, track in enumerate(self._data["tracks"]):
                track["events"] = [event for event in track["events"] if event["at_tick"] < maximum]
                self._ticks[index] = [event["at_tick"] for event in track["events"]]
        return True
