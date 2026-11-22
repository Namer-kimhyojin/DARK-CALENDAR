# -*- coding: utf-8 -*-
import json

import pytest

from calendar_app.presentation.widgets.widget_free_layout import (
    seed_free_layout,
    write_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    create_layout_preset,
    read_layout_presets,
    write_layout_presets,
)
from calendar_app.presentation.widgets.widget_mode_display import (
    LayoutDisplay,
    read_layout_display,
)
from calendar_app.presentation.widgets.widget_mode_migration import (
    classify_user_layout,
    migrate_widget_mode_settings,
)
from calendar_app.presentation.widgets.widget_mode_skins import get_widget_mode_layout


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


@pytest.fixture
def missing(tmp_path):
    return tmp_path / "absent.json"


@pytest.mark.parametrize(
    "old,new,display",
    [
        ("day_brief", "stacked", LayoutDisplay("week", True, True)),
        ("month_focus", "stacked", LayoutDisplay("month", False, True)),
        ("week_navigator", "stacked", LayoutDisplay("week", False, True)),
        ("agenda_first", "stacked", LayoutDisplay("week", False, False)),
        ("side_planner", "dashboard", LayoutDisplay("month", True, True)),
        ("magazine", "dashboard", LayoutDisplay("month", False, False)),
        ("focus_dock", "minimal", LayoutDisplay("week", False, True)),
    ],
)
def test_retired_layout_maps_with_display(old, new, display, missing):
    s = Settings()
    s.setValue("widget_mode_layout", old)
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is True
    assert s.value("widget_mode_layout") == new
    assert s.value("widget_mode_layout_legacy") == old
    assert read_layout_display(s, get_widget_mode_layout(new)) == display


def test_kept_layouts_get_defaults_without_rewrite(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "dashboard")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_layout") == "dashboard"
    assert s.value("widget_mode_layout_legacy") is None
    assert s.value("widget_mode_calendar_style_dashboard") == "month"
    assert s.value("widget_mode_show_overview_work_board") in (True, "true")


def test_geometry_size_and_calendar_visibility_follow_active_layout(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "month_focus")
    s.setValue("unified_widget_geometry_month_focus", "G1")
    s.setValue("unified_widget_size_month_focus_calendar_hidden", "S1")
    s.setValue("unified_widget_geometry_stacked", "OLD")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("unified_widget_geometry_stacked") == "G1"
    assert s.value("unified_widget_size_stacked_calendar_hidden") == "S1"
    assert str(s.value("widget_mode_calendar_visible_stacked")).lower() == "true"
    assert s.value("unified_widget_geometry_month_focus") == "G1"


def test_existing_display_keys_are_not_overwritten(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "day_brief")
    s.setValue("widget_mode_show_overview_stacked", False)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_show_overview_stacked") is False


def test_missing_layout_uses_legacy_skin_link(missing):
    s = Settings()
    s.setValue("widget_mode_skin", "forest_mist")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_layout") == "stacked"
    assert s.value("widget_mode_surface") == "card"


@pytest.mark.parametrize(
    "skin,surface",
    [
        ("studio_linen", "line"),
        ("studio_contrast", "outline"),
        ("studio_graphite", "compact"),
        ("studio_lilac", "card"),
        (None, "card"),
    ],
)
def test_skin_maps_to_surface(skin, surface, missing):
    s = Settings()
    if skin:
        s.setValue("widget_mode_skin", skin)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_surface") == surface


def test_existing_surface_is_kept(missing):
    s = Settings()
    s.setValue("widget_mode_skin", "studio_linen")
    s.setValue("widget_mode_surface", "outline")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_surface") == "outline"


def test_second_run_changes_nothing(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "side_planner")
    s.setValue("widget_mode_skin", "studio_arctic")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    snapshot = dict(s.values)
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is False
    assert s.values == snapshot


def test_unsaved_free_layout_is_preserved_once(missing):
    s = Settings()
    write_free_layout(s, seed_free_layout("stacked"))
    migrate_widget_mode_settings(s, user_styles_path=missing)
    presets = read_layout_presets(s)
    assert [p["name"] for p in presets] == ["이전 자유 구성"]
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is False
    assert len(read_layout_presets(s)) == 1
    assert s.value("widget_mode_layout_mode") == "free"


