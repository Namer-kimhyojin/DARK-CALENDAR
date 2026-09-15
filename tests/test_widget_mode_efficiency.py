# -*- coding: utf-8 -*-
"""Compact header, density preferences and list hierarchy regressions."""

import re

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.unified_widget_mode import (
    AgendaItemWidget,
    UnifiedWidgetController,
)
from calendar_app.presentation.widgets.widget_mode_density import DENSITY_KEY, read_widget_density
from calendar_app.presentation.widgets.widget_mode_typography import read_widget_typography
from calendar_app.presentation.widgets.widget_mode_visibility import calendar_visibility_key
from tests.test_widget_mode_ux import _APP, Settings, workspace  # noqa: F401


def _rows(widget):
    return [
        widget.scroll_layout.itemAt(index).widget()
        for index in range(widget.scroll_layout.count() - 1)
        if isinstance(widget.scroll_layout.itemAt(index).widget(), AgendaItemWidget)
    ]


def test_header_is_one_row_and_first_item_appears_above_window_midpoint(workspace):
    _, _, widget = workspace
    widget.resize(420, 660)
    _APP.processEvents()
    for control in (
        widget.date_picker_btn,
        widget.today_btn,
        widget.pin_btn,
        widget.customize_btn,
        widget.more_btn,
    ):
        assert widget.toolbar.isAncestorOf(control)
        assert control.isVisible()
        assert control.geometry().bottom() <= widget.toolbar.height()
    assert widget.hero.isHidden()
    assert _rows(widget)[0].mapTo(widget, _rows(widget)[0].rect().topLeft()).y() < 230
    assert widget.clock_label.isVisible()


def test_density_only_changes_spacing_and_retains_every_item(workspace):
    host, _, widget = workspace
    host.settings.setValue("widget_mode_font_size", 16)
    heights = []
    for key in ("compact", "standard", "comfortable"):
        widget.set_density(key)
        _APP.processEvents()
        rows = _rows(widget)
        assert len(rows) == 3
        heights.append(sum(row.height() for row in rows))
        assert host.settings.value("widget_mode_font_size") == 16
    assert heights[0] < heights[1] < heights[2]
    assert read_widget_density(Settings()).key == "standard"
    host.settings.setValue(DENSITY_KEY, "obsolete")
    assert read_widget_density(host.settings).key == "standard"


def test_section_type_is_not_repeated_in_each_row(workspace):
    _, _, widget = workspace
    assert not widget.scroll_content.findChildren(QLabel, "agenda_item_meta")
    widget.set_filter("schedule")
    assert not [
        label
        for label in widget.scroll_content.findChildren(QLabel, "unified_section")
        if not label.isHidden()
    ]
    assert len(_rows(widget)) == 1
    assert len([item for item in widget._last_items if item.get("item_id")]) == 3


def test_overall_text_size_uses_one_bounded_semantic_scale():
    settings = Settings()
    settings.setValue("widget_mode_font_size", 10)
    small = read_widget_typography(settings)
    settings.setValue("widget_mode_font_size", 18)
    large = read_widget_typography(settings)

    assert small.title < large.title
    assert small.control < large.control
    assert small.calendar < large.calendar
    assert large.title == large.body == 11.0
    assert large.title - large.control <= 0.5
    assert large.title < large.preference


def test_overall_text_size_applies_to_controls_calendar_and_agenda(workspace):
    host, _, widget = workspace
    host.settings.setValue("widget_mode_font_size", 18)
    widget._style_signature = None
    widget.apply_theme()
    _APP.processEvents()

    typography = read_widget_typography(host.settings)
    stylesheet = widget.styleSheet()
    assert f"font-size: {typography.title:.1f}pt" in stylesheet
    assert f"font-size: {typography.control:.1f}pt" in stylesheet
    assert f"font-size: {typography.section:.1f}pt" in stylesheet
    assert f"font-size: {typography.date:.1f}pt" in stylesheet
    assert all(
        f"font-size: {typography.calendar:.1f}pt" in button.styleSheet()
        for button in widget.cal_grid._buttons
    )
    title = widget.scroll_content.findChildren(QPushButton, "agenda_item_title")[0]
    section = widget.scroll_content.findChildren(QLabel, "unified_section")[0]
    assert title.font().pointSizeF() == pytest.approx(typography.title)
    assert widget._filter_buttons["all"].font().pointSizeF() == pytest.approx(typography.control)
    assert widget.date_picker_btn.font().pointSizeF() == pytest.approx(typography.date)
    assert section.font().pointSizeF() == pytest.approx(typography.section)
    assert widget.cal_grid._buttons[0].font().pointSizeF() == pytest.approx(typography.calendar)
    assert title.font().pointSizeF() == pytest.approx(typography.body)


