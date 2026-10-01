# -*- coding: utf-8 -*-
"""User preset selection and staged library editing in customization."""

from copy import deepcopy
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QDialog, QMessageBox
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.widget_free_layout import (
    read_free_layout,
    seed_free_layout,
    write_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    SELECTED_LAYOUT_PRESET_KEY,
    USER_LAYOUT_PRESETS_KEY,
    create_layout_preset,
    get_layout_preset,
    read_layout_presets,
    update_layout_preset,
    write_layout_presets,
)
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


@pytest.fixture
def library_dialog(workspace):
    host, coordinator, widget = workspace
    host.settings.values.update({"widget_mode_skin": "classic_dark", "widget_mode_font_size": 16})
    library, first_id = create_layout_preset([], "Desk", seed_free_layout("stacked"))
    custom = seed_free_layout("dashboard")
    custom["canvas"] = [800, 600]
    for block in custom["blocks"]:
        if block["id"] in ("clock", "calendar"):
            block["enabled"] = False
    library, second_id = create_layout_preset(library, "Focus", custom)
    write_layout_presets(host.settings, library)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.show()
    _APP.processEvents()
    yield dialog, host, coordinator.controller, first_id, second_id
    dialog.reject()
    dialog.deleteLater()
    _APP.processEvents()


def test_custom_selection_apply_keeps_appearance_and_skips_builtin_setter(library_dialog):
    dialog, host, controller, _first_id, second_id = library_dialog
    appearance = {"widget_mode_skin": "classic_dark", "widget_mode_font_size": 16}
    dialog.user_layout_list.setCurrentRow(1)
    assert dialog.draft.value(SELECTED_LAYOUT_PRESET_KEY) == second_id
    assert not any(button.isChecked() for button in dialog.layout_buttons.values())
    assert not dialog.calendar_visibility_checkbox.isChecked()
    assert not dialog.clock_visibility_checkbox.isChecked()
    assert host.settings.value(SELECTED_LAYOUT_PRESET_KEY) is None
    with patch.object(controller, "set_layout") as builtin_setter:
        dialog._apply()
    builtin_setter.assert_not_called()
    assert host.settings.value(SELECTED_LAYOUT_PRESET_KEY) == second_id
    assert read_free_layout(host.settings)["canvas"] == [800, 600]
    assert {key: host.settings.value(key) for key in appearance} == appearance


def test_rename_delete_are_staged_cancel_restores_source_and_geometry(library_dialog):
    dialog, host, controller, first_id, _second_id = library_dialog
    before = deepcopy(host.settings.values)
    geometry = controller.widget.geometry()
    dialog.user_layout_list.setCurrentRow(0)
    dialog._rename_user_layout("Renamed desk")
    assert get_layout_preset(read_layout_presets(dialog.draft), first_id)["name"] == "Renamed desk"
    layout = read_free_layout(dialog.draft)
    dialog._delete_user_layout(confirmed=True)
    assert len(read_layout_presets(dialog.draft)) == 1
    assert dialog.draft.value(SELECTED_LAYOUT_PRESET_KEY) == ""
    assert read_free_layout(dialog.draft) == layout
    dialog.reject()
    assert host.settings.values == before
    assert controller.widget.geometry() == geometry


def test_duplicate_name_rejected_and_builtin_selection_clears_user_id(library_dialog):
    dialog, _host, _controller, _first_id, _second_id = library_dialog
    dialog.user_layout_list.setCurrentRow(0)
    before = read_layout_presets(dialog.draft)
    with patch.object(dialog, "_preset_error") as error:
        dialog._rename_user_layout("Focus")
    error.assert_called_once_with(invalid_name=True)
    assert read_layout_presets(dialog.draft) == before
    dialog.layout_buttons["minimal"].click()
    assert dialog.draft.value(SELECTED_LAYOUT_PRESET_KEY) == ""
    assert dialog.user_layout_list.currentItem() is None
    assert not dialog.preset_edit_btn.isEnabled()


def test_delete_confirmation_names_preset_and_defaults_to_cancel(library_dialog):
    dialog, _host, _controller, first_id, _second_id = library_dialog
    dialog.user_layout_list.setCurrentRow(0)
    before = read_layout_presets(dialog.draft)
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
        dialog._delete_user_layout()
    message = dialog.findChildren(QMessageBox)[-1]
    assert "Desk" in message.text()
    assert message.standardButton(message.defaultButton()) == QMessageBox.StandardButton.Cancel
    assert read_layout_presets(dialog.draft) == before
    assert dialog.draft.value(SELECTED_LAYOUT_PRESET_KEY) == first_id


def test_my_layouts_navigation_reveals_selected_list(library_dialog):
    dialog, _host, _controller, _first_id, _second_id = library_dialog
    dialog.my_layouts_btn.click()
    _APP.processEvents()
    assert dialog.controls_scroll.verticalScrollBar().value() > 0
    assert dialog.user_layout_list.hasFocus()


@pytest.mark.parametrize("accepted", [False, True])
def test_child_editor_apply_stays_in_parent_draft_and_cancel_restores_it(library_dialog, accepted):
    dialog, host, controller, first_id, _second_id = library_dialog
    dialog.user_layout_list.setCurrentRow(0)
    source_before = deepcopy(host.settings.values)
    parent_before = deepcopy(dialog.draft.values)
    changed = read_free_layout(dialog.draft)
    changed["canvas"] = [1000, 700]

    def make_editor(child_controller, parent, *, preset_id):
        assert child_controller.main_window.settings is dialog.draft
        assert child_controller.widget is controller.widget
        assert parent is dialog and preset_id == first_id

        def finish():
            child_controller.apply_free_layout(changed)
            write_layout_presets(
                dialog.draft,
                update_layout_preset(read_layout_presets(dialog.draft), first_id, changed),
            )
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        return Mock(exec=finish)

    with patch(
        "calendar_app.presentation.dialogs.widget_free_layout_editor.WidgetFreeLayoutEditorDialog",
        side_effect=make_editor,
    ):
        dialog._edit_user_layout()
    assert host.settings.values == source_before
    if accepted:
        assert read_free_layout(dialog.draft)["canvas"] == [1000, 700]
        assert get_layout_preset(read_layout_presets(dialog.draft), first_id)["layout"][
            "canvas"
        ] == [1000, 700]
        dialog._apply()
        assert read_free_layout(host.settings)["canvas"] == [1000, 700]
        assert USER_LAYOUT_PRESETS_KEY in host.settings.values
    else:
        assert dialog.draft.values == parent_before
