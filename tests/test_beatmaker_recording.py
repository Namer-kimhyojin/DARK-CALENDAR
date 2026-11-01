# -*- coding: utf-8 -*-
"""Recording boundaries, drift-free loops, suspended clocks and untrusted takes."""

from copy import deepcopy

import pytest

from calendar_app.domain.beatmaker_recording import (
    MAX_RECORDING_EVENTS,
    MAX_RECORDING_MS,
    BeatmakerTimeline,
    normalize_recording,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms / 1000


def hit(sound="beat_lofi_kick", at=0):
    return {"at_ms": at, "sound": sound, "sound_path": "", "volume": 80, "key_id": "pad"}


def take():
    return {"version": 1, "duration_ms": 1000, "events": [hit(), hit("beat_neon_snare", 500)]}


def test_first_pad_trims_wait_and_stop_preserves_trailing_silence_and_gain():
    clock = Clock()
    timeline = BeatmakerTimeline(clock=clock)
    timeline.start_recording()
    clock.advance(30_000)
    assert timeline.position_ms == 0
    assert timeline.append(hit())
    clock.advance(500)
    timeline.append(hit("beat_neon_snare"))
    clock.advance(500)
    timeline.stop()
    assert timeline.take == take()
    assert timeline.mode == "idle"
    assert timeline.position_ms == 0


def test_empty_attempt_keeps_previous_take_and_recording_does_not_mutate_source():
    source = take()
    timeline = BeatmakerTimeline(source)
    timeline.start_recording()
    timeline.stop()
    assert timeline.take == source
    timeline.take["events"][0]["volume"] = 10
    assert source["events"][0]["volume"] == 80
    timeline.clear()
    assert not timeline.play()
    assert timeline.take is None


def test_once_plays_each_hit_once_then_waits_for_tail():
    clock = Clock()
    timeline = BeatmakerTimeline(take(), clock=clock)
    assert timeline.play(repeat=False)
    assert timeline.due_events() == [hit()]
    assert timeline.due_events() == []
    clock.advance(500)
    assert timeline.due_events() == [hit("beat_neon_snare", 500)]
    assert timeline.mode == "playing"
    clock.advance(500)
    assert timeline.due_events() == []
    assert timeline.mode == "idle"


def test_loop_uses_epoch_not_timer_tick_so_jitter_does_not_accumulate():
    clock = Clock()
    timeline = BeatmakerTimeline(take(), clock=clock)
    timeline.play()
    assert timeline.due_events() == [hit()]
    for cycle in range(20):
        clock.now = 100 + cycle + 0.513
        assert timeline.due_events() == [hit("beat_neon_snare", 500)]
        clock.now = 100 + cycle + 1.007
        assert timeline.due_events() == [hit()]
        assert timeline.position_ms == 7
        assert timeline.due_events() == []
    timeline.stop()
    clock.advance(2000)
    assert timeline.due_events() == []


def test_resume_drops_stale_loops_instead_of_audio_burst():
    clock = Clock()
    timeline = BeatmakerTimeline(take(), clock=clock)
    timeline.play()
    timeline.due_events()
    clock.advance(120_050)
    assert timeline.due_events() == [hit()]
    assert timeline.due_events() == []
    clock.advance(450)
    assert timeline.due_events() == [hit("beat_neon_snare", 500)]


def test_simultaneous_pads_keep_order_and_do_not_duplicate_at_boundary():
    recording = take()
    recording["events"][1]["at_ms"] = 0
    clock = Clock()
    timeline = BeatmakerTimeline(recording, clock=clock)
    timeline.play()
    assert timeline.due_events() == recording["events"]
    clock.advance(1000)
    assert timeline.due_events() == recording["events"]
    assert timeline.due_events() == []


@pytest.mark.parametrize("boundary", ["time", "events"])
def test_recording_limits_commit_valid_take(boundary):
    clock = Clock()
    timeline = BeatmakerTimeline(clock=clock)
    timeline.start_recording()
    timeline.append(hit())
    if boundary == "time":
        clock.advance(MAX_RECORDING_MS)
        timeline.due_events()
        assert timeline.take["duration_ms"] == MAX_RECORDING_MS
    else:
        for _ in range(MAX_RECORDING_EVENTS - 1):
            timeline.append(hit())
        assert len(timeline.take["events"]) == MAX_RECORDING_EVENTS
    assert timeline.mode == "idle"
    assert timeline.limited
    assert normalize_recording(timeline.take) == timeline.take
    assert not timeline.append(hit())


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 2),
        ("duration_ms", True),
        ("duration_ms", 99),
        ("duration_ms", MAX_RECORDING_MS + 1),
        ("events", []),
        ("events", [None]),
        ("events", [hit()] * (MAX_RECORDING_EVENTS + 1)),
    ],
)
def test_invalid_take_is_rejected_as_a_whole(field, value):
    recording = take()
    recording[field] = value
    assert normalize_recording(recording) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("at_ms", -1),
        ("at_ms", 1000),
        ("at_ms", True),
        ("volume", float("nan")),
        ("volume", 101),
        ("volume", True),
        ("sound", {}),
        ("sound", "../launch.exe"),
        ("sound", "auto"),
        ("sound", "none"),
        ("sound_path", "x\0.wav"),
        ("key_id", []),
    ],
)
def test_invalid_event_never_reaches_audio(field, value):
    recording = take()
    recording["events"][0][field] = value
    assert normalize_recording(recording) is None


def test_normalization_strips_actions_and_rejects_out_of_order_and_non_wav():
    recording = take()
    recording["events"][0]["action"] = {"type": "hotkey", "target": "Ctrl+W"}
    assert "action" not in normalize_recording(recording)["events"][0]
    recording["events"].reverse()
    assert normalize_recording(recording) is None
    recording = take()
    recording["events"][0].update(sound="custom", sound_path="C:/file.exe")
    assert normalize_recording(recording) is None


def test_custom_sound_references_survive_and_outputs_are_independent():
    recording = take()
    recording["events"][0].update(sound="custom", sound_path="asset:" + "a" * 64)
    assert normalize_recording(recording) == recording
    result = normalize_recording(recording)
    result["events"][0]["volume"] = 1
    assert recording["events"][0]["volume"] == 80


def test_new_take_replaces_only_after_valid_note_and_stop():
    original = take()
    timeline = BeatmakerTimeline(original)
    timeline.start_recording()
    assert timeline.take == original
    timeline.append(hit("beat_arcade_clap"))
    assert timeline.take == original
    timeline.stop()
    assert timeline.take["events"][0]["sound"] == "beat_arcade_clap"
    assert original == take()
