# -*- coding: utf-8 -*-
"""Fake-clock transport, transactional layers, bounded input and sound-only output."""

from copy import deepcopy

import pytest

from calendar_app.domain import beatmaker_looper as looper
from calendar_app.domain.beatmaker_looper import (
    MAX_LOOP_EVENTS,
    MAX_TRACK_EVENTS,
    TICKS_PER_BEAT,
    BeatmakerLooperTimeline,
    default_looper,
    normalize_looper,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, milliseconds):
        self.now += milliseconds / 1000


def hit(sound="beat_lofi_kick", tick=0, volume=80, **extra):
    return {
        "at_tick": tick,
        "sound": sound,
        "sound_path": "",
        "volume": volume,
        "key_id": "pad",
        **extra,
    }


def project():
    value = default_looper()
    value["tracks"][0]["events"] = [hit(), hit("beat_neon_snare", 960)]
    return value


def sounds(events):
    return [(event["track"], event["sound"], event["at_tick"], event["volume"]) for event in events]


def test_first_pad_starts_an_empty_clock_and_commits_exactly_one_turn_later():
    first, second = default_looper(), default_looper()
    first["tracks"][0]["volume"] = 25
    assert second["tracks"][0]["volume"] == 100
    assert normalize_looper(second) == second
    clock = Clock()
    timeline = BeatmakerLooperTimeline(clock=clock)
    assert not timeline.play()
    assert timeline.arm_recording(0)
    clock.advance(60000)
    assert timeline.mode == "armed" and timeline.position_ticks == 0
    assert timeline.due_events() == []
    assert timeline.append(hit())
    assert timeline.mode == "recording" and timeline.record_track == 0
    assert timeline.event_count == timeline.track_event_count(0) == 1
    assert timeline.data["tracks"][0]["events"] == []
    assert timeline.due_events() == []
    clock.advance(1999)
    assert timeline.mode == "recording"
    clock.advance(1)
    assert timeline.mode == "playing" and timeline.record_track is None
    assert sounds(timeline.due_events()) == [(0, "beat_lofi_kick", 0, 80)]
    assert timeline.due_events() == []
    assert timeline.position_ticks == 0
    assert normalize_looper(timeline.data) == timeline.data


def test_empty_arm_or_invalid_pad_preserves_previous_data_and_source_is_independent():
    source = project()
    original = deepcopy(source)
    clock = Clock()
    timeline = BeatmakerLooperTimeline(source, clock=clock)
    assert timeline.arm_recording(0, overdub=False)
    assert not timeline.append({"sound": "none", "volume": 80})
    assert timeline.mode == "armed"
    clock.advance(500)
    timeline.stop()
    assert timeline.data == original and source == original
    timeline.data["tracks"][0]["events"][0]["volume"] = 3
    assert source == original


def test_layer_recording_keeps_the_existing_epoch_and_waits_a_full_turn_from_first_pad():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.play()
    assert len(timeline.due_events()) == 1
    clock.advance(500)
    assert sounds(timeline.due_events()) == [(0, "beat_neon_snare", 960, 80)]
    timeline.arm_recording(1)
    clock.advance(250)
    timeline.append(hit("beat_neon_hat"))
    assert timeline.position_ticks == 1440 and timeline.due_events() == []
    clock.advance(1250)
    assert timeline.mode == "recording"
    assert sounds(timeline.due_events()) == [(0, "beat_lofi_kick", 0, 80)]
    clock.advance(750)
    assert timeline.mode == "playing"
    assert sounds(timeline.due_events()) == [(1, "beat_neon_hat", 1440, 80)]
    assert timeline.position_ticks == 1440


def test_overdub_merges_stably_without_echoing_live_pending_pads():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.arm_recording(0)
    assert sounds(timeline.due_events()) == [(0, "beat_lofi_kick", 0, 80)]
    timeline.append(hit("beat_neon_hat"))
    assert timeline.due_events() == [] and timeline.track_event_count(0) == 3
    clock.advance(2000)
    assert sounds(timeline.due_events()) == [
        (0, "beat_lofi_kick", 0, 80),
        (0, "beat_neon_hat", 0, 80),
    ]
    assert [event["sound"] for event in timeline.data["tracks"][0]["events"]] == [
        "beat_lofi_kick",
        "beat_neon_hat",
        "beat_neon_snare",
    ]


