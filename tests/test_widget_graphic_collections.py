# -*- coding: utf-8 -*-
"""Collection previews, reversible styling, responsive figures and live controls."""

from copy import deepcopy
import importlib
from unittest.mock import Mock, patch

from PyQt6.QtCore import QDate, QDateTime, QRect, QSettings, QSize, Qt, QTime
from PyQt6.QtGui import QTextDocument
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QWidget
import pytest

from calendar_app.presentation.widgets.clock_flipbook import _sticker_frames
from calendar_app.presentation.widgets.widget_graphic_catalog import CLOCK_FLIPBOOK_STICKER_DESIGNS
from calendar_app.presentation.widgets.widget_graphics import (
    COLLECTIONS,
    contrast_ratio,
    keydeck_collection_deck,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_widget(app, tmp_path):
    created = []
    network = Mock()
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
        return_value=network,
    ):

        def make(kind="clock", name="Clock"):
            owner = QWidget()
            owner.settings = QSettings(
                str(tmp_path / f"{kind}-{len(created)}.ini"), QSettings.Format.IniFormat
            )
            cls = getattr(
                importlib.import_module("calendar_app.presentation.widgets.overlay_" + kind),
                "Overlay" + name + "Widget",
            )
            widget = cls(owner)
            if kind != "launcher_deck":
                widget._set("fixed_w", 300)
                widget._set("fixed_h", 220)
            created.append((widget, owner))
            return widget

        yield make
        for widget, owner in created:
            widget._set_runtime_active(False)
            widget.close()
            owner.close()
        app.processEvents()
    assert network.get.call_count == 0


@pytest.mark.parametrize(
    "kind,name",
    [
        ("clock", "Clock"),
        ("stopwatch", "Stopwatch"),
        ("countdown", "Countdown"),
        ("datecard", "DateCard"),
        ("dday", "DDay"),
        ("text", "Text"),
    ],
)
@pytest.mark.parametrize("collection", [item.collection_id for item in COLLECTIONS])
def test_each_collection_renders_native_content_and_fits_compact_sizes(
    make_widget, kind, name, collection
):
    widget = make_widget(kind, name)
    widget.apply_graphic_collection(collection, motion=False)
    assert widget.graphic_collection_id() == collection
    assert not widget._graphic_surface.isHidden()
    for size in (QSize(160, 120), QSize(320, 220), QSize(480, 320)):
        widget._set("fixed_w", size.width())
        widget._set("fixed_h", size.height())
        widget._fit_font_to_size(size.width(), size.height())
        assert not widget.grab().isNull()
        surface = widget._graphic_surface
        assert all(
            surface.rect().adjusted(-1, -1, 1, 1).contains(box.toAlignedRect())
            for box in surface._text_bounds
        )
        assert surface._transition.state() != surface._transition.State.Running


def test_default_and_legacy_appearance_restore_without_reverting_new_user_content(make_widget):
    widget = make_widget("text", "Text")
    assert widget.display_preset_id() == "pure_type" and not widget.graphic_collection_id()
    widget._set("label_text", "Original memo")
    widget._set("widget_opacity", 75)
    widget._set("text_shadow_enabled", False)
    before = {
        key: widget._get(key)
        for key in ("appearance_preset", "text_color_rgba", "bg_color_rgba", "font_family")
    }
    widget.apply_graphic_collection("soft_object")
    assert widget._get("widget_opacity") == 75
    widget._set("label_text", "New memo\nKeep this text")
    widget._set("font_family", "Consolas")
    widget._apply_appearance()
    assert widget._graphic_surface.data["title"] == "New memo"
    widget.apply_graphic_collection("")
    assert {key: widget._get(key) for key in before if key != "font_family"} == {
        key: value for key, value in before.items() if key != "font_family"
    }
    assert widget._get("font_family") == "Consolas"
    assert widget._get("label_text") == "New memo\nKeep this text"
    assert widget._get("text_shadow_enabled") is False
    assert widget._graphic_surface.isHidden()


def test_direct_template_edits_return_to_legacy_without_losing_template(make_widget):
    widget = make_widget()
    widget.apply_graphic_collection("air_instrument")
    widget._set("clock_template", "{time:%I:%M|bold}\nCustom text")
    widget._apply_appearance()
    assert not widget.graphic_collection_id()
    assert widget._graphic_surface.isHidden()
    assert "Custom text" in widget._template_label.text()
    widget.apply_graphic_collection("soft_object")
    widget.apply_graphic_collection("")
    assert "Custom text" in widget._get("clock_template")


