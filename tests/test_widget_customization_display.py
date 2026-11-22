# -*- coding: utf-8 -*-
"""Per-layout display options in the widget customization dialog."""

import json
from unittest.mock import Mock

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QPushButton, QSlider

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.widget_free_layout import seed_free_layout
from calendar_app.presentation.widgets.widget_layout_presets import (
    USER_LAYOUT_PRESETS_KEY,
    create_layout_preset,
    read_layout_presets,
    write_layout_presets,
)
from calendar_app.presentation.widgets.widget_mode_display import (
    CALENDAR_STYLE_PREFIX,
    SEARCH_PINNED_PREFIX,
    SHOW_OVERVIEW_PREFIX,
    display_key,
)
from calendar_app.presentation.widgets.widget_mode_surfaces import widget_mode_surfaces
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


def _open(workspace):
    host, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.show()
    _APP.processEvents()
    return dialog, host


def _close(dialog):
    dialog.reject()
    dialog.deleteLater()
    _APP.processEvents()


def test_display_options_apply_to_selected_layout_only(workspace):
    host, _coordinator, _widget = workspace
    host.settings.values["widget_mode_layout"] = "stacked"
    dialog, host = _open(workspace)
    dashboard_before = {
        prefix: host.settings.value(display_key(prefix, "dashboard"))
        for prefix in (CALENDAR_STYLE_PREFIX, SHOW_OVERVIEW_PREFIX, SEARCH_PINNED_PREFIX)
    }
    dialog.calendar_style_combo.setCurrentIndex(dialog.calendar_style_combo.findData("month"))
    dialog.show_overview_checkbox.setChecked(True)
    dialog.search_pinned_checkbox.setChecked(True)
    dialog._apply()
    assert host.settings.value(display_key(CALENDAR_STYLE_PREFIX, "stacked")) == "month"
    assert host.settings.value(display_key(SHOW_OVERVIEW_PREFIX, "stacked")) is True
    assert host.settings.value(display_key(SEARCH_PINNED_PREFIX, "stacked")) is True
    for prefix, value in dashboard_before.items():
        assert host.settings.value(display_key(prefix, "dashboard")) == value
    dialog.deleteLater()


def test_display_options_follow_the_draft_layout(workspace):
    host, _coordinator, _widget = workspace
    host.settings.values[display_key(CALENDAR_STYLE_PREFIX, "dashboard")] = "week"
    host.settings.values[display_key(SHOW_OVERVIEW_PREFIX, "work_board")] = True
    dialog, host = _open(workspace)
    dialog._change("widget_mode_layout", "dashboard")
    assert dialog.calendar_style_combo.currentData() == "week"
    dialog._change("widget_mode_layout", "work_board")
    assert dialog.show_overview_checkbox.isChecked()
    dialog._change("widget_mode_layout", "stacked")
    assert dialog.calendar_style_combo.currentData() == "week"
    _close(dialog)


def test_display_options_cancel_keeps_settings(workspace):
    dialog, host = _open(workspace)
    key = display_key(CALENDAR_STYLE_PREFIX, "stacked")
    before = host.settings.value(key)
    dialog.calendar_style_combo.setCurrentIndex(1 - dialog.calendar_style_combo.currentIndex())
    dialog.reject()
    assert host.settings.value(key) == before
    dialog.deleteLater()


def test_calendar_style_hidden_for_list_layout_and_free_layout(workspace):
    dialog, _host = _open(workspace)
    dialog._change("widget_mode_layout", "stacked")
    assert not dialog.calendar_style_combo.isHidden()
    dialog._change("widget_mode_layout", "minimal")
    assert dialog.calendar_style_combo.isHidden()
    assert dialog.calendar_style_label.isHidden()
    assert not dialog.show_overview_checkbox.isHidden()
    assert not dialog.search_pinned_checkbox.isHidden()
    dialog._change("widget_mode_layout", "stacked")
    assert not dialog.calendar_style_combo.isHidden()
    dialog.draft.setValue("widget_mode_layout_mode", "free")
    dialog._sync_visibility_controls()
    assert dialog.calendar_style_combo.isHidden()
    _close(dialog)


