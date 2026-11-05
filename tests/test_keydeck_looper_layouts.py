# -*- coding: utf-8 -*-
"""Independent looper persistence and portable sound-only layout snapshots."""

from copy import deepcopy
import json
from pathlib import Path
import wave

import pytest

from calendar_app.domain.beatmaker_looper import default_looper, normalize_looper
from calendar_app.presentation.widgets.keydeck import layout_library as library
from calendar_app.presentation.widgets.keydeck import model


def _event(*, at_tick=0, path="", key_id="original-pad"):
    return {
        "at_tick": at_tick,
        "sound": "custom" if path else "beat_lofi_kick",
        "sound_path": str(path),
        "volume": 78,
        "key_id": key_id,
    }


def _looper():
    project = default_looper()
    project.update(bpm=137, bars=2, quantize="off")
    project["tracks"][0]["events"] = [_event(at_tick=120)]
    project["tracks"][2].update(muted=True, volume=37)
    return project


def _recording():
    return {
        "version": 1,
        "duration_ms": 500,
        "events": [
            {
                "at_ms": 0,
                "sound": "beat_lofi_snare",
                "sound_path": "",
                "volume": 63,
                "key_id": "previous-pad",
            }
        ],
    }


def _deck():
    return {
        **model.build_template_deck("beatmaker_4x4"),
        "beatmaker_recording": _recording(),
        "beatmaker_looper": _looper(),
    }


def _wav(path: Path, sample: int) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(sample.to_bytes(2, "little", signed=True) * 80)
    return path


def _read_document(document):
    return library.parse_document(json.dumps(document).encode("utf-8", errors="strict"))


def test_looper_is_optional_and_round_trip_preserves_both_independent_performances():
    plain = model.build_template_deck("beatmaker_4x4")
    assert "beatmaker_looper" not in model.normalize_deck(plain)
    source = _deck()
    original = deepcopy(source)
    result = model.deck_from_json(model.deck_to_json(source))
    assert result["beatmaker_looper"] == source["beatmaker_looper"]
    assert result["beatmaker_recording"] == source["beatmaker_recording"]
    result["beatmaker_looper"]["tracks"][0]["events"][0]["volume"] = 0
    assert source == original
    source["beatmaker_looper"] = default_looper()
    assert model.normalize_deck(source)["beatmaker_looper"] == default_looper()


@pytest.mark.parametrize("damage", ["future", "tracks", "tick", "boolean_bpm"])
def test_corrupt_looper_does_not_remove_pages_actions_or_v1_take(damage):
    source = _deck()
    if damage == "future":
        source["beatmaker_looper"]["version"] = 2
    elif damage == "tracks":
        source["beatmaker_looper"]["tracks"].pop()
    elif damage == "tick":
        source["beatmaker_looper"]["tracks"][0]["events"][0]["at_tick"] = 9_000
    else:
        source["beatmaker_looper"]["bpm"] = True
    expected = model.normalize_deck({**source, "beatmaker_looper": None})
    result = model.normalize_deck(source)
    assert result == expected
    assert result["beatmaker_recording"] == source["beatmaker_recording"]
    assert result["pages"] == source["pages"]
    document, skipped = library.build_document(source, kind="deck", name="Damaged")
    assert not skipped
    assert _read_document(document)["deck"] == expected


def test_looper_snapshots_cannot_add_import_actions():
    source = _deck()
    event = source["beatmaker_looper"]["tracks"][0]["events"][0]
    event.update(action={"type": "app", "target": "C:/unexpected.exe"}, hold_action="bad")
    document, _ = library.build_document(source, kind="deck", name="Sounds only")
    clean = document["deck"]["beatmaker_looper"]["tracks"][0]["events"][0]
    assert set(clean) == {"at_tick", "sound", "sound_path", "volume", "key_id"}
    summary = library.summarize_actions(document)
    assert "C:/unexpected.exe" not in summary["targets"]
    assert source["beatmaker_looper"]["tracks"][0]["events"][0]["action"]


