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
from calendar_app.presentation.widgets.widget_mode_display import (
    LayoutDisplay,
    write_layout_display,
)
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    widget_mode_layouts,
)
from calendar_app.presentation.widgets.widget_mode_surfaces import widget_mode_surfaces
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401

LAYOUTS = ("stacked", "dashboard", "work_board", "minimal")
SURFACES = [surface.key for surface in widget_mode_surfaces()]


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
    assert len(widget_mode_layouts()) == 4 and len(widget_mode_surfaces()) == 4
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


@pytest.mark.parametrize("layout", ["work_board"])
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


def test_board_search_with_no_match_keeps_original_items_cached(workspace):
    _, coordinator, widget = workspace
    coordinator.controller.set_layout("work_board")
    widget.search_input.setText("no-such-title-827")
    _wait_for_rows(widget, 0)
    assert sum(not item.get("is_section") for item in widget._last_items) == 3


def test_list_empty_state_explains_how_to_return_when_search_is_pinned(workspace):
    host, coordinator, widget = workspace
    write_layout_display(host.settings, "stacked", LayoutDisplay("week", False, True))
    coordinator.controller.set_layout("stacked")
    widget.apply_selected_layout(force=True)
    assert not widget.search_input.isHidden()
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


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("text_theme", ["light", "dark"])
def test_surfaces_keep_contrast_floor(workspace, surface, text_theme):
    host, coordinator, widget = workspace
    host.settings.setValue("text_theme", text_theme)
    coordinator.controller.set_surface(surface)
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
    assert dialog.surface_gallery.count() == 4
    item = next(
        dialog.surface_gallery.item(index)
        for index in range(dialog.surface_gallery.count())
        if dialog.surface_gallery.item(index).data(Qt.ItemDataRole.UserRole) == "line"
    )
    dialog.surface_gallery.setCurrentItem(item)
    dialog.layout_buttons["work_board"].click()
    assert dialog.draft.value("widget_mode_surface") == "line"
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


def test_surface_changes_item_border_style(workspace):
    host, coordinator, widget = workspace
    coordinator.controller.set_surface("line")
    assert "border-bottom: 1px solid" in widget.styleSheet()
    coordinator.controller.set_surface("outline")
    assert "border-bottom: 1px solid" not in widget.styleSheet()
    assert host.settings.value("widget_mode_surface") == "outline"


def test_customization_gallery_offers_four_surfaces_and_cancel_keeps_setting(workspace):
    host, coordinator, widget = workspace
    surface_before = host.settings.value("widget_mode_surface")
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    keys = [
        dialog.surface_gallery.item(index).data(Qt.ItemDataRole.UserRole)
        for index in range(dialog.surface_gallery.count())
    ]
    assert keys == ["card", "line", "outline", "compact"]
    dialog.surface_gallery.setCurrentItem(dialog.surface_gallery.item(2))
    assert dialog.draft.value("widget_mode_surface") == "outline"
    dialog.reject()
    dialog.deleteLater()
    _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert host.settings.value("widget_mode_surface") == surface_before


def test_card_surface_item_border_uses_card_border_token():
    from calendar_app.presentation.widgets.widget_mode_surfaces import get_widget_mode_surface
    from calendar_app.presentation.widgets.widget_workspace_styles import workspace_styles

    tokens = {
        "text_primary": "#111111",
        "text_secondary": "#222222",
        "section_bg": "#333333",
        "section_bg_alt": "#444444",
        "panel_border": "#aa0001",
        "card_border": "#00bb02",
        "accent": "#555555",
        "card_bg": "#666666",
    }
    card = workspace_styles(tokens, get_widget_mode_surface("card"))
    rule = card[card.index("QFrame#agenda_item_task") :]
    assert "1px solid #00bb02" in rule and "#aa0001" not in rule
    outline = workspace_styles(tokens, get_widget_mode_surface("outline"))
    assert "1px solid #aa0001" in outline[outline.index("QFrame#agenda_item_task") :]


@pytest.mark.parametrize("width", [700, 760, 940, 1280])
def test_surface_gallery_shows_all_cards_without_scrolling(workspace, width):
    _, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.resize(width, 680)
    dialog.show()
    dialog.preferences_tabs.setCurrentIndex(1)
    for _ in range(5):
        _APP.processEvents()
    gallery = dialog.surface_gallery
    assert gallery.count() == 4
    viewport = gallery.viewport().rect()
    for index in range(4):
        assert viewport.contains(gallery.visualItemRect(gallery.item(index))), (width, index)
    assert gallery.verticalScrollBar().maximum() == 0
    dialog.reject()
    dialog.deleteLater()
    _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
