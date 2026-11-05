# -*- coding: utf-8 -*-
"""Pad input, layered transport and the existing draft/persistence lifecycle."""

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QKeyEvent, QPainter, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QBoxLayout, QDialog, QMessageBox, QWidget
import pytest

from calendar_app.domain.beatmaker_looper import default_looper, normalize_looper
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_theme_tokens,
    install_common_dialog_style_filter,
)
from calendar_app.presentation.theme.style_builder import build_global_stylesheet
from calendar_app.presentation.widgets.keydeck import model
from calendar_app.presentation.widgets.keydeck.beatmaker_dialog import BeatmakerPerformanceDialog
from calendar_app.presentation.widgets.keydeck.looper_dialog import BeatmakerLooperDialog
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, milliseconds):
        self.now += milliseconds / 1000


def _progress_pixels(progress):
    """Inspect Qt paint output in an offscreen unit test, never native evidence."""
    previous = progress.value()
    progress.setValue((progress.minimum() + progress.maximum()) // 2)
    image = QImage(progress.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        progress.render(painter)
    finally:
        painter.end()
    progress.setValue(previous)
    return {
        "chunk": image.pixelColor(image.width() // 4, image.height() // 2).name(),
        "groove": image.pixelColor(3 * image.width() // 4, image.height() // 2).name(),
    }


def _style_diagnostic(view):
    app = QApplication.instance()
    controls = {}
    for name in (
        "bpm_spin",
        "bars_combo",
        "page_combo",
        "record_button",
        "overdub_check",
        "progress",
        "status",
        "sound_check",
        "close_button",
    ):
        widget = getattr(view, name)
        font = widget.font()
        controls[name] = {
            "height": widget.height(),
            "hint": widget.sizeHint().height(),
            "minimum": widget.minimumHeight(),
            "family": font.family(),
            "pt": font.pointSizeF(),
            "px": font.pixelSize(),
            "metrics": widget.fontMetrics().height(),
        }
    result = {
        "app_font": app.font().toString(),
        "app_style_sha256": sha256(app.styleSheet().encode("utf-8", errors="strict")).hexdigest(),
        "app_style_length": len(app.styleSheet()),
        "progress_highlight": view.progress.palette()
        .color(QPalette.ColorRole.Highlight)
        .name(QColor.NameFormat.HexArgb),
        "progress_css": view.progress.styleSheet(),
        "viewport": (
            view.workspace_scroll.viewport().width(),
            view.workspace_scroll.viewport().height(),
        ),
        "controls": controls,
        "offscreen_qt_progress_pixels": _progress_pixels(view.progress),
    }
    prefix = os.environ.get("AIR_UI_ORDER_DIAGNOSTIC")
    if prefix:
        profile = getattr(view, "_dc_chrome_settings", None)
        label = Path(profile.fileName()).stem if profile is not None else "global"
        directory = Path("artifacts/beatmaker-loopdeck-20261106/ordering-diagnostics")
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{prefix}-{label}.json"
        result["app_style"] = app.styleSheet()
        result["global_font_size"] = QSettings("kimhyojin", "Dark Calendar").value(
            "font_size", None
        )
        result["dialog_tokens"] = get_dialog_theme_tokens(settings=profile)
        destination.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", errors="strict"
        )
    return result


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


@pytest.fixture
def make_view(app, bank):
    created = []

    def make(deck=None, *, draft=False, parent=None):
        clock = Clock()
        source = model.build_template_deck("beatmaker_4x4") if deck is None else deck
        view = BeatmakerLooperDialog(source, parent, clock=clock, draft=draft)
        view.show()
        app.processEvents()
        view.canvas._armed_at = 0
        created.append(view)
        return view, clock

    yield make
    for view in created:
        view.reject()
        view.deleteLater()
    app.processEvents()


def first_loop(view, clock):
    view.record_button.click()
    QTest.keyClick(view.canvas, Qt.Key.Key_Q)
    clock.advance(250)
    QTest.keyClick(view.canvas, Qt.Key.Key_Z)
    clock.advance(1750)
    view._tick()
    return deepcopy(view.timeline.data)


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


def test_opening_does_not_play_or_create_an_untouched_loop(make_view, bank):
    view, _clock = make_view()
    assert view.canvas.hasFocus()
    assert not view.timer.isActive()
    assert view.timeline.mode == "idle"
    assert view.result_performance()["beatmaker_looper"] is None
    bank.play.assert_not_called()
    assert len(view.track_controls) == 4
    assert not view.play_button.isEnabled()


@pytest.mark.parametrize("mode,base", [("light", "#f6f7fb"), ("dark", "#121827")])
def test_workspace_uses_owning_modal_reading_palette(make_view, tmp_path, mode, base):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / f"{mode}.ini"), QSettings.Format.IniFormat)
    owner.settings.setValue("text_theme", mode)
    owner.settings.setValue("panel_base_color", base)
    owner.settings.setValue("font_size", 11)
    view, _clock = make_view(parent=owner)
    tokens = get_dialog_theme_tokens(settings=owner.settings)
    expected = QColor(tokens["content_bg"])
    assert expected.isValid()
    for widget in (view.workspace_scroll.viewport(), view.workspace_body):
        assert widget.palette().color(QPalette.ColorRole.Window) == expected
        assert widget.palette().color(QPalette.ColorRole.Base) == expected
    assert tokens["content_bg"] in view.workspace_scroll.styleSheet()
    view.reject()
    owner.deleteLater()


def test_transport_stays_visible_while_workspace_scrolls_and_reflows(make_view, app):
    view, _clock = make_view()
    view.setMaximumSize(2000, 2000)
    view.resize(880, 860)
    app.processEvents()
    minimum_width = (
        view.canvas.sizeHint().width()
        + view._mixer_group.minimumSizeHint().width()
        + view.workspace_layout.spacing()
    )
    expected = (
        QBoxLayout.Direction.LeftToRight
        if view.workspace_scroll.viewport().width() >= minimum_width
        else QBoxLayout.Direction.TopToBottom
    )
    assert view.workspace_layout.direction() == expected
    viewport = view.workspace_scroll.viewport()
    if expected == QBoxLayout.Direction.LeftToRight:
        for select, *_rest in view.track_controls:
            position = select.mapTo(viewport, QPoint())
            assert position.y() >= 0
            assert position.y() + select.height() <= viewport.height()
    transport = (view.record_button, view.play_button, view.stop_button, view.progress, view.status)
    positions = [widget.mapTo(view, QPoint()) for widget in transport]
    for widget in transport:
        assert not view.workspace_body.isAncestorOf(widget)
        assert widget.isVisibleTo(view)
        position = widget.mapTo(view, QPoint())
        assert position.y() >= 0
        assert position.y() + widget.height() <= view.height()
    view.resize(600, 700)
    app.processEvents()
    minimum_width = (
        view.canvas.sizeHint().width()
        + view._mixer_group.minimumSizeHint().width()
        + view.workspace_layout.spacing()
    )
    assert view.workspace_scroll.viewport().width() < minimum_width
    assert view.workspace_layout.direction() == QBoxLayout.Direction.TopToBottom
    scroll = view.workspace_scroll.verticalScrollBar()
    fixed_positions = [widget.mapTo(view, QPoint()) for widget in transport]
    for value in (scroll.maximum(), 0):
        scroll.setValue(value)
        app.processEvents()
        assert [widget.mapTo(view, QPoint()) for widget in transport] == fixed_positions
    assert all(position.y() < view.height() for position in positions)


def test_progress_uses_theme_accent_and_neutral_reading_groove(make_view, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "progress.ini"), QSettings.Format.IniFormat)
    owner.settings.setValue("text_theme", "light")
    owner.settings.setValue("panel_base_color", "#f6f7fb")
    owner.settings.setValue("theme_color", "#8e61d7")
    view, _clock = make_view(parent=owner)
    tokens = get_dialog_theme_tokens(settings=owner.settings)
    diagnostic = _style_diagnostic(view)
    assert view.progress.palette().color(QPalette.ColorRole.Highlight) == QColor(
        tokens["accent"]
    ), diagnostic
    assert view.progress.palette().color(QPalette.ColorRole.Base) == QColor(tokens["input_bg"])
    assert "QProgressBar#looperPosition::chunk" in view.progress.styleSheet()
    assert tokens["accent"] in view.progress.styleSheet()
    assert tokens["border_soft"] in view.progress.styleSheet()
    view.reject()
    owner.deleteLater()