def test_replace_is_transactional_and_suppresses_only_selected_track_after_first_pad():
    raw = project()
    raw["tracks"][1]["events"] = [hit("beat_neon_hat", 960)]
    original = deepcopy(raw)
    clock = Clock()
    timeline = BeatmakerLooperTimeline(raw, clock=clock)
    timeline.arm_recording(0, overdub=False)
    assert len(timeline.due_events()) == 1
    clock.advance(250)
    timeline.append(hit("beat_tom"))
    assert timeline.data == original and timeline.track_event_count(0) == 1
    clock.advance(250)
    assert sounds(timeline.due_events()) == [(1, "beat_neon_hat", 960, 80)]
    timeline.stop()
    assert timeline.mode == "idle"
    assert timeline.data["tracks"][0]["events"] == [hit("beat_tom", 480)]
    assert timeline.data["tracks"][1] == original["tracks"][1]
    assert raw == original


@pytest.mark.parametrize("quantize,expected", [("1/16", 240), ("off", 190)])
def test_grid_and_off_record_absolute_shared_phase(quantize, expected):
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    assert timeline.configure(quantize=quantize)
    timeline.arm_recording(1)
    clock.advance(99)
    timeline.append(hit("beat_clap"))
    timeline.stop()
    assert timeline.data["tracks"][1]["events"][0]["at_tick"] == expected


def test_quantizing_near_loop_end_wraps_and_never_backfills_before_commit():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.play()
    timeline.due_events()
    clock.advance(1990)
    timeline.arm_recording(1)
    timeline.append(hit("beat_clap"))
    clock.advance(2000)
    assert timeline.mode == "playing"
    assert not any(event["track"] == 1 for event in timeline.due_events())
    clock.advance(10)
    assert any(event["track"] == 1 and event["at_tick"] == 0 for event in timeline.due_events())


def test_mute_gain_and_clear_preserve_other_track_phase():
    raw = project()
    raw["tracks"][1]["events"] = [hit("beat_hat", volume=49)]
    clock = Clock()
    timeline = BeatmakerLooperTimeline(raw, clock=clock)
    timeline.set_track_muted(0, True)
    timeline.set_track_volume(1, 50)
    timeline.play()
    assert sounds(timeline.due_events()) == [(1, "beat_hat", 0, 25)]
    timeline.set_track_muted(0, False)
    assert timeline.due_events() == []
    clock.advance(500)
    assert timeline.due_events()[0]["sound"] == "beat_neon_snare"
    assert timeline.clear_track(1)
    assert timeline.mode == "playing" and timeline.position_ticks == 960
    clock.advance(1500)
    assert sounds(timeline.due_events()) == [(0, "beat_lofi_kick", 0, 80)]
    timeline.set_track_volume(0, 0)
    clock.advance(500)
    assert timeline.due_events() == []


def test_tempo_keeps_ticks_and_bar_shrink_requires_explicit_truncation():
    raw = project()
    raw["bars"] = 2
    raw["tracks"][0]["events"].append(hit("beat_end", 5000))
    timeline = BeatmakerLooperTimeline(raw)
    assert timeline.configure(bpm=60)
    assert timeline.data["tracks"] == raw["tracks"] and timeline.duration_ms == 8000
    before = deepcopy(timeline.data)
    assert not timeline.configure(bpm=140, bars=1)
    assert timeline.data == before
    assert timeline.configure(bpm=140, bars=1, truncate=True)
    assert [event["at_tick"] for event in timeline.data["tracks"][0]["events"]] == [0, 960]
    timeline.play()
    assert not timeline.configure(bpm=120)
    timeline.arm_recording(2)
    assert not timeline.clear_track(0) and not timeline.configure(quantize="off")