@pytest.mark.parametrize(
    "kind,name",
    [
        ("clock", "Clock"),
        ("stopwatch", "Stopwatch"),
        ("countdown", "Countdown"),
        ("datecard", "DateCard"),
        ("dday", "DDay"),
        ("text", "Text"),
        ("weather", "Weather"),
    ],
)
def test_saved_collection_reloads_without_mutating_content(make_widget, kind, name):
    original = make_widget(kind, name)
    original.apply_graphic_collection("soft_object", motion=False)
    original.owner.settings.sync()
    owner = QWidget()
    owner.settings = original.owner.settings
    cls = type(original)
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager", return_value=Mock()
    ):
        restored = cls(owner)
    try:
        restored._apply_and_resize()
        assert restored.graphic_collection_id() == "soft_object"
        assert not restored.grab().isNull()
        assert restored._widget_template() == original._widget_template()
    finally:
        restored._set_runtime_active(False)
        restored.close()
        owner.close()


def test_text_alignment_and_wrap_controls_remain_live(make_widget):
    widget = make_widget("text", "Text")
    widget._set("label_text", "Title\nBody")
    widget.apply_graphic_collection("soft_object")
    widget._set_align("right")
    assert widget._graphic_surface.data["alignment"] == "right"
    widget._set("word_wrap", False)
    widget._apply_appearance()
    assert widget._graphic_surface.data["wrap"] is False


def test_gallery_browsing_and_acceptance_only_return_a_draft(make_widget):
    from calendar_app.presentation.widgets.widget_graphic_dialog import GraphicCollectionDialog

    widget = make_widget()
    before = {key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()}
    dialog = GraphicCollectionDialog(widget, allow_group=True)
    dialog.radios["soft_object"].click()
    dialog.scope.setCurrentIndex(1)
    dialog.apply_button.click()
    assert dialog.result() == dialog.DialogCode.Accepted and dialog.apply_group
    assert dialog.collection_id == "soft_object"
    assert {
        key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()
    } == before
    dialog.close()


def test_countdown_progress_requires_a_matching_known_duration(make_widget):
    widget = make_widget("countdown", "Countdown")
    target = QDateTime.currentDateTime().addSecs(120).toString(Qt.DateFormat.ISODate)
    widget._set("cd_target_iso", target)
    assert widget._graphic_data()["progress"] is None
    widget._set("cd_duration_target", target)
    widget._set("cd_duration_seconds", 120)
    assert 0.9 < widget._graphic_data()["progress"] <= 1
    widget._set(
        "cd_target_iso", QDateTime.currentDateTime().addSecs(240).toString(Qt.DateFormat.ISODate)
    )
    assert widget._graphic_data()["progress"] is None


def test_legacy_stopwatch_measurement_does_not_clip_the_last_digit(make_widget):
    widget = make_widget("stopwatch", "Stopwatch")
    widget._set("sw_elapsed_ms", 1_422_150)
    widget._set("sw_template", widget._DEFAULT_TEMPLATE)
    widget._fit_font_to_size(300, 220)
    widget.grab()
    label = widget._template_label
    doc = QTextDocument()
    doc.setDefaultFont(label.font())
    doc.setDocumentMargin(0)
    doc.setHtml(label.text())
    assert doc.idealWidth() <= label.width() + 1
    assert not label.wordWrap()


def test_custom_stopwatch_templates_keep_wrapping_and_styles_do_not_accumulate(make_widget):
    widget = make_widget("stopwatch", "Stopwatch")
    widget._set("sw_template", "{elapsed}\nA long custom description can wrap")
    widget._apply_appearance()
    assert widget._template_label.wordWrap()
    before = widget._template_label.styleSheet()
    for _ in range(20):
        widget._apply_appearance()
    assert widget._template_label.styleSheet() == before


def test_transparent_collection_does_not_paint_an_opaque_black_rectangle(make_widget):
    widget = make_widget()
    widget.apply_graphic_collection("pure_air", motion=False)
    image = widget.grab().toImage()
    assert image.pixelColor(3, 3).alpha() < 10