def test_parent_accent_overrides_main_global_selection_palette(make_view, app, tmp_path):
    app.setStyleSheet(
        build_global_stylesheet(base_pt=11, theme_color="#7653c4", text_theme="light")
    )
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "explicit-progress.ini"), QSettings.Format.IniFormat)
    owner.settings.setValue("font_size", 11)
    owner.settings.setValue("text_theme", "light")
    owner.settings.setValue("panel_base_color", "#f6f7fb")
    owner.settings.setValue("theme_color", "#8e61d7")
    view, _clock = make_view(parent=owner)
    tokens = get_dialog_theme_tokens(settings=owner.settings)
    pixels = _progress_pixels(view.progress)
    assert pixels["chunk"] == QColor(tokens["accent"]).name()
    assert pixels["groove"] == QColor(tokens["input_bg"]).name()
    diagnostic = _style_diagnostic(view)
    assert view.progress.palette().color(QPalette.ColorRole.Highlight) == QColor(
        tokens["accent"]
    ), diagnostic
    view.reject()
    owner.deleteLater()


@pytest.mark.parametrize("points", [11, 24])
def test_target_client_area_fits_full_pads_and_tracks_or_large_font_scroll(
    make_view, app, tmp_path, points
):
    original = QFont(app.font())
    app.setFont(QFont("Malgun Gothic", points))
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / f"client-{points}.ini"), QSettings.Format.IniFormat)
    owner.settings.setValue("font_size", points)
    try:
        # QPA's 800x800 virtual monitor must not re-fit the already-fitted
        # 880x736 client area used on the real 1536x816 logical display.
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=None,
        ):
            view, _clock = make_view(parent=owner)
            view.setProperty("_dc_preferred_size", QSize(880, 736))
            view.resize(880, 736)
            for _ in range(4):
                app.processEvents()
            assert view.size() == QSize(880, 736)
            viewport = view.workspace_scroll.viewport()
            for control in (
                view.record_button,
                view.play_button,
                view.stop_button,
                view.progress,
                view.status,
                view.sound_check,
                view.volume_slider,
                view.close_button,
            ):
                origin = control.mapTo(view, QPoint())
                assert view.rect().contains(origin)
                assert origin.y() + control.height() <= view.height()
            assert view.record_button.toolTip()
            assert view.close_button.toolTip() == view.close_button.accessibleDescription()
            diagnostic = _style_diagnostic(view)
            if points == 11:
                assert view._transport_inline
                assert view.workspace_layout.direction() == QBoxLayout.Direction.LeftToRight
                assert viewport.height() >= view.canvas.sizeHint().height(), diagnostic
                clip = QRectF(viewport.rect())
                offset = (
                    QPointF(view.canvas.mapTo(viewport, QPoint())) + view.canvas.content_offset()
                )
                keys = view.canvas.renderer.geometry.keys
                assert len(keys) == 16
                for key in keys:
                    assert clip.contains(
                        view.canvas.renderer.geometry.key_rect(key).translated(offset)
                    )
                for select, *_rest in view.track_controls:
                    row = select.parentWidget()
                    origin = row.mapTo(viewport, QPoint())
                    assert viewport.rect().contains(row.rect().translated(origin))
                assert view.workspace_scroll.verticalScrollBar().maximum() == 0
            else:
                assert view.workspace_scroll.verticalScrollBar().maximum() > 0
    finally:
        owner.deleteLater()
        app.processEvents()
        app.setFont(original)