def test_absolute_epoch_orders_boundary_hits_and_poll_jitter_never_accumulates():
    raw = project()
    raw["tracks"][0]["events"] = [hit("a"), hit("b", 3840 - 24)]
    raw["tracks"][1]["events"] = [hit("c")]
    clock = Clock()
    timeline = BeatmakerLooperTimeline(raw, clock=clock)
    timeline.play()
    assert [event["sound"] for event in timeline.due_events()] == ["a", "c"]
    for cycle in range(20):
        clock.now = 100 + (cycle + 1) * 2 + 0.007
        assert [event["sound"] for event in timeline.due_events()] == ["b", "a", "c"]
        assert timeline.position_ticks == 13 and timeline.due_events() == []


def test_suspend_skips_billions_of_old_loops_and_stale_hits_without_a_burst():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.play()
    timeline.due_events()
    clock.advance(2_000_000_000_050)
    assert sounds(timeline.due_events()) == [(0, "beat_lofi_kick", 0, 80)]
    assert timeline.due_events() == []
    clock.advance(450)
    assert sounds(timeline.due_events()) == [(0, "beat_neon_snare", 960, 80)]


@pytest.mark.parametrize("delay,expected", [(100, 1), (101, 0)])
def test_exact_freshness_boundary_discards_hits_older_than_100_ms(delay, expected):
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.play()
    clock.advance(delay)
    assert len(timeline.due_events()) == expected
    assert timeline.due_events() == []


def test_recording_resume_commits_once_and_only_plays_the_current_fresh_cycle():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(clock=clock)
    timeline.arm_recording(0)
    timeline.append(hit())
    clock.advance(2_000_000_000_050)
    assert sounds(timeline.due_events()) == [(0, "beat_lofi_kick", 0, 80)]
    assert timeline.mode == "playing" and timeline.event_count == 1
    assert timeline.due_events() == []


def test_commit_does_not_catch_up_a_quantized_hit_before_its_activation_phase():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.play()
    timeline.due_events()
    clock.advance(50)
    timeline.arm_recording(1)
    timeline.append(hit("beat_hat"))
    clock.advance(2000)
    assert timeline.mode == "playing"
    assert not any(event["track"] == 1 for event in timeline.due_events())
    clock.advance(1950)
    assert any(event["track"] == 1 for event in timeline.due_events())


def test_due_events_are_independent_sound_snapshots_without_executable_actions():
    raw = project()
    raw["tracks"][0]["events"][0]["action"] = {"type": "command", "target": "cmd.exe"}
    clock = Clock()
    timeline = BeatmakerLooperTimeline(raw, clock=clock)
    timeline.play()
    events = timeline.due_events()
    assert set(events[0]) == {"at_tick", "sound", "sound_path", "volume", "key_id", "track"}
    events[0]["volume"] = 1
    assert timeline.data["tracks"][0]["events"][0]["volume"] == 80
    assert "action" not in timeline.data["tracks"][0]["events"][0]


def test_backwards_or_nonfinite_clock_never_duplicates_or_moves_progress_backwards():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project(), clock=clock)
    timeline.play()
    timeline.due_events()
    clock.advance(500)
    assert timeline.due_events()[0]["at_tick"] == 960
    for value in (99.0, float("nan"), float("inf"), 100.4):
        clock.now = value
        assert timeline.due_events() == [] and timeline.position_ticks == 960
    clock.now = 102.0
    assert timeline.due_events()[0]["at_tick"] == 0


@pytest.mark.parametrize("cap", ["track", "project"])
def test_caps_commit_pending_and_do_not_replay_the_final_live_hit(cap, monkeypatch):
    monkeypatch.setattr(looper, "MAX_TRACK_EVENTS", 3)
    monkeypatch.setattr(looper, "MAX_LOOP_EVENTS", 4 if cap == "project" else 12)
    clock = Clock()
    timeline = BeatmakerLooperTimeline(project() if cap == "project" else None, clock=clock)
    timeline.arm_recording(1)
    count = 2 if cap == "project" else 3
    for _ in range(count):
        assert timeline.append(hit("beat_clap"))
    assert timeline.mode == "playing" and timeline.limited
    assert timeline.track_event_count(1) == count
    assert not timeline.append(hit())
    assert all(event["track"] != 1 for event in timeline.due_events())
    clock.advance(2000)
    assert len([event for event in timeline.due_events() if event["track"] == 1]) == count
    assert normalize_looper(timeline.data) == timeline.data