def test_state_transitions_stop_when_hidden_or_motion_is_disabled(make_widget, app):
    widget = make_widget("stopwatch", "Stopwatch")
    widget.apply_graphic_collection("air_instrument")
    widget.show()
    widget._set_graphics_runtime_active(True)
    widget.grab()
    surface = widget._graphic_surface
    with patch(
        "calendar_app.presentation.widgets.widget_graphics.system_allows_weather_motion",
        return_value=True,
    ):
        widget._set("sw_running", True)
        widget._tick_sw()
        assert surface._transition.state() == surface._transition.State.Running
        QTest.qWait(30)
        widget.hide()
        assert surface._transition.state() == surface._transition.State.Stopped
    widget.apply_graphic_collection("air_instrument", motion=False)
    assert surface._transition.state() == surface._transition.State.Stopped


def test_flipbook_menu_animates_only_changed_digits_at_the_minute_boundary(make_widget, app):
    widget = make_widget()
    widget._set("clock_template", "{time:%H:%M}")
    date = QDate(2026, 11, 11)
    with (
        patch.object(widget, "_now_tz", return_value=QDateTime(date, QTime(12, 34, 58))) as clock,
        patch(
            "calendar_app.presentation.widgets.widget_graphics.system_allows_weather_motion",
            return_value=True,
        ),
    ):
        menu = QMenu(widget)
        widget._build_context_menu(menu)
        menu.actions()[0].trigger()
        assert widget.graphic_collection_id() == "clock_flipbook"
        widget.show()
        widget._set_graphics_runtime_active(True)
        app.processEvents()
        surface = widget._graphic_surface
        before = surface.grab().toImage()
        tiles = [box.toAlignedRect() for box in surface._text_bounds[1:-1]]
        assert len(tiles) == 4

        clock.return_value = QDateTime(date, QTime(12, 34, 59))
        widget._tick()
        assert surface._flip_from is None
        clock.return_value = QDateTime(date, QTime(12, 35, 0))
        widget._tick()
        assert surface._flip_from == "12:34"
        assert surface.data["main"] == "12:35"
        surface._transition.setCurrentTime(145)
        frame = surface.grab().toImage()
        assert all(before.copy(tile) == frame.copy(tile) for tile in tiles[:-1])
        assert before.copy(tiles[-1]) != frame.copy(tiles[-1])
        surface._transition.setCurrentTime(surface._transition.duration())
        assert surface._flip_from is None

        menu = QMenu(widget)
        widget._build_context_menu(menu)
        assert menu.actions()[0].isChecked()
        menu.actions()[0].trigger()
        assert not widget.graphic_collection_id()
        assert widget._widget_template() == "{time:%H:%M}"


def test_flipbook_snaps_to_time_jumps_and_respects_motion_policy(make_widget, app):
    widget = make_widget()
    widget._set("clock_template", "{time:%I:%M:%S %p}")
    date = QDate(2026, 11, 11)
    with (
        patch.object(widget, "_now_tz", return_value=QDateTime(date, QTime(23, 59, 59))) as clock,
        patch(
            "calendar_app.presentation.widgets.widget_graphics.system_allows_weather_motion",
            return_value=True,
        ),
    ):
        widget.apply_graphic_collection("clock_flipbook")
        widget.show()
        widget._set_graphics_runtime_active(True)
        app.processEvents()
        surface = widget._graphic_surface
        clock.return_value = QDateTime(date.addDays(1), QTime(0, 0, 0))
        widget._tick()
        assert surface._flip_from == "11:59:59"
        assert surface.data["main"] == "12:00"
        assert surface.data["minor"] == ":00"
        assert surface.data["ampm"]
        surface.set_motion_policy("static")
        assert surface._flip_from is None
        clock.return_value = QDateTime(date.addDays(1), QTime(0, 0, 1))
        widget._tick()
        assert surface._flip_from is None
        surface.set_motion_policy("balanced")
        clock.return_value = QDateTime(date.addDays(1), QTime(9, 0, 1))
        widget._tick()
        assert surface._flip_from is None
        assert surface.data["main"] == "09:00"
        clock.return_value = QDateTime(date.addDays(1), QTime(9, 0, 2))
        widget._tick()
        assert surface._flip_from == "09:00:01"
        widget.hide()
        assert surface._flip_from is None


