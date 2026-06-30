import re
import unittest

from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
    _COLOR_PRESETS,
    _normalize_color,
    get_color_preset_tokens,
)

_RGBA_RE = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)


class DialogTokenColorPresetTests(unittest.TestCase):
    def test_light_aqua_presets_exist(self):
        self.assertIn("Light Aqua Form", _COLOR_PRESETS)
        self.assertIn("Light Aqua Form (Soft)", _COLOR_PRESETS)

    def test_color_preset_lookup_helper_returns_tokens(self):
        tokens = get_color_preset_tokens("Light Aqua Form")
        self.assertIsInstance(tokens, dict)
        self.assertEqual(tokens.get("accent"), "#22c3ca")
        self.assertEqual(get_color_preset_tokens("Unknown Preset"), {})

    def test_light_aqua_presets_define_readable_light_tokens(self):
        for preset_name in ("Light Aqua Form", "Light Aqua Form (Soft)"):
            payload = _COLOR_PRESETS[preset_name]
            self.assertIsInstance(payload, dict)
            tokens = payload.get("tokens", {})
            self.assertIsInstance(tokens, dict)

            accent = str(tokens.get("accent", "")).lower()
            self.assertIn(accent, {"#22c3ca", "#2ec0c7"})

            for key in (
                "surface_bg",
                "surface_alt",
                "surface_item",
                "text_primary",
                "border",
                "border_soft",
            ):
                self.assertIsNotNone(
                    _normalize_color(tokens.get(key)), msg=f"{preset_name} missing valid {key}"
                )

            border = str(tokens.get("border", ""))
            match = _RGBA_RE.match(border)
            self.assertIsNotNone(match, msg=f"{preset_name} border must be rgba")
            r, g, b, a = (int(match.group(i)) for i in range(1, 5))
            self.assertLess(
                max(r, g, b), 200, msg=f"{preset_name} border should be dark enough on light bg"
            )
            self.assertGreater(a, 80, msg=f"{preset_name} border alpha too low")


if __name__ == "__main__":
    unittest.main()
