# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_display_presets import (
    CUSTOM_DISPLAY_PRESET_ID,
    DEFAULT_DISPLAY_PRESET_ID,
    overlay_display_preset,
    overlay_display_presets,
)
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.presentation.widgets.overlay_widgets import (
    OverlayCountdownWidget,
    OverlayDateCardWidget,
    OverlayDDayWidget,
    OverlayStopwatchWidget,
    OverlayTextWidget,
    OverlayWeatherWidget,
)


class OverlayDisplayPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.owner = QWidget()
        self.owner.settings = QSettings("codex_test", "dark_calendar_display_presets")
        self.owner.settings.clear()

    def tearDown(self):
        self.owner.settings.clear()
        self.owner.close()
        super().tearDown()

    def test_registry_has_at_least_twelve_complete_and_distinct_presets(self):
        presets = overlay_display_presets()

        self.assertGreaterEqual(len(presets), 12)
        self.assertEqual(len(presets), len({preset.preset_id for preset in presets}))
        visual_signatures = {
            (
                preset.font_candidates,
                preset.text_rgba,
                preset.background_rgba,
                preset.border_rgba,
                tuple(sorted((key, str(value)) for key, value in preset.style_params.items())),
            )
            for preset in presets
        }
        self.assertEqual(len(presets), len(visual_signatures))
        for preset in presets:
            self.assertTrue(preset.font_candidates)
            self.assertRegex(preset.text_rgba, r"^#[0-9a-fA-F]{8}$")
            self.assertRegex(preset.background_rgba, r"^#[0-9a-fA-F]{8}$")
            self.assertRegex(preset.border_rgba, r"^#[0-9a-fA-F]{8}$")
            self.assertIn("margins", preset.style_params)
            self.assertIn("radius", preset.style_params)

    def test_pure_type_preset_renders_only_text_and_persists(self):
        preset = overlay_display_preset("pure_type")
        assert preset is not None
        self.assertEqual("00", preset.background_rgba[1:3])
        self.assertEqual("00", preset.border_rgba[1:3])
        self.assertNotEqual("00", preset.text_rgba[1:3])

        widget = OverlayClockWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set_display_preset("pure_type")

        self.assertEqual("pure_type", widget.display_preset_id())
        self.assertIn("background: transparent", widget.face.styleSheet())
        self.assertIn("border: none", widget.face.styleSheet())
        widget.close()

        restored = OverlayClockWidget(self.owner)
        self.addCleanup(restored.close)
        self.assertEqual("pure_type", restored.display_preset_id())
        self.assertEqual(preset.background_rgba, restored.bg_color_rgba())
        self.assertEqual(preset.border_rgba, restored.border_color_rgba())

    def test_every_widget_exposes_the_same_display_presets(self):
        classes = (
            OverlayClockWidget,
            OverlayStopwatchWidget,
            OverlayDateCardWidget,
            OverlayCountdownWidget,
            OverlayDDayWidget,
            OverlayTextWidget,
            OverlayWeatherWidget,
        )
        expected_ids = [preset.preset_id for preset in overlay_display_presets()]

        widgets = [widget_class(self.owner) for widget_class in classes]
        for widget in widgets:
            self.addCleanup(widget.close)
            self.assertEqual(expected_ids, [item[0] for item in widget._display_preset_items()])
            self.assertEqual(DEFAULT_DISPLAY_PRESET_ID, widget.display_preset_id())

    def test_selecting_preset_applies_and_persists_complete_appearance(self):
        widget = OverlayClockWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set_display_preset("electric_cyan")
        preset = overlay_display_preset("electric_cyan")
        assert preset is not None

        self.assertEqual("electric_cyan", widget.display_preset_id())
        self.assertEqual(preset.text_rgba, widget.text_color_rgba())
        self.assertEqual(preset.background_rgba, widget.bg_color_rgba())
        self.assertEqual(preset.border_rgba, widget.border_color_rgba())
        widget.close()

        restored = OverlayClockWidget(self.owner)
        self.addCleanup(restored.close)
        self.assertEqual("electric_cyan", restored.display_preset_id())
        self.assertEqual(preset.text_rgba, restored.text_color_rgba())
        self.assertEqual(preset.background_rgba, restored.bg_color_rgba())
        self.assertEqual(preset.border_rgba, restored.border_color_rgba())

    def test_manual_legacy_appearance_is_preserved_as_custom(self):
        custom_text = "#ff123456"
        self.owner.settings.setValue("overlay_clock_text_color_rgba", custom_text)

        widget = OverlayClockWidget(self.owner)
        self.addCleanup(widget.close)

        self.assertEqual(CUSTOM_DISPLAY_PRESET_ID, widget.display_preset_id())
        self.assertEqual(custom_text, widget.text_color_rgba())

    def test_visual_preset_does_not_replace_widget_specific_display_format(self):
        widget = OverlayClockWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set_display_style("split")
        widget._set_display_preset("paper_ivory")

        self.assertEqual("split", widget.display_style())
        self.assertEqual("paper_ivory", widget.display_preset_id())

    def test_instance_prefixed_preset_survives_manager_restore(self):
        manager = OverlayWidgetManager(self.owner)
        self.addCleanup(manager.remove_all)
        instance_id = manager.add_instance("clock")
        widget = manager.get_widget(instance_id)
        widget._set_display_preset("retro_amber")
        manager.save_all()

        restored_manager = OverlayWidgetManager(self.owner)
        self.addCleanup(restored_manager.remove_all)
        restored_manager.restore_all()
        restored = restored_manager.get_widget(instance_id)

        self.assertEqual("retro_amber", restored.display_preset_id())
        preset = overlay_display_preset("retro_amber")
        assert preset is not None
        self.assertEqual(preset.text_rgba, restored.text_color_rgba())


if __name__ == "__main__":
    unittest.main()
