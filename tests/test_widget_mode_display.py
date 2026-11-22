# -*- coding: utf-8 -*-
from calendar_app.presentation.widgets.widget_mode_display import (
    LayoutDisplay,
    default_layout_display,
    display_key,
    read_layout_display,
    write_layout_display,
)
from calendar_app.presentation.widgets.widget_mode_skins import get_widget_mode_layout


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def test_defaults_follow_layout_definition():
    assert default_layout_display(get_widget_mode_layout("stacked")) == LayoutDisplay(
        "week", False, False
    )
    assert default_layout_display(get_widget_mode_layout("dashboard")) == LayoutDisplay(
        "month", False, False
    )


def test_round_trip_is_scoped_per_layout():
    s = Settings()
    write_layout_display(s, "stacked", LayoutDisplay("month", True, True))
    assert read_layout_display(s, get_widget_mode_layout("stacked")) == LayoutDisplay(
        "month", True, True
    )
    assert read_layout_display(s, get_widget_mode_layout("dashboard")) == LayoutDisplay(
        "month", False, False
    )
    assert (
        display_key("widget_mode_calendar_style_", "stacked")
        == "widget_mode_calendar_style_stacked"
    )


def test_bad_values_fall_back_to_defaults():
    s = Settings()
    s.setValue("widget_mode_calendar_style_stacked", "yearly")
    s.setValue("widget_mode_show_overview_stacked", "maybe")
    assert read_layout_display(s, get_widget_mode_layout("stacked")) == LayoutDisplay(
        "week", False, False
    )
