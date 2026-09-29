# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.widgets.launcher_deck_model import KEYCAP_ICONS, new_key
from calendar_app.presentation.widgets.launcher_keycap_assets import (
    KEYCAP_ASSETS,
    crop_mosaic_pixmap,
    keycap_asset,
)
from calendar_app.presentation.widgets.launcher_keycap_icons import (
    KEYCAP_ICON_PACKS,
    keycap_icon_pack,
)
from calendar_app.presentation.widgets.overlay_launcher_deck import LauncherKeycapButton


class LauncherKeycapAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_bundled_library_contains_twenty_one_renderable_decals(self):
        bundled = [asset for asset in KEYCAP_ASSETS if asset.filename]
        self.assertEqual(len(bundled), 21)
        for asset in bundled:
            path = asset.path()
            self.assertTrue(path.is_file(), asset.asset_id)
            pixmap = QPixmap(str(path))
            self.assertFalse(pixmap.isNull(), asset.asset_id)
            self.assertEqual((pixmap.width(), pixmap.height()), (128, 128))

    def test_unknown_asset_falls_back_to_none(self):
        self.assertEqual(keycap_asset("missing").asset_id, "none")

    def test_mosaic_crop_returns_each_keys_portion(self):
        source = QPixmap(120, 60)
        painter = QPainter(source)
        painter.fillRect(0, 0, 60, 60, QColor("#ff0000"))
        painter.fillRect(60, 0, 60, 60, QColor("#0000ff"))
        painter.end()
        deck = {"columns": 2, "rows": 1}
        left = crop_mosaic_pixmap(source, deck, {"column": 0, "row": 0, "width": 1, "height": 1})
        right = crop_mosaic_pixmap(source, deck, {"column": 1, "row": 0, "width": 1, "height": 1})
        self.assertGreater(
            left.toImage().pixelColor(left.width() // 2, left.height() // 2).red(), 240
        )
        self.assertGreater(
            right.toImage().pixelColor(right.width() // 2, right.height() // 2).blue(), 240
        )

    def test_icon_packs_provide_consistent_valid_colors(self):
        self.assertEqual(len(KEYCAP_ICON_PACKS), 5)
        for pack in KEYCAP_ICON_PACKS:
            self.assertTrue(QColor(pack.color).isValid(), pack.pack_id)
            self.assertEqual(keycap_icon_pack(pack.pack_id), pack)

    def test_all_registered_vector_icons_render(self):
        self.assertEqual(len(KEYCAP_ICONS), 35)
        key = new_key("Icon", 0, 0)
        button = LauncherKeycapButton(key, lambda _key: True)
        for icon_id, _label_key, _fallback in KEYCAP_ICONS:
            key["icon"] = icon_id
            resolved = button._resolved_icon()
            if icon_id == "none":
                self.assertTrue(resolved.isNull())
            else:
                self.assertFalse(resolved.isNull(), icon_id)
        button.close()


if __name__ == "__main__":
    unittest.main()
