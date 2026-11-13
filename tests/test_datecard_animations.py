# -*- coding: utf-8 -*-
"""Real GIF decoding, live dates, reversible selection and playback lifecycle."""

from unittest.mock import patch

from PyQt6.QtCore import QDate, QLocale, QSettings, QSize, QTimer
from PyQt6.QtGui import QImageReader, QMovie
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QPushButton, QWidget
import pytest

from calendar_app.presentation.widgets.datecard_animation_dialog import DateAnimationDialog
from calendar_app.presentation.widgets.datecard_animations import (
    DATE_ANIMATIONS,
    AnimatedDateSurface,
)
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "date.ini"), QSettings.Format.IniFormat)
    card = OverlayDateCardWidget(owner)
    yield card
    card._set_runtime_active(False)
    card.close()
    owner.close()
    app.processEvents()


@pytest.mark.parametrize("animation", DATE_ANIMATIONS, ids=lambda item: item.animation_id)
def test_bundled_gif_has_real_changing_frames_and_infinite_loop(app, animation):
    reader = QImageReader(animation.filename())
    assert reader.canRead()
    assert reader.supportsAnimation()
    assert reader.imageCount() >= 16
    assert reader.loopCount() == -1
    frames = []
    for _ in range(reader.imageCount()):
        frame = reader.read()
        assert not frame.isNull()
        assert frame.size() == QSize(320, 320)
        frames.append(frame)
    assert any(image != frames[0] for image in frames[1:])


def test_selection_keeps_user_template_and_saved_appearance_and_survives_recreation(widget):
    widget._set("dc_template", "{year}.{month}.{day}")
    widget._set("font_family", "Malgun Gothic")
    widget._set("widget_opacity", 75)
    widget._set("text_color_rgba", "#fffefefe")
    before = {
        key: widget._get(key)
        for key in ("dc_template", "font_family", "widget_opacity", "text_color_rgba")
    }
    widget._set_date_animation("cat", motion=False)
    assert widget.display_style() == "animated"
    assert widget._animated_date_surface.animation.animation_id == "cat"
    assert {key: widget._get(key) for key in before} == before
    assert widget._animated_date_surface._movie.state() != QMovie.MovieState.Running
    restored = OverlayDateCardWidget(widget.owner)
    try:
        restored._apply_and_resize()
        assert restored._animated_date_surface.animation.animation_id == "cat"
        assert restored._get("datecard_animation_motion", True, type_=bool) is False
    finally:
        restored._set_runtime_active(False)
        restored.close()
    widget._set_display_style("default")
    assert widget._animated_date_surface.isHidden()
    assert not widget._template_label.isHidden()
    assert widget._get("dc_template") == before["dc_template"]


def test_movie_advances_pauses_and_resumes_without_new_timer_or_movie(widget, app):
    with patch(
        "calendar_app.presentation.widgets.datecard_animations.system_allows_weather_motion",
        return_value=True,
    ):
        widget._set_date_animation("sakura")
        widget.set_enabled(True)
        surface = widget._animated_date_surface
        movie = surface._movie
        app.processEvents()
        assert movie.state() == QMovie.MovieState.Running
        frame = movie.currentFrameNumber()
        QTest.qWait(300)
        assert movie.currentFrameNumber() != frame
        widget.hide()
        app.processEvents()
        assert movie.state() == QMovie.MovieState.Paused
        widget.show()
        app.processEvents()
        assert surface._movie is movie
        assert movie.state() == QMovie.MovieState.Running
        surface.set_motion_policy("static")
        assert movie.state() == QMovie.MovieState.Paused
        surface.set_motion_policy("balanced", paused=True)
        assert movie.state() == QMovie.MovieState.Paused
        surface.set_motion_policy("balanced")
        assert movie.state() == QMovie.MovieState.Running
        widget.set_enabled(False)
        assert movie.state() == QMovie.MovieState.Paused
        assert not widget._dc_timer.isActive()


def test_system_motion_setting_stops_playback(widget, app):
    widget._set_date_animation("moon")
    with patch(
        "calendar_app.presentation.widgets.datecard_animations.system_allows_weather_motion",
        return_value=False,
    ):
        widget.set_enabled(True)
        app.processEvents()
        assert widget._animated_date_surface._movie.state() != QMovie.MovieState.Running


def test_gallery_cancel_writes_nothing_and_only_selected_preview_runs(widget, app):
    before = {key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()}
    dialog = DateAnimationDialog(widget)
    dialog.show()
    app.processEvents()
    dialog.choices.setCurrentRow(4)
    dialog.motion_check.setChecked(False)
    assert dialog.preview.animation.animation_id == "coffee"
    dialog.reject()
    app.processEvents()
    assert not dialog.preview._active
    assert {
        key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()
    } == before
    dialog.deleteLater()


def test_graphic_collections_and_animated_cards_switch_both_directions(widget):
    widget._set_date_animation("forest", motion=False)
    widget.apply_graphic_collection("soft_object", motion=False)
    assert widget._animated_date_surface.isHidden()
    assert not widget._graphic_surface.isHidden()
    widget._set_date_animation("ocean", motion=False)
    assert not widget._animated_date_surface.isHidden()
    assert widget._graphic_surface.isHidden()
    widget._set_display_style("mini_grid")
    assert widget._animated_date_surface.isHidden()
    assert not widget._grid_widget.isHidden()


def test_context_menu_apply_updates_the_live_card(widget, app):
    menu = QMenu(widget)
    widget._build_context_menu(menu)

    def choose_and_apply():
        dialog = app.activeModalWidget()
        dialog.choices.setCurrentRow(1)
        dialog.motion_check.setChecked(False)
        dialog.findChild(QPushButton, "primary_btn").click()

    QTimer.singleShot(0, choose_and_apply)
    menu.actions()[0].trigger()
    assert widget.display_style() == "animated"
    assert widget._animated_date_surface.animation.animation_id == "ocean"
    assert widget._get("datecard_animation_motion", True, type_=bool) is False


@pytest.mark.parametrize(
    "size", [QSize(120, 100), QSize(180, 240), QSize(300, 160), QSize(480, 640)]
)
@pytest.mark.parametrize("locale", ["ko_KR", "en_US", "de_DE", "ar_SA"])
def test_live_dates_and_localized_text_fit_resized_surface(app, size, locale):
    previous = QLocale()
    QLocale.setDefault(QLocale(locale))
    surface = AnimatedDateSurface()
    try:
        surface.configure("coffee", motion=False, day=QDate(2026, 12, 31))
        surface.resize(size)
        assert not surface.grab().isNull()
        assert surface.day == QDate(2026, 12, 31)
        assert all(surface.rect().contains(rect.toAlignedRect()) for rect in surface._text_bounds)
        surface.configure("coffee", motion=False, day=QDate(2027, 1, 1))
        assert surface.day == QDate(2027, 1, 1)
    finally:
        surface.close()
        QLocale.setDefault(previous)
