# -*- coding: utf-8 -*-
"""Eighty selectable designs must render, persist and restore the original data."""

from copy import deepcopy

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QWidget
import pytest

from calendar_app.presentation.widgets.widget_graphic_catalog import (
    COLLECTIONS,
    DESIGNS_BY_KIND,
    collection_for_kind,
    graphic_collections,
)
from calendar_app.presentation.widgets.widget_graphic_dialog import GraphicCollectionDialog
from tests.test_widget_graphic_collections import app, make_widget  # noqa: F401

KINDS = {
    "clock": ("clock", "Clock"),
    "date_card": ("datecard", "DateCard"),
    "dday": ("dday", "DDay"),
    "stopwatch": ("stopwatch", "Stopwatch"),
    "countdown": ("countdown", "Countdown"),
    "text": ("text", "Text"),
    "weather": ("weather", "Weather"),
    "launcher_deck": ("launcher_deck", "LauncherDeck"),
}
DESIGNS = [design for designs in DESIGNS_BY_KIND.values() for design in designs]


def test_catalog_has_ten_additional_stable_designs_for_each_widget():
    assert len(DESIGNS_BY_KIND) == 8
    assert len(DESIGNS) == len({design.collection_id for design in DESIGNS}) == 80
    for kind, designs in DESIGNS_BY_KIND.items():
        assert len(designs) == len({design.layout for design in designs}) == 10
        assert graphic_collections(kind) == COLLECTIONS + designs


@pytest.mark.parametrize("design", DESIGNS, ids=lambda design: design.collection_id)
def test_all_eighty_designs_render_in_compact_standard_and_large_sizes(make_widget, design):
    module, name = KINDS[design.widget_kind]
    widget = make_widget(module, name)
    if module == "text":
        widget._set("label_text", "A title\nUseful information\nA second line")
    before_template = widget._widget_template()
    before_deck = deepcopy(widget.deck()) if module == "launcher_deck" else None
    widget.apply_graphic_collection(design.collection_id, motion=False)
    assert widget.graphic_collection_id() == design.collection_id
    if module != "launcher_deck":
        for size in (QSize(160, 120), QSize(320, 220), QSize(480, 360)):
            widget._set("fixed_w", size.width())
            widget._set("fixed_h", size.height())
            widget._fit_font_to_size(size.width(), size.height())
            assert not widget.grab().isNull()
            surface = (
                widget._scene_surface._design_surface
                if module == "weather"
                else widget._graphic_surface
            )
            assert surface is not None
            assert all(
                surface.rect().adjusted(-1, -1, 1, 1).contains(box.toAlignedRect())
                for box in surface._text_bounds
            )
    else:
        assert widget.deck()["scale"] == before_deck["scale"]
        for page, old_page in zip(widget.deck()["pages"], before_deck["pages"], strict=True):
            for key, old_key in zip(page["keys"], old_page["keys"], strict=True):
                assert key["action"] == old_key["action"]
                assert key["cap"]["material"] == old_key["cap"]["material"]
    widget.apply_graphic_collection("")
    assert widget._widget_template() == before_template
    if before_deck is not None:
        assert widget.deck() == before_deck


@pytest.mark.parametrize("kind", KINDS)
def test_gallery_offers_thirteen_designs_and_one_original_with_exclusive_selection(
    make_widget, kind
):
    widget = make_widget(*KINDS[kind])
    before = {key: widget._s().value(key) for key in widget._s().allKeys()}
    dialog = GraphicCollectionDialog(widget)
    assert len(dialog.radios) == 14
    last = DESIGNS_BY_KIND[kind][-1]
    dialog.radios[last.collection_id].click()
    assert sum(radio.isChecked() for radio in dialog.radios.values()) == 1
    assert dialog.collection_id == last.collection_id
    dialog.radios[""].click()
    assert sum(radio.isChecked() for radio in dialog.radios.values()) == 1
    assert {key: widget._s().value(key) for key in widget._s().allKeys()} == before
    dialog.reject()
    dialog.deleteLater()


def test_group_selection_maps_to_the_same_design_family_for_each_widget(make_widget):
    source = DESIGNS_BY_KIND["clock"][4]
    for kind, values in KINDS.items():
        target = collection_for_kind(source.collection_id, kind)
        widget = make_widget(*values)
        widget.apply_graphic_collection(source.collection_id, motion=False)
        assert target.layout == source.layout
        assert target.widget_kind == kind
        assert widget.graphic_collection_id() == target.collection_id


@pytest.mark.parametrize("kind", KINDS)
def test_new_design_restores_when_a_widget_is_recreated(make_widget, kind):
    widget = make_widget(*KINDS[kind])
    selected = DESIGNS_BY_KIND[kind][7]
    widget.apply_graphic_collection(selected.collection_id, motion=False)
    widget._s().sync()
    owner = QWidget()
    owner.settings = widget._s()
    restored = type(widget)(owner)
    try:
        assert restored.graphic_collection_id() == selected.collection_id
        assert not restored.grab().isNull()
        if kind == "launcher_deck":
            assert restored.deck() == widget.deck()
    finally:
        restored._set_runtime_active(False)
        restored.close()
        restored.deleteLater()
        owner.close()
        owner.deleteLater()


@pytest.mark.parametrize(
    "design", DESIGNS_BY_KIND["weather"], ids=lambda design: design.collection_id
)
def test_expanded_weather_keeps_forecasts_inside_one_rounded_card(make_widget, design):
    widget = make_widget("weather", "Weather")
    widget._weather_data.update(
        city="City",
        temp="18.2",
        forecast_high="21",
        forecast_low="15",
        _wmo=2,
        hourly=[
            {"label": f"{15 + hour}:00", "temp": str(19 - hour), "_wmo": 2, "precip_mm": 0.0}
            for hour in range(6)
        ],
    )
    widget.apply_graphic_collection(design.collection_id, motion=False)
    widget._set("fixed_w", 480)
    widget._set("fixed_h", 360)
    widget._fit_font_to_size(480, 360)
    scene = widget._scene_surface
    image = scene.grab().toImage()
    assert len(scene.data["hourly"]) == 6
    assert scene._design_surface.height() == scene.height() - 165
    assert scene._art_rect.bottom() <= scene._design_surface.height()
    assert (
        "15" in scene._design_surface.data["detail"]
        and "21" in scene._design_surface.data["detail"]
    )
    assert image.pixelColor(1, image.height() - 2).alpha() < 10
