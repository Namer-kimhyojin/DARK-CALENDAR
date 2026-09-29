# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.widgets.moment_asset_packs import (
    get_moment_asset_pack,
    moment_asset_html,
    moment_asset_packs,
    moment_asset_pixmap,
    moment_pack_preview_pixmap,
    season_moment_id,
)


class MomentAssetPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_generated_packs_render_every_authored_slot(self):
        slots = (
            "spring",
            "summer",
            "autumn",
            "winter",
            "birthday",
            "anniversary",
            "deadline",
            "launch",
            "travel",
            "study",
            "health",
            "celebration",
            "calm",
            "sparkle",
        )
        for pack in moment_asset_packs()[:2]:
            for slot in slots:
                pixmap = moment_asset_pixmap(pack.pack_id, slot, 64)
                self.assertFalse(pixmap.isNull(), (pack.pack_id, slot))
                self.assertEqual(pixmap.size(), QSize(64, 64))

    def test_text_only_pack_returns_no_art(self):
        self.assertEqual(get_moment_asset_pack("none").pack_id, "none")
        self.assertTrue(moment_asset_pixmap("none", "birthday", 48).isNull())
        self.assertEqual(moment_asset_html("none", "birthday", 48), "")

    def test_preview_and_html_are_renderable(self):
        preview = moment_pack_preview_pixmap("air_moments", QSize(300, 96))
        self.assertFalse(preview.isNull())
        self.assertIn("data:image/png;base64,", moment_asset_html("air_moments", "travel", 52))

    def test_months_map_to_four_seasons(self):
        self.assertEqual(season_moment_id(4), "spring")
        self.assertEqual(season_moment_id(7), "summer")
        self.assertEqual(season_moment_id(10), "autumn")
        self.assertEqual(season_moment_id(1), "winter")


if __name__ == "__main__":
    unittest.main()