def test_first_pad_starts_recording_and_one_bar_becomes_a_playing_layer(make_view, bank):
    view, clock = make_view()
    view.record_button.click()
    clock.advance(10_000)
    view._tick()
    assert view.timeline.mode == "armed"
    assert view.timeline.position_ticks == 0
    QTest.keyPress(view.canvas, Qt.Key.Key_Q)
    repeat = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier, "q", True, 1
    )
    view.canvas.keyPressEvent(repeat)
    QTest.keyRelease(view.canvas, Qt.Key.Key_Q)
    assert view.timeline.event_count == 1
    assert bank.play.call_count == 1
    clock.advance(2000)
    view._tick()
    assert view.timeline.mode == "playing"
    assert len(view.timeline.data["tracks"][0]["events"]) == 1
    assert view.record_button.isEnabled()
    assert view.stop_button.isEnabled()
    assert bank.play.call_count == 2


def test_second_layer_records_while_first_layer_keeps_the_shared_phase(make_view, bank):
    view, clock = make_view()
    first = first_loop(view, clock)
    view.track_controls[1][0].click()
    view.record_button.click()
    QTest.keyClick(view.canvas, Qt.Key.Key_W)
    assert view.timeline.record_track == 1
    bank.play.reset_mock()
    clock.advance(250)
    view._tick()
    assert bank.play.call_count == 1
    assert len(view.timeline.data["tracks"][1]["events"]) == 0
    assert view.timeline.track_event_count(1) == 1
    clock.advance(1750)
    view._tick()
    assert view.timeline.mode == "playing"
    assert view.timeline.data["tracks"][0] == first["tracks"][0]
    assert len(view.timeline.data["tracks"][1]["events"]) == 1
    assert bank.play.call_count == 3


