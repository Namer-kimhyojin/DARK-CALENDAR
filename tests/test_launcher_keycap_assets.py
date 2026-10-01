# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.widgets.keydeck import resources
from calendar_app.presentation.widgets.keydeck.physics import SWITCH_PROFILES
from calendar_app.presentation.widgets.launcher_keycap_assets import KEYCAP_ASSETS, keycap_asset
from calendar_app.presentation.widgets.launcher_keycap_icons import (
    KEYCAP_ICON_ASSETS,
    keycap_icon_asset,
)


class KeycapAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_bundled_library_contains_twenty_one_renderable_decals(self):
        bundled = [asset for asset in KEYCAP_ASSETS if asset.filename]
        self.assertEqual(len(bundled), 21)
        for asset in bundled:
            pixmap = QPixmap(str(asset.path()))
            self.assertFalse(pixmap.isNull(), asset.asset_id)
            self.assertEqual((pixmap.width(), pixmap.height()), (128, 128))

    def test_unknown_asset_falls_back_to_none(self):
        self.assertEqual(keycap_asset("missing").asset_id, "none")

    def test_patterns_are_recoloured_and_cached(self):
        image = resources.pattern_image("spark", "#ff0000", 64)
        self.assertIsNotNone(image)
        center = image.pixelColor(32, 32)
        self.assertGreater(center.alpha(), 0)
        self.assertGreater(center.red(), 200)
        self.assertLess(center.green(), 40)
        self.assertIs(image, resources.pattern_image("spark", "#ff0000", 64))

    def test_every_registered_glyph_renders(self):
        self.assertGreaterEqual(len(KEYCAP_ICON_ASSETS), 80)
        for asset in KEYCAP_ICON_ASSETS:
            pixmap = resources.glyph_pixmap(asset.icon_id, "#ffffff", 24)
            if asset.icon_id in {"auto", "none"}:
                self.assertIsNone(pixmap)
            else:
                self.assertIsNotNone(pixmap, asset.icon_id)
        self.assertEqual(keycap_icon_asset("missing").icon_id, "auto")

    def test_switch_sounds_resolve_to_bundled_wav_files(self):
        for switch_id, profile in SWITCH_PROFILES.items():
            press, _release = resources.key_sound_paths({"sound": "auto", "switch": switch_id})
            if profile.press_sound:
                self.assertTrue(press.endswith(".wav"), switch_id)
            else:
                self.assertEqual(press, "")
        self.assertEqual(resources.key_sound_paths({"sound": "none", "switch": "clicky"}), ("", ""))
        self.assertEqual(
            resources.key_sound_paths({"sound": "custom", "sound_path": "C:/missing.wav"}), ("", "")
        )

    def test_synthesized_switch_sound_set_is_complete_and_short(self):
        import wave

        for kind in resources.SWITCH_SOUND_KINDS:
            variants = resources.switch_sound_variants(kind)
            self.assertEqual(len(variants), 4, kind)
            for path in variants:
                with wave.open(path, "rb") as source:
                    self.assertEqual(
                        (source.getnchannels(), source.getsampwidth(), source.getframerate()),
                        (1, 2, 44_100),
                    )
                    duration = source.getnframes() / source.getframerate()
                    self.assertTrue(0.015 <= duration <= 0.1, (kind, duration))
        first = resources.pick_switch_sound("bottom_deep")
        self.assertNotEqual(first, resources.pick_switch_sound("bottom_deep"))

    def test_sound_tone_follows_keycap_material_and_case(self):
        crystal = {"cap": {"material": "crystal"}, "switch": "linear", "sound": "auto"}
        pbt = {"cap": {"material": "solid"}, "switch": "linear", "sound": "auto"}
        aluminum = {"case": {"style": "anodized"}}
        walnut = {"case": {"style": "walnut"}}
        self.assertEqual(resources.key_tone(crystal, aluminum), "bright")
        self.assertEqual(resources.key_tone(pbt, walnut), "deep")
        plan = resources.physical_sound_plan({**crystal, "switch": "clicky"}, aluminum)
        self.assertEqual(plan["click"][0], "click")
        self.assertEqual(plan["bottom"][0], "bottom_bright")
        self.assertEqual(
            resources.physical_sound_plan({**pbt, "switch": "silent"}, walnut),
            {"bottom": ("silent", 0.55)},
        )
        self.assertIsNone(resources.physical_sound_plan({**pbt, "sound": "pop"}, walnut))

    def test_source_images_are_decoded_once_and_capped(self):
        import tempfile

        from PyQt6.QtGui import QImage

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "huge.png")
            image = QImage(3000, 1500, QImage.Format.Format_ARGB32)
            image.fill(QColor("#336699"))
            image.save(path)
            decoded = resources.source_image(path)
            self.assertLessEqual(max(decoded.width(), decoded.height()), 1024)
            self.assertIs(decoded, resources.source_image(path))
            self.assertIsNone(resources.source_image(os.path.join(tmpdir, "missing.png")))

    def test_lru_cache_evicts_oldest(self):
        cache = resources.LruCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")
        cache.put("c", 3)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)


if __name__ == "__main__":
    unittest.main()
