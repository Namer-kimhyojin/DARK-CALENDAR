# -*- coding: utf-8 -*-
"""Layout-scoped calendar visibility preference regressions."""

from calendar_app.presentation.widgets.widget_mode_visibility import (
    LEGACY_CALENDAR_VISIBILITY_KEY,
    calendar_visibility_key,
    read_widget_calendar_visibility,
    write_widget_calendar_visibility,
)


class _Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def test_board_layouts_default_to_visible_even_when_legacy_week_was_hidden():
    settings = _Settings({LEGACY_CALENDAR_VISIBILITY_KEY: False})

    assert read_widget_calendar_visibility(settings, "dashboard") is True
    assert read_widget_calendar_visibility(settings, "magazine") is True
    assert read_widget_calendar_visibility(settings, "stacked") is False


def test_scoped_visibility_overrides_default_and_other_layouts():
    settings = _Settings()
    write_widget_calendar_visibility(settings, "dashboard", False)

    assert read_widget_calendar_visibility(settings, "dashboard") is False
    assert read_widget_calendar_visibility(settings, "magazine") is True
    assert settings.values[calendar_visibility_key("dashboard")] is False
    assert settings.values[LEGACY_CALENDAR_VISIBILITY_KEY] is False


def test_scoped_visibility_normalizes_empty_layout_id():
    settings = _Settings()
    write_widget_calendar_visibility(settings, "", True)

    assert calendar_visibility_key("") == "widget_mode_calendar_visible_stacked"
    assert read_widget_calendar_visibility(settings, "stacked") is True
