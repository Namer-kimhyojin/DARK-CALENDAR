# -*- coding: utf-8 -*-
"""Deterministic PCM contracts; no devices, Qt, clocks or personal data."""

from array import array

import pytest

from calendar_app.domain import loop_mixer as mix


def stereo(left=1000, right=None, frames=16):
    return array("h", [left, left if right is None else right]) * frames


def small_state(monkeypatch):
    monkeypatch.setattr(mix, "loop_length", lambda _bpm, _bars: 16)
    result = mix.LoopMixerState()
    result.master_volume = 100
    return result


@pytest.mark.parametrize("bpm,bars", [(40, 8), (120, 1), (240, 1)])
def test_frame_length_is_exact_bounded_musical_duration(bpm, bars):
    frames = mix.loop_length(bpm, bars)
    assert frames == round(mix.SAMPLE_RATE * 240 * bars / bpm)
    assert 0 < frames <= mix.MAX_FRAMES


@pytest.mark.parametrize("bpm,bars", [(39, 1), (241, 1), (120, 3), (True, 1), (120, True)])
def test_invalid_tempo_rejects_instead_of_allocating(bpm, bars):
    with pytest.raises(ValueError):
        mix.loop_length(bpm, bars)


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2])
def test_integer_pcm_conversion_keeps_sign_and_channel_order(width, channels):
    values = (
        [32, 224]
        if width == 1
        else [-1000 * 256 ** max(0, width - 2), 1000 * 256 ** max(0, width - 2)]
    )
    raw = b"".join(
        bytes([value]) if width == 1 else value.to_bytes(width, "little", signed=True)
        for value in values
        for _channel in range(channels)
    )
    result = mix.convert_pcm(raw, channels, width, mix.SAMPLE_RATE)
    expected = [-24576, -24576, 24576, 24576] if width == 1 else [-1000, -1000, 1000, 1000]
    assert list(result) == expected
    assert mix.pcm_samples(mix.pcm_bytes(result)) == result


def test_44100_downsampling_is_frame_based_and_preserves_stereo():
    source = array("h", [100, -100, 200, -200, 300, -300, 400, -400])
    assert list(mix.convert_pcm(mix.pcm_bytes(source), 2, 2, 44100)) == [100, -100, 300, -300]


@pytest.mark.parametrize(
    "channels,width,rate,raw",
    [
        (3, 2, 22050, b"123456"),
        (1, 5, 22050, b"12345"),
        (1, 2, 0, b"12"),
        (1, 2, 22050, b"1"),
        (1, 2, 22050, b""),
    ],
)
def test_malformed_pcm_rejects(channels, width, rate, raw):
    with pytest.raises(ValueError):
        mix.convert_pcm(raw, channels, width, rate)


def test_mixer_sum_master_pan_mute_and_solo_are_applied_once(monkeypatch):
    state = small_state(monkeypatch)
    for index in range(2):
        state.load_audio(index, stereo(1000))
    state.set_track(0, volume=50, pan=-100)
    state.set_track(1, volume=100, pan=100)
    state.master_volume = 50
    state.play()
    assert list(mix.pcm_samples(state.render(1))) == [250, 500]
    state.set_track(1, muted=True)
    assert list(mix.pcm_samples(state.render(1))) == [250, 0]
    state.set_track(0, solo=True)
    state.set_track(1, muted=False)
    assert list(mix.pcm_samples(state.render(1))) == [250, 0]


def test_summing_saturates_without_integer_overflow(monkeypatch):
    state = small_state(monkeypatch)
    for index in range(6):
        state.load_audio(index, stereo(30000, -30000))
    state.play()
    assert list(mix.pcm_samples(state.render(1))) == [32767, -32768]


def test_simultaneous_mic_and_keydeck_record_pre_fader_with_no_mic_monitor(monkeypatch):
    state = small_state(monkeypatch)
    state.set_track(0, source="mic", armed=True, muted=True, volume=0)
    state.set_track(1, source="launcher_deck_0", armed=True, volume=50)
    state.record()
    state.add_voice("launcher_deck_0", stereo(4000), 0.5)
    output = mix.pcm_samples(state.render(16, mix.pcm_bytes(stereo(1000))))
    assert set(output) == {1000}  # Only live deck gain .5 and track gain .5, never mic.
    assert state.mode == "playing" and state.position_frames == 0
    assert set(state.tracks[0].audio) == {1000}
    assert set(state.tracks[1].audio) == {2000}
    state.set_track(0, muted=False, volume=100)
    assert list(mix.pcm_samples(state.render(1))) == [2000, 2000]