def test_overdub_adds_to_the_selected_track_and_empty_replace_keeps_it(make_view):
    view, clock = make_view()
    first_loop(view, clock)
    view.record_button.click()
    clock.advance(125)
    QTest.keyClick(view.canvas, Qt.Key.Key_A)
    clock.advance(2000)
    view._tick()
    assert len(view.timeline.data["tracks"][0]["events"]) == 3
    view._stop()
    before = deepcopy(view.timeline.data)
    view.overdub_check.setChecked(False)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view.record_button.click()
    view.stop_button.click()
    assert view.timeline.data == before


def test_mute_and_track_volume_change_only_their_playback_layer(make_view, bank):
    view, clock = make_view()
    first_loop(view, clock)
    view.track_controls[1][0].click()
    view.record_button.click()
    QTest.keyClick(view.canvas, Qt.Key.Key_W)
    clock.advance(2000)
    view._tick()
    view.stop_button.click()
    view.track_controls[0][3].setValue(50)
    view.track_controls[1][2].setChecked(True)
    bank.play.reset_mock()
    view.play_button.click()
    assert bank.play.call_count == 1
    assert bank.play.call_args.args[1] == pytest.approx(0.3)
    assert view.timeline.data["tracks"][0]["volume"] == 50
    assert view.timeline.data["tracks"][1]["muted"] is True


def test_clear_confirmation_preserves_other_layers_and_reopen_does_not_play(make_view, bank):
    view, clock = make_view()
    first = first_loop(view, clock)
    view.stop_button.click()
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        view.track_controls[0][5].click()
    assert view.timeline.data == first
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view.track_controls[0][5].click()
    assert not view.timeline.data["tracks"][0]["events"]
    assert view.timeline.data["tracks"][1:] == first["tracks"][1:]
    source = {**view.deck, **view.result_performance()}
    loaded = model.deck_from_json(model.deck_to_json(source))
    bank.play.reset_mock()
    reopened, _clock = make_view(loaded)
    assert reopened.timeline.data == view.timeline.data
    assert not reopened.timer.isActive()
    bank.play.assert_not_called()


def test_grid_controls_keep_saved_ticks_and_confirm_a_destructive_bar_change(make_view):
    project = default_looper()
    project["bars"] = 2
    project["tracks"][0]["events"] = [
        {
            "at_tick": 4800,
            "sound": "beat_lofi_kick",
            "sound_path": "",
            "volume": 100,
            "key_id": "pad",
        }
    ]
    source = {**model.build_template_deck("beatmaker_4x4"), "beatmaker_looper": project}
    view, _clock = make_view(source)
    view.bpm_spin.setValue(90)
    assert view.timeline.data["bpm"] == 90
    assert view.timeline.data["tracks"][0]["events"][0]["at_tick"] == 4800
    view.quantize_combo.setCurrentIndex(view.quantize_combo.findData("off"))
    view.quantize_combo.activated.emit(view.quantize_combo.currentIndex())
    assert view.timeline.data["quantize"] == "off"
    view.bars_combo.setCurrentIndex(view.bars_combo.findData(1))
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        view.bars_combo.activated.emit(view.bars_combo.currentIndex())
    assert view.timeline.data["bars"] == 2
    assert view.bars_combo.currentData() == 2
    view.bars_combo.setCurrentIndex(view.bars_combo.findData(1))
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view.bars_combo.activated.emit(view.bars_combo.currentIndex())
    assert view.timeline.data["bars"] == 1
    assert not view.timeline.data["tracks"][0]["events"]


def test_controls_keep_keyboard_input_out_of_pad_recording(make_view, bank, app):
    view, _clock = make_view()
    view.record_button.click()
    view.bpm_spin.setFocus()
    QTest.keyClick(view.bpm_spin, Qt.Key.Key_Q)
    view.page_combo.setFocus()
    QTest.keyClick(view.page_combo, Qt.Key.Key_Q)
    app.processEvents()
    assert view.timeline.event_count == 0
    bank.play.assert_not_called()


def test_hide_and_close_stop_the_clock_and_disable_instrument_input(make_view):
    view, clock = make_view()
    first_loop(view, clock)
    view.hide()
    assert view.timeline.mode == "idle"
    assert not view.timer.isActive()
    assert not view.canvas._keyboard_performance
    view.reject()
    assert not view.canvas._keyboard_performance


