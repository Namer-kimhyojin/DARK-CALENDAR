import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from calendar_app.presentation.widgets.alarm_popup import (
    _alarm_popup_style_bundle,
    _build_alarm_popup_stylesheet,
)


class AlarmPopupStyleTests(unittest.TestCase):
    def test_style_bundle_forces_opaque_surface_colors(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_hover": "#5de0e5",
            "bg_main": "rgba(12,24,36,230)",
            "bg_alt": "rgba(18,30,42,220)",
            "bg_item_hover": "rgba(255,255,255,0.08)",
            "bg_hover": "rgba(255,255,255,0.12)",
            "border": "rgba(255,255,255,0.16)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "warning_hex": "#f0a030",
            "success_hex": "#46CC71",
            "danger_hex": "#e05050",
        }

        bundle = _alarm_popup_style_bundle(tokens=tokens)
        stylesheet = _build_alarm_popup_stylesheet(bundle)

        self.assertEqual(bundle["card_bg"], "#0c1824")
        self.assertEqual(bundle["card_surface"], "#121e2a")
        self.assertEqual(bundle["card_hover"], "#25303b")
        self.assertIn("background: #0c1824;", stylesheet)
        self.assertIn("background-color: #121e2a;", stylesheet)


if __name__ == "__main__":
    unittest.main()
