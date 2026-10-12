# -*- coding: utf-8 -*-
"""Weather display presets remain complete, renderable and safe for saved templates."""

import json
from pathlib import Path
import re
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.widgets import overlay_base
from calendar_app.presentation.widgets.overlay_base import _PRESET_FALLBACK, _get_widget_presets
from calendar_app.presentation.widgets.overlay_template_validation import validate_widget_template
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget

CATALOG = Path("calendar_app/presentation/widgets/widget_presets.json")
WEATHER_PRESETS = _PRESET_FALLBACK["weather"]
LEGACY_IDS = (
    "default",
    "temp_only",
    "icon_temp",
    "full",
    "compact_inline",
    "city_focus",
    "desc_card",
    "wind_humidity",
    "minimal_icon",
)
NEW_IDS = (
    "daily_card",
    "horizontal_bar",
    "wide_weather",
    "hero_icon",
    "night_card",
    "travel_city",
    "humidity_focus",
    "wind_focus",
    "rain_focus",
    "temperature_badge",
    "mini_dashboard",
)


@pytest.fixture
def weather(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "presets.ini"), QSettings.Format.IniFormat)
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
        return_value=Mock(),
    ):
        widget = OverlayWeatherWidget(owner)
        widget._weather_data.update(
            city="Seoul",
            temp="23",
            unit="°C",
            desc="Clear",
            humidity="65",
            wind="3.2",
            _wmo=0,
            _day_period="day",
            error="",
        )
        yield widget, owner
        widget._set_runtime_active(False)
        widget.close()
        owner.close()
        app.processEvents()


def test_weather_catalog_keeps_legacy_order_and_adds_eleven_distinct_valid_layouts():
    shipped = json.loads(CATALOG.read_text(encoding="utf-8", errors="strict"))["weather"]
    assert shipped == WEATHER_PRESETS
    assert len(shipped) == 20
    assert [entry["label_key"] for entry in shipped] == [
        "widget.weather.preset_" + suffix for suffix in LEGACY_IDS + NEW_IDS
    ]
    assert len({entry["template"] for entry in shipped}) == 20
    for entry in shipped:
        assert entry["label_default"]
        assert not validate_widget_template("weather", entry["template"])
        variables = re.findall(r"\{([^{}|]+)", entry["template"])
        assert set(variables) <= {"city", "temp", "unit", "desc", "icon", "humidity", "wind"}


def test_bundled_default_has_balanced_icon_temperature_unit_and_city_sizes():
    assert WEATHER_PRESETS[0]["template"] == (
        "{icon|size=64}\n{temp|size=28|bold}{unit|size=14}\n{city|size=12|color=muted}"
    )


def test_malformed_catalog_recovers_all_weather_presets_and_translates_each_label(monkeypatch):
    broken = {"weather": [dict(WEATHER_PRESETS[0], template="{rain_chance}")]}
    monkeypatch.setattr(overlay_base, "_load_widget_presets_json", lambda: broken)
    seen = []

    def translate(key, fallback):
        seen.append(key)
        return "translated:" + fallback

    presets = _get_widget_presets("weather", translate)
    assert len(presets) == 20
    assert seen == [entry["label_key"] for entry in WEATHER_PRESETS]
    assert [template for _, template in presets] == [entry["template"] for entry in WEATHER_PRESETS]
    assert all(name.startswith("translated:") for name, _ in presets)


@pytest.mark.parametrize(
    "preset", WEATHER_PRESETS, ids=lambda entry: entry["label_key"].split(".")[-1]
)
def test_each_weather_layout_resolves_and_renders_available_values_without_live_requests(
    weather, preset
):
    widget, _ = weather
    widget._set("font_size", 24)
    widget._set("weather_template", preset["template"])
    widget._apply_and_resize()
    html = widget._template_label.text()
    assert "{" not in html and "}" not in html
    assert widget._template_label.sizeHint().width() > 0
    assert widget._template_label.sizeHint().height() > 0
    assert not widget._template_label.isHidden()
    if "{icon" in preset["template"]:
        assert "<img " in html
    if "{temp" in preset["template"]:
        assert "23" in html and "°C" in html
    if "{city" in preset["template"]:
        assert "Seoul" in html
    if "{humidity" in preset["template"]:
        assert "65" in html
    if "{wind" in preset["template"]:
        assert "3.2" in html
    widget._network_manager.get.assert_not_called()


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_metric_layouts_preserve_temperature_units_and_missing_values(weather, unit):
    widget, _ = weather
    widget._weather_data.update(temp="--", unit=unit, humidity="--", wind="--")
    widget._set("weather_template", WEATHER_PRESETS[-1]["template"])
    widget._apply_and_resize()
    html = widget._template_label.text()
    assert unit in html
    assert "--" in html
    assert "{" not in html
    assert widget._weather_data["humidity"] == "--"
    assert widget._weather_data["wind"] == "--"


@pytest.mark.parametrize(
    "custom_template",
    [
        "{city|size=18|bold}\n{temp|size=48|bold}{unit|size=16}",
        "{icon|size=32}\n{temp|size=24|bold}{unit}\n{city|size=11|color=muted}",
    ],
)
def test_existing_saved_templates_survive_catalog_lookup_initialization_and_restart(
    weather, custom_template
):
    widget, owner = weather
    widget._set("weather_template", custom_template)
    widget.apply_initial_settings()
    before = {key: owner.settings.value(key) for key in owner.settings.allKeys()}
    assert len(_get_widget_presets("weather", lambda key, fallback: fallback)) == 20
    assert before == {key: owner.settings.value(key) for key in owner.settings.allKeys()}
    widget.close()
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
        return_value=Mock(),
    ):
        restored = OverlayWeatherWidget(owner)
        try:
            restored.apply_initial_settings()
            assert restored._get("weather_template") == custom_template
        finally:
            restored.close()
