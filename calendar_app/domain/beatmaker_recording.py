# -*- coding: utf-8 -*-
"""Bounded, sound-only performances and an absolute-time recording/playback clock."""

from bisect import bisect_left
from copy import deepcopy
import re
import time

MAX_RECORDING_MS = 300_000
MAX_RECORDING_EVENTS = 4096
_SOUND_ID = re.compile(r"[a-z0-9_]{1,80}\Z")


def normalize_recording(raw: object) -> dict | None:
    """Reject corrupt/future takes as a whole; never accept executable key actions."""
    if not isinstance(raw, dict) or type(raw.get("version")) is not int or raw["version"] != 1:
        return None
    duration = raw.get("duration_ms")
    events = raw.get("events")
    if (
        type(duration) is not int
        or not 100 <= duration <= MAX_RECORDING_MS
        or not isinstance(events, list)
        or not 1 <= len(events) <= MAX_RECORDING_EVENTS
    ):
        return None
    clean = []
    previous = -1
    for event in events:
        if not isinstance(event, dict):
            return None
        at = event.get("at_ms")
        volume = event.get("volume")
        sound = event.get("sound")
        path = event.get("sound_path", "")
        key_id = event.get("key_id", "")
        if (
            type(at) is not int
            or not 0 <= at < duration
            or at < previous
            or type(volume) is not int
            or not 0 <= volume <= 100
            or not isinstance(sound, str)
            or not _SOUND_ID.fullmatch(sound)
            or sound in {"none", "auto", "switch"}
            or not isinstance(path, str)
            or len(path) > 1024
            or "\0" in path
            or not isinstance(key_id, str)
            or len(key_id) > 80
            or (
                sound == "custom"
                and not path.lower().endswith(".wav")
                and not path.startswith("asset:")
            )
        ):
            return None
        clean.append(
            {
                "at_ms": at,
                "sound": sound,
                "sound_path": path if sound == "custom" else "",
                "volume": volume,
                "key_id": key_id,
            }
        )
        previous = at
    return {"version": 1, "duration_ms": duration, "events": clean}


class BeatmakerTimeline:
    """One replaceable take. Empty attempts preserve the previous recording.

    Timing starts at the first pad; the trailing interval ends when Stop is pressed.
    Repeated playback uses the original epoch, so timer jitter cannot accumulate drift.
    A suspended UI skips old hits instead of bursting through missed loops on resume.
    """

    def __init__(self, recording=None, *, clock=time.monotonic):
        self.take = normalize_recording(recording)
        self.mode = "idle"
        self.repeat = True
        self.limited = False
        self._clock = clock
        self._started = None
        self._pending = []
        self._cycle = 0
        self._index = 0

    @property
    def position_ms(self) -> int:
        if self._started is None:
            return 0
        elapsed = max(0, int(round((self._clock() - self._started) * 1000)))
        if self.mode == "recording":
            return min(MAX_RECORDING_MS, elapsed)
        if self.take:
            return (
                elapsed % self.take["duration_ms"]
                if self.repeat
                else min(elapsed, self.take["duration_ms"])
            )
        return 0

    @property
    def event_count(self) -> int:
        return (
            len(self._pending)
            if self.mode == "recording"
            else len(self.take["events"])
            if self.take
            else 0
        )

    def start_recording(self) -> None:
        self.stop()
        self.mode = "recording"
        self.limited = False
        self._pending = []
        self._started = None

    def append(self, snapshot: dict) -> bool:
        if self.mode != "recording":
            return False
        at = self.position_ms
        event = {**snapshot, "at_ms": at}
        probe = normalize_recording(
            {"version": 1, "duration_ms": max(100, at + 1), "events": [event]}
        )
        if probe is None:
            if at >= MAX_RECORDING_MS:
                self.limited = True
                self.stop()
            return False
        if self._started is None:
            self._started = self._clock()
        self._pending.append(probe["events"][0])
        if len(self._pending) == MAX_RECORDING_EVENTS:
            self.limited = True
            self.stop()
        return True

    def stop(self) -> None:
        if self.mode == "recording" and self._pending:
            duration = max(100, self.position_ms, self._pending[-1]["at_ms"] + 1)
            self.take = {
                "version": 1,
                "duration_ms": min(MAX_RECORDING_MS, duration),
                "events": deepcopy(self._pending),
            }
        self.mode = "idle"
        self._started = None
        self._pending = []

    def play(self, *, repeat=True) -> bool:
        self.stop()
        if not self.take:
            return False
        self.repeat = bool(repeat)
        self.mode = "playing"
        self._started = self._clock()
        self._cycle = self._index = 0
        return True

    def clear(self) -> None:
        self.stop()
        self.take = None
        self.limited = False

    def due_events(self) -> list[dict]:
        if self.mode == "recording":
            if self.position_ms >= MAX_RECORDING_MS:
                self.limited = True
                self.stop()
            return []
        if self.mode != "playing":
            return []
        elapsed = max(0, int(round((self._clock() - self._started) * 1000)))
        duration, events = self.take["duration_ms"], self.take["events"]
        cycle = elapsed // duration
        if self.repeat and cycle > self._cycle + 1:
            self._cycle = cycle
            self._index = bisect_left(
                [event["at_ms"] for event in events], max(0, elapsed % duration - 100)
            )
        due = []
        # At most two cycles can be relevant after discarding suspended time.
        for _ in range(len(events) * 2 + 1):
            if self._index == len(events):
                if not self.repeat:
                    if elapsed >= duration:
                        self.stop()
                    break
                self._cycle += 1
                self._index = 0
            event = events[self._index]
            when = self._cycle * duration + event["at_ms"]
            if when > elapsed:
                break
            if elapsed - when <= 100:
                due.append(deepcopy(event))
            self._index += 1
        return due