def test_schedule_marker_is_centered_on_the_title_line(workspace):
    _, _, widget = workspace
    row = _rows(widget)[0]
    marker = row.findChild(QFrame, "agenda_item_marker_schedule")
    title = row.findChild(QPushButton, "agenda_item_title")
    marker_y = marker.mapTo(row, marker.rect().center()).y()
    title_y = title.mapTo(row, title.rect().center()).y()

    assert abs(marker_y - title_y) <= 2


def test_primary_add_hover_keeps_an_explicit_text_color(workspace):
    _, _, widget = workspace
    stylesheet = widget.styleSheet()
    match = re.search(
        r"QToolButton#unified_primary_action:hover,\s*"
        r"QToolButton#unified_primary_action:pressed\s*\{([^}]+)\}",
        stylesheet,
    )

    assert match is not None
    hover_block = match.group(1)
    assert "color:" in hover_block
    assert "background:" in hover_block
    assert "border:" in hover_block


@pytest.mark.parametrize("layout", ["dashboard", "magazine"])
def test_wide_board_layouts_use_a_full_month_calendar(workspace, layout):
    host, coordinator, widget = workspace
    coordinator.controller.set_layout(layout)
    _APP.processEvents()

    assert widget.cal_grid.display_mode == "month"
    assert widget.cal_grid._week_strip.isHidden()
    assert not widget.cal_grid.month_calendar.isHidden()
    assert widget.cal_grid.month_calendar.selectedDate() == host.current_date
    assert len(widget.cal_grid.month_calendar.day_buttons) == 42
    assert "background: transparent" in widget.cal_grid.month_calendar.styleSheet()
    assert "background: transparent" in (widget.cal_grid.month_calendar.day_buttons[0].styleSheet())
    assert widget.week_toggle_btn.text()

    selected = host.current_date.addDays(3)
    widget.cal_grid.month_calendar.dateClicked.emit(selected)
    assert host.current_date == selected


def test_stacked_layout_keeps_the_compact_week_strip(workspace):
    _, coordinator, widget = workspace
    coordinator.controller.set_layout("stacked")

    assert widget.cal_grid.display_mode == "week"
    assert not widget.cal_grid._week_strip.isHidden()
    assert widget.cal_grid.month_calendar.isHidden()


def test_board_calendar_defaults_visible_and_visibility_is_layout_scoped(workspace):
    host, coordinator, widget = workspace
    host.settings.setValue("widget_mode_show_week", False)

    coordinator.controller.set_layout("dashboard")
    assert not widget.cal_grid.isHidden()
    assert widget.week_toggle_btn.isChecked()
    widget.week_toggle_btn.click()
    assert widget.cal_grid.isHidden()
    assert host.settings.value(calendar_visibility_key("dashboard")) is False

    coordinator.controller.set_layout("magazine")
    assert not widget.cal_grid.isHidden()
    assert widget.week_toggle_btn.isChecked()

    coordinator.controller.set_layout("dashboard")
    assert widget.cal_grid.isHidden()
    assert not widget.week_toggle_btn.isChecked()


@pytest.mark.parametrize(
    ("layout", "calendar_column", "content_column"),
    [("dashboard", 0, 1), ("magazine", 1, 0)],
)
def test_board_layout_content_is_opposite_the_calendar(
    workspace, layout, calendar_column, content_column
):
    _, coordinator, widget = workspace
    coordinator.controller.set_layout(layout)
    _APP.processEvents()

    positions = {}
    for name, section in {
        "calendar": widget.cal_grid,
        "filters": widget.filter_section,
        "agenda": widget.agenda_section,
    }.items():
        index = widget.container_layout.indexOf(section)
        positions[name] = widget.container_layout.getItemPosition(index)

    assert positions["calendar"] == (1, calendar_column, 2, 1)
    assert positions["filters"][1] == content_column
    assert positions["agenda"][1] == content_column


