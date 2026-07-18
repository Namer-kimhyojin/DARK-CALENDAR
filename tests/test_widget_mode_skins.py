# -*- coding: utf-8 -*-
from pathlib import Path
import tempfile
import unittest

from calendar_app.presentation.widgets.widget_mode_skins import (
    WIDGET_MODE_LAYOUT_SETTING_KEY,
    WIDGET_MODE_SKIN_SETTING_KEY,
    WidgetModeLayout,
    WidgetModeSkin,
    apply_widget_mode_skin,
    create_user_widget_layout,
    create_user_widget_skin,
    get_widget_mode_layout,
    get_widget_mode_skin,
    load_user_widget_styles,
    read_widget_mode_layout_id,
    read_widget_mode_skin_id,
    register_widget_mode_layout,
    register_widget_mode_skin,
    widget_mode_layouts,
    widget_mode_skins,
    write_widget_mode_layout_id,
    write_widget_mode_skin_id,
)


class _FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class WidgetModeSkinTests(unittest.TestCase):
    def test_builtin_layouts_cover_distinct_compositions(self):
        layout_ids = {layout.layout_id for layout in widget_mode_layouts()}

        self.assertTrue(
            {"stacked", "dashboard", "agenda_first", "magazine", "minimal"} <= layout_ids
        )
        self.assertEqual((720, 520), get_widget_mode_layout("dashboard").preferred_size)
        self.assertNotIn(
            "calendar",
            {placement[0] for placement in get_widget_mode_layout("minimal").placements},
        )

    def test_builtin_skins_have_stable_unique_ids(self):
        skin_ids = [skin.skin_id for skin in widget_mode_skins()]

        self.assertEqual(len(skin_ids), len(set(skin_ids)))
        self.assertGreaterEqual(len(skin_ids), 6)
        self.assertIn("classic_light", skin_ids)
        self.assertIn("classic_dark", skin_ids)
        self.assertIn("midnight_blue", skin_ids)

    def test_missing_skin_uses_legacy_dark_setting(self):
        settings = _FakeSettings({"widget_mode_panel_theme": "dark"})

        self.assertEqual("classic_dark", read_widget_mode_skin_id(settings))

    def test_unknown_saved_skin_falls_back_safely(self):
        settings = _FakeSettings(
            {WIDGET_MODE_SKIN_SETTING_KEY: "removed_skin", "widget_mode_panel_theme": "light"}
        )

        self.assertEqual("classic_light", read_widget_mode_skin_id(settings))
        self.assertEqual("classic_light", get_widget_mode_skin("removed_skin").skin_id)

    def test_writing_skin_keeps_legacy_theme_compatible(self):
        settings = _FakeSettings()

        written = write_widget_mode_skin_id(settings, "forest_mist")

        self.assertEqual("forest_mist", written)
        self.assertEqual("forest_mist", settings.values[WIDGET_MODE_SKIN_SETTING_KEY])
        self.assertEqual("dark", settings.values["widget_mode_panel_theme"])
        self.assertEqual("stacked", settings.values[WIDGET_MODE_LAYOUT_SETTING_KEY])

    def test_legacy_skin_layout_is_migrated_then_color_and_layout_are_independent(self):
        settings = _FakeSettings({WIDGET_MODE_SKIN_SETTING_KEY: "midnight_blue"})

        self.assertEqual("dashboard", read_widget_mode_layout_id(settings))
        write_widget_mode_skin_id(settings, "lavender_dream")

        self.assertEqual("dashboard", read_widget_mode_layout_id(settings))
        self.assertEqual("lavender_dream", read_widget_mode_skin_id(settings))

    def test_writing_layout_does_not_change_skin(self):
        settings = _FakeSettings({WIDGET_MODE_SKIN_SETTING_KEY: "forest_mist"})

        write_widget_mode_layout_id(settings, "magazine")

        self.assertEqual("forest_mist", read_widget_mode_skin_id(settings))
        self.assertEqual("magazine", read_widget_mode_layout_id(settings))

    def test_registered_extension_is_discoverable_without_ui_changes(self):
        skin = WidgetModeSkin(
            "test_extension_skin",
            "widget_mode.skin_test_extension",
            "Test Extension",
            token_overrides={"accent": "#123456"},
        )
        register_widget_mode_skin(skin, replace=True)

        self.assertIs(skin, get_widget_mode_skin("test_extension_skin"))
        self.assertIn(skin, widget_mode_skins())
        self.assertEqual(
            "#123456",
            apply_widget_mode_skin({"accent": "#ffffff"}, skin.skin_id)["accent"],
        )

    def test_registered_layout_can_be_referenced_by_a_skin(self):
        layout = WidgetModeLayout(
            "test_extension_layout",
            "widget_mode.layout_test_extension",
            "Test Layout",
            placements=(("hero", 0, 0, 1, 1), ("agenda", 1, 0, 1, 1)),
        )
        register_widget_mode_layout(layout, replace=True)
        skin = WidgetModeSkin(
            "test_layout_skin",
            "widget_mode.skin_test_layout",
            "Test Layout Skin",
            legacy_layout_id=layout.layout_id,
        )
        register_widget_mode_skin(skin, replace=True)

        self.assertEqual(layout.layout_id, get_widget_mode_skin(skin.skin_id).legacy_layout_id)

    def test_skin_definition_copies_and_freezes_token_overrides(self):
        source = {"accent": "#abcdef"}
        skin = WidgetModeSkin(
            "immutable_skin", "skin.immutable", "Immutable", token_overrides=source
        )
        source["accent"] = "#000000"

        self.assertEqual("#abcdef", skin.token_overrides["accent"])
        with self.assertRaises(TypeError):
            skin.token_overrides["accent"] = "#111111"

    def test_user_skin_and_layout_are_persisted_and_reloadable(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tmp") as temp_dir:
            path = Path(temp_dir) / "widget_styles.json"
            skin = create_user_widget_skin(
                "Ocean Custom", base_theme="dark", accent="#336699", path=path
            )
            layout = create_user_widget_layout(
                "Wide Custom",
                template_id="dashboard",
                preferred_size=(900, 600),
                show_eyebrow=False,
                show_hint=True,
                path=path,
            )

            loaded_skins, loaded_layouts = load_user_widget_styles(path)

            self.assertEqual((1, 1), (loaded_skins, loaded_layouts))
            self.assertEqual(
                "#336699", get_widget_mode_skin(skin.skin_id).token_overrides["accent"]
            )
            self.assertEqual((900, 600), get_widget_mode_layout(layout.layout_id).preferred_size)
            self.assertFalse(get_widget_mode_layout(layout.layout_id).show_eyebrow)


if __name__ == "__main__":
    unittest.main()
