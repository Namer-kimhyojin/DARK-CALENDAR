# -*- coding: utf-8 -*-
"""Focused pad performance, audio gain and non-destructive overlay bank switching."""

import os
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QSettings, Qt
from PyQt6.QtGui import QFocusEvent, QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
import pytest

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck import resources
from calendar_app.presentation.widgets.keydeck.beatmaker import beatmaker_state
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas, action_summary
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bank(monkeypatch):
    value = Mock()
    monkeypatch.setattr(
        "calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: value
    )
    return value


@pytest.fixture
def canvas(app, bank):
    value = KeyDeckCanvas()
    value.set_deck(m.build_template_deck("beatmaker_4x4"))
    value.resize(value.sizeHint())
    value.show()
    value._armed_at = 0.0
    app.processEvents()
    yield value
    value.set_keyboard_performance(False)
    value.close()
    value.deleteLater()
    app.processEvents()


def test_keyboard_requires_opt_in_and_ignores_typing_shortcuts(canvas, bank):
    QTest.keyClick(canvas, Qt.Key.Key_Z)
    bank.play.assert_not_called()
    canvas.set_keyboard_performance(True)
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    bank.play.assert_not_called()
    QTest.keyClick(canvas, Qt.Key.Key_Z)
    assert bank.play.call_count == 1
    assert bank.play.call_args.args[0].endswith("lofi-kick.wav")


def test_overlapping_pads_repeat_suppression_and_release(canvas, bank):
    canvas.set_keyboard_performance(True)
    activated = []
    canvas.keyActivated.connect(lambda *args: activated.append(args))
    QTest.keyPress(canvas, Qt.Key.Key_Z)
    QTest.keyPress(canvas, Qt.Key.Key_X)
    assert len(canvas._keyboard_held) == 2
    assert bank.play.call_count == 2
    repeat = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier, "z", True, 1
    )
    canvas.keyPressEvent(repeat)
    QTest.keyPress(canvas, Qt.Key.Key_Z)
    assert bank.play.call_count == 2
    assert len(activated) == 2
    QTest.keyRelease(canvas, Qt.Key.Key_Z)
    assert len(canvas._keyboard_held) == 1
    QTest.keyRelease(canvas, Qt.Key.Key_X)
    assert not canvas._keyboard_held
    assert bank.play.call_count == 2


@pytest.mark.parametrize("release_first", ["mouse", "keyboard"])
def test_same_pad_stays_down_until_both_input_sources_release(canvas, bank, release_first):
    canvas.deck["reduce_motion"] = True
    canvas.set_keyboard_performance(True)
    key = canvas.deck["pages"][0]["keys"][12]
    position = canvas.renderer.geometry.key_rect(key).center() + canvas.content_offset()
    QTest.keyPress(canvas, Qt.Key.Key_Z)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=position.toPoint())
    runtime = canvas._runtime[key["id"]]
    assert runtime.visual.travel == 1.0
    if release_first == "mouse":
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=position.toPoint())
        assert runtime.visual.travel == 1.0
        QTest.keyRelease(canvas, Qt.Key.Key_Z)
    else:
        QTest.keyRelease(canvas, Qt.Key.Key_Z)
        assert runtime.visual.travel == 1.0
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=position.toPoint())
    assert runtime.visual.travel == 0.0


@pytest.mark.parametrize("boundary", ["focus", "hide", "inactive", "page", "escape"])
def test_held_keys_are_released_at_input_boundaries(canvas, bank, boundary):
    canvas.set_keyboard_performance(True)
    QTest.keyPress(canvas, Qt.Key.Key_Z)
    assert canvas._keyboard_held
    if boundary == "focus":
        canvas.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
    elif boundary == "hide":
        canvas.hide()
    elif boundary == "inactive":
        canvas.set_runtime_active(False)
    elif boundary == "page":
        canvas.deck["page"] = 1
        canvas.set_deck(canvas.deck)
    else:
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        assert not canvas._keyboard_performance
    assert not canvas._keyboard_held
    assert bank.play.call_count == 1


def test_disabled_pad_mute_and_individual_gain(canvas, bank):
    key = canvas.deck["pages"][0]["keys"][12]
    canvas.set_keyboard_performance(True)
    key["enabled"] = False
    QTest.keyClick(canvas, Qt.Key.Key_Z)
    bank.play.assert_not_called()
    key.update(enabled=True, sound_volume=25)
    canvas.deck["sound_volume"] = 40
    canvas.refresh({key["id"]})
    QTest.keyClick(canvas, Qt.Key.Key_Z)
    assert bank.play.call_args.args[1] == pytest.approx(0.1)
    canvas.deck["sound_enabled"] = False
    bank.play.reset_mock()
    QTest.keyClick(canvas, Qt.Key.Key_Z)
    bank.play.assert_not_called()


