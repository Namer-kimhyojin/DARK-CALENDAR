# -*- coding: utf-8 -*-
"""User preset persistence, detached drafts and defensive validation."""

from copy import deepcopy
import json
from uuid import UUID

from PyQt6.QtCore import QSettings
import pytest

from calendar_app.presentation.widgets.widget_free_layout import seed_free_layout
from calendar_app.presentation.widgets.widget_layout_presets import (
    MAX_LAYOUT_PRESETS,
    MAX_PRESET_JSON_BYTES,
    SELECTED_LAYOUT_PRESET_KEY,
    USER_LAYOUT_PRESETS_KEY,
    create_layout_preset,
    delete_layout_preset,
    get_layout_preset,
    read_layout_presets,
    rename_layout_preset,
    update_layout_preset,
    write_layout_presets,
)


class Settings:
    def __init__(self, raw=None):
        self.values = {} if raw is None else {USER_LAYOUT_PRESETS_KEY: raw}
        self.writes = []

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.writes.append((key, value))
        self.values[key] = value


def library():
    return create_layout_preset([], "첫 번째 배치", seed_free_layout("stacked"))


def test_crud_preserves_identity_and_draft_isolation():
    source = seed_free_layout("stacked")
    presets, preset_id = create_layout_preset([], "  첫 번째 배치  ", source)
    assert preset_id.startswith("user_")
    assert UUID(preset_id[5:]).version == 4
    assert presets[0]["name"] == "첫 번째 배치"
    source["blocks"][0]["enabled"] = False
    assert presets[0]["layout"]["blocks"][0]["enabled"] is True
    original = deepcopy(presets)

    renamed = rename_layout_preset(presets, preset_id, "새 이름")
    replacement = seed_free_layout("dashboard")
    updated = update_layout_preset(renamed, preset_id, replacement)
    replacement["calendar_mode"] = "week"
    assert updated[0]["id"] == preset_id
    assert updated[0]["name"] == "새 이름"
    assert updated[0]["layout"]["calendar_mode"] == "month"
    assert presets == original
    assert delete_layout_preset(updated, preset_id) == []
    assert len(updated) == 1


def test_roundtrip_real_qsettings_restart(tmp_path):
    path = str(tmp_path / "widget.ini")
    first = QSettings(path, QSettings.Format.IniFormat)
    first.setValue("widget_mode_layout", "dashboard")
    first.setValue("widget_mode_skin", "classic_dark")
    presets, preset_id = library()
    stored = write_layout_presets(first, presets)
    first.setValue(SELECTED_LAYOUT_PRESET_KEY, preset_id)
    first.sync()
    fresh = QSettings(path, QSettings.Format.IniFormat)
    assert read_layout_presets(fresh) == stored
    assert fresh.value(SELECTED_LAYOUT_PRESET_KEY) == preset_id
    assert fresh.value("widget_mode_layout") == "dashboard"
    assert fresh.value("widget_mode_skin") == "classic_dark"
    assert json.loads(fresh.value(USER_LAYOUT_PRESETS_KEY))["version"] == 1


def test_only_explicit_write_changes_settings_and_returns_detached_library():
    settings = Settings()
    assert read_layout_presets(settings) == []
    presets, preset_id = library()
    renamed = rename_layout_preset(presets, preset_id, "draft")
    assert settings.writes == []
    written = write_layout_presets(settings, renamed)
    assert [key for key, _ in settings.writes] == [USER_LAYOUT_PRESETS_KEY]
    written[0]["layout"]["blocks"][0]["enabled"] = False
    loaded = read_layout_presets(settings)
    loaded[0]["name"] = "local mutation"
    assert read_layout_presets(settings)[0]["name"] == "draft"
    assert read_layout_presets(settings)[0]["layout"]["blocks"][0]["enabled"] is True


def test_get_is_detached_and_unknown_returns_none():
    presets, preset_id = library()
    found = get_layout_preset(presets, preset_id)
    found["layout"]["blocks"][0]["rect"][0] = 999
    assert found != presets[0]
    assert get_layout_preset(presets, "user_" + "0" * 32) is None


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, "a\nb", "a\x00b", "a\u200bb", 42])
def test_invalid_names_rejected_without_mutation(name):
    presets, preset_id = library()
    original = deepcopy(presets)
    with pytest.raises(ValueError):
        create_layout_preset(presets, name, seed_free_layout())
    with pytest.raises(ValueError):
        rename_layout_preset(presets, preset_id, name)
    assert presets == original