def test_no_free_layout_key_creates_no_preset(missing):
    s = Settings()
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert read_layout_presets(s) == []


def test_free_layout_equal_to_saved_preset_is_not_duplicated(missing):
    s = Settings()
    write_free_layout(s, seed_free_layout("stacked"))
    presets, _ = create_layout_preset([], "내 배치", json.loads(s.value("widget_mode_free_layout")))
    write_layout_presets(s, presets)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert [p["name"] for p in read_layout_presets(s)] == ["내 배치"]


def test_invalid_free_layout_is_ignored(missing):
    s = Settings()
    s.setValue("widget_mode_free_layout", "{broken")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert read_layout_presets(s) == []


def test_unknown_and_messy_layout_values(missing):
    for raw in ("", "  ", "NOPE", " Day_Brief "):
        s = Settings()
        s.setValue("widget_mode_layout", raw)
        migrate_widget_mode_settings(s, user_styles_path=missing)
        assert s.value("widget_mode_layout") == "stacked"
    s = Settings()
    s.setValue("widget_mode_layout", "NOPE")
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_layout_legacy") is None


def test_legacy_keys_are_left_untouched(missing):
    s = Settings()
    for key, value in {
        "widget_mode_skin": "studio_linen",
        "widget_mode_panel_theme": "dark",
        "widget_mode_text_opacity": 80,
        "widget_mode_background_opacity": 70,
    }.items():
        s.setValue(key, value)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_skin") == "studio_linen"
    assert s.value("widget_mode_panel_theme") == "dark"
    assert s.value("widget_mode_text_opacity") == 80
    assert s.value("widget_mode_background_opacity") == 70


def _style_file(tmp_path, layout):
    path = tmp_path / "widget_mode_styles.json"
    path.write_text(
        json.dumps({"version": 1, "skins": [], "layouts": [layout]}),
        encoding="utf-8",
        errors="strict",
    )
    return path


def test_user_layout_classified_from_style_file(tmp_path):
    raw = {
        "layout_id": "user_layout_abc123",
        "placements": [["hero", 0, 0, 1, 1], ["calendar", 0, 1, 1, 1]],
        "calendar_mode": "month",
        "show_overview": True,
        "searchable": False,
    }
    path = _style_file(tmp_path, raw)
    s = Settings()
    s.setValue("widget_mode_layout", "user_layout_abc123")
    migrate_widget_mode_settings(s, user_styles_path=path)
    assert s.value("widget_mode_layout") == "dashboard"
    assert s.value("widget_mode_layout_legacy") == "user_layout_abc123"
    assert read_layout_display(s, get_widget_mode_layout("dashboard")) == LayoutDisplay(
        "month", True, False
    )


def test_classify_user_layout_rules():
    assert classify_user_layout({"presentation": "board"})[0] == "work_board"
    assert classify_user_layout({"placements": [["hero", 0, 0, 1, 1]]})[0] == "minimal"
    stacked = {"placements": [["calendar", 0, 0, 1, 1], ["agenda", 1, 0, 1, 1]]}
    new_id, display = classify_user_layout(stacked)
    assert new_id == "stacked" and display.calendar_style == "week"


def test_user_layout_with_missing_style_file(tmp_path):
    s = Settings()
    s.setValue("widget_mode_layout", "user_layout_abc123")
    bad = tmp_path / "widget_mode_styles.json"
    bad.write_text("{broken", encoding="utf-8", errors="strict")
    migrate_widget_mode_settings(s, user_styles_path=bad)
    assert s.value("widget_mode_layout") == "stacked"
    assert bad.read_text(encoding="utf-8", errors="strict") == "{broken"


def test_free_layout_with_taken_name_is_kept_under_numbered_name(missing):
    s = Settings()
    layout_a = seed_free_layout("stacked")
    layout_b = seed_free_layout("dashboard")
    assert layout_a != layout_b
    presets, _ = create_layout_preset([], "이전 자유 구성", layout_a)
    write_layout_presets(s, presets)
    write_free_layout(s, layout_b)
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is True
    saved = read_layout_presets(s)
    assert [p["name"] for p in saved] == ["이전 자유 구성", "이전 자유 구성 2"]
    assert saved[1]["layout"] == json.loads(s.value("widget_mode_free_layout"))
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is False
    assert len(read_layout_presets(s)) == 2
