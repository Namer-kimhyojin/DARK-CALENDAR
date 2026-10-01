# -*- coding: utf-8 -*-
"""Persistence and hostile-input boundaries for the freely arranged widget."""

from copy import deepcopy
import json

import pytest

from calendar_app.presentation.widgets.widget_free_layout import (
    BLOCK_IDS,
    BLOCK_MINIMUM_SIZES,
    FREE_LAYOUT_MODE_KEY,
    FREE_LAYOUT_SETTING_KEY,
    read_free_layout,
    seed_free_layout,
    validate_free_layout,
    write_free_layout,
)


class Settings:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value


@pytest.mark.parametrize("preset", ["stacked", "dashboard", "agenda_first", "magazine", "minimal"])
def test_each_preset_can_seed_and_roundtrip_without_replacing_legacy_settings(preset):
    settings = Settings(
        {
            "widget_mode_layout": preset,
            "widget_mode_show_clock": "false",
            "widget_mode_calendar_visible_stacked": "false",
            "unrelated": 42,
        }
    )
    original = deepcopy(settings.data)
    seeded = read_free_layout(settings)
    assert settings.data == original
    assert not next(block for block in seeded["blocks"] if block["id"] == "clock")["enabled"]
    assert {block["id"] for block in seeded["blocks"]} == set(BLOCK_IDS)
    written = write_free_layout(settings, seeded)
    assert settings.data[FREE_LAYOUT_MODE_KEY] == "free"
    assert all(settings.data[key] == value for key, value in original.items())
    assert (
        read_free_layout(settings) == written == json.loads(settings.data[FREE_LAYOUT_SETTING_KEY])
    )
    assert write_free_layout(Settings(), written) == written


@pytest.mark.parametrize("raw", ["broken", '{"version":9}', {"version": 1}, [], 17])
def test_corrupt_settings_fall_back_without_writing(raw):
    settings = Settings({FREE_LAYOUT_SETTING_KEY: raw, "widget_mode_layout": "magazine"})
    original = deepcopy(settings.data)
    assert read_free_layout(settings) == seed_free_layout("magazine")
    assert settings.data == original


def test_free_layout_allows_empty_selection_and_intentional_overlap():
    data = seed_free_layout("stacked")
    for block in data["blocks"]:
        block["enabled"] = False
        block["rect"][:2] = [0, 0]
    result = validate_free_layout(data)
    assert not any(block["enabled"] for block in result["blocks"])
    assert all(block["rect"][:2] == [0, 0] for block in result["blocks"])
    result["blocks"][0]["enabled"] = True
    assert not data["blocks"][0]["enabled"]


def test_geometry_is_bounded_and_missing_components_are_disabled():
    result = validate_free_layout(
        {
            "version": 1,
            "canvas": [-12, 99999],
            "snap": False,
            "blocks": [{"id": "calendar", "enabled": True, "rect": [-100, 9999, 9999, -50]}],
        }
    )
    assert result["canvas"] == [320, 1800]
    assert len(result["blocks"]) == 8
    for block in result["blocks"]:
        x, y, width, height = block["rect"]
        assert width >= BLOCK_MINIMUM_SIZES[block["id"]][0]
        assert height >= BLOCK_MINIMUM_SIZES[block["id"]][1]
        assert 0 <= x <= 320 - width
        assert 0 <= y <= 1800 - height
        assert block["enabled"] == (block["id"] == "calendar")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "100", True, None])
def test_invalid_coordinates_do_not_modify_settings(bad):
    settings = Settings({"unrelated": "safe"})
    data = seed_free_layout()
    data["blocks"][0]["rect"][0] = bad
    with pytest.raises(ValueError):
        write_free_layout(settings, data)
    assert settings.data == {"unrelated": "safe"}


@pytest.mark.parametrize(
    "mutation", ["version", "duplicate", "unknown", "enabled", "snap", "calendar_mode"]
)
def test_ambiguous_or_future_data_is_rejected(mutation):
    data = seed_free_layout()
    if mutation == "version":
        data["version"] = True
    elif mutation == "duplicate":
        data["blocks"].append(deepcopy(data["blocks"][0]))
    elif mutation == "unknown":
        data["blocks"][0]["id"] = "unsupported"
    elif mutation == "enabled":
        data["blocks"][0]["enabled"] = "false"
    elif mutation == "snap":
        data["snap"] = "false"
    else:
        data["calendar_mode"] = "unknown"
    with pytest.raises(ValueError):
        validate_free_layout(data)
