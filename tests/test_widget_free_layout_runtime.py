# -*- coding: utf-8 -*-
"""Free layout preserves preset behavior, cached records and existing actions."""

from copy import deepcopy
from unittest.mock import patch

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QCheckBox, QPushButton
import pytest

from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController
from calendar_app.presentation.widgets.widget_free_layout import (
    FREE_LAYOUT_MODE_KEY,
    FREE_LAYOUT_SETTING_KEY,
    read_free_layout,
)
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


def layout_data():
    return {
        "version": 1,
        "canvas": [900, 800],
        "snap": False,
        "blocks": [
            {"id": "date", "enabled": True, "rect": [0, 0, 220, 60]},
            {"id": "clock", "enabled": True, "rect": [240, 0, 160, 60]},
            {"id": "calendar", "enabled": True, "rect": [0, 80, 300, 180]},
            {"id": "filters", "enabled": True, "rect": [320, 80, 560, 100]},
            {"id": "agenda", "enabled": True, "rect": [320, 200, 560, 250]},
            {"id": "schedule", "enabled": True, "rect": [0, 480, 280, 300]},
            {"id": "work", "enabled": True, "rect": [300, 480, 280, 300]},
            {"id": "directive", "enabled": True, "rect": [600, 480, 280, 300]},
        ],
    }


def flush():
    for _ in range(5):
        _APP.processEvents()


def enable(workspace):
    _, coordinator, widget = workspace
    widget.resize(900, 800)
    coordinator.controller.apply_free_layout(layout_data())
    flush()
    return coordinator.controller, widget._free_runtime


def test_apply_free_layout_stays_inside_one_window_and_preserves_controls(workspace):
    host, coordinator, widget = workspace
    _, runtime = enable(workspace)
    assert widget.active_layout_id() == "free"
    assert host.settings.value(FREE_LAYOUT_MODE_KEY) == "free"
    assert runtime.parent() is widget.container
    assert runtime.frames["clock"].isAncestorOf(widget.clock_label)
    for control in (
        widget.restore_btn,
        widget.customize_btn,
        widget.completed_btn,
        widget.undo_btn,
    ):
        assert control.window() is widget
    assert coordinator.controller is widget.controller


@pytest.mark.parametrize("width,height", [(320, 480), (420, 520), (760, 600), (1100, 900)])
def test_runtime_rects_remain_inside_canvas_and_resize_without_saving(workspace, width, height):
    host, _, widget = workspace
    _, runtime = enable(workspace)
    saved = deepcopy(read_free_layout(host.settings))
    widget.resize(width, height)
    flush()
    for frame in runtime.frames.values():
        assert runtime.rect().contains(frame.geometry())
    assert read_free_layout(host.settings) == saved


def test_split_panels_filter_locally_without_mutating_main_filter(workspace):
    _, _, widget = workspace
    _, runtime = enable(workspace)
    widget.set_filter("work")
    flush()
    assert widget._active_filter == "work"
    assert [row.item_key for row in runtime.panels["schedule"].rows] == [("task", 1)]
    assert [row.item_key for row in runtime.panels["work"].rows] == [("task", 2)]
    assert [row.item_key for row in runtime.panels["directive"].rows] == [("directive", 3)]
    for panel in runtime.panels.values():
        assert len({row.item_key for row in panel.rows}) == len(panel.rows)


def test_split_panel_original_ids_route_to_existing_dialogs(workspace):
    host, _, _ = workspace
    _, runtime = enable(workspace)
    runtime.panels["schedule"].rows[0].findChild(QPushButton, "agenda_item_title").click()
    host.open_modify_task_dialog.assert_called_once_with(1)
    runtime.panels["directive"].rows[0].findChild(QPushButton, "agenda_item_title").click()
    host.open_directive_dialog.assert_called_once_with(task_id=3)


