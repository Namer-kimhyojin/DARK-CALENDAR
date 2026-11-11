# -*- coding: utf-8 -*-
"""Real pad input, player cleanup, Studio drafts and persistent/shareable recordings."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
import pytest

from calendar_app.domain.beatmaker_recording import normalize_recording
from calendar_app.presentation.widgets.keydeck import layout_library, model
from calendar_app.presentation.widgets.keydeck.beatmaker_dialog import BeatmakerPerformanceDialog
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


@pytest.fixture
def player(app, bank):
    clock = Mock(return_value=100.0)
    player = BeatmakerPerformanceDialog(model.build_template_deck("beatmaker_4x4"), clock=clock)
    player.show()
    app.processEvents()
    player.canvas._armed_at = 0
    yield player, clock
    player.reject()
    player.deleteLater()
    app.processEvents()


def _perform(player, clock):
    player._record()
    QTest.keyClick(player.canvas, Qt.Key.Key_Q)
    clock.return_value = 100.250
    QTest.keyClick(player.canvas, Qt.Key.Key_Z)
    clock.return_value = 100.500
    player._stop()
    return deepcopy(player.timeline.take)


def test_keyboard_records_contact_once_ignores_auto_repeat_and_replays_without_feedback(
    player, bank
):
    view, clock = player
    assert view.canvas.hasFocus()
    view._record()
    QTest.keyPress(view.canvas, Qt.Key.Key_Q)
    repeat = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier, "q", True, 1
    )
    view.canvas.keyPressEvent(repeat)
    QTest.keyRelease(view.canvas, Qt.Key.Key_Q)
    clock.return_value = 100.250
    view._stop()
    assert view.timeline.event_count == 1
    assert view.timeline.take["events"][0]["sound"] == "beat_lofi_tom_low"
    assert view.timeline.take["duration_ms"] == 250
    assert bank.play.call_count == 1
    before = deepcopy(view.timeline.take)
    view._play()
    assert not view.play_button.isEnabled()
    assert view.stop_button.isEnabled()
    assert bank.play.call_count == 2
    assert bank.play.call_args.args[0].endswith("lofi-tom_low.wav")
    assert view.timeline.take == before
    assert view.timeline.event_count == 1
    assert view.timeline.mode == "playing"


def test_mouse_and_keyboard_share_timeline_while_bank_changes_keep_recording(player, bank):
    view, clock = player
    view._record()
    key = view.deck["pages"][0]["keys"][0]
    point = view.canvas.renderer.geometry.key_rect(key).center() + view.canvas.content_offset()
    QTest.mouseClick(view.canvas, Qt.MouseButton.LeftButton, pos=point.toPoint())
    assert view.timeline.event_count == 1
    clock.return_value = 100.250
    view.page_combo.setCurrentIndex(1)
    view._page_changed()
    QTest.keyClick(view.canvas, Qt.Key.Key_Z)
    clock.return_value = 100.500
    view._stop()
    assert [event["at_ms"] for event in view.timeline.take["events"]] == [0, 250]
    assert view.timeline.take["events"][1]["sound"] == "beat_lofi_note_c3"


@pytest.mark.parametrize("boundary", ["escape", "close", "hide", "stop"])
def test_every_exit_stops_loop_timer_and_active_voices(player, bank, boundary):
    view, clock = player
    _perform(view, clock)
    view._play()
    assert view.timer.isActive()
    bank.stop_all.reset_mock()
    if boundary == "escape":
        QTest.keyClick(view.canvas, Qt.Key.Key_Escape)
    elif boundary == "close":
        view.close()
    elif boundary == "hide":
        view.hide()
    else:
        view._stop()
    assert view.timeline.mode == "idle"
    assert not view.timer.isActive()
    assert not view.canvas._keyboard_held
    assert bank.stop_all.called


def test_stop_while_recording_commits_but_empty_retry_preserves_take(player):
    view, clock = player
    original = _perform(view, clock)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        view._record()
    assert view.timeline.mode == "idle"
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view._record()
    view.reject()
    assert view.timeline.take == original


def test_disabled_mute_zero_volume_and_missing_sounds_are_not_silent_recordings(player, bank):
    view, clock = player
    view._record()
    key = view.deck["pages"][0]["keys"][4]
    key["enabled"] = False
    QTest.keyClick(view.canvas, Qt.Key.Key_Q)
    assert view.timeline.event_count == 0
    key["enabled"] = True
    view.sound_check.setChecked(False)
    QTest.keyClick(view.canvas, Qt.Key.Key_Q)
    assert view.timeline.event_count == 0
    assert view.warning.isVisible()
    view.sound_check.setChecked(True)
    view.volume_slider.setValue(0)
    QTest.keyClick(view.canvas, Qt.Key.Key_Q)
    assert view.timeline.event_count == 0
    view.volume_slider.setValue(60)
    key["sound"] = "custom"
    key["sound_path"] = "C:/missing/file.wav"
    view.canvas.refresh({key["id"]})
    QTest.keyClick(view.canvas, Qt.Key.Key_Q)
    assert view.timeline.event_count == 0
    assert view._missing_sounds
    view._stop()
    assert view.timeline.take is None


def test_one_shot_repeat_gain_and_captured_sound_survive_pad_edits(player, bank):
    view, clock = player
    key = view.deck["pages"][0]["keys"][4]
    key["sound_volume"] = 25
    view.canvas.refresh({key["id"]})
    view.volume_slider.setValue(40)
    _perform(view, clock)
    key["sound"] = "beat_neon_clap"
    key["action"] = {"type": "hotkey", "target": "Ctrl+W", "paste": False}
    bank.play.reset_mock()
    view.loop_check.setChecked(False)
    view._play()
    assert bank.play.call_args.args[0].endswith("lofi-tom_low.wav")
    assert bank.play.call_args.args[1] == pytest.approx(0.1)
    clock.return_value += 0.25
    view._tick()
    clock.return_value += 0.25
    view._tick()
    assert view.timeline.mode == "idle"
    assert not view.timer.isActive()
    assert bank.play.call_count == 2


def test_recording_source_is_private_and_normalized_round_trip_persists(player):
    view, clock = player
    original = model.build_template_deck("beatmaker_4x4")
    before = deepcopy(original)
    source = BeatmakerPerformanceDialog(original)
    source.sound_check.setChecked(False)
    assert original == before
    source.reject()
    source.deleteLater()
    recording = _perform(view, clock)
    deck = {**view.deck, **view.result_performance()}
    loaded = model.deck_from_json(model.deck_to_json(deck))
    assert loaded["beatmaker_recording"] == recording
    damaged = deepcopy(deck)
    damaged["beatmaker_recording"]["version"] = 99
    assert "beatmaker_recording" not in model.normalize_deck(damaged)
    assert model.normalize_deck(damaged)["pages"] == loaded["pages"]


def test_clear_requires_confirmation(player):
    view, clock = player
    original = _perform(view, clock)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        view._clear()
    assert view.timeline.take == original
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view._clear()
    assert view.timeline.take is None
    assert not view.play_button.isEnabled()


@pytest.mark.parametrize("operation", ["record", "clear"])
def test_closing_during_confirmation_does_not_restart_recording_or_erase_take(player, operation):
    view, clock = player
    original = _perform(view, clock)

    def close_during_confirmation(*args):
        view.reject()
        return QMessageBox.StandardButton.Yes

    with patch.object(QMessageBox, "question", side_effect=close_during_confirmation):
        (view._record if operation == "record" else view._clear)()
    assert view.timeline.mode == "idle"
    assert not view.timer.isActive()
    assert view.timeline.take == original


def test_shared_deck_embeds_custom_recording_sound_and_keeps_receiving_recording_on_page_import(
    player, tmp_path
):
    view, clock = player
    recording = _perform(view, clock)
    recording["events"][0].update(
        sound="custom", sound_path=str(keycap_sound("beat_lofi_kick").path())
    )
    deck = {**view.deck, "beatmaker_recording": recording}
    doc, skipped = layout_library.build_document(deck, kind="deck", name="Music")
    assert not skipped
    assert doc["deck"]["beatmaker_recording"]["events"][0]["sound_path"].startswith("asset:")
    parsed = layout_library.parse_document(json.dumps(doc).encode("utf-8", errors="strict"))
    materialized = layout_library.materialize(parsed, asset_root=tmp_path)
    restored = layout_library.apply_content(view.deck, materialized)
    path = restored["beatmaker_recording"]["events"][0]["sound_path"]
    assert Path(path).is_file()
    assert Path(path).read_bytes() == keycap_sound("beat_lofi_kick").path().read_bytes()
    page_doc, _ = layout_library.build_document(view.deck, kind="page", name="Pads")
    page_content = layout_library.materialize(page_doc, asset_root=tmp_path)
    assert (
        layout_library.apply_content(restored, page_content)["beatmaker_recording"]
        == restored["beatmaker_recording"]
    )


def test_studio_entry_keeps_text_editing_silent_and_opens_independent_mixer(app, bank, player):
    view, clock = player
    recording = _perform(view, clock)
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


def test_widget_mixer_entry_preserves_saved_recording_in_instance_settings(
    app, bank, player, tmp_path
):
    view, clock = player
    recording = _perform(view, clock)
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
        assert widget._performance_dialog is None
    finally:
        widget.close()
        widget.deleteLater()
        owner.close()
        owner.deleteLater()
        app.processEvents()


def test_legacy_modal_class_still_accepts_keyboard_from_non_focus_overlay_parent(
    app, bank, tmp_path
):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "focus.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    widget._apply_deck(model.build_template_deck("beatmaker_4x4"))
    widget.show()
    dialog = BeatmakerPerformanceDialog(widget.deck(), widget)
    widget._performance_dialog = dialog
    result = {}

    def perform():
        dialog = widget._performance_dialog
        try:
            dialog._focus_pads()
            # Window activation is delivered through the event loop.
            QApplication.processEvents()
            result["dialog_accepts_focus"] = not bool(
                dialog.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
            )
            result["canvas_focused"] = dialog.canvas.hasFocus()
            dialog._record()
            focused = QApplication.focusWidget()
            # QTest.keyClick(None) trips a Qt assertion that aborts the process.
            assert focused is not None, "no focus widget after _focus_pads()"
            QTest.keyClick(focused, Qt.Key.Key_Q)
            dialog._stop()
            result["take"] = dialog.timeline.take
        except BaseException as exc:  # noqa: BLE001 - re-raised after the modal loop
            # An exception escaping a Qt timer slot aborts the interpreter
            # (PyQt6 calls qFatal), which killed the whole suite with 0xC0000409.
            result["error"] = exc
        finally:
            dialog.reject()

    try:
        QTimer.singleShot(100, perform)
        dialog.exec()
        if "error" in result:
            raise result["error"]
        assert result["dialog_accepts_focus"]
        assert result["canvas_focused"]
        assert result["take"]["events"][0]["sound"] == "beat_lofi_tom_low"
        assert "beatmaker_recording" not in widget.deck()
        assert widget.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    finally:
        widget._performance_dialog = None
        dialog.deleteLater()
        widget.close()
        widget.deleteLater()
        owner.close()
        owner.deleteLater()
        app.processEvents()