def test_name_length_boundary_and_casefold_duplicates():
    presets, _ = create_layout_preset([], "Straße", seed_free_layout())
    with pytest.raises(ValueError):
        create_layout_preset(presets, " STRASSE ", seed_free_layout())
    presets, second_id = create_layout_preset(presets, "x" * 80, seed_free_layout())
    with pytest.raises(ValueError):
        rename_layout_preset(presets, second_id, "strasse")


@pytest.mark.parametrize(
    "mutator", [update_layout_preset, rename_layout_preset, delete_layout_preset]
)
def test_unknown_id_mutators_fail_without_mutation(mutator):
    presets, _ = library()
    original = deepcopy(presets)
    arguments = [presets, "user_" + "0" * 32]
    if mutator is update_layout_preset:
        arguments.append(seed_free_layout())
    elif mutator is rename_layout_preset:
        arguments.append("renamed")
    with pytest.raises(ValueError, match="unknown"):
        mutator(*arguments)
    assert presets == original


@pytest.mark.parametrize(
    "raw",
    ["{secret malformed", "null", '{"version":2,"presets":[]}', '{"version":true,"presets":[]}'],
)
def test_corrupt_or_future_read_is_safe_and_does_not_rewrite(raw, caplog):
    settings = Settings(raw)
    assert read_layout_presets(settings) == []
    assert settings.values[USER_LAYOUT_PRESETS_KEY] == raw
    assert settings.writes == []
    assert "Invalid user widget layout presets" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.parametrize(
    "problem", ["duplicate_id", "duplicate_name", "invalid_id", "invalid_layout", "extra_field"]
)
def test_invalid_libraries_rejected_atomically_on_write_and_read(problem):
    presets, _ = library()
    if problem.startswith("duplicate"):
        presets.append(deepcopy(presets[0]))
        if problem == "duplicate_id":
            presets[1]["name"] = "another"
        else:
            presets[1]["id"] = "user_" + "0" * 32
    elif problem == "invalid_id":
        presets[0]["id"] = "stacked"
    elif problem == "invalid_layout":
        presets[0]["layout"]["version"] = 2
    else:
        presets[0]["skin"] = "classic_dark"
    settings = Settings()
    with pytest.raises(ValueError):
        write_layout_presets(settings, presets)
    assert settings.writes == []
    raw = json.dumps({"version": 1, "presets": presets})
    settings = Settings(raw)
    assert read_layout_presets(settings) == []
    assert settings.values[USER_LAYOUT_PRESETS_KEY] == raw
    assert settings.writes == []


def test_library_limit_and_json_size_limit():
    layout = seed_free_layout()
    presets = [
        {"id": "user_" + f"{index:032x}", "name": f"preset {index}", "layout": layout}
        for index in range(MAX_LAYOUT_PRESETS)
    ]
    assert len(write_layout_presets(Settings(), presets)) == 100
    with pytest.raises(ValueError):
        create_layout_preset(presets, "extra", layout)
    oversized = " " * MAX_PRESET_JSON_BYTES + '{"version":1,"presets":[]}'
    settings = Settings(oversized)
    assert read_layout_presets(settings) == []
    assert settings.writes == []
    invalid = deepcopy(presets[:1])
    invalid[0]["layout"]["extra"] = "x" * MAX_PRESET_JSON_BYTES
    with pytest.raises(ValueError, match="size limit"):
        write_layout_presets(settings, invalid)
    assert settings.writes == []


def test_layout_normalization_keeps_layout_only():
    source = seed_free_layout()
    source["skin"] = "classic_dark"
    source["appearance"] = {"font": "example"}
    presets, _ = create_layout_preset([], "layout only", source)
    assert "skin" not in presets[0]["layout"]
    assert "appearance" not in presets[0]["layout"]
    assert source["skin"] == "classic_dark"
