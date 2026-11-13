# -*- coding: utf-8 -*-
"""Studio drafts, mixer entries and persistent/shareable recordings."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QWidget
import pytest

from calendar_app.domain.beatmaker_recording import normalize_recording
from calendar_app.presentation.widgets.keydeck import layout_library, model
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.presentation.widgets.launcher_keycap_sounds import keycap_sound
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY


@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    app.setProperty(EXITING_PROPERTY, False)
    return app


@pytest.fixture
def bank(monkeypatch):
    bank = Mock()
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: bank)
    return bank


def _recording():
    """A saved Q-then-Z take, as the retired performance dialog recorded it."""
    return normalize_recording(
        {
            "version": 1,
            "duration_ms": 500,
            "events": [
                {
                    "at_ms": 0,
                    "sound": "beat_lofi_tom_low",
                    "sound_path": "",
                    "volume": 100,
                    "key_id": "q",
                },
                {
                    "at_ms": 250,
                    "sound": "beat_lofi_kick",
                    "sound_path": "",
                    "volume": 100,
                    "key_id": "z",
                },
            ],
        }
    )


def test_shared_deck_embeds_custom_recording_sound_and_keeps_receiving_recording_on_page_import(
    app, tmp_path
):
    base = model.build_template_deck("beatmaker_4x4")
    recording = _recording()
    recording["events"][0].update(
        sound="custom", sound_path=str(keycap_sound("beat_lofi_kick").path())
    )
    deck = {**base, "beatmaker_recording": recording}
    doc, skipped = layout_library.build_document(deck, kind="deck", name="Music")
    assert not skipped
    assert doc["deck"]["beatmaker_recording"]["events"][0]["sound_path"].startswith("asset:")
    parsed = layout_library.parse_document(json.dumps(doc).encode("utf-8", errors="strict"))
    materialized = layout_library.materialize(parsed, asset_root=tmp_path)
    restored = layout_library.apply_content(base, materialized)
    path = restored["beatmaker_recording"]["events"][0]["sound_path"]
    assert Path(path).is_file()
    assert Path(path).read_bytes() == keycap_sound("beat_lofi_kick").path().read_bytes()
    page_doc, _ = layout_library.build_document(base, kind="page", name="Pads")
    page_content = layout_library.materialize(page_doc, asset_root=tmp_path)
    assert (
        layout_library.apply_content(restored, page_content)["beatmaker_recording"]
        == restored["beatmaker_recording"]
    )


def test_studio_entry_keeps_text_editing_silent_and_opens_independent_mixer(app, bank):
    recording = _recording()
    source = model.build_template_deck("beatmaker_4x4")
    source["beatmaker_recording"] = recording
    before = deepcopy(source)
    studio = KeyDeckStudioDialog(source)
    studio.show()
    app.processEvents()
    try:
        assert studio.beatmaker_controls.performance_button.isVisible()
        studio.canvas.select([studio.current_keys()[4]["id"]])
        edit = studio.key_inspector.sublabel_edit
        bank.play.reset_mock()
        edit.setFocus()
        QTest.keyClicks(edit, "Q")
        bank.play.assert_not_called()
        prior = deepcopy(studio.deck)

        dirty = studio._dirty
        with (
            patch(
                "calendar_app.presentation.widgets.overlay_launcher_deck.open_loop_mixer_widget"
            ) as open_mixer,
            patch.object(studio, "_ask_unsaved_changes", return_value="keep"),
        ):
            studio.open_beatmaker_performance()
            open_mixer.assert_not_called()
        assert studio.deck == prior
        assert source == before
        assert studio._dirty == dirty
        assert studio.isVisible()
    finally:
        studio.force_close()
        studio.deleteLater()
        app.processEvents()


def test_widget_mixer_entry_preserves_saved_recording_in_instance_settings(app, bank, tmp_path):
    recording = _recording()
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "recording.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    source = model.build_template_deck("beatmaker_4x4")
    source["beatmaker_recording"] = recording
    widget._apply_deck(source)

    try:
        with patch(
            "calendar_app.presentation.widgets.overlay_launcher_deck.open_loop_mixer_widget"
        ) as open_mixer:
            widget._open_beatmaker_performance()
            open_mixer.assert_called_once_with(widget)
        assert widget._load_deck()["beatmaker_recording"] == recording
    finally:
        widget.close()
        widget.deleteLater()
        owner.close()
        owner.deleteLater()
        app.processEvents()
