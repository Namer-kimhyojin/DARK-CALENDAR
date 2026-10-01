# -*- coding: utf-8 -*-
"""User layout menu application and compatibility with built-in layout switching."""

from copy import deepcopy
from unittest.mock import patch

from PyQt6.QtCore import QPoint

from calendar_app.presentation.widgets.widget_free_layout import (
    FREE_LAYOUT_MODE_KEY,
    read_free_layout,
    seed_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    SELECTED_LAYOUT_PRESET_KEY,
    USER_LAYOUT_PRESETS_KEY,
    create_layout_preset,
    read_layout_presets,
    write_layout_presets,
)
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


def _save_preset(settings):
    layout = seed_free_layout("dashboard")
    layout["blocks"][0]["rect"][0] = 24
    presets, preset_id = create_layout_preset([], "나의 자유 배치", layout)
    write_layout_presets(settings, presets)
    return preset_id, presets[0]["layout"]


def test_apply_user_preset_then_builtin_preserves_library_and_appearance(workspace):
    host, coordinator, widget = workspace
    settings = host.settings
    settings.setValue("widget_mode_skin", "classic_dark")
    settings.setValue("widget_mode_font_size", 16)
    preset_id, layout = _save_preset(settings)
    payload = settings.value(USER_LAYOUT_PRESETS_KEY)
    assert coordinator.controller.apply_layout_preset(preset_id)
    assert settings.value(SELECTED_LAYOUT_PRESET_KEY) == preset_id
    assert settings.value(FREE_LAYOUT_MODE_KEY) == "free"
    assert read_free_layout(settings) == layout
    assert widget._free_layout_active
    coordinator.controller.set_layout("minimal")
    assert not widget._free_layout_active
    assert settings.value(SELECTED_LAYOUT_PRESET_KEY) == ""
    assert settings.value(USER_LAYOUT_PRESETS_KEY) == payload
    assert settings.value("widget_mode_font_size") == 16
    assert settings.value("widget_mode_skin") == "classic_dark"
    assert coordinator.controller.apply_layout_preset(preset_id)
    assert read_layout_presets(settings)[0]["id"] == preset_id
    assert read_free_layout(settings) == layout


def test_missing_preset_does_not_modify_live_widget_or_settings(workspace):
    host, coordinator, widget = workspace
    before = deepcopy(host.settings.values)
    geometry = widget.geometry()
    assert not coordinator.controller.apply_layout_preset("missing")
    assert host.settings.values == before
    assert widget.geometry() == geometry


def test_user_layout_menu_marks_only_matching_saved_configuration(workspace):
    host, coordinator, widget = workspace
    preset_id, _layout = _save_preset(host.settings)
    coordinator.controller.apply_layout_preset(preset_id)
    captured = []

    def execute(menu, _position):
        for action in menu.actions():
            child = action.menu()
            if child is not None:
                captured.extend(child.actions())
        return None

    with patch("PyQt6.QtWidgets.QMenu.exec", execute):
        widget._open_menu(QPoint(0, 0))
    selected = next(action for action in captured if action.text() == "나의 자유 배치")
    assert selected.isChecked()
    coordinator.controller.set_layout("stacked")
    captured.clear()
    with patch("PyQt6.QtWidgets.QMenu.exec", execute):
        widget._open_menu(QPoint(0, 0))
    selected = next(action for action in captured if action.text() == "나의 자유 배치")
    assert not selected.isChecked()
    selected.trigger()
    assert host.settings.value(SELECTED_LAYOUT_PRESET_KEY) == preset_id
    assert widget._free_layout_active
