# -*- coding: utf-8 -*-
import unittest

from calendar_app.presentation.widgets import widget_mode_skins as skins_module
from calendar_app.presentation.widgets.widget_mode_skins import (
    WIDGET_MODE_LAYOUT_SETTING_KEY,
    WidgetModeLayout,
    get_widget_mode_layout,
    read_widget_mode_layout_id,
    register_widget_mode_layout,
    widget_mode_layouts,
    write_widget_mode_layout_id,
)


class _FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class WidgetModeLayoutTests(unittest.TestCase):
    def test_builtin_layouts_cover_distinct_compositions(self):
        layout_ids = {layout.layout_id for layout in widget_mode_layouts()}

        self.assertEqual({"stacked", "dashboard", "work_board", "minimal"}, layout_ids)
        self.assertEqual((720, 520), get_widget_mode_layout("dashboard").preferred_size)
        self.assertNotIn(
            "calendar",
            {placement[0] for placement in get_widget_mode_layout("minimal").placements},
        )

    def test_board_layouts_place_filters_with_the_agenda_opposite_the_calendar(self):
        dashboard = {
            section: (row, column, row_span, column_span)
            for section, row, column, row_span, column_span in get_widget_mode_layout(
                "dashboard"
            ).placements
        }

        self.assertEqual((1, 0, 2, 1), dashboard["calendar"])
        self.assertEqual(1, dashboard["filters"][1])
        self.assertEqual(1, dashboard["agenda"][1])

    def test_legacy_skin_value_maps_to_a_kept_layout_without_writing(self):
        settings = _FakeSettings({"widget_mode_skin": "midnight_blue"})

        self.assertEqual("dashboard", read_widget_mode_layout_id(settings))
        self.assertEqual({"widget_mode_skin": "midnight_blue"}, settings.values)

    def test_legacy_skin_with_retired_layout_maps_to_the_kept_one(self):
        settings = _FakeSettings({"widget_mode_skin": "forest_mist"})

        self.assertEqual("stacked", read_widget_mode_layout_id(settings))

    def test_retired_saved_layout_maps_to_a_kept_layout(self):
        settings = _FakeSettings({WIDGET_MODE_LAYOUT_SETTING_KEY: "side_planner"})

        self.assertEqual("dashboard", read_widget_mode_layout_id(settings))

    def test_unknown_values_fall_back_to_the_default_layout(self):
        settings = _FakeSettings(
            {WIDGET_MODE_LAYOUT_SETTING_KEY: "nope", "widget_mode_skin": "removed_skin"}
        )

        self.assertEqual("stacked", read_widget_mode_layout_id(settings))
        self.assertEqual("stacked", read_widget_mode_layout_id(None))

    def test_writing_layout_does_not_touch_other_settings(self):
        settings = _FakeSettings({"widget_mode_surface": "line"})

        write_widget_mode_layout_id(settings, "work_board")

        self.assertEqual("line", settings.values["widget_mode_surface"])
        self.assertEqual("work_board", read_widget_mode_layout_id(settings))

    def test_registered_layout_is_discoverable(self):
        layout = WidgetModeLayout(
            "test_extension_layout",
            "widget_mode.layout_test_extension",
            "Test Layout",
            placements=(("hero", 0, 0, 1, 1), ("agenda", 1, 0, 1, 1)),
        )
        register_widget_mode_layout(layout, replace=True)
        self.addCleanup(skins_module._LAYOUTS.pop, layout.layout_id, None)

        self.assertIs(layout, get_widget_mode_layout("test_extension_layout"))
        self.assertIn(layout, widget_mode_layouts())


if __name__ == "__main__":
    unittest.main()
