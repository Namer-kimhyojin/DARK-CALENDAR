# -*- coding: utf-8 -*-
"""Actual widget rows honor explicit all-day flags without hiding real midnight times."""

from copy import deepcopy

from PyQt6.QtCore import QDate, QLocale, QTime
from PyQt6.QtWidgets import QLabel, QPushButton
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.panel_widget_common import (
    _format_compact_date,
    _format_compact_date_with_weekday,
    _format_widget_datetime_label,
)
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
def test_actual_unified_rows_keep_all_day_and_midnight_distinct(
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
        all_day if flag else _format_widget_datetime_label(start, reference_date=target)
    )
    assert items[1]["time"] == expected_unified
    widget.update_agenda(items)
    assert len(widget._agenda_rows) == 1
    current_row = widget._agenda_rows[0]
    assert current_row.findChild(QLabel, "agenda_item_time").text() == expected_unified
    current_row.findChild(QPushButton, "agenda_item_title").click()
    host.open_modify_task_dialog.assert_called_once_with(41)
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


# Moved from the retired tests/test_panel_widget_mode_ui.py: these helpers still
# format the unified widget's dates and times.
def test_widget_mode_date_helpers_are_locale_aware():
    locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    target = QDate(2026, 3, 28)

    compact = _format_compact_date(target, locale)
    with_weekday = _format_compact_date_with_weekday(target, locale)

    assert "2026" not in compact
    assert locale.dayName(target.dayOfWeek(), QLocale.FormatType.ShortFormat) in with_weekday
    assert compact in with_weekday


def test_widget_mode_datetime_label_uses_locale_short_time_and_compact_date():
    locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    reference = QDate(2026, 3, 28)

    same_day = _format_widget_datetime_label(
        "2026-03-28 14:30:00", reference_date=reference, locale=locale
    )
    other_day = _format_widget_datetime_label(
        "2026-03-30 09:15:00", reference_date=reference, locale=locale
    )

    assert same_day == locale.toString(QTime(14, 30), QLocale.FormatType.ShortFormat)
    assert _format_compact_date(QDate(2026, 3, 30), locale) in other_day
    assert locale.toString(QTime(9, 15), QLocale.FormatType.ShortFormat) in other_day
    assert "2026-03-30" not in other_day
