# -*- coding: utf-8 -*-
"""Weather families scale safely and remain visually distinct across conditions."""

import base64
from hashlib import sha256
import re

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.widgets import weather_asset_packs as packs
from calendar_app.presentation.widgets.weather_vector_art import (
    VECTOR_WEATHER_PACK_IDS,
    render_weather_vector,
)

STATES = (
    (0, "day", "clear_day"),
    (0, "night", "clear_night"),
    (2, "day", "partly_cloudy_day"),
    (2, "night", "partly_cloudy_night"),
    (3, "day", "cloudy"),
    (45, "day", "fog"),
    (51, "day", "drizzle"),
    (61, "day", "rain"),
    (65, "day", "heavy_rain"),
    (71, "day", "snow"),
    (75, "day", "heavy_snow"),
    (95, "day", "thunderstorm"),
    (99, "day", "hail"),
    (-1, "day", "unknown"),
)


@pytest.fixture(scope="module", autouse=True)
def _application():
    app = QApplication.instance() or QApplication([])
    yield app


def _rgba(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return image.constBits().asstring(image.sizeInBytes())


def _fingerprint(pixmap):
    return sha256(_rgba(pixmap)).hexdigest()


def test_existing_packs_and_default_are_preserved_with_six_additions():
    entries = packs.weather_asset_packs()
    assert tuple(pack.pack_id for pack in entries[:4]) == (
        "air_soft",
        "paper_weather",
        "mono_atmosphere",
        "classic",
    )
    assert packs.DEFAULT_WEATHER_ASSET_PACK_ID == "air_soft"
    assert len(entries) == 10
    assert {pack.pack_id for pack in entries[4:]} == VECTOR_WEATHER_PACK_IDS
    assert len({pack.pack_id for pack in entries}) == 10
    for pack in entries[4:]:
        assert pack.label_key == f"widget.weather.asset_pack_{pack.pack_id}"


@pytest.mark.parametrize("pack_id", sorted(VECTOR_WEATHER_PACK_IDS))
@pytest.mark.parametrize("code,period,state", STATES)
def test_every_vector_family_renders_all_fourteen_conditions(pack_id, code, period, state):
    assert packs.weather_condition_id(code, period) == state
    art = packs.weather_asset_pixmap(pack_id, code, period, 128)
    assert not art.isNull()
    assert art.size() == QSize(128, 128)
    alpha = _rgba(art)[3::4]
    assert any(alpha)
    assert sum(bool(value) for value in alpha) < 128 * 128
    assert max(alpha[:128]) == max(alpha[-128:]) == 0
    assert max(alpha[::128]) == max(alpha[127::128]) == 0


@pytest.mark.parametrize("code,period,_state", STATES)
def test_family_choices_have_distinct_silhouettes_and_actual_pixels(code, period, _state):
    images = [
        packs.weather_asset_pixmap(pack_id, code, period, 128)
        for pack_id in sorted(VECTOR_WEATHER_PACK_IDS)
    ]
    assert len({_fingerprint(image) for image in images}) == 6
    assert len({sha256(_rgba(image)[3::4]).hexdigest() for image in images}) >= 5


@pytest.mark.parametrize("pack_id", sorted(VECTOR_WEATHER_PACK_IDS) + ["classic"])
def test_day_and_night_are_visually_distinct(pack_id):
    for code in (0, 2):
        day = packs.weather_asset_pixmap(pack_id, code, "day", 128)
        night = packs.weather_asset_pixmap(pack_id, code, "night", 128)
        assert not day.isNull() and not night.isNull()
        assert _fingerprint(day) != _fingerprint(night)


@pytest.mark.parametrize("pack_id", [pack.pack_id for pack in packs.weather_asset_packs()])
def test_all_packs_render_at_1024_pixels_and_html_png_dimensions_agree(pack_id):
    html = packs.weather_asset_html(pack_id, 61, "day", 1024)
    assert 'width="1024" height="1024"' in html
    payload = re.search(r"base64,([A-Za-z0-9+/=]+)", html)
    assert payload is not None
    decoded = QImage.fromData(base64.b64decode(payload.group(1)))
    assert not decoded.isNull()
    assert decoded.size() == QSize(1024, 1024)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 96),
        ("oops", 96),
        (float("nan"), 96),
        (float("inf"), 96),
        ([], 96),
        ({}, 96),
        (0, 16),
        (-22, 16),
        (10**100, 1536),
        (1536, 1536),
    ],
)
def test_malformed_and_extreme_sizes_are_bounded_without_exceptions(value, expected):
    art = packs.weather_asset_pixmap("outline_weather", 0, "day", value, color="bad color")
    assert art.size() == QSize(expected, expected)
    html = packs.weather_asset_html("outline_weather", 0, "day", value)
    assert f'width="{expected}" height="{expected}"' in html


