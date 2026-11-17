# -*- coding: utf-8 -*-
"""Unassigned (미지정) priority/status and custom label colours."""

from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.domain import task_constants
from calendar_app.domain.task_status_view import can_transition_status, normalize_status
from calendar_app.domain.task_validation import normalize_task_payload
from calendar_app.presentation.theme import task_glyphs

_APP = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_labels():
    task_constants.reset_custom_labels()
    task_glyphs.clear_glyph_cache()
    yield
    task_constants.reset_custom_labels()
    task_glyphs.clear_glyph_cache()


def test_new_item_without_priority_or_status_starts_unassigned():
    payload, issues = normalize_task_payload({"name": "회의", "type": "schedule"})
    assert not issues
    assert payload["priority"] == "none"
    assert payload["status"] == "none"


def test_update_keeps_existing_values_and_accepts_unassigned():
    payload, issues = normalize_task_payload(
        {"priority": "none", "status": "none"}, is_update=True, existing_task={"priority": "high"}
    )
    assert not issues
    assert payload == {"priority": "none", "status": "none"}
    payload, _ = normalize_task_payload({}, is_update=True, existing_task={"priority": "high"})
    assert "priority" not in payload


def test_unassigned_status_moves_freely():
    assert normalize_status("none") == "none"
    assert normalize_status(None) == "pending"  # legacy NULL rows keep their meaning
    for status in ("pending", "in_progress", "completed", "deferred"):
        assert can_transition_status(status, "none")
        assert can_transition_status("none", status)


def test_menus_list_unassigned_last_and_combos_first():
    assert task_constants.PRIORITY_MENU_ITEMS[-1][1] == "none"
    assert task_constants.STATUS_MENU_ITEMS[-1][1] == "none"
    assert task_constants.PRIORITY_COMBO_ITEMS[0][1] == "none"
    assert task_constants.STATUS_COMBO_ITEMS[0][1] == "none"
    assert task_constants.priority_label("none") == "미지정"
    assert task_constants.status_label("none") == "미지정"


def test_unassigned_items_show_no_glyph_on_chips_but_do_in_menus():
    assert task_glyphs.event_qicon({"priority": "none"}) is None
    assert task_glyphs.chip_priority_qicon("none").isNull()
    assert task_glyphs.chip_status_qicon("none").isNull()
    # Menus and combos still get a glyph for the unassigned entry.
    assert task_constants.priority_icon("none") == "fa6s.circle-minus"
    assert task_constants.status_icon("none") == "fa6s.circle-minus"
    assert task_glyphs.priority_glyph_html("none") == ""
    assert task_glyphs.event_qicon({"priority": "high"}) is not None


def test_custom_colour_round_trip_and_reset():
    default_urgent = task_glyphs.priority_color("urgent")
    labels = task_constants.get_current_labels()
    labels["priority"]["urgent"]["color"] = "#22C55E"
    labels["status"]["none"]["color"] = "not-a-colour"
    task_constants.save_custom_labels(labels["priority"], labels["status"])
    task_glyphs.clear_glyph_cache()

    assert task_constants.priority_custom_color("urgent") == "#22c55e"
    assert task_constants.status_custom_color("none") == ""
    assert task_glyphs.priority_color("urgent") != default_urgent
    assert task_glyphs.default_priority_color("urgent") == default_urgent

    task_constants.reset_custom_labels()
    task_glyphs.clear_glyph_cache()
    assert task_constants.priority_custom_color("urgent") == ""
    assert task_glyphs.priority_color("urgent") == default_urgent


def test_colour_schemes_cover_every_row_and_presets_cover_unassigned():
    for scheme in task_constants.COLOR_SCHEMES.values():
        assert set(scheme["priority"]) == set(task_constants.PRIORITY_KEYS)
        assert set(scheme["status"]) == set(task_constants.STATUS_KEYS)
        for value in (*scheme["priority"].values(), *scheme["status"].values()):
            assert value == "" or task_constants.is_color(value)
    for preset in task_constants.get_builtin_presets().values():
        assert set(preset["priority"]) == set(task_constants.PRIORITY_KEYS)
        assert set(preset["status"]) == set(task_constants.STATUS_KEYS)
    assert len(task_constants.GLYPH_CHOICES) == len(set(task_constants.GLYPH_CHOICES)) >= 64
    assert all(task_constants.is_color(c) for c in task_constants.COLOR_SWATCHES)


def test_label_dialog_colour_scheme_reset_and_unassigned_rows():
    from calendar_app.presentation.dialogs.label_settings_dialog import (
        ColorPickerPopup,
        LabelSettingsDialog,
    )

    dialog = LabelSettingsDialog()
    try:
        assert "none" in dialog.prio_fields and "none" in dialog.status_fields
        dialog._apply_color_scheme("vivid")
        priority, status = dialog._collect_data()
        assert priority["urgent"]["color"] == "#ef4444"
        assert status["completed"]["color"] == "#22c55e"

        glyph_btn, color_btn, _text = dialog.prio_fields["urgent"]
        before = glyph_btn.color
        dialog._set_row_color(color_btn, glyph_btn, "")
        assert color_btn.custom_color() == ""
        assert glyph_btn.color != before

        popup = ColorPickerPopup("#ef4444", "#ffffff", dialog)
        assert popup.choice_buttons["#ef4444"].isChecked()
        popup.default_btn.click()
        assert popup.selected_color == ""

        dialog._apply_values(dialog._default_values())
        priority, status = dialog._collect_data()
        assert all(v["color"] == "" for v in priority.values())
        assert priority["none"]["icon"] == task_constants._DEFAULT_PRIORITY_ICON["none"]
    finally:
        dialog.close()
        dialog.deleteLater()
