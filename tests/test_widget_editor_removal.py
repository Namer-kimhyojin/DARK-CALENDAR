# -*- coding: utf-8 -*-
"""The free-layout editor and style editor are gone; saved layouts keep working."""

from unittest.mock import patch

from PyQt6.QtCore import QPoint
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.widget_free_layout import seed_free_layout
from calendar_app.presentation.widgets.widget_layout_presets import (
    create_layout_preset,
    write_layout_presets,
)
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


def _all_action_texts(menu):
    texts = []
    for action in menu.actions():
        texts.append(action.text())
        if action.menu() is not None:
            texts.extend(_all_action_texts(action.menu()))
    return texts


def test_more_menu_has_no_editor_entries(workspace):
    _host, _coordinator, widget = workspace
    captured = []

    def execute(menu, _position):
        captured.extend(_all_action_texts(menu))

    with patch("calendar_app.presentation.widgets.unified_widget_mode.QMenu.exec", new=execute):
        widget._open_menu(QPoint())
    assert captured
    assert not any("구성 편집" in text for text in captured)
    assert not any("위젯 스타일 만들기" in text for text in captured)


def test_controller_has_no_free_layout_editor_entry(workspace):
    _host, coordinator, _widget = workspace
    assert not hasattr(coordinator.controller, "open_free_layout_" + "editor")


def test_saved_free_layout_still_opens_without_editor(workspace):
    host, coordinator, widget = workspace
    library, preset_id = create_layout_preset([], "Desk", seed_free_layout("dashboard"))
    write_layout_presets(host.settings, library)
    assert coordinator.controller.apply_layout_preset(preset_id) is not False
    for _ in range(5):
        _APP.processEvents()
    assert widget._free_layout_active is True
    assert widget._free_runtime is not None
    assert widget._free_runtime.frames


def test_customization_keeps_rename_and_delete_only(workspace):
    host, coordinator, widget = workspace
    library, _preset_id = create_layout_preset([], "Desk", seed_free_layout("stacked"))
    write_layout_presets(host.settings, library)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    try:
        assert not hasattr(dialog, "free_layout_btn")
        assert not hasattr(dialog, "preset_edit_btn")
        assert not hasattr(dialog, "_edit_user_layout")
        dialog.user_layout_list.setCurrentRow(0)
        assert dialog.preset_rename_btn.isEnabled()
        assert dialog.preset_delete_btn.isEnabled()
    finally:
        dialog.reject()
        dialog.deleteLater()


def test_management_hub_has_no_free_editor_button():
    from calendar_app.presentation.widgets import widget_management_ui

    assert not hasattr(widget_management_ui.WidgetModeManagementPanel, "_edit_free")


@pytest.mark.parametrize(
    "module",
    [
        "presentation.dialogs.widget_free_layout_" + "editor",
        "presentation.dialogs.widget_style_" + "editor_dialog",
        "presentation.widgets.widget_layout_" + "editor_canvas",
        "presentation.widgets.widget_layout_" + "editor_preview",
        "presentation.widgets.widget_layout_" + "editor_io",
    ],
)
def test_editor_modules_are_deleted(module):
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"calendar_app.{module}")
