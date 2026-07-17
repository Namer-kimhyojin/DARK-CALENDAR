# -*- coding: utf-8 -*-
import json
from pathlib import Path
import unittest

from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
    _DARK_PRESETS,
    _FAMILY_BY_PRESET_KEY,
    _LIGHT_PRESETS,
    _PRESETS,
    _STYLE_FAMILIES,
    _accessible_text_palette,
    _contrast_ratio,
    _preset_mode_for_key,
)


class PanelColorPickerPresetTests(unittest.TestCase):
    def test_style_families_pair_dark_and_light_variants(self):
        family_ids = [family_id for family_id, *_ in _STYLE_FAMILIES]
        self.assertEqual(len(family_ids), len(set(family_ids)))
        self.assertGreaterEqual(len(family_ids), 6)

        for family_id, dark_key, light_key in _STYLE_FAMILIES:
            self.assertEqual(_preset_mode_for_key(dark_key), "dark")
            self.assertEqual(_preset_mode_for_key(light_key), "light")
            self.assertEqual(_FAMILY_BY_PRESET_KEY[dark_key], family_id)
            self.assertEqual(_FAMILY_BY_PRESET_KEY[light_key], family_id)

    def test_accessible_palette_meets_role_contrast_targets(self):
        for background in ("#101820", "#f4f7fb", "#777777"):
            palette = _accessible_text_palette(background)
            self.assertGreaterEqual(_contrast_ratio(palette["primary"], background), 4.5)
            self.assertGreaterEqual(_contrast_ratio(palette["secondary"], background), 4.5)
            self.assertGreaterEqual(_contrast_ratio(palette["muted"], background), 3.0)
            self.assertGreaterEqual(_contrast_ratio(palette["faint"], background), 2.0)

    def test_dark_light_groups_are_complete_and_disjoint(self):
        dark_keys = {name_key for name_key, *_ in _DARK_PRESETS}
        light_keys = {name_key for name_key, *_ in _LIGHT_PRESETS}
        all_keys = {name_key for name_key, *_ in _PRESETS}

        self.assertTrue(dark_keys, msg="dark preset group must not be empty")
        self.assertTrue(light_keys, msg="light preset group must not be empty")
        self.assertTrue(
            dark_keys.isdisjoint(light_keys), msg="dark/light preset keys must not overlap"
        )
        self.assertEqual(
            all_keys, dark_keys | light_keys, msg="combined preset set must match dark+light groups"
        )

    def test_preset_mode_helper_matches_groups(self):
        for name_key, *_ in _DARK_PRESETS:
            self.assertEqual("dark", _preset_mode_for_key(name_key))
        for name_key, *_ in _LIGHT_PRESETS:
            self.assertEqual("light", _preset_mode_for_key(name_key))

    def test_includes_diverse_light_presets(self):
        keys = {key for key, _, _, _, _ in _PRESETS}
        self.assertTrue(
            {
                "dialog.theme.preset.pastel_mint",
                "dialog.theme.preset.pastel_sky",
                "dialog.theme.preset.pastel_lavender",
                "dialog.theme.preset.pastel_peach",
                "dialog.theme.preset.pastel_rose",
                "dialog.theme.preset.pastel_coral",
                "dialog.theme.preset.pastel_lemon",
                "dialog.theme.preset.pastel_aqua",
                "dialog.theme.preset.pastel_sand",
                "dialog.theme.preset.pastel_sage",
                "dialog.theme.preset.pastel_ice",
                "dialog.theme.preset.pastel_blush",
            }.issubset(keys)
        )

    def test_pastel_presets_have_full_text_palette(self):
        for name_key, _fallback, _base, _theme, text_dict in _PRESETS:
            if not name_key.startswith("dialog.theme.preset.pastel_"):
                continue
            self.assertEqual(
                {"primary", "secondary", "muted", "faint"},
                set(text_dict.keys()),
                msg=f"{name_key} text palette keys mismatch",
            )

    def test_en_ko_have_preset_and_point_labels(self):
        locale_dir = Path(__file__).resolve().parents[1] / "locales"
        required_preset_keys = [name_key.split(".")[-1] for name_key, *_ in _PRESETS]
        required_preset_filter_keys = ["filter_label", "filter_all", "filter_dark", "filter_light"]
        required_point_keys = [
            "blue",
            "sky",
            "emerald",
            "mint",
            "violet",
            "pink",
            "orange",
            "red",
            "gold",
            "gray",
        ]

        for lang in ("en", "ko"):
            data = json.loads(
                (locale_dir / f"{lang}.json").read_text(encoding="utf-8", errors="strict")
            )
            theme = data["dialog"]["theme"]
            preset_dict = theme.get("preset", {})
            point_dict = theme.get("point", {})
            bg_dict = theme.get("bg", {})
            self.assertTrue(
                all(k in preset_dict for k in required_preset_keys),
                msg=f"{lang} preset keys missing",
            )
            self.assertTrue(
                all(k in preset_dict for k in required_preset_filter_keys),
                msg=f"{lang} preset filter keys missing",
            )
            self.assertTrue(
                all(k in point_dict for k in required_point_keys), msg=f"{lang} point keys missing"
            )
            self.assertIn("auto_apply_text", bg_dict, msg=f"{lang} auto_apply_text missing")
            self.assertIn("auto_apply_text_tip", bg_dict, msg=f"{lang} auto_apply_text_tip missing")

            if lang == "ko":
                for key in required_preset_keys:
                    value = str(preset_dict.get(key, "")).strip()
                    self.assertNotEqual("", value, msg=f"{lang} preset label empty: {key}")
                    self.assertFalse(
                        set(value) <= {"?"}, msg=f"{lang} preset label placeholder: {key}"
                    )
                for key in required_point_keys:
                    value = str(point_dict.get(key, "")).strip()
                    self.assertNotEqual("", value, msg=f"{lang} point label empty: {key}")
                    self.assertFalse(
                        set(value) <= {"?"}, msg=f"{lang} point label placeholder: {key}"
                    )


if __name__ == "__main__":
    unittest.main()