def test_closing_during_first_recording_commits_without_starting_audio(make_view, bank):
    view, clock = make_view()
    view.record_button.click()
    QTest.keyClick(view.canvas, Qt.Key.Key_Q)
    clock.advance(500)
    calls = bank.play.call_count
    view.reject()
    result = view.result_performance()
    assert result["beatmaker_looper"]["tracks"][0]["events"]
    assert bank.play.call_count == calls
    assert not view.timer.isActive()


def test_looper_close_during_bar_confirmation_does_not_touch_deleted_controls(make_view):
    project = default_looper()
    project["bars"] = 2
    project["tracks"][0]["events"] = [
        {
            "at_tick": 4800,
            "sound": "beat_lofi_kick",
            "sound_path": "",
            "volume": 100,
            "key_id": "pad",
        }
    ]
    source = {**model.build_template_deck("beatmaker_4x4"), "beatmaker_looper": project}
    view, _clock = make_view(source)
    view.bars_combo.setCurrentIndex(view.bars_combo.findData(1))

    def close(*_args, **_kwargs):
        view.reject()
        return QMessageBox.StandardButton.Yes

    with (
        patch.object(QMessageBox, "question", side_effect=close),
        patch.object(view, "_sync_grid_controls") as sync,
    ):
        view._grid_changed()
    sync.assert_not_called()
    assert view.timeline.data == project


def test_close_during_clear_confirmation_cannot_mutate_the_project(make_view):
    view, clock = make_view()
    first_loop(view, clock)
    view._stop()
    before = deepcopy(view.timeline.data)

    def close(*_args, **_kwargs):
        view.reject()
        return QMessageBox.StandardButton.Yes

    with patch.object(QMessageBox, "question", side_effect=close):
        view._clear_track(0)
    assert view.timeline.data == before
    assert not view.timer.isActive()


def perform_and_close(dialog):
    dialog.timeline.arm_recording(0)
    dialog.timeline.append(
        {"sound": "beat_lofi_kick", "sound_path": "", "volume": 100, "key_id": "pad"}
    )
    dialog.timeline.stop()
    dialog.reject()
    return QDialog.DialogCode.Rejected


def test_studio_loop_is_an_undoable_draft_and_v1_recording_is_unchanged(app, bank):
    source = model.build_template_deck("beatmaker_4x4")
    source["beatmaker_recording"] = legacy_take()
    before = deepcopy(source)
    studio = KeyDeckStudioDialog(source)
    try:
        assert studio.beatmaker_controls.looper_button is not None
        with patch.object(BeatmakerLooperDialog, "exec", new=perform_and_close):
            studio.open_beatmaker_looper()
        assert normalize_looper(studio.deck["beatmaker_looper"]) is not None
        assert studio.deck["beatmaker_recording"] == legacy_take()
        assert source == before
        assert studio._dirty
        studio.undo()
        assert "beatmaker_looper" not in studio.deck
        studio.redo()
        assert studio.result_deck()["beatmaker_looper"]["tracks"][0]["events"]
    finally:
        studio.force_close()
        studio.deleteLater()
        app.processEvents()


def test_widget_saves_loop_in_temporary_settings_and_reopens_silently(app, bank, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "loop.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    reopened = None
    try:
        widget._apply_deck(model.build_template_deck("beatmaker_4x4"))
        with patch.object(BeatmakerLooperDialog, "exec", new=perform_and_close):
            widget._open_beatmaker_looper()
        saved = widget._load_deck()["beatmaker_looper"]
        assert saved["tracks"][0]["events"]
        assert widget._performance_dialog is None
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


def test_existing_single_performance_opens_loop_without_replacing_v1(app, bank):
    source = model.build_template_deck("beatmaker_4x4")
    source["beatmaker_recording"] = legacy_take()
    performance = BeatmakerPerformanceDialog(source)
    try:
        with patch.object(BeatmakerLooperDialog, "exec", new=perform_and_close):
            performance.looper_button.click()
        result = performance.result_performance()
        assert result["beatmaker_recording"] == legacy_take()
        assert result["beatmaker_looper"]["tracks"][0]["events"]
        assert "beatmaker_looper" not in source
        assert performance._looper_dialog is None
        assert not performance.timer.isActive()
    finally:
        performance.reject()
        performance.deleteLater()
        app.processEvents()
