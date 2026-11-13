# -*- coding: utf-8 -*-
"""Studio and widget looper entries open the loop mixer and keep saved loops."""

from copy import deepcopy
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont, QPalette
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.domain.beatmaker_looper import default_looper, normalize_looper
from calendar_app.presentation.dialogs.dialog_styles import install_common_dialog_style_filter
from calendar_app.presentation.widgets.keydeck import model
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    previous_font = QFont(application.font())
    previous_palette = QPalette(application.palette())
    previous_style = application.styleSheet()
    install_common_dialog_style_filter(application)
    application.setProperty(EXITING_PROPERTY, False)
    yield application
    application.setStyleSheet(previous_style)
    application.setFont(previous_font)
    application.setPalette(previous_palette)


@pytest.fixture
def bank(monkeypatch):
    sound = Mock()
    monkeypatch.setattr(
        "calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: sound
    )
    return sound


def legacy_take():
    return {
        "version": 1,
        "duration_ms": 1000,
        "events": [
            {
                "at_ms": 0,
                "sound": "beat_lofi_kick",
                "sound_path": "",
                "volume": 80,
                "key_id": "legacy",
            }
        ],
    }


def test_studio_loop_entry_opens_independent_mixer_and_v1_recording_is_unchanged(app, bank):
    source = model.build_template_deck("beatmaker_4x4")
    source["beatmaker_recording"] = legacy_take()
    before = deepcopy(source)
    studio = KeyDeckStudioDialog(source)
    try:
        assert studio.beatmaker_controls.looper_button is not None
        with patch(
            "calendar_app.presentation.widgets.overlay_launcher_deck.open_loop_mixer_widget"
        ) as open_mixer:
            studio.open_beatmaker_looper()
            app.processEvents()
            open_mixer.assert_called_once_with(None)
        assert studio.deck == before
        assert studio.deck["beatmaker_recording"] == legacy_take()
        assert source == before
        assert not studio._dirty
    finally:
        studio.force_close()
        studio.deleteLater()
        app.processEvents()


def test_widget_mixer_entry_preserves_saved_loop_and_reopens_silently(app, bank, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "loop.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    reopened = None
    try:
        source = model.build_template_deck("beatmaker_4x4")
        source["beatmaker_looper"] = default_looper()
        source["beatmaker_looper"]["tracks"][0]["events"] = [
            {
                "at_tick": 0,
                "sound": "beat_lofi_kick",
                "sound_path": "",
                "volume": 100,
                "key_id": "pad",
            }
        ]
        widget._apply_deck(source)
        with patch(
            "calendar_app.presentation.widgets.overlay_launcher_deck.open_loop_mixer_widget"
        ) as open_mixer:
            widget._open_beatmaker_looper()
            open_mixer.assert_called_once_with(widget)
        saved = widget._load_deck()["beatmaker_looper"]
        assert saved["tracks"][0]["events"]
        bank.play.reset_mock()
        reopened = OverlayLauncherDeckWidget(owner)
        assert reopened._load_deck()["beatmaker_looper"] == saved
        bank.play.assert_not_called()
    finally:
        for child in (widget, reopened):
            if child is not None:
                child.close()
                child.deleteLater()
        owner.close()
        owner.deleteLater()
        app.processEvents()