@pytest.mark.parametrize("index,design", enumerate(CLOCK_FLIPBOOK_STICKER_DESIGNS))
def test_transparent_flipbook_gifs_render_only_during_flips(make_widget, app, index, design):
    frames = tuple(frame.toImage() for frame in _sticker_frames(design.clock_sticker))
    assert len(frames) == 16
    assert any(frame != frames[0] for frame in frames[1:])
    for frame in frames:
        assert frame.size() == QSize(144, 144)
        assert frame.pixelColor(0, 0).alpha() == 0
        assert frame.pixelColor(143, 143).alpha() == 0
        assert any(
            frame.pixelColor(x, y).alpha() > 0
            for x in range(20, 124, 10)
            for y in range(20, 124, 10)
        )

    widget = make_widget()
    widget._set("clock_template", "{time:%H:%M}")
    date = QDate(2026, 11, 11)
    with (
        patch.object(widget, "_now_tz", return_value=QDateTime(date, QTime(12, 34, 59))) as clock,
        patch(
            "calendar_app.presentation.widgets.widget_graphics.system_allows_weather_motion",
            return_value=True,
        ),
    ):
        menu = QMenu(widget)
        widget._build_context_menu(menu)
        menu.actions()[1].menu().actions()[index].trigger()
        assert widget.graphic_collection_id() == design.collection_id
        widget.show()
        widget._set_graphics_runtime_active(True)
        app.processEvents()
        surface = widget._graphic_surface
        still = surface.grab().toImage()
        assert still.pixelColor(1, 1).alpha() == 0
        assert still.pixelColor(still.width() // 2, 8).alpha() == 0
        badge = QRect(still.width() * 2 // 3, 0, still.width() // 3, still.height() // 3)
        clock.return_value = QDateTime(date, QTime(12, 35, 0))
        widget._tick()
        assert surface._flip_from == "12:34"
        surface._transition.setCurrentTime(164)
        animated = surface.grab().toImage()
        assert still.copy(badge) != animated.copy(badge)
        surface.set_motion_policy("static")
        assert surface._flip_from is None
        assert still.copy(badge) == surface.grab().toImage().copy(badge)


def test_weather_shadow_does_not_overwrite_text_color_and_contrast_is_readable(make_widget):
    widget = make_widget("weather", "Weather")
    widget._weather_data.update(city="Text", temp="18.2", desc="Clear", _wmo=2)
    widget._apply_weather_design("air_atmosphere")
    widget._set("text_shadow_enabled", True)
    widget._apply_appearance()
    image = widget.grab().toImage()
    white = sum(
        1
        for x in range(20, 140)
        for y in range(20, 170)
        if min(image.pixelColor(x, y).getRgb()[:3]) > 200
    )
    assert white > 100
    surface = widget._scene_surface
    surface.configure(
        scene_id="air_atmosphere",
        data=widget._weather_data,
        foreground="#000000",
        auto_contrast=True,
    )
    top, bottom, fg, _ = surface._palette()
    assert min(contrast_ratio(fg, top), contrast_ratio(fg, bottom)) >= 4.5


def test_keydeck_collection_preserves_actions_profiles_user_art_and_can_restore(make_widget):
    widget = make_widget("launcher_deck", "LauncherDeck")
    original = deepcopy(widget.deck())
    copy = keydeck_collection_deck(original, "soft_object")
    assert original == widget.deck()
    for page, copied in zip(original["pages"], copy["pages"], strict=True):
        for key, other in zip(page["keys"], copied["keys"], strict=True):
            assert key["action"] == other["action"] and key["label"] == other["label"]
            assert key["cap"]["profile"] == other["cap"]["profile"]
    widget.apply_graphic_collection("soft_object")
    assert widget.deck()["case"]["color"] != original["case"]["color"]
    widget.apply_graphic_collection("")
    assert widget.deck() == original


def test_group_apply_leaves_hidden_widgets_untouched(app, tmp_path):
    from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager

    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "group.ini"), QSettings.Format.IniFormat)
    manager = OverlayWidgetManager(owner)
    try:
        first = manager.add_instance("clock", "First")
        second = manager.add_instance("dday", "Second")
        hidden = manager.add_instance("text", "Hidden")
        manager.show_instance(first)
        manager.show_instance(second)
        manager.get_widget(hidden).set_enabled(False)
        manager.apply_graphic_collection(first, "soft_object", motion=False)
        assert manager.get_widget(first).graphic_collection_id() == "soft_object"
        assert manager.get_widget(second).graphic_collection_id() == "soft_object"
        assert manager.get_widget(hidden).graphic_collection_id() == ""
    finally:
        manager.remove_all()
        owner.close()
        app.processEvents()
