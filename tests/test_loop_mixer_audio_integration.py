# -*- coding: utf-8 -*-
"""Synthetic source buses, microphone PCM and disposable WAVs; no audio devices."""

from array import array
import wave

from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.domain import loop_mixer as domain
from calendar_app.infrastructure.runtime import loop_mixer_audio as audio


@pytest.fixture(scope="session", autouse=True)
def application_lifetime():
    # Keep Qt alive across controller tests and later widget-entry fixtures.
    application = QApplication.instance() or QApplication([])
    yield application


def _pcm(value, frames):
    return domain.pcm_bytes(array("h", [value, value]) * frames)


def _wav(path, value, frames):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(domain.SAMPLE_RATE)
        output.writeframes(_pcm(value, frames))
    return path


@pytest.fixture
def mixers(monkeypatch):
    values = []

    def forbidden():
        raise AssertionError("Synthetic integration must never open a physical device")

    monkeypatch.setattr(audio, "_winmm", forbidden)

    def create(**kwargs):
        value = audio.LoopMixer(threaded=False, **kwargs)
        values.append(value)
        return value

    yield create
    for value in values:
        value.shutdown()


@pytest.mark.parametrize("overdub", [False, True])
def test_backing_wav_is_not_rerecorded_when_a_microphone_take_is_armed(
    mixers, monkeypatch, tmp_path, overdub
):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: 16)
    mixer = mixers()
    assert mixer.load_wav(0, _wav(tmp_path / "backing.wav", 1000, 16))
    # Loading a WAV retains the user's arm flag; it still is a playback source.
    assert mixer.set_track(0, armed=True)
    assert mixer.set_track(1, source="mic", armed=True)
    assert mixer.record(overdub=overdub)
    heard = domain.pcm_samples(mixer._process_block(_pcm(200, 16), frames=16))
    assert set(heard) == {800}
    assert mixer.snapshot()["mode"] == "playing"
    assert set(mixer._state.tracks[0].audio) == {1000}
    assert set(mixer._state.tracks[1].audio) == {200}
    assert mixer.snapshot()["tracks"][0]["armed"] is True


def test_only_backing_wav_armed_rejects_capture_without_changing_the_clip(
    mixers, monkeypatch, tmp_path
):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: 16)
    mixer = mixers()
    assert mixer.load_wav(0, _wav(tmp_path / "backing.wav", 1000, 16))
    assert mixer.set_track(0, armed=True)
    assert not mixer.record(overdub=True)
    assert mixer.snapshot()["error_code"] == "no_armed_tracks"
    assert mixer.snapshot()["mode"] == "idle"
    assert set(mixer._state.tracks[0].audio) == {1000}
    assert audio._active() is None


def test_two_keydecks_and_mic_record_loop_overdub_mix_export_and_restore(
    mixers, monkeypatch, tmp_path
):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: 16)
    mixer = mixers()
    a = _wav(tmp_path / "deck-a.wav", 800, 16)
    b = _wav(tmp_path / "deck-b.wav", 1200, 16)
    assert mixer.set_master_volume(100)
    assert mixer.set_track(0, source="launcher_deck_11", armed=True)
    assert mixer.set_track(1, source="launcher_deck_29", armed=True)
    assert mixer.set_track(2, source="mic", armed=True)
    assert mixer.load_wav(3, _wav(tmp_path / "backing.wav", 200, 16))
    assert mixer.record()
    assert audio.route_keydeck_sound("launcher_deck_11", a, 0.5)
    assert audio.route_keydeck_sound("launcher_deck_29", b, 0.25)
    assert not audio.route_keydeck_sound("launcher_deck_30", a, 1)
    # Live pads hear each source exactly once; microphone monitoring stays off.
    assert set(domain.pcm_samples(mixer._process_block(_pcm(400, 16), frames=16))) == {900}
    assert [set(track.audio) for track in mixer._state.tracks[:4]] == [{400}, {300}, {400}, {200}]
    for _ in range(3):
        # Unarmed microphone PCM cannot leak into playback or grow the recording.
        assert set(domain.pcm_samples(mixer._process_block(_pcm(9000, 16), frames=16))) == {1300}
    assert all(len(track.audio) == 32 for track in mixer._state.tracks[:4])
    assert mixer.set_track(0, armed=False)
    assert mixer.set_track(1, armed=False)
    assert mixer.record(overdub=True)
    mixer._process_block(_pcm(100, 16), frames=16)
    assert [set(track.audio) for track in mixer._state.tracks[:4]] == [{400}, {300}, {500}, {200}]
    assert mixer.set_master_volume(50)
    assert mixer.set_track(0, volume=50, pan=-100)
    assert mixer.set_track(1, pan=100)
    assert mixer.set_track(2, muted=True)
    assert list(domain.pcm_samples(mixer._process_block(frames=1))) == [200, 250]
    assert mixer.set_track(0, solo=True)
    assert list(domain.pcm_samples(mixer._process_block(frames=1))) == [100, 0]
    assert mixer.set_track(0, solo=False)
    mixer.stop()
    target = tmp_path / "mix.wav"
    assert mixer.export_wav(target) and mixer.snapshot()["operation_success"]
    with wave.open(str(target), "rb") as output:
        assert (output.getnframes(), output.getnchannels(), output.getframerate()) == (
            16,
            2,
            domain.SAMPLE_RATE,
        )
        exported = output.readframes(16)
    assert list(domain.pcm_samples(exported)) == [200, 250] * 16
    project = tmp_path / "session.airloop"
    assert mixer.save_project(project) and mixer.snapshot()["operation_success"]
    restored = mixers()
    assert restored.load_project(project) and restored.snapshot()["operation_success"]
    assert restored.snapshot()["mode"] == "idle" and audio._active() is None
    assert restored.snapshot()["tracks"] == mixer.snapshot()["tracks"]
    second = tmp_path / "restored.wav"
    assert restored.export_wav(second) and restored.snapshot()["operation_success"]
    assert second.read_bytes() == target.read_bytes()