def test_whole_deck_restores_custom_wav_for_all_tracks_and_v1_after_pad_replacement(tmp_path):
    source = _deck()
    samples = [_wav(tmp_path / f"track-{index}.wav", index + 1) for index in range(4)]
    expected_bytes = [path.read_bytes() for path in samples]
    for index, track in enumerate(source["beatmaker_looper"]["tracks"]):
        track["events"] = [_event(at_tick=index * 120, path=samples[index])]
    source["beatmaker_recording"]["events"][0].update(sound="custom", sound_path=str(samples[0]))
    # The pad that created the snapshot no longer references its original custom WAV.
    pad = source["pages"][0]["keys"][0]
    pad.update(sound="beat_lofi_snare", sound_path="")
    original = deepcopy(source)
    document, skipped = library.build_document(source, kind="deck", name="Four tracks")
    assert not skipped
    assert source == original
    assert len(document["assets"]) == 4  # v1 and track 1 share one embedded asset.
    for track in document["deck"]["beatmaker_looper"]["tracks"]:
        assert track["events"][0]["sound_path"].startswith(library.ASSET_PREFIX)
    for path in samples:
        path.unlink()  # A receiving PC cannot rely on the sender's original files.
    target = tmp_path / "receiver"
    restored = library.materialize(_read_document(document), asset_root=target)["deck"]
    assert restored["beatmaker_looper"]["tracks"][2]["muted"] is True
    assert restored["beatmaker_looper"]["tracks"][2]["volume"] == 37
    for index, track in enumerate(restored["beatmaker_looper"]["tracks"]):
        path = Path(track["events"][0]["sound_path"])
        assert path.parent == target / "launcher_assets" / "sound"
        assert path.read_bytes() == expected_bytes[index]
    assert (
        restored["beatmaker_recording"]["events"][0]["sound_path"]
        == restored["beatmaker_looper"]["tracks"][0]["events"][0]["sound_path"]
    )
    assert normalize_looper(restored["beatmaker_looper"]) == restored["beatmaker_looper"]


def test_preview_restores_looper_sounds_only_inside_requested_cache(tmp_path, monkeypatch):
    source = _deck()
    sample = _wav(tmp_path / "snapshot.wav", 4)
    source["beatmaker_looper"]["tracks"][3]["events"] = [_event(path=sample)]
    document, _ = library.build_document(source, kind="deck", name="Preview")
    original = deepcopy(document)
    sample.unlink()

    def forbidden_store_write(*_args, **_kwargs):
        pytest.fail("Preview must not materialize into the user's asset store")

    monkeypatch.setattr(library, "import_launcher_asset", forbidden_store_write)
    cache = tmp_path / "preview-cache"
    preview = library.preview_deck(_read_document(document), cache_dir=cache)
    restored_path = Path(preview["beatmaker_looper"]["tracks"][3]["events"][0]["sound_path"])
    assert restored_path.parent == cache
    assert restored_path.is_file()
    assert document == original


@pytest.mark.parametrize("mode", ["replace", "new_page"])
def test_page_import_preserves_receiving_v1_take_and_looper(tmp_path, mode):
    receiver = _deck()
    sender = _deck()
    sender["beatmaker_looper"]["bpm"] = 160
    sender["beatmaker_recording"]["duration_ms"] = 800
    document, skipped = library.build_document(sender, kind="page", name="New pads")
    assert not skipped
    assert "beatmaker_looper" not in document
    assert "beatmaker_recording" not in document
    original = deepcopy(receiver)
    content = library.materialize(_read_document(document), asset_root=tmp_path / "receiver")
    imported = library.apply_content(receiver, content, mode)
    assert imported["beatmaker_looper"] == receiver["beatmaker_looper"]
    assert imported["beatmaker_recording"] == receiver["beatmaker_recording"]
    assert len(imported["pages"]) == len(receiver["pages"]) + (mode == "new_page")
    assert receiver == original


def test_whole_deck_import_uses_sender_looper_without_receiver_data_mutation(tmp_path):
    receiver = _deck()
    original = deepcopy(receiver)
    sender = _deck()
    sender["beatmaker_looper"]["bpm"] = 240
    sender["beatmaker_recording"]["duration_ms"] = 900
    document, _ = library.build_document(sender, kind="deck", name="Entire project")
    content = library.materialize(_read_document(document), asset_root=tmp_path / "receiver")
    result = library.apply_content(receiver, content)
    assert result["beatmaker_looper"] == sender["beatmaker_looper"]
    assert result["beatmaker_recording"] == sender["beatmaker_recording"]
    assert receiver == original
