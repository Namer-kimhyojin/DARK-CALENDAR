# -*- coding: utf-8 -*-
"""Pearl light surfaces retain readable hierarchy and decorative opacity."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

from calendar_app.shared.color_utils import (
    composite_color,
    contrast_ratio,
    derive_modal_state_palette,
    derive_panel_palette,
    derive_state_palette,
    derive_text_palette,
    derive_ui_palette,
    hex_to_rgba,
    parse_css_color,
)


class LightPaletteLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_pearl_canvas_and_white_reading_cards_are_distinct(self):
        palette = derive_panel_palette("#f6f7fb", 1.0)
        self.assertEqual(parse_css_color(palette["surface_bg"]).name(), "#f6f7fb")
        for role in ("item_bg", "content_bg", "floating_bg"):
            with self.subTest(role=role):
                self.assertEqual(parse_css_color(palette[role]).name(), "#ffffff")
        self.assertGreaterEqual(len(set(palette.values())), 5)

    def test_primary_secondary_and_supporting_text_keep_their_reading_contrast(self):
        for base in ("#f6f7fb", "#e7f5ff", "#e6fcf5", "#fff0f6", "#fff4e6"):
            palette = derive_ui_palette("light", base, 1.0, "#7653c4")
            for surface in (palette["bg_primary"], palette["content_bg"], palette["selection_bg"]):
                background = composite_color(surface, base)
                for role in ("text_primary", "text_secondary"):
                    with self.subTest(base=base, surface=surface, role=role):
                        self.assertGreaterEqual(contrast_ratio(palette[role], background), 4.5)
                for role in ("text_muted", "text_faint"):
                    with self.subTest(base=base, surface=surface, role=role):
                        self.assertGreaterEqual(contrast_ratio(palette[role], background), 3.0)
            for role in ("text_primary", "text_secondary", "text_muted", "text_faint"):
                self.assertEqual(parse_css_color(palette[role]).alpha(), 255)

    def test_weekend_labels_remain_readable_on_calendar_and_header_surfaces(self):
        panel = derive_panel_palette("#f6f7fb", 1.0)
        palette = derive_ui_palette("light", "#f6f7fb", 1.0, "#7653c4")
        for role in ("weekday_sat", "weekday_sun"):
            for surface in ("#f6f7fb", "#ffffff", panel["topbar_bg"]):
                with self.subTest(role=role, surface=surface):
                    self.assertGreaterEqual(
                        contrast_ratio(palette[role], composite_color(surface, "#ffffff")), 4.5
                    )

    def test_decorative_opacity_endpoints_preserve_reading_surface_floors(self):
        decorative = (
            "surface_bg",
            "surface_hover_bg",
            "toolbar_bg",
            "topbar_bg",
            "item_bg",
            "item_hover_bg",
        )
        for base in ("#f6f7fb", "#fff0f6", "#121827"):
            transparent = derive_panel_palette(base, 0.0)
            opaque = derive_panel_palette(base, 1.0)
            for role in decorative:
                with self.subTest(base=base, role=role):
                    self.assertEqual(parse_css_color(transparent[role]).alpha(), 0)
                    self.assertEqual(parse_css_color(opaque[role]).alpha(), 255)
            self.assertGreaterEqual(parse_css_color(transparent["content_bg"]).alpha(), 220)
            self.assertGreaterEqual(parse_css_color(transparent["floating_bg"]).alpha(), 248)
        for opacity, alpha in ((0.0, 0), (1.0, 255)):
            palette = derive_ui_palette("light", "#f6f7fb", opacity, "#7653c4")
            self.assertEqual(parse_css_color(palette["selection_bg"]).alpha(), alpha)
            self.assertEqual(parse_css_color(palette["control_bg"]).alpha(), alpha)

    def test_light_selection_tracks_the_user_accent(self):
        lilac = derive_ui_palette("light", "#f6f7fb", 1.0, "#7653c4")
        teal = derive_ui_palette("light", "#f6f7fb", 1.0, "#008e82")
        self.assertNotEqual(lilac["selection_bg"], teal["selection_bg"])
        self.assertGreaterEqual(
            contrast_ratio(lilac["text_secondary"], parse_css_color(lilac["selection_bg"])), 4.5
        )

    def test_existing_navy_dark_values_are_unchanged(self):
        panel = derive_panel_palette("#121827", 1.0)
        expected = {
            "surface_bg": "rgba(18, 24, 39, 255)",
            "surface_hover_bg": "rgba(26, 32, 47, 255)",
            "toolbar_bg": "rgba(27, 33, 48, 255)",
            "topbar_bg": "rgba(24, 30, 44, 255)",
            "item_bg": "rgba(31, 37, 51, 255)",
            "item_hover_bg": "rgba(42, 47, 61, 255)",
            "content_bg": "rgba(18, 24, 39, 255)",
            "floating_bg": "rgba(27, 33, 48, 255)",
        }
        self.assertEqual(panel, expected)
        text = derive_text_palette("dark", "#c5a3f5")
        self.assertEqual(text["text_primary"], "#f4f7fb")
        self.assertEqual(text["text_secondary"], "rgba(244,247,251,0.76)")
        ui = derive_ui_palette("dark", "#121827", 1.0, "#c5a3f5")
        self.assertEqual(ui["border"], "rgba(255,255,255,0.16)")
        self.assertEqual(ui["control_bg"], "rgba(255,255,255,0.05)")
        self.assertEqual(ui["weekday_sat"], "#8ab7ff")
        self.assertEqual(ui["weekday_sun"], "#ff9ea8")
        self.assertEqual(ui["selection_bg"], expected["toolbar_bg"])

    def test_light_state_text_meets_aa_on_cards_and_its_soft_badges(self):
        for role, color in derive_state_palette("light").items():
            for surface in ("#ffffff", "#f6f7fb"):
                for alpha in (0.0, 0.14, 0.16, 0.20, 0.22, 0.32):
                    with self.subTest(role=role, surface=surface, badge_alpha=alpha):
                        background = composite_color(hex_to_rgba(color, alpha), surface)
                        self.assertGreaterEqual(contrast_ratio(color, background), 4.5)
        self.assertEqual(
            derive_state_palette("dark"),
            {"success": "#35b66a", "warning": "#d39a2a", "danger": "#d25a66"},
        )

    def test_main_states_stay_semantic_and_modal_states_follow_the_custom_accent(self):
        from calendar_app.shared.theme_snapshot import (
            build_dialog_base_tokens,
            build_shared_ui_tokens,
        )

        for mode, base in (("dark", "#121827"), ("light", "#f6f7fb")):
            shared = build_shared_ui_tokens(
                text_theme=mode, panel_base_color=base, theme_color="#246fba", opacity_factor=1.0
            )
            dialog = build_dialog_base_tokens(
                text_theme=mode, panel_base_color=base, theme_color="#246fba", opacity_factor=1.0
            )
            self.assertEqual(shared["accent"], "#246fba")
            self.assertEqual(dialog["accent"], "#246fba")
            for role, expected in derive_state_palette(mode).items():
                with self.subTest(mode=mode, role=role):
                    self.assertEqual(shared[role], expected)
                    self.assertEqual(shared[f"{role}_hex"], expected)
                    modal = derive_modal_state_palette(
                        "#246fba", composite_color(dialog["floating_bg"], base).name()
                    )
                    self.assertEqual(dialog[f"{role}_hex"], modal[role])

    def test_real_widget_visibility_badge_uses_the_light_success_role(self):
        from calendar_app.presentation.widgets.overlay_manager_dialog import (
            _load_tokens,
            _ToggleBtn,
        )

        with TemporaryDirectory() as folder:
            settings = QSettings(str(Path(folder) / "badge.ini"), QSettings.Format.IniFormat)
            for key, value in {
                "text_theme": "light",
                "panel_base_color": "#f6f7fb",
                "theme_color": "#7653c4",
                "last_opacity": 255,
                "last_opacity_unit": "byte",
            }.items():
                settings.setValue(key, value)
            tokens = _load_tokens(settings=settings)
            badge = _ToggleBtn(True, tokens)
            self.addCleanup(badge.close)
            badge.setText("표시 중")
            badge.ensurePolished()
            self.assertEqual(
                tokens["success"], derive_modal_state_palette("#7653c4", "#ffffff")["success"]
            )
            self.assertIn(f"color: {tokens['success']};", badge.styleSheet())
            self.assertEqual(
                badge.palette().color(QPalette.ColorRole.ButtonText).name(), tokens["success"]
            )
            for role in ("success_bg", "success_bg_hover"):
                self.assertIn(tokens[role], badge.styleSheet())
                background = composite_color(tokens[role], "#ffffff")
                self.assertGreaterEqual(contrast_ratio(tokens["success"], background), 4.5)