def test_worker_captures_two_buses_and_microphone_then_repeats_committed_pcm(
    mixers, monkeypatch, tmp_path
):
    frames = domain.BLOCK_FRAMES
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: frames * 2)
    order, output = [], []

    class Backend:
        def __init__(self, stop):
            self.stop = stop

        def open_output(self):
            order.append("output_open")

        def open_input(self, device):
            assert device == "default"
            order.append("input_open")

        def read_input(self, count):
            order.append("input_read")
            return _pcm(400, count)

        def close_input(self):
            order.append("input_close")

        def wait_output(self):
            return not self.stop.is_set()

        def write_output(self, data):
            output.append(domain.pcm_samples(data))
            if len(output) == 2:
                assert order[-1] == "input_close"
                assert mixer.snapshot()["mode"] == "playing"
            if len(output) == 4:
                self.stop.set()
            return not self.stop.is_set()

        def close(self):
            order.append("closed")

    mixer = mixers(backend_factory=Backend)
    assert mixer.set_master_volume(100)
    for index, source in enumerate(("launcher_deck_11", "launcher_deck_29", "mic")):
        assert mixer.set_track(index, source=source, armed=True)
    assert mixer.record()
    assert audio.route_keydeck_sound(
        "launcher_deck_11", _wav(tmp_path / "a.wav", 800, frames * 2), 0.5
    )
    assert audio.route_keydeck_sound(
        "launcher_deck_29", _wav(tmp_path / "b.wav", 1200, frames * 2), 0.25
    )
    mixer._run()  # Actual controller loop, injected synthetic device boundary.
    assert len(output) == 4
    assert [set(block) for block in output] == [{700}, {700}, {1100}, {1100}]
    assert order.count("input_open") == order.count("input_close") == 1
    assert order.count("input_read") == 2 and order[-1] == "closed"
    assert audio._active() is None
    mixer.stop()
    assert mixer.snapshot()["mode"] == "idle"


@pytest.mark.parametrize("start", [0, 14])
def test_partial_overdub_survives_stop_project_restore_and_export(
    mixers, monkeypatch, tmp_path, start
):
    monkeypatch.setattr(domain, "loop_length", lambda _bpm, _bars: 16)
    mixer = mixers()
    assert mixer.load_wav(0, _wav(tmp_path / "source.wav", 1000, 16))
    assert mixer.set_track(0, source="mic", armed=True)
    assert mixer.set_master_volume(100)
    assert mixer.play()
    if start:
        mixer._process_block(frames=start)
    assert mixer.record(overdub=True)
    mixer._process_block(_pcm(200, 4), frames=4)
    assert mixer.stop()
    expected = array("h", [1000, 1000]) * 16
    for offset in range(4):
        index = ((start + offset) % 16) * 2
        expected[index] = expected[index + 1] = 1200
    assert mixer._state.tracks[0].audio == expected
    project = tmp_path / "partial.airloop"
    assert mixer.save_project(project) and mixer.snapshot()["operation_success"]
    restored = mixers()
    assert restored.load_project(project) and restored.snapshot()["operation_success"]
    assert restored._state.tracks[0].audio == expected
    target = tmp_path / "partial.wav"
    assert restored.export_wav(target) and restored.snapshot()["operation_success"]
    with wave.open(str(target), "rb") as output:
        assert domain.pcm_samples(output.readframes(16)) == expected
