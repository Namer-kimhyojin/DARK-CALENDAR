# -*- coding: utf-8 -*-
"""Actual widget rows honor explicit all-day flags without hiding real midnight times."""

from copy import deepcopy
from unittest.mock import patch

from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QLabel, QPushButton
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets import panel_widget_mode as legacy
from calendar_app.presentation.widgets.unified_widget_mode import _widget_theme_tokens
from tests.test_widget_mode_ux import workspace  # noqa: F401


@pytest.mark.parametrize(
    "case,flag,start_offset,end_offset,date_only",
    [
        ("all_day", 1, 0, 0, False),
        ("multiday_all_day", True, -1, 1, False),
        ("actual_midnight", False, 0, 1, False),
        ("date_only_legacy", None, 0, 0, True),
        ("multiday_date_only_legacy", None, -1, 1, True),
        ("normal_time", 0, 0, 0, False),
    ],
)
def test_actual_unified_and_legacy_rows_keep_all_day_and_midnight_distinct(
    workspace, case, flag, start_offset, end_offset, date_only
):
    host, coordinator, widget = workspace
    target = host.current_date
    start = target.addDays(start_offset).toString("yyyy-MM-dd")
    end = target.addDays(end_offset).toString("yyyy-MM-dd")
    if not date_only:
        start += " 14:00:00" if case == "normal_time" else " 00:00:00"
        end += " 15:30:00" if case == "normal_time" else " 00:00:00"
    row = {"id": 41, "name": case, "deadline": start, "end_date": end}
    if flag is not None:
        row["all_day"] = flag
    original = deepcopy(row)
    host._latest_calendar_range_data["rows"] = [row]
    settings_before = deepcopy(host.settings.values)
    all_day = t("widget_mode.all_day", "종일")
    controller = coordinator.controller
    items = controller._schedule_items_for_date(target)
    assert [item["item_id"] for item in items if not item.get("is_section")] == [41]
    expected_unified = (
        all_day if flag else legacy._format_widget_datetime_label(start, reference_date=target)
    )
    assert items[1]["time"] == expected_unified
    widget.update_agenda(items)
    assert len(widget._agenda_rows) == 1
    current_row = widget._agenda_rows[0]
    assert current_row.findChild(QLabel, "agenda_item_time").text() == expected_unified
    current_row.findChild(QPushButton, "agenda_item_title").click()
    host.open_modify_task_dialog.assert_called_once_with(41)

    old_controller = legacy.PanelWidgetModeController(host)
    with patch.object(
        legacy.search_repo, "get_schedule_tasks_overlapping_range_with_progress", return_value=[row]
    ):
        entries = old_controller._collect_schedule_entries_for_date(target)
    assert len(entries) == 1
    if flag:
        expected_legacy = all_day
    elif date_only:
        expected_legacy = ""
    else:
        locale = QLocale()
        expected_legacy = "~".join(
            locale.toString(
                legacy._parse_qdatetime(value).time(), QLocale.FormatType.ShortFormat
            ).strip()
            for value in (start, end)
        )
    assert entries[0].subtitle == expected_legacy
    old_rows = legacy._EntryListWidget(host)
    try:
        old_rows.set_entries(entries, _widget_theme_tokens(host), "Empty")
        labels = old_rows.findChildren(QLabel, "widget_entry_time_label")
        assert [label.text() for label in labels] == [expected_legacy]
        with patch.object(old_controller, "_open_task") as open_task:
            entries[0].callback()
            open_task.assert_called_once_with(41)
    finally:
        old_rows.close()
        old_rows.deleteLater()
        old_controller._debounce_timer.stop()
    assert row == original
    assert host.settings.values == settings_before


def test_all_day_presentation_preserves_existing_chronological_order(workspace):
    host, coordinator, _widget = workspace
    target = host.current_date
    date = target.toString("yyyy-MM-dd")
    rows = [
        {"id": 7, "name": "Afternoon", "deadline": f"{date} 14:00:00", "all_day": 0},
        {"id": 3, "name": "All day", "deadline": f"{date} 00:00:00", "all_day": 1},
        {"id": 2, "name": "Midnight", "deadline": f"{date} 00:00:00", "all_day": 0},
    ]
    host._latest_calendar_range_data["rows"] = rows
    items = coordinator.controller._schedule_items_for_date(target)
    assert [item["item_id"] for item in items if not item.get("is_section")] == [2, 3, 7]
    old_controller = legacy.PanelWidgetModeController(host)
    with patch.object(
        legacy.search_repo, "get_schedule_tasks_overlapping_range_with_progress", return_value=rows
    ):
        entries = old_controller._collect_schedule_entries_for_date(target)
    assert [entry.title for entry in entries] == ["Midnight", "All day", "Afternoon"]
    old_controller._debounce_timer.stop()