@pytest.mark.parametrize("value", [None, "bad", [], {}, float("inf"), float("nan")])
def test_malformed_wmo_values_use_unknown_art(value):
    assert packs.weather_condition_id(value, "night") == "unknown"
    art = packs.weather_asset_pixmap("flat_weather", value, None, 64)
    assert not art.isNull()


def test_sprite_cell_transparent_space_is_trimmed_without_distorting_the_art():
    source = QPixmap(200, 160)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    painter.fillRect(QRectF(80, 60, 40, 20), Qt.GlobalColor.red)
    painter.end()
    trimmed = packs._trim_transparent(source)
    assert trimmed.size() == QSize(44, 24)
    assert trimmed.toImage().pixelColor(2, 2).red() == 255
    assert trimmed.toImage().pixelColor(0, 0).alpha() == 0


def test_sprite_crop_empty_and_null_images_are_safe():
    assert packs._trim_transparent(QPixmap()).isNull()
    transparent = QPixmap(32, 32)
    transparent.fill(Qt.GlobalColor.transparent)
    assert packs._trim_transparent(transparent).size() == QSize(32, 32)


@pytest.mark.parametrize("pack_id", ("air_soft", "paper_weather", "mono_atmosphere"))
def test_generated_art_uses_a_substantial_part_of_the_requested_icon_size(pack_id):
    art = packs.weather_asset_pixmap(pack_id, 0, "day", 128)
    image = art.toImage()
    points = [(x, y) for y in range(128) for x in range(128) if image.pixelColor(x, y).alpha() > 32]
    assert points
    width = max(x for x, _y in points) - min(x for x, _y in points) + 1
    height = max(y for _x, y in points) - min(y for _x, y in points) + 1
    assert max(width, height) >= 92


def test_html_cache_reuses_encoded_png_for_identical_normalized_request(monkeypatch):
    packs._weather_asset_html_cached.cache_clear()
    original = packs.weather_asset_pixmap
    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(packs, "weather_asset_pixmap", record)
    first = packs.weather_asset_html("flat_weather", 61, "day", 83)
    second = packs.weather_asset_html(" FLAT_WEATHER ", "61", " DAY ", "83")
    assert first == second
    assert len(calls) == 1
    assert packs._weather_asset_html_cached.cache_info().maxsize == 64


@pytest.mark.parametrize("size", [QSize(-1, -1), QSize(0, 0), QSize(10**6, 10**6), None])
def test_preview_bounds_are_safe(size):
    preview = packs.weather_pack_preview_pixmap("neon_weather", size)
    assert not preview.isNull()
    assert 1 <= preview.width() <= packs.MAX_WEATHER_ART_SIZE
    assert 1 <= preview.height() <= packs.MAX_WEATHER_ART_SIZE


def test_direct_vector_entry_point_rejects_unknown_pack_and_defends_bad_inputs():
    assert render_weather_vector([], "clear_day", 48).isNull()
    assert render_weather_vector("missing", "clear_day", 48).isNull()
    assert render_weather_vector("flat_weather", [], None).size() == QSize(96, 96)
