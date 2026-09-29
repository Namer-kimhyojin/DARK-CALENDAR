# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, QSize
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from calendar_app.presentation.widgets.weather_asset_packs import (
    DEFAULT_WEATHER_ASSET_PACK_ID,
    get_weather_asset_pack,
    weather_asset_html,
    weather_asset_packs,
    weather_asset_pixmap,
    weather_condition_id,
    weather_pack_preview_pixmap,
)


class WeatherAssetPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_registry_contains_three_bundled_art_packs_and_classic_fallback(self):
        pack_ids = [pack.pack_id for pack in weather_asset_packs()]

        self.assertEqual(len(pack_ids), len(set(pack_ids)))
        self.assertEqual(DEFAULT_WEATHER_ASSET_PACK_ID, "air_soft")
        self.assertTrue(
            {"air_soft", "paper_weather", "mono_atmosphere", "classic"} <= set(pack_ids)
        )
        self.assertEqual(get_weather_asset_pack("missing").pack_id, "air_soft")

    def test_condition_mapping_distinguishes_day_night_and_intensity(self):
        self.assertEqual(weather_condition_id(0, "day"), "clear_day")
        self.assertEqual(weather_condition_id(0, "night"), "clear_night")
        self.assertEqual(weather_condition_id(2, "night"), "partly_cloudy_night")
        self.assertEqual(weather_condition_id(65, "day"), "heavy_rain")
        self.assertEqual(weather_condition_id(99, "day"), "hail")
        self.assertEqual(weather_condition_id(-1, "day"), "unknown")

    def test_every_bundled_pack_renders_weather_and_preview(self):
        for pack in weather_asset_packs():
            with self.subTest(pack=pack.pack_id):
                pixmap = weather_asset_pixmap(pack.pack_id, 61, "day", 72)
                preview = weather_pack_preview_pixmap(pack.pack_id, QSize(300, 104))
                html = weather_asset_html(pack.pack_id, 61, "day", 72)

                self.assertFalse(pixmap.isNull())
                self.assertEqual(pixmap.size(), QSize(72, 72))
                self.assertFalse(preview.isNull())
                self.assertIn("data:image/png;base64,", html)
                self.assertIn('width="72"', html)

    def test_weather_widget_persists_asset_pack_independently(self):
        owner = QWidget()
        self.addCleanup(owner.close)
        owner.settings = QSettings("codex_test", "weather_asset_pack")
        owner.settings.clear()
        self.addCleanup(owner.settings.clear)

        with patch.object(OverlayWeatherWidget, "request_update"):
            widget = OverlayWeatherWidget(owner)
        self.addCleanup(widget.close)
        widget._set_weather_asset_pack("paper_weather")

        self.assertEqual(widget._get("weather_asset_pack"), "paper_weather")
        self.assertEqual(widget.display_style(), "default")
        self.assertIn(
            "data:image/png;base64,",
            widget._resolve_weather_template(
                "{icon|size=64}",
                {"_wmo": 0, "_day_period": "night", "desc": "Clear"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