def test_switching_record_track_commits_partial_without_resetting_phase():
    clock = Clock()
    timeline = BeatmakerLooperTimeline(clock=clock)
    timeline.arm_recording(0)
    timeline.append(hit())
    clock.advance(500)
    timeline.arm_recording(1)
    assert timeline.mode == "armed" and timeline.position_ticks == 960
    assert timeline.data["tracks"][0]["events"] == [hit()]
    timeline.append(hit("beat_hat"))
    timeline.stop()
    assert timeline.data["tracks"][1]["events"] == [hit("beat_hat", 960)]


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 2),
        ("version", "1"),
        ("bpm", True),
        ("bpm", 39),
        ("bpm", 241),
        ("bpm", 120.0),
        ("bars", True),
        ("bars", 3),
        ("quantize", "1/8"),
        ("tracks", []),
        ("tracks", [None] * 4),
    ],
)
def test_corrupt_or_future_projects_reject_as_a_whole(field, value):
    raw = project()
    raw[field] = value
    assert normalize_looper(raw) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("muted", 1),
        ("muted", "false"),
        ("volume", True),
        ("volume", -1),
        ("volume", 101),
        ("events", None),
        ("events", [None]),
        ("events", [hit()] * (MAX_TRACK_EVENTS + 1)),
    ],
)
def test_invalid_tracks_reject_as_a_whole(field, value):
    raw = project()
    raw["tracks"][0][field] = value
    assert normalize_looper(raw) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("at_tick", True),
        ("at_tick", -1),
        ("at_tick", 3840),
        ("at_tick", 1.0),
        ("volume", True),
        ("volume", 101),
        ("sound", "none"),
        ("sound", "auto"),
        ("sound", "switch"),
        ("sound", "../run.exe"),
        ("sound_path", "x\0.wav"),
        ("key_id", []),
    ],
)
def test_invalid_sound_snapshots_or_ticks_reject(field, value):
    raw = project()
    raw["tracks"][0]["events"][0][field] = value
    assert normalize_looper(raw) is None


def test_actions_are_stripped_custom_assets_survive_and_unsorted_or_non_wav_reject():
    raw = project()
    raw["tracks"][0]["events"].reverse()
    assert normalize_looper(raw) is None
    raw = project()
    raw["tracks"][0]["events"][0].update(sound="custom", sound_path="C:/tool.exe")
    assert normalize_looper(raw) is None
    raw["tracks"][0]["events"][0].update(sound_path="asset:" + "a" * 64, action={"type": "command"})
    original = deepcopy(raw)
    clean = normalize_looper(raw)
    assert "action" not in clean["tracks"][0]["events"][0]
    assert clean["tracks"][0]["events"][0]["sound_path"].startswith("asset:")
    assert raw == original


def test_maximum_project_and_invalid_public_edits_are_bounded():
    raw = default_looper()
    for track in raw["tracks"]:
        track["events"] = [hit() for _ in range(MAX_TRACK_EVENTS)]
    assert sum(len(track["events"]) for track in raw["tracks"]) == MAX_LOOP_EVENTS
    assert normalize_looper(raw) == raw
    timeline = BeatmakerLooperTimeline()
    for invalid in (True, -1, 4, None):
        assert not timeline.arm_recording(invalid)
        assert not timeline.set_track_muted(invalid, False)
        assert not timeline.set_track_volume(invalid, 50)
        assert not timeline.clear_track(invalid)
        assert timeline.track_event_count(invalid) == 0
    assert not timeline.set_track_muted(0, 1) and not timeline.set_track_volume(0, True)
    for kwargs in ({"bpm": True}, {"bars": 3}, {"quantize": "bad"}, {"truncate": 1}):
        assert not timeline.configure(**kwargs)
    assert timeline.loop_ticks == 4 * TICKS_PER_BEAT