def test_split_panel_completion_failure_and_undo_restore_original_status(workspace):
    host, _, widget = workspace
    controller, runtime = enable(workspace)
    check = runtime.panels["work"].rows[0].findChild(QCheckBox, "agenda_complete")
    host.handle_task_status_changed.return_value = False
    check.setFocus()
    check.click()
    flush()
    assert not check.isChecked()
    assert check.hasFocus()
    host.handle_task_status_changed.return_value = True
    check.click()
    flush()
    assert not runtime.panels["work"].rows
    assert widget.undo_btn.isVisible()
    widget.undo_btn.click()
    flush()
    host.handle_task_status_changed.assert_called_with(2, "in_progress")
    assert [row.item_key for row in runtime.panels["work"].rows] == [("task", 2)]
    assert controller._undo_completion is None


def test_free_blocks_own_clock_calendar_visibility_and_presets_keep_their_settings(workspace):
    host, _, widget = workspace
    controller, runtime = enable(workspace)
    host.settings.setValue("widget_mode_show_clock", False)
    host.settings.setValue("widget_mode_calendar_visible_stacked", False)
    widget.apply_selected_layout(force=True)
    flush()
    assert widget.clock_label.isVisible()
    assert widget.cal_grid.isVisible()
    widget.week_toggle_btn.click()
    flush()
    assert not runtime.frames["calendar"].isVisible()
    assert host.settings.value("widget_mode_calendar_visible_stacked") is False
    controller.set_layout("stacked")
    flush()
    assert not widget._free_layout_active
    assert not widget.clock_label.isVisible()
    assert not widget.cal_grid.isVisible()


def test_presets_remain_available_and_return_without_deleting_free_draft(workspace):
    host, _, widget = workspace
    controller, _ = enable(workspace)
    stored = host.settings.value(FREE_LAYOUT_SETTING_KEY)
    controller.set_layout("dashboard")
    flush()
    assert widget.active_layout_id() == "dashboard"
    assert widget._free_runtime is None
    assert host.settings.value(FREE_LAYOUT_MODE_KEY) == "preset"
    assert host.settings.value(FREE_LAYOUT_SETTING_KEY) == stored
    assert widget.container.isAncestorOf(widget.agenda_section)
    assert not widget.container.isAncestorOf(widget.clock_label)


def test_settings_reload_and_theme_change_keep_free_coordinates(workspace):
    host, _, widget = workspace
    controller, _ = enable(workspace)
    stored = deepcopy(read_free_layout(host.settings))
    controller.set_skin("classic_dark")
    flush()
    assert read_free_layout(host.settings) == stored
    fresh = UnifiedWidgetController(host)
    fresh.show_widget()
    flush()
    assert fresh.widget.active_layout_id() == "free"
    assert fresh.widget._free_runtime.data == stored
    fresh.prepare_shutdown()
    fresh.widget.close()
    fresh.widget.deleteLater()
    flush()


def test_editor_cancel_does_not_change_settings_or_live_mode(workspace):
    host, coordinator, widget = workspace
    before = deepcopy(host.settings.values)
    with patch(
        "calendar_app.presentation.dialogs.widget_free_layout_editor.WidgetFreeLayoutEditorDialog"
    ) as dialog:
        dialog.return_value.exec.return_value = 0
        coordinator.controller.open_free_layout_editor()
    assert host.settings.values == before
    assert not widget._free_layout_active


def test_free_date_uses_existing_date_dialog_without_new_global_shortcuts(workspace):
    _, _, widget = workspace
    _, runtime = enable(workspace)
    with patch.object(widget, "_pick_date") as picker:
        runtime.date_button.clicked.disconnect()
        runtime.date_button.clicked.connect(widget._pick_date)
        runtime.date_button.click()
        picker.assert_called_once()
    assert runtime.date_button.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_read_only_split_schedule_keeps_original_mutation_guard(workspace):
    host, _, widget = workspace
    _, runtime = enable(workspace)
    items = deepcopy(widget._last_items)
    next(item for item in items if item.get("item_id") == 1)["read_only"] = True
    widget.update_agenda(items)
    flush()
    runtime.panels["schedule"].rows[0].findChild(QPushButton, "agenda_item_title").click()
    assert not host.open_modify_task_dialog.called
    assert widget.feedback_label.isVisible()


