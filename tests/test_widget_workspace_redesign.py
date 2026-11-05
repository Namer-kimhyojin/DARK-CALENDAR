# -*- coding: utf-8 -*-
"""Modern workspace views must reuse original data, actions and draft boundaries."""

from unittest.mock import patch

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QCheckBox, QLabel, QPushButton
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.panel_widget_style import css_to_qcolor
from calendar_app.presentation.widgets.unified_widget_mode import _widget_theme_tokens
from calendar_app.presentation.widgets.widget_graphics import contrast_ratio
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    widget_mode_layouts,
    widget_mode_skins,
)
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401

LAYOUTS = ("day_brief", "month_focus", "side_planner", "week_navigator", "work_board", "focus_dock")
SKINS = [skin for skin in widget_mode_skins() if skin.skin_id.startswith("studio_")]


def _wait_for_rows(widget, count):
    for _ in range(100):
        rows = (
            widget._workspace_board.rows()
            if widget._workspace_board_active
            else widget._agenda_rows
        )
        if len(rows) == count:
            return rows
        QTest.qWait(10)
    assert len(rows) == count


def test_original_and_new_catalogs_coexist():
    assert len(widget_mode_layouts()) >= 11 and len(widget_mode_skins()) >= 16
    assert len(SKINS) == 10
    assert {get_widget_mode_layout(key).presentation for key in LAYOUTS} == {"list", "board"}


@pytest.mark.parametrize("layout", LAYOUTS)
def test_new_layouts_keep_selected_date_and_render_at_narrow_and_preferred_sizes(workspace, layout):
    host, coordinator, widget = workspace
    selected = host.current_date
    coordinator.controller.set_layout(layout)
    for width, height in (get_widget_mode_layout(layout).preferred_size, (360, 570)):
        widget.resize(width, height)
        _APP.processEvents()
        assert widget.active_layout_id() == layout
        assert coordinator.controller._current_date() == selected
        assert not widget.grab().isNull()
        for button in (widget.date_picker_btn, widget.more_btn, widget.add_btn):
            point = button.mapTo(widget, QPoint())
            assert point.x() >= 0 and point.x() + button.width() <= widget.width()


def test_board_routes_original_ids_to_original_dialogs_and_completion(workspace):
    host, coordinator, widget = workspace
    coordinator.controller.set_layout("work_board")
    board = widget._workspace_board
    assert [len(board.panels[kind].rows) for kind in ("schedule", "work", "directive")] == [1, 1, 1]
    for panel in board.panels.values():
        panel.rows[0].findChild(QPushButton, "agenda_item_title").click()
    host.open_modify_task_dialog.assert_any_call(1)
    host.open_modify_task_dialog.assert_any_call(2)
    host.open_directive_dialog.assert_called_once_with(task_id=3)
    board.panels["work"].rows[0].findChild(QCheckBox, "agenda_complete").click()
    assert host.handle_task_status_changed.called


@pytest.mark.parametrize("layout", ["day_brief", "work_board"])
def test_search_uses_cached_items_without_fetching_or_losing_originals(workspace, layout):
    host, coordinator, widget = workspace
    coordinator.controller.set_layout(layout)
    original = [dict(item) for item in widget._last_items]
    with patch.object(coordinator.controller, "refresh_data") as fetch:
        widget.search_input.setText("회의")
        rows = _wait_for_rows(widget, 2)
        assert len(rows) == 2
        assert widget._last_items == original
        fetch.assert_not_called()
        widget.search_input.clear()
        rows = _wait_for_rows(widget, 3)
        assert len(rows) == 3


def test_search_empty_state_explains_how_to_return(workspace):
    _, coordinator, widget = workspace
    coordinator.controller.set_layout("day_brief")
    widget.search_input.setText("no-such-title-827")
    _wait_for_rows(widget, 0)
    assert "검색" in widget.scroll_content.findChild(QLabel, "unified_empty").text()
    assert sum(not item.get("is_section") for item in widget._last_items) == 3


def test_summary_buttons_filter_and_board_reverts_to_legacy_list(workspace):
    _, coordinator, widget = workspace
    coordinator.controller.set_layout("work_board")
    widget.workspace_overview.buttons["directive"].click()
    assert widget._active_filter == "directive"
    assert widget._workspace_board.panels["work"].isHidden()
    coordinator.controller.set_layout("stacked")
    assert not widget._workspace_board_active and not widget.scroll.isHidden()
    assert widget.workspace_overview.isHidden() and widget.search_input.isHidden()
    assert len(widget._agenda_rows) == 1


@pytest.mark.parametrize("skin", SKINS, ids=lambda skin: skin.skin_id)
def test_new_skins_keep_text_and_selected_day_readable(workspace, skin):
    host, coordinator, widget = workspace
    coordinator.controller.set_skin(skin.skin_id)
    tokens = _widget_theme_tokens(host)
    background = css_to_qcolor(tokens["panel_bg"])
    for role in ("text_primary", "text_secondary"):
        assert contrast_ratio(css_to_qcolor(tokens[role]).name(), background.name()) >= 4.5
    fill = css_to_qcolor(tokens["hero_bg_strong"])
    alpha = fill.alphaF()
    rgb = [
        round(a * alpha + b * (1 - alpha))
        for a, b in zip(fill.getRgb()[:3], background.getRgb()[:3], strict=True)
    ]
    composite = "#" + "".join(f"{value:02x}" for value in rgb)
    assert contrast_ratio(css_to_qcolor(tokens["accent_deep"]).name(), composite) >= 4.5


def test_gallery_and_layout_changes_cancel_without_persisting(workspace):
    host, coordinator, widget = workspace
    original = dict(host.settings.values)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    assert dialog.skin_gallery.count() >= 16
    item = next(
        dialog.skin_gallery.item(index)
        for index in range(dialog.skin_gallery.count())
        if str(dialog.skin_gallery.item(index).data(Qt.ItemDataRole.UserRole)).startswith("studio_")
    )
    dialog.skin_gallery.setCurrentItem(item)
    dialog.layout_buttons["work_board"].click()
    assert dialog.draft.value("widget_mode_skin").startswith("studio_")
    dialog.reject()
    dialog.deleteLater()
    _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert host.settings.values == original


def test_free_composition_disables_builtin_board_without_changing_saved_layout(workspace):
    host, coordinator, widget = workspace
    coordinator.controller.set_layout("work_board")
    from calendar_app.presentation.widgets.widget_free_layout import FREE_LAYOUT_MODE_KEY

    host.settings.setValue(FREE_LAYOUT_MODE_KEY, "free")
    widget.apply_selected_layout(force=True)
    assert widget.active_layout_id() == "free"
    assert not widget._workspace_board_active
    assert widget._workspace_board.isHidden()
    assert host.settings.value("widget_mode_layout") == "work_board"