def test_mouse_pad_is_one_shot_and_stop_clears_auditions(canvas, bank):
    key = canvas.deck["pages"][0]["keys"][12]
    position = canvas.renderer.geometry.key_rect(key).center() + canvas.content_offset()
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=position.toPoint())
    assert bank.play.call_count == 1
    canvas._sound_preview_queue = [(9999999999.0, "future.wav", 1.0)]
    canvas._sound_preview_timer.start(1000)
    canvas.stop_sounds()
    assert not canvas._sound_preview_queue
    assert not canvas._sound_preview_timer.isActive()
    bank.stop_all.assert_called_once()


@pytest.fixture
def overlay(app, bank, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "beatmaker.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    widget._set("enabled", True)
    widget._apply_deck(m.build_template_deck("beatmaker_4x4"))
    widget.show()
    app.processEvents()
    yield widget
    widget._set_keyboard_performance(False)
    widget.close()
    owner.close()
    widget.deleteLater()
    owner.deleteLater()
    app.processEvents()


def test_sound_action_has_no_target_or_external_side_effect(overlay):
    with patch("calendar_app.presentation.widgets.overlay_launcher_deck.send_hotkey") as sender:
        with patch(
            "calendar_app.presentation.widgets.overlay_launcher_deck.QToolTip.showText"
        ) as tip:
            key = overlay.deck()["pages"][0]["keys"][0]
            overlay._run_key(key["id"], "tap")
            assert overlay._execute_action({"type": "sound"}) is True
            assert action_summary(key["action"]) == m.option_label(m.ACTION_TYPES, "sound")
            tip.assert_not_called()
        sender.assert_not_called()


def test_overlay_focus_mode_is_explicit_and_escape_restores_macro_flags(overlay):
    assert overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    position = QPoint(overlay.pos())
    overlay._set_keyboard_performance(True)
    assert overlay._keyboard_performance
    assert not overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert overlay.pos() == position
    QTest.keyClick(overlay._canvas, Qt.Key.Key_Escape)
    assert not overlay._keyboard_performance
    assert overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert overlay.pos() == position


def test_bank_switch_preserves_existing_custom_pads_and_no_duplicate_pages(overlay):
    deck = overlay.deck()
    deck["pages"][1]["keys"][0]["label"] = "My melody"
    overlay._set_beatmaker_bank("melody")
    assert overlay.deck()["page"] == 1
    assert overlay.deck()["pages"][1]["keys"][0]["label"] == "My melody"
    overlay._set_beatmaker_bank("drums")
    overlay._set_beatmaker_bank("melody")
    assert len(overlay.deck()["pages"]) == 2


def test_kit_change_is_confirmed_and_preserves_other_pages(overlay):
    module = "calendar_app.presentation.widgets.overlay_launcher_deck.QMessageBox.question"
    with patch(module, return_value=QMessageBox.StandardButton.No):
        overlay._set_beatmaker_kit("neon")
    assert beatmaker_state(overlay.deck()["pages"][0])["kit"] == "lofi"
    untouched = m.deck_to_json(overlay.deck())
    with patch(module, return_value=QMessageBox.StandardButton.Yes):
        overlay._set_beatmaker_kit("neon")
    assert beatmaker_state(overlay.deck()["pages"][0])["kit"] == "neon"
    assert overlay.deck()["pages"][1] == m.deck_from_json(untouched)["pages"][1]


def test_missing_bank_is_added_without_overwriting_current_page(overlay):
    overlay.deck()["pages"].pop()
    original = overlay.deck()["pages"][0]["keys"][0]["id"]
    overlay._set_beatmaker_bank("melody")
    assert len(overlay.deck()["pages"]) == 2
    assert overlay.deck()["pages"][0]["keys"][0]["id"] == original
    assert beatmaker_state(m.current_page(overlay.deck()))["bank"] == "melody"


def test_full_deck_and_invalid_bank_do_not_replace_user_pages(overlay):
    overlay.deck()["pages"] = overlay.deck()["pages"][:1]
    while len(overlay.deck()["pages"]) < m.MAX_PAGES:
        overlay.deck()["pages"].append(m.new_page("User page"))
    before = m.deck_to_json(overlay.deck())
    module = "calendar_app.presentation.widgets.overlay_launcher_deck.QToolTip.showText"
    with patch(module) as notice:
        overlay._set_beatmaker_bank("melody")
        notice.assert_called_once()
    overlay._set_beatmaker_bank("invalid")
    overlay._set_beatmaker_kit("invalid")
    assert m.deck_to_json(overlay.deck()) == before


def test_sound_bank_stop_keeps_cached_qt_voices(monkeypatch):
    bank = resources.SoundBank()
    effects = [Mock(), Mock()]
    bank._pools["cached.wav"] = effects
    native = Mock()
    bank._native = native
    bank.stop_all()
    assert bank._pools["cached.wav"] == effects
    for effect in effects:
        effect.stop.assert_called_once()
    native.stop_all.assert_called_once()
