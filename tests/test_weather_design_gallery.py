# -*- coding: utf-8 -*-
"""Weather designs are complete local recipes; gallery browsing remains a draft."""

from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSettings, QSize, Qt
from PyQt6.QtGui import QTextDocument, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QLabel
import pytest

from calendar_app.presentation.widgets.overlay_display_presets import overlay_display_presets
from calendar_app.presentation.widgets.overlay_template_validation import validate_widget_template
from calendar_app.presentation.widgets.weather_asset_packs import weather_asset_packs
from calendar_app.presentation.widgets.weather_design_dialog import (
    WeatherDesignGalleryDialog,
    weather_design_preview_pixmap,
)
from calendar_app.presentation.widgets.weather_designs import (
    WEATHER_DESIGN_CATEGORIES,
    weather_design,
    weather_designs,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def data():
    return {
        "city": "Seoul",
        "temp": "18.2",
        "unit": "°C",
        "desc": "Cloudy",
        "humidity": "62",
        "wind": "2.4",
        "_wmo": 2,
        "_day_period": "day",
        "error": "",
    }


@pytest.fixture
def gallery(app, data):
    dialog = WeatherDesignGalleryDialog(data, current_design_id="soft_cloud")
    yield dialog
    dialog.reject()
    dialog.close()
    app.processEvents()


def _choose(dialog, design_id):
    item = next(
        dialog.grid.item(row)
        for row in range(dialog.grid.count())
        if dialog.grid.item(row).data(Qt.ItemDataRole.UserRole) == design_id
    )
    dialog.grid.setCurrentItem(item)
    return item


def test_catalog_has_twenty_four_distinct_complete_recipes_in_six_balanced_categories():
    designs = weather_designs()
    assert len(designs) == len({design.design_id for design in designs}) == 24
    assert Counter(design.category for design in designs) == dict.fromkeys(
        [item[0] for item in WEATHER_DESIGN_CATEGORIES], 4
    )
    assert {design.appearance_preset_id for design in designs} >= {
        "midnight_glass",
        "pearl_mist",
        "graphite_minimal",
        "pure_type",
        "electric_cyan",
        "aurora_violet",
        "forest_moss",
        "sunset_coral",
        "champagne_gold",
        "paper_ivory",
        "terminal_green",
        "retro_amber",
        "high_contrast",
    }
    assert {design.asset_pack_id for design in designs} == {
        pack.pack_id for pack in weather_asset_packs()
    }
    assert {design.shape for design in designs} == {"card", "capsule", "circle", "poster"}
    assert len({design.template for design in designs}) >= 18
    appearances = {preset.preset_id for preset in overlay_display_presets()}
    for design in designs:
        assert design.appearance_preset_id in appearances
        assert not validate_widget_template("weather", design.template)
        assert "{temp" in design.template and "{city" in design.template
        assert weather_design(design.design_id) is design
    assert weather_design("unknown-weather-design") is None


def test_design_catalog_cannot_be_mutated_by_gallery_consumers():
    design = weather_design("soft_cloud")
    with pytest.raises(FrozenInstanceError):
        design.template = "changed"


def test_browsing_filtering_and_cancel_do_not_mutate_weather_or_return_a_design(gallery, data):
    before = deepcopy(data)
    _choose(gallery, "cyan_pulse")
    gallery.search_edit.setText("paper")
    gallery.search_edit.clear()
    gallery.category_combo.setCurrentIndex(gallery.category_combo.findData("nature"))
    assert gallery.grid.count() == 4
    gallery.reject()
    assert gallery.selected_design is None
    assert data == before


def test_only_explicit_apply_returns_the_selected_complete_design(gallery, data):
    before = deepcopy(data)
    _choose(gallery, "violet_orbit")
    assert gallery.selected_design is None
    gallery.apply_button.click()
    assert gallery.result() == QDialog.DialogCode.Accepted
    assert gallery.selected_design is weather_design("violet_orbit")
    assert gallery.selected_design.asset_pack_id == "orbit_weather"
    assert gallery.selected_design.shape == "circle"
    assert data == before


def test_search_matches_ids_korean_names_and_recovers_from_no_results(gallery):
    gallery.search_edit.setText("pixel_board")
    assert gallery.grid.count() == 1
    assert gallery.selected_design_id() == "pixel_board"
    gallery.search_edit.setText("세이지")
    assert gallery.grid.count() == 1
    assert gallery.selected_design_id() == "sage_card"
    gallery.search_edit.setText("no-design-matches-f714af9")
    assert gallery.grid.count() == 0
    assert not gallery.apply_button.isEnabled()
    assert not gallery.detail_preview.pixmap() or gallery.detail_preview.pixmap().isNull()
    gallery.apply_button.click()
    assert gallery.selected_design is None
    gallery.search_edit.clear()
    assert gallery.grid.count() == 24
    assert gallery.apply_button.isEnabled()


def test_double_click_previews_without_applying(gallery):
    item = _choose(gallery, "paper_weather")
    gallery.grid.itemDoubleClicked.emit(item)
    assert gallery.selected_design is None
    assert gallery.result() != QDialog.DialogCode.Accepted


def test_gallery_renders_selected_recipe_through_the_shared_weather_renderer(app, data):
    from calendar_app.presentation.widgets import weather_design_dialog as module

    with patch.object(
        module, "render_weather_template", wraps=module.render_weather_template
    ) as render:
        dialog = WeatherDesignGalleryDialog(data)
        try:
            _choose(dialog, "clear_line")
            args, kwargs = render.call_args
            design = weather_design("clear_line")
            assert args[0] == design.template
            assert args[1] == data and args[1] is not data
            assert kwargs["asset_pack_id"] == design.asset_pack_id
            assert kwargs["base_font_size"] == design.font_size
            assert not dialog.detail_preview.pixmap().isNull()
        finally:
            dialog.reject()


def test_gallery_never_writes_settings_during_browse_or_apply(app, data):
    with patch.object(QSettings, "setValue") as write:
        dialog = WeatherDesignGalleryDialog(data)
        _choose(dialog, "desert_note")
        dialog.apply_button.click()
        assert dialog.selected_design.design_id == "desert_note"
        write.assert_not_called()


def test_lazy_cards_keep_thumbnail_and_label_height_and_stop_on_close(gallery, app):
    assert not gallery._icons
    gallery.show()
    app.processEvents()
    item = gallery.grid.item(0)
    required = gallery.grid.iconSize().height() + gallery.grid.fontMetrics().height()
    assert gallery.grid.visualItemRect(item).height() >= required
    QTest.qWait(100)
    assert not item.icon().isNull()
    assert 0 < len(gallery._icons) < 24
    assert gallery.grid.visualItemRect(item).height() >= required
    gallery.reject()
    assert not gallery._thumb_timer.isActive()


def test_category_wheel_does_not_change_the_filter(gallery):
    combo = gallery.category_combo
    before = combo.currentIndex()
    local = QPointF(combo.rect().center())
    event = QWheelEvent(
        local,
        QPointF(combo.mapToGlobal(local.toPoint())),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(combo, event)
    assert combo.currentIndex() == before


def test_preview_polishes_the_native_face_before_rendering_light_and_violet_backgrounds(
    app, data, monkeypatch
):
    original_render = QFrame.render
    face_bounds = []

    def capture_bounds(frame, painter, *args):
        face_bounds.append(painter.worldTransform().mapRect(QRectF(frame.rect())))
        return original_render(frame, painter, *args)

    monkeypatch.setattr(QFrame, "render", capture_bounds)
    light = weather_design_preview_pixmap(weather_design("crystal_band"), data, QSize(400, 280))
    violet = weather_design_preview_pixmap(weather_design("aurora_panel"), data, QSize(400, 280))
    # Font availability changes each face's fitted size and position. Sample the
    # top-center background inside the actual rendered face, before its text.
    # Without native style polishing both remain the dark desktop sample.
    light_bounds, violet_bounds = face_bounds
    light_background = light.toImage().pixelColor(
        round(light_bounds.center().x()), round(light_bounds.top() + 6)
    )
    assert min(light_background.red(), light_background.green(), light_background.blue()) > 180
    violet_background = violet.toImage().pixelColor(
        round(violet_bounds.center().x()), round(violet_bounds.top() + 6)
    )
    assert violet_background.red() > violet_background.green()
    assert violet_background.blue() > violet_background.red()


def test_all_native_preview_frames_and_complete_html_fit_the_painter_bounds(app, data, monkeypatch):
    original_render = QFrame.render
    rendered = []

    def checked_render(frame, painter, *args):
        label = frame.findChild(QLabel)
        document = QTextDocument()
        document.setDefaultFont(label.font())
        document.setDocumentMargin(0)
        document.setHtml(label.text())
        assert label.height() >= document.size().height()
        logical_device = QRectF(
            0,
            0,
            painter.device().width() / painter.device().devicePixelRatio(),
            painter.device().height() / painter.device().devicePixelRatio(),
        )
        fitted = painter.worldTransform().mapRect(QRectF(frame.rect()))
        assert logical_device.contains(fitted)
        rendered.append(frame.size())
        return original_render(frame, painter, *args)

    monkeypatch.setattr(QFrame, "render", checked_render)
    for design in weather_designs():
        weather_design_preview_pixmap(design, data, QSize(264, 188), dpr=2)
    assert len(rendered) == 24


@pytest.mark.parametrize("design", weather_designs(), ids=lambda design: design.design_id)
def test_every_recipe_renders_real_static_weather_without_modifying_data(app, data, design):
    before = deepcopy(data)
    pixmap = weather_design_preview_pixmap(design, data, QSize(264, 188), dpr=2)
    assert not pixmap.isNull()
    assert pixmap.devicePixelRatio() == 2
    assert pixmap.width() == 528
    assert pixmap.height() == 376
    image = pixmap.toImage()
    background = image.pixelColor(0, 0)
    assert any(
        image.pixelColor(x, y) != background
        for x in range(20, image.width() - 20, 20)
        for y in range(20, image.height() - 20, 20)
    )
    assert data == before
