# -*- coding: utf-8 -*-
"""Malformed JSON settings must not break color menus or label dialogs."""

import json
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
import pytest

from calendar_app.application import task_usecases
from calendar_app.domain import task_constants
from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin


@pytest.fixture
def settings(tmp_path, monkeypatch):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(task_usecases, "QSettings", lambda *args: store)
    monkeypatch.setattr("PyQt6.QtCore.QSettings", lambda *args: store)
    return store


@pytest.mark.parametrize("raw", ["null", "true", "123", '"red"', '{"red": 1}', "broken"])
def test_auto_color_history_rejects_non_list_settings(settings, raw):
    settings.setValue("auto_color_recent_history", raw)
    assert task_usecases._load_auto_color_history() == []
    assert len(task_usecases.auto_assign_theme_colors("#4da6ff", 3)) == 3


def test_auto_color_history_preserves_valid_entries(settings):
    settings.setValue("auto_color_recent_history", '[null, {}, 42, "red", "#123456", "bad"]')
    assert task_usecases._load_auto_color_history() == ["#ff0000", "#123456"]


@pytest.mark.parametrize("raw", ["null", "true", "123", '"red"', '{"red": 1}', "broken"])
def test_recent_panel_colors_reject_non_list_settings(settings, raw):
    settings.setValue("panel_base_color_recent", raw)
    owner = SimpleNamespace(
        settings=settings,
        _normalize_hex_color=MainWindowUiActionsMixin._normalize_hex_color,
    )
    # Bind the existing helper as a method, as it is on OverlayApp.
    owner._normalize_hex_color = lambda value: MainWindowUiActionsMixin._normalize_hex_color(
        owner, value
    )
    assert MainWindowUiActionsMixin._get_recent_panel_colors(owner) == []


@pytest.mark.parametrize(
    "raw", ["null", "true", "123", '"preset"', '{"name": "wrong root"}', "broken"]
)
def test_label_presets_recover_from_invalid_root(settings, raw):
    settings.setValue("label_user_presets", raw)
    assert task_constants.get_user_presets() == []
    task_constants.save_user_preset("new", {}, {})
    assert task_constants.get_user_presets() == [{"name": "new", "priority": {}, "status": {}}]


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        12,
        "bad",
        {},
        {"name": 1},
        {"name": "bad", "priority": []},
        {"name": "bad", "status": {"pending": None}},
        {"name": "bad", "priority": {"high": {"icon": []}}},
    ],
)
def test_label_presets_keep_valid_rows_and_can_still_delete(settings, invalid):
    valid = {"name": "keep", "priority": {"high": {"icon": "!", "text": "High"}}, "status": {}}
    settings.setValue("label_user_presets", json.dumps([invalid, valid]))
    assert task_constants.get_user_presets() == [valid]
    task_constants.save_user_preset("new", {}, {})
    assert [row["name"] for row in task_constants.get_user_presets()] == ["keep", "new"]
    task_constants.delete_user_preset("new")
    assert task_constants.get_user_presets() == [valid]
