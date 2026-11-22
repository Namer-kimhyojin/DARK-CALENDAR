# -*- coding: utf-8 -*-
from calendar_app.presentation.widgets.widget_mode_surfaces import (
    get_widget_mode_surface,
    read_widget_mode_surface,
    widget_mode_surfaces,
    write_widget_mode_surface,
)


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def test_catalog_order_and_values():
    keys = [s.key for s in widget_mode_surfaces()]
    assert keys == ["card", "line", "outline", "compact"]
    line = get_widget_mode_surface("line")
    assert (line.radius, line.item_radius, line.item_background, line.item_border) == (
        6,
        2,
        "transparent",
        "bottom",
    )


def test_unknown_surface_reads_as_card():
    s = Settings()
    s.setValue("widget_mode_surface", "glass")
    assert read_widget_mode_surface(s) == "card"
    assert write_widget_mode_surface(s, "OUTLINE ") == "outline"
    assert s.values["widget_mode_surface"] == "outline"