def test_split_background_refresh_keeps_checkbox_focus_and_retained_rows(workspace):
    _, _, widget = workspace
    _, runtime = enable(workspace)
    panel = runtime.panels["work"]
    row = panel.rows[0]
    check = row.findChild(QCheckBox, "agenda_complete")
    check.setFocus()
    items = deepcopy(widget._last_items)
    next(item for item in items if item.get("item_id") == 1)["title"] += " · 수정"
    widget.update_agenda(items)
    flush()
    assert panel.rows[0] is row
    assert check.hasFocus()


def test_disjoint_saved_blocks_do_not_auto_overlap_when_window_shrinks(workspace):
    _, _, widget = workspace
    _, runtime = enable(workspace)
    widget.resize(320, 480)
    flush()
    frames = [runtime.frames[kind] for kind in ("schedule", "work", "directive")]
    for index, frame in enumerate(frames):
        for other in frames[index + 1 :]:
            assert not frame.geometry().intersects(other.geometry())
    assert runtime.frames["calendar"].content_viewport.horizontalScrollBar().maximum() > 0


def test_preset_and_free_geometry_round_trip_independently(workspace):
    host, coordinator, widget = workspace
    controller = coordinator.controller
    widget.resize(420, 620)
    flush()
    preset_size = widget.size()
    data = layout_data()
    controller.apply_free_layout(data)
    flush()
    assert widget.size() == preset_size
    widget.resize(760, 600)
    flush()
    free_size = widget.size()
    widget.week_toggle_btn.click()
    flush()
    assert widget.size() == free_size
    assert controller._geometry_layout_id("free", False) == "free"
    assert host.settings.value("unified_widget_size_free") == free_size
    controller.set_layout("stacked")
    flush()
    assert widget.size() == preset_size
    controller.apply_free_layout(read_free_layout(host.settings))
    flush()
    assert widget.size() == free_size


@pytest.mark.parametrize("mode", ["week", "month"])
def test_free_calendar_mode_and_transparent_background(workspace, mode):
    _, coordinator, widget = workspace
    data = layout_data()
    data["calendar_mode"] = mode
    coordinator.controller.apply_free_layout(data)
    flush()
    assert widget.cal_grid.display_mode == mode
    assert not widget.cal_grid.autoFillBackground()
    assert (
        not widget._free_runtime.frames["calendar"].content_viewport.viewport().autoFillBackground()
    )


def test_free_first_restart_uses_canvas_size_when_no_free_geometry_saved(workspace):
    host, coordinator, _ = workspace
    from calendar_app.presentation.widgets.widget_free_layout import write_free_layout

    write_free_layout(host.settings, layout_data())
    host.settings.setValue(FREE_LAYOUT_MODE_KEY, "free")
    fresh = UnifiedWidgetController(host)
    fresh.show_widget()
    flush()
    available = fresh.widget.screen().availableGeometry()
    assert fresh.widget.size() == QSize(min(900, available.width()), min(800, available.height()))
    fresh.prepare_shutdown()
    fresh.widget.close()
    fresh.widget.deleteLater()
    # Existing fixture controller keeps ownership of the original preset window.
    coordinator.controller.widget.show()
    flush()


def test_small_date_clock_cards_fit_without_scrollbars_or_font_setting_changes(workspace):
    host, _, widget = workspace
    _, runtime = enable(workspace)
    saved_font = host.settings.value("widget_mode_font_size")
    widget.resize(320, 480)
    flush()
    for kind in ("date", "clock"):
        assert runtime.frames[kind].content_viewport is None
        content = runtime.contents[kind]
        assert content.toolTip()
        assert content.accessibleName()
        assert content.font().pointSizeF() >= 6
    assert host.settings.value("widget_mode_font_size") == saved_font
