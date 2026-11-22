# -*- coding: utf-8 -*-
import json

import pytest

from calendar_app.presentation.widgets.widget_free_layout import (
    seed_free_layout,
    write_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    create_layout_preset,
    delete_layout_preset,
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
from calendar_app.presentation.widgets.widget_mode_visibility import (
    read_widget_calendar_visibility,
)


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


@pytest.mark.parametrize(
    "old,new",
    [("month_focus", "stacked"), ("side_planner", "dashboard"), ("magazine", "dashboard")],
)
def test_former_board_layout_keeps_its_calendar_visible_without_a_scoped_key(old, new, missing):
    # Before phase 1 these IDs defaulted to a visible calendar and ignored the
    # legacy widget_mode_show_week mirror; the migrated layout must open the same way.
    s = Settings()
    s.setValue("widget_mode_layout", old)
    s.setValue("widget_mode_show_week", False)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert str(s.value(f"widget_mode_calendar_visible_{new}")).lower() == "true"
    assert read_widget_calendar_visibility(s, new) is True
    assert s.value("widget_mode_show_week") is False


def test_former_board_layout_keeps_an_explicit_collapsed_calendar(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "month_focus")
    s.setValue("widget_mode_calendar_visible_month_focus", False)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert read_widget_calendar_visibility(s, "stacked") is False


def test_non_board_retired_layout_still_follows_the_legacy_mirror(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "day_brief")
    s.setValue("widget_mode_show_week", False)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert read_widget_calendar_visibility(s, "stacked") is False


def test_dashboard_calendar_visibility_is_unchanged_by_migration(missing):
    s = Settings()
    s.setValue("widget_mode_layout", "dashboard")
    s.setValue("widget_mode_show_week", False)
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert s.value("widget_mode_calendar_visible_dashboard") is None
    assert read_widget_calendar_visibility(s, "dashboard") is True


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
    # The old app resolved "auto" to month only for the built-in dashboard and
    # magazine IDs; a user_layout_* ID always resolved it to week.
    side_by_side = [["calendar", 0, 0, 1, 1], ["agenda", 0, 1, 1, 1]]
    for raw in (
        {"placements": side_by_side, "calendar_mode": "auto"},
        {"placements": side_by_side},
    ):
        new_id, display = classify_user_layout(raw)
        assert new_id == "dashboard" and display.calendar_style == "week"
    month = classify_user_layout({"placements": side_by_side, "calendar_mode": "month"})
    assert month[1].calendar_style == "month"


def test_user_layout_with_missing_style_file(tmp_path):
    s = Settings()
    s.setValue("widget_mode_layout", "user_layout_abc123")
    bad = tmp_path / "widget_mode_styles.json"
    bad.write_text("{broken", encoding="utf-8", errors="strict")
    migrate_widget_mode_settings(s, user_styles_path=bad)
    assert s.value("widget_mode_layout") == "stacked"
    assert bad.read_text(encoding="utf-8", errors="strict") == "{broken"


@pytest.mark.parametrize(
    "placements",
    [5, 3.5, True, {"calendar": 1}, "calendar", [5, None, ["calendar"], ["calendar", 0]]],
)
def test_corrupt_user_layout_placements_do_not_abort_migration(placements, tmp_path):
    path = _style_file(tmp_path, {"layout_id": "user_layout_bad", "placements": placements})
    s = Settings()
    s.setValue("widget_mode_layout", "user_layout_bad")
    s.setValue("widget_mode_skin", "studio_linen")
    write_free_layout(s, seed_free_layout("stacked"))
    migrate_widget_mode_settings(s, user_styles_path=path)
    assert s.value("widget_mode_layout") == "minimal"
    assert s.value("widget_mode_layout_legacy") == "user_layout_bad"
    assert s.value("widget_mode_surface") == "line"
    assert [p["name"] for p in read_layout_presets(s)] == ["이전 자유 구성"]


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


def _delete_all_presets(s):
    presets = read_layout_presets(s)
    for preset in presets:
        presets = delete_layout_preset(presets, preset["id"])
    write_layout_presets(s, presets)


def test_deleted_preserved_free_layout_is_not_added_again(missing):
    s = Settings()
    write_free_layout(s, seed_free_layout("stacked"))
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert [p["name"] for p in read_layout_presets(s)] == ["이전 자유 구성"]
    _delete_all_presets(s)
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is False
    assert read_layout_presets(s) == []


def test_applied_then_deleted_preset_does_not_return_as_preserved_layout(missing):
    s = Settings()
    write_free_layout(s, seed_free_layout("dashboard"))
    applied = json.loads(s.value("widget_mode_free_layout"))
    presets, _ = create_layout_preset([], "내 배치", applied)
    write_layout_presets(s, presets)
    # A launch while the preset is applied: the working layout matches it.
    migrate_widget_mode_settings(s, user_styles_path=missing)
    assert [p["name"] for p in read_layout_presets(s)] == ["내 배치"]
    _delete_all_presets(s)
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is False
    assert read_layout_presets(s) == []


def test_preserved_fingerprint_list_is_capped(missing):
    s = Settings()
    s.setValue(
        "widget_mode_preserved_free_layouts",
        json.dumps([f"{index:064x}" for index in range(60)]),
    )
    write_free_layout(s, seed_free_layout("stacked"))
    migrate_widget_mode_settings(s, user_styles_path=missing)
    stored = json.loads(s.value("widget_mode_preserved_free_layouts"))
    assert len(stored) == 50
    assert f"{59:064x}" in stored and f"{0:064x}" not in stored


def test_unreadable_fingerprint_list_still_preserves_once(missing):
    s = Settings()
    s.setValue("widget_mode_preserved_free_layouts", "{broken")
    write_free_layout(s, seed_free_layout("stacked"))
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is True
    assert len(read_layout_presets(s)) == 1
    assert migrate_widget_mode_settings(s, user_styles_path=missing) is False


class _KeyedSettings(Settings):
    def allKeys(self):
        return list(self.values)

    def remove(self, key):
        self.values.pop(key, None)


def test_ensure_widget_migrates_before_first_layout():
    from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController
    from tests.test_widget_mode_ux import _APP, Host  # noqa: F401

    host = Host()
    host.settings.setValue("widget_mode_layout", "side_planner")
    controller = UnifiedWidgetController(host)
    window = controller.ensure_widget()
    try:
        assert window.active_layout_id() == "dashboard"
        assert window.workspace_overview.isVisibleTo(window)
    finally:
        window.deleteLater()
        host.deleteLater()


def test_ensure_widget_survives_migration_failure(monkeypatch):
    from calendar_app.presentation.widgets import unified_widget_mode
    from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController
    from tests.test_widget_mode_ux import _APP, Host  # noqa: F401

    def boom(*args, **kwargs):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(unified_widget_mode, "migrate_widget_mode_settings", boom)
    host = Host()
    window = UnifiedWidgetController(host).ensure_widget()
    try:
        assert window is not None
    finally:
        window.deleteLater()
        host.deleteLater()


def test_restoring_old_snapshot_migrates_layout():  # Review Focus 3
    from types import SimpleNamespace

    from calendar_app.presentation.widgets.widget_workspace_runtime import (
        WidgetWorkspaceService,
    )

    settings = _KeyedSettings()
    settings.setValue("widget_mode_layout", "dashboard")
    settings.setValue("widget_mode_calendar_style_dashboard", "week")
    service = SimpleNamespace(settings=settings, owner=SimpleNamespace())
    WidgetWorkspaceService._restore_mode(
        service, {"widget_mode_layout": "month_focus", "widget_mode_skin": "studio_linen"}
    )
    assert settings.value("widget_mode_layout") == "stacked"
    assert settings.value("widget_mode_calendar_style_stacked") == "month"
    assert settings.value("widget_mode_surface") == "line"
    # The stale per-layout key was dropped by the restore, then refilled with the default.
    assert settings.value("widget_mode_calendar_style_dashboard") != "week"


def test_restore_survives_migration_failure(monkeypatch):
    from types import SimpleNamespace

    from calendar_app.presentation.widgets import widget_workspace_runtime as runtime

    def boom(*args, **kwargs):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(runtime, "migrate_widget_mode_settings", boom)
    settings = _KeyedSettings()
    service = SimpleNamespace(settings=settings, owner=SimpleNamespace())
    runtime.WidgetWorkspaceService._restore_mode(service, {"widget_mode_layout": "stacked"})
    assert settings.value("widget_mode_layout") == "stacked"


def test_restoring_snapshot_keeps_handled_free_layouts_and_preserves_new_ones(missing):
    from types import SimpleNamespace

    from calendar_app.presentation.widgets.widget_workspace_runtime import (
        WidgetWorkspaceService,
    )

    settings = _KeyedSettings()
    write_free_layout(settings, seed_free_layout("stacked"))
    old_layout = settings.value("widget_mode_free_layout")
    migrate_widget_mode_settings(settings, user_styles_path=missing)
    _delete_all_presets(settings)
    service = SimpleNamespace(settings=settings, owner=SimpleNamespace())

    # The same, already handled layout from an old snapshot is not added back.
    WidgetWorkspaceService._restore_mode(
        service,
        {
            "widget_mode_layout": "stacked",
            "widget_mode_layout_mode": "free",
            "widget_mode_free_layout": old_layout,
        },
    )
    assert read_layout_presets(settings) == []

    # A snapshot carrying a different free layout is still preserved.
    write_free_layout(settings, seed_free_layout("dashboard"))
    other_layout = settings.value("widget_mode_free_layout")
    WidgetWorkspaceService._restore_mode(
        service,
        {
            "widget_mode_layout": "stacked",
            "widget_mode_layout_mode": "free",
            "widget_mode_free_layout": other_layout,
        },
    )
    saved = read_layout_presets(settings)
    assert [p["name"] for p in saved] == ["이전 자유 구성"]
    assert saved[0]["layout"] == json.loads(other_layout)
