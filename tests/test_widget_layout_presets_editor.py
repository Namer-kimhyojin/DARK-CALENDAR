# -*- coding: utf-8 -*-
"""Named layout transactions, shared undo and persisted editor reopen behavior."""

from copy import deepcopy

import pytest

from calendar_app.presentation.dialogs.widget_free_layout_editor import WidgetFreeLayoutEditorDialog
from calendar_app.presentation.widgets.widget_free_layout import read_free_layout
from calendar_app.presentation.widgets.widget_layout_presets import (
    SELECTED_LAYOUT_PRESET_KEY,
    USER_LAYOUT_PRESETS_KEY,
    read_layout_presets,
)
from tests.test_widget_free_layout_editor import editor  # noqa: F401
from tests.test_widget_mode_ux import _APP  # noqa: F401


def test_save_rename_update_delete_share_undo_and_cancel_does_not_persist(editor):
    dialog, settings, live = editor
    saved = deepcopy(settings.values)
    geometry = live.geometry()
    first = dialog.save_as_preset("  집중  ")
    assert dialog.presets[0]["name"] == "집중"
    assert dialog.selected_preset_id == first
    original = deepcopy(dialog.draft)
    dialog.rename_selected_preset("업무")
    dialog.canvas.select_block("date")
    dialog.rect_spins["x"].setValue(80)
    dialog.update_selected_preset()
    assert dialog.presets[0]["layout"] == dialog.draft
    dialog.undo()
    assert dialog.presets[0]["layout"] == original
    dialog.redo()
    before_delete = deepcopy(dialog.draft)
    dialog.delete_selected_preset()
    assert dialog.presets == [] and dialog.selected_preset_id == ""
    assert dialog.draft == before_delete
    dialog.undo()
    assert dialog.presets[0]["id"] == first
    assert dialog.presets[0]["name"] == "업무"
    dialog.reject()
    assert settings.values == saved and live.geometry() == geometry
    dialog.controller.apply_free_layout.assert_not_called()


def test_apply_persists_named_layout_reopen_then_delete_retains_free_geometry(editor):
    dialog, settings, _ = editor
    first = dialog.save_as_preset("내 배치")
    dialog.apply_btn.click()
    assert read_layout_presets(settings) == dialog.presets
    assert settings.value(SELECTED_LAYOUT_PRESET_KEY) == first
    reopened = WidgetFreeLayoutEditorDialog(dialog.controller, preset_id=first)
    try:
        assert reopened.selected_preset_id == first
        assert reopened.draft == dialog.presets[0]["layout"]
        layout = deepcopy(reopened.draft)
        reopened.delete_selected_preset()
        reopened._apply()
        assert read_layout_presets(settings) == []
        assert settings.value(SELECTED_LAYOUT_PRESET_KEY) == ""
        assert read_free_layout(settings) == layout
    finally:
        reopened.close()
        reopened.deleteLater()


def test_select_saved_layout_restores_components_and_positions_preserving_appearance(editor):
    dialog, settings, _ = editor
    first = dialog.save_as_preset("A")
    original = deepcopy(dialog.draft)
    dialog.component_checks["work"].setChecked(True)
    dialog.font_size.setValue(18)
    second = dialog.save_as_preset("B")
    target = deepcopy(dialog.draft)
    dialog.preset_library_combo.setCurrentIndex(dialog.preset_library_combo.findData(first))
    assert dialog.draft == original
    assert dialog.font_size.value() == 18
    dialog.preset_library_combo.setCurrentIndex(dialog.preset_library_combo.findData(second))
    assert dialog.draft == target
    assert settings.value(USER_LAYOUT_PRESETS_KEY) is None


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, "A", "a", "bad\nname"])
def test_invalid_or_duplicate_name_keeps_draft_history_and_settings(editor, name):
    dialog, settings, _ = editor
    dialog.save_as_preset("A")
    before = dialog._snapshot()
    history_index = dialog._history_index
    saved = deepcopy(settings.values)
    with pytest.raises(ValueError):
        dialog.save_as_preset(name)
    assert dialog._snapshot() == before
    assert dialog._history_index == history_index
    assert settings.values == saved


def test_normal_layout_apply_does_not_overwrite_unknown_future_library(editor):
    dialog, settings, _ = editor
    raw = '{"version":9,"presets":[{"future":"keep"}]}'
    settings.setValue(USER_LAYOUT_PRESETS_KEY, raw)
    dialog._apply()
    assert settings.value(USER_LAYOUT_PRESETS_KEY) == raw


def test_explicit_preset_edit_apply_updates_saved_layout_without_extra_save_button(editor):
    dialog, settings, _ = editor
    preset_id = dialog.save_as_preset("수정할 배치")
    dialog._apply()
    changed = WidgetFreeLayoutEditorDialog(dialog.controller, preset_id=preset_id)
    try:
        changed.canvas.select_block("date")
        changed.rect_spins["x"].setValue(80)
        changed._apply()
        assert read_layout_presets(settings)[0]["layout"] == changed.draft
        assert read_layout_presets(settings)[0]["layout"]["blocks"][0]["rect"][0] == 80
    finally:
        changed.close()
        changed.deleteLater()
