# -*- coding: utf-8 -*-
"""Brand mark tinting preserves alpha and follows the active surface and DPI."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from calendar_app.shared.brand_assets import brand_mark_pixmap, clear_brand_mark_cache
from calendar_app.shared.color_utils import contrast_ratio


class BrandAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "alpha-mask.png"
        mask = QImage(8, 8, QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        for y in range(2, 6):
            for x in range(2, 6):
                mask.setPixelColor(x, y, QColor(100, 120, 180, 255))
        mask.setPixelColor(1, 1, QColor(100, 120, 180, 128))
        mask.save(str(self.path))
        self.patch = patch(
            "calendar_app.shared.brand_assets._source_mark_path", return_value=str(self.path)
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(clear_brand_mark_cache)

    def test_tint_preserves_transparent_and_partial_alpha_without_new_files(self):
        before = list(self.path.parent.iterdir())
        image = brand_mark_pixmap("#c5a3f5", 8).toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(1, 1).alpha(), 128)
        self.assertEqual(image.pixelColor(3, 3).name(), "#c5a3f5")
        self.assertEqual(list(self.path.parent.iterdir()), before)

    def test_color_size_and_dpr_have_separate_cached_results(self):
        first = brand_mark_pixmap("#c5a3f5", 8)
        same = brand_mark_pixmap("#c5a3f5", 8)
        changed = brand_mark_pixmap("#35cda5", 8)
        high_dpi = brand_mark_pixmap("#c5a3f5", 8, dpr=1.25)
        self.assertEqual(first.cacheKey(), same.cacheKey())
        self.assertNotEqual(first.cacheKey(), changed.cacheKey())
        self.assertEqual(changed.toImage().pixelColor(3, 3).name(), "#35cda5")
        self.assertEqual((high_dpi.width(), high_dpi.height()), (10, 10))
        self.assertEqual(high_dpi.devicePixelRatio(), 1.25)

    def test_light_background_tones_bright_accents_but_dark_keeps_lilac(self):
        dark = brand_mark_pixmap("#c5a3f5", 8, background="#121827")
        self.assertEqual(dark.toImage().pixelColor(3, 3).name(), "#c5a3f5")
        light = brand_mark_pixmap("#ffff80", 8, background="#ffffff", base="#ffffff")
        color = light.toImage().pixelColor(3, 3).name()
        self.assertGreaterEqual(contrast_ratio(color, "#ffffff"), 3.0)