def test_week_dates_use_modern_card_states_instead_of_capsules(workspace):
    host, coordinator, widget = workspace
    coordinator.controller.set_layout("stacked")
    widget.cal_grid.update_grid(host.current_date)

    states = [button.property("dateState") for button in widget.cal_grid._buttons]
    selected = widget.cal_grid._buttons[states.index("selected")]
    stylesheet = selected.styleSheet()

    assert "border-radius: 8px" in stylesheet
    assert "border-bottom: 3px" in stylesheet
    assert "qlineargradient" in stylesheet
    assert "QToolButton:hover" in stylesheet
    assert "QToolButton:focus" in stylesheet
    assert "border-radius: 14px" not in stylesheet


def test_customize_icon_has_an_uncropped_dedicated_size(workspace):
    _, _, widget = workspace

    assert not widget.customize_btn.icon().isNull()
    assert widget.customize_btn.iconSize().width() == 18
    assert widget.customize_btn.width() == 32


def test_density_preview_cancel_apply_and_restart_preserve_other_preferences(workspace, tmp_path):
    host, coordinator, widget = workspace
    path = str(tmp_path / "density.ini")
    host.settings = QSettings(path, QSettings.Format.IniFormat)
    host.settings.setValue("widget_mode_font_size", 16)
    host.settings.setValue("widget_mode_text_opacity", 81)
    host.settings.setValue("widget_mode_background_opacity", 41)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    assert dialog.preview.isWindow()
    assert dialog.preview.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    assert not dialog.preview.isVisible()
    assert not dialog.preview.scroll.verticalScrollBar().isVisibleTo(dialog.preview.scroll)
    dialog.density_combo.setCurrentIndex(dialog.density_combo.findData("compact"))
    assert read_widget_density(dialog.draft).key == "compact"
    assert dialog.preview.scroll_layout.spacing() == 4
    assert host.settings.value(DENSITY_KEY) is None
    dialog.reject()
    dialog.deleteLater()
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    assert dialog.density_combo.currentData() == "standard"
    dialog.density_combo.setCurrentIndex(dialog.density_combo.findData("comfortable"))
    dialog._apply()
    widget.week_toggle_btn.click()
    assert widget.cal_grid.isHidden()
    coordinator.close_for_shutdown()
    host.settings.sync()
    host.settings = QSettings(path, QSettings.Format.IniFormat)
    fresh = UnifiedWidgetController(host)
    fresh.show_widget()
    _APP.processEvents()
    assert read_widget_density(host.settings).key == "comfortable"
    assert fresh.widget.scroll_layout.spacing() == 10
    assert fresh.widget.cal_grid.isHidden()
    assert not fresh.widget.week_toggle_btn.isChecked()
    assert int(host.settings.value("widget_mode_font_size")) == 16
    assert int(host.settings.value("widget_mode_text_opacity")) == 81
    assert int(host.settings.value("widget_mode_background_opacity")) == 41
    fresh.hide_widget()
    fresh.widget.deleteLater()
    dialog.deleteLater()


@pytest.mark.parametrize("layout", ["stacked", "minimal", "dashboard"])
@pytest.mark.parametrize("density", ["compact", "standard", "comfortable"])
def test_small_window_large_font_keeps_controls_and_rows_separate(workspace, layout, density):
    host, coordinator, widget = workspace
    host.settings.setValue("widget_mode_font_size", 18)
    coordinator.controller.set_layout(layout)
    widget.set_density(density)
    widget.resize(350, 500)
    _APP.processEvents()
    controls = [
        widget.restore_btn,
        widget.date_picker_btn,
        widget.today_btn,
        widget.pin_btn,
        widget.customize_btn,
        widget.more_btn,
    ]
    assert all(
        not a.geometry().intersects(b.geometry())
        for a, b in zip(controls, controls[1:], strict=False)
    )
    rows = _rows(widget)
    assert all(
        a.geometry().bottom() < b.geometry().top() for a, b in zip(rows, rows[1:], strict=False)
    )
    assert all(
        button.height() >= 28
        for row in rows
        for button in row.findChildren(QPushButton, "agenda_item_title")
    )