def test_overdub_and_replacement_commit_once_and_preserve_other_layers(monkeypatch):
    state = small_state(monkeypatch)
    state.load_audio(0, stereo(1000))
    state.load_audio(1, stereo(500))
    state.set_track(0, source="mic", armed=True)
    state.play()
    state.render(5)
    state.record(overdub=True)
    assert state.position_frames == 5
    state.render(16, mix.pcm_bytes(stereo(200)))
    assert set(state.tracks[0].audio) == {1200}
    assert set(state.tracks[1].audio) == {500}
    state.record(overdub=False)
    state.render(16, mix.pcm_bytes(stereo(300)))
    assert set(state.tracks[0].audio) == {300}
    assert set(state.tracks[1].audio) == {500}


def test_failed_or_empty_arm_does_not_replace_committed_audio(monkeypatch):
    state = small_state(monkeypatch)
    state.load_audio(0, stereo(1000))
    with pytest.raises(ValueError, match="no_armed_tracks"):
        state.record()
    state.set_track(0, source="mic", armed=True)
    state.record()
    state.render(3, mix.pcm_bytes(stereo(200, frames=3)))
    state.stop(commit=False)
    assert set(state.tracks[0].audio) == {1000}


def test_stop_commits_partial_take_once_and_clear_is_track_local(monkeypatch):
    state = small_state(monkeypatch)
    state.set_track(0, source="mic", armed=True)
    state.load_audio(1, stereo(500))
    state.record()
    state.render(3, mix.pcm_bytes(stereo(200, frames=3)))
    state.stop()
    assert list(state.tracks[0].audio[:6]) == [200] * 6
    assert not any(state.tracks[0].audio[6:])
    state.stop()
    state.clear_track(0)
    assert not state.tracks[0].audio and set(state.tracks[1].audio) == {500}


def test_tempo_view_changes_preserve_full_committed_clip_and_snapshot_is_independent():
    state = mix.LoopMixerState()
    original = stereo(frames=100)
    state.load_audio(0, original)
    state.configure(240, 1)
    state.configure(40, 8)
    assert state.tracks[0].audio == original
    snapshot = state.snapshot()
    snapshot["tracks"][0]["peaks"].clear()
    snapshot["tracks"][0]["volume"] = 0
    assert state.snapshot()["tracks"][0]["peaks"]
    assert state.tracks[0].volume == 100


@pytest.mark.parametrize("start, frames", [(0, 3), (5, 3), (14, 4)])
@pytest.mark.parametrize("existing_frames", [0, 7, 16])
def test_partial_overdub_preserves_unvisited_audio(monkeypatch, start, frames, existing_frames):
    state = small_state(monkeypatch)
    original = stereo(1000, -500, frames=existing_frames)
    state.load_audio(0, original)
    state.load_audio(1, stereo(500))
    state.set_track(0, source="mic", armed=True)
    state.play()
    if start:
        state.render(start)
    state.record(overdub=True)
    state.render(frames, mix.pcm_bytes(stereo(200, 100, frames=frames)))
    # Pending audio must not mutate the committed clip before Stop.
    assert state.tracks[0].audio == original
    state.stop()
    expected = array("h", original)
    expected.extend([0] * (32 - len(expected)))
    for offset in range(frames):
        index = ((start + offset) % 16) * 2
        expected[index] += 200
        expected[index + 1] += 100
    assert state.tracks[0].audio == expected
    assert state.tracks[1].audio == stereo(500)
    state.stop()
    assert state.tracks[0].audio == expected


def test_cancelled_partial_overdub_preserves_original_audio(monkeypatch):
    state = small_state(monkeypatch)
    original = stereo(1000, -500)
    state.load_audio(0, original)
    state.set_track(0, source="mic", armed=True)
    state.record(overdub=True)
    state.render(3, mix.pcm_bytes(stereo(200, frames=3)))
    state.stop(commit=False)
    assert state.tracks[0].audio == original


def test_partial_replacement_still_clears_old_unrecorded_audio(monkeypatch):
    state = small_state(monkeypatch)
    state.load_audio(0, stereo(1000))
    state.set_track(0, source="mic", armed=True)
    state.record(overdub=False)
    state.render(3, mix.pcm_bytes(stereo(200, frames=3)))
    state.stop()
    assert state.tracks[0].audio == stereo(200, frames=3) + stereo(0, frames=13)


def test_voice_and_frame_clock_bounds_prevent_catchup_or_unbounded_live_data(monkeypatch):
    state = small_state(monkeypatch)
    state.set_track(0, source="launcher_deck_0")
    state.play()
    for _ in range(100):
        state.add_voice("launcher_deck_0", stereo(), 1)
    assert len(state._voices) == mix.MAX_VOICES
    for _ in range(100):
        state.render(7)
    assert state.position_frames == 700 % 16
    state.stop_source("launcher_deck_0")
    assert not state._voices and state.mode == "playing"


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "../../app.exe"},
        {"armed": 1},
        {"volume": True},
        {"pan": 101},
        {"name": ""},
        {"executable": "app.exe"},
    ],
)
def test_track_validation_is_transactional(changes):
    state = mix.LoopMixerState()
    before = state.snapshot()
    with pytest.raises(ValueError):
        state.set_track(0, **changes)
    assert state.snapshot() == before