def test_opacity_sliders_removed_and_appearance_link_present(workspace):
    host, _coordinator, _widget = workspace
    host.open_panel_background_color_dialog = Mock()
    dialog, _host = _open(workspace)
    assert not [w for w in dialog.findChildren(QSlider) if "투명" in w.accessibleName()]
    button = dialog.findChild(QPushButton, "open_appearance_btn")
    assert button is not None
    assert not button.isHidden()
    button.click()
    host.open_panel_background_color_dialog.assert_called_once()
    _close(dialog)


def test_appearance_link_hidden_without_main_window_method(workspace):
    dialog, _host = _open(workspace)
    button = dialog.findChild(QPushButton, "open_appearance_btn")
    assert button is not None and button.isHidden()
    _close(dialog)


def test_unknown_future_presets_survive_unrelated_apply(workspace):
    host, _coordinator, _widget = workspace
    blob = json.dumps({"version": 99, "presets": [{"id": "x", "name": "Future"}]})
    host.settings.values[USER_LAYOUT_PRESETS_KEY] = blob
    assert read_layout_presets(host.settings) == []
    dialog, host = _open(workspace)
    dialog.density_combo.setCurrentIndex(1 - dialog.density_combo.currentIndex())
    dialog._apply()
    assert host.settings.value(USER_LAYOUT_PRESETS_KEY) == blob
    dialog.deleteLater()


def test_preset_rename_and_delete_then_cancel_leave_store_unchanged(workspace):
    host, _coordinator, _widget = workspace
    library, _first = create_layout_preset([], "Desk", seed_free_layout("stacked"))
    write_layout_presets(host.settings, library)
    stored = host.settings.value(USER_LAYOUT_PRESETS_KEY)
    dialog, host = _open(workspace)
    dialog.user_layout_list.setCurrentRow(0)
    dialog._rename_user_layout("Renamed")
    dialog._delete_user_layout(confirmed=True)
    dialog.reject()
    assert host.settings.value(USER_LAYOUT_PRESETS_KEY) == stored
    dialog.deleteLater()


def test_surface_thumbnails_are_pairwise_different(workspace):
    dialog, _host = _open(workspace)
    surfaces = widget_mode_surfaces()
    size = QSize(150, 74)
    images = [dialog._surface_icon(surface).pixmap(size).toImage() for surface in surfaces]
    for first in range(len(images)):
        for second in range(first + 1, len(images)):
            assert images[first] != images[second], (surfaces[first].key, surfaces[second].key)
    _close(dialog)


def test_surface_gallery_shows_all_cards_at_one_column_width(workspace):
    dialog, _host = _open(workspace)
    gallery = dialog.surface_gallery
    grid = gallery.gridSize()
    count = gallery.count()
    for viewport_width in (grid.width(), grid.width() * 2 + 10, 3 * grid.width()):
        columns = max(1, viewport_width // grid.width())
        rows = -(-count // columns)
        dialog._fit_surface_gallery_height(viewport_width)
        assert gallery.height() >= rows * grid.height() + 2 * gallery.frameWidth()
    dialog._fit_surface_gallery_height(grid.width())
    assert gallery.height() >= count * grid.height()
    _close(dialog)


def test_surface_gallery_resize_recomputes_height(workspace):
    dialog, _host = _open(workspace)
    dialog.preferences_tabs.setCurrentIndex(1)
    dialog.controls_scroll.setMinimumWidth(280)
    dialog.resize(560, 700)
    _APP.processEvents()
    gallery = dialog.surface_gallery
    grid = gallery.gridSize()
    columns = max(1, gallery.viewport().width() // grid.width())
    rows = -(-gallery.count() // columns)
    assert gallery.height() >= rows * grid.height()
    assert gallery.verticalScrollBar().maximum() == 0
    _close(dialog)
