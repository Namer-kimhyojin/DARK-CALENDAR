# -*- coding: utf-8 -*-
"""Sound defaults, individual overrides, explicit auditions and packaged fallback."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.widgets.keydeck import layout_library as library
from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck import resources
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.keydeck.physics import EVENT_CLICK
from calendar_app.presentation.widgets.launcher_keycap_sounds import keycap_sound


class KeyDeckSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.bank = Mock()
        patcher = patch(
            "calendar_app.presentation.widgets.keydeck.canvas.sound_bank", return_value=self.bank
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.deck = m.build_template_deck("macro_3x3")
        self.key = self.deck["pages"][0]["keys"][0]
        self.canvas = KeyDeckCanvas()
        self.canvas.set_deck(self.deck)
        self.addCleanup(self.canvas.deleteLater)
        self.addCleanup(self.canvas.close)

    def test_legacy_defaults_and_new_sound_settings_round_trip(self):
        old = m.normalize_deck({"pages": self.deck["pages"]})
        self.assertEqual((old["sound"], old["sound_path"]), ("auto", ""))
        self.deck.update(sound="custom", sound_path="C:/audio/key.wav", sound_volume=37)
        saved = m.deck_from_json(m.deck_to_json(self.deck))
        self.assertEqual(saved["sound"], "custom")
        self.assertEqual(saved["sound_path"], "C:/audio/key.wav")
        self.assertEqual(saved["sound_volume"], 37)
        self.assertEqual(m.normalize_deck({"sound": "switch"})["sound"], "auto")

    def test_global_default_applies_to_inheriting_keys_across_pages(self):
        self.deck["sound"] = "glass"
        self.canvas.refresh()
        runtime = self.canvas._runtime[self.key["id"]]
        self.assertEqual(Path(runtime.press_path).name, "glass.wav")
        self.assertIsNone(runtime.plan)
        self.deck["pages"].append(m.new_page("second"))
        second = m.default_key()
        self.deck["pages"][1]["keys"] = [second]
        self.deck["page"] = 1
        self.canvas.set_deck(self.deck)
        self.assertEqual(Path(self.canvas._runtime[second["id"]].press_path).name, "glass.wav")

    def test_individual_choice_and_silence_override_global_default(self):
        self.deck["sound"] = "glass"
        self.key["sound"] = "pop"
        self.assertEqual(Path(resources.key_sound_paths(self.key, self.deck)[0]).name, "pop.wav")
        self.key["sound"] = "none"
        self.assertEqual(resources.key_sound_paths(self.key, self.deck), ("", ""))
        self.assertIsNone(resources.physical_sound_plan(self.key, self.deck))
        self.key["sound"] = "switch"
        self.assertIsNotNone(resources.physical_sound_plan(self.key, self.deck))
        self.deck["sound"] = "none"
        self.assertIsNotNone(resources.physical_sound_plan(self.key, self.deck))
        self.key["sound"] = "auto"
        self.assertEqual(resources.key_sound_paths(self.key, self.deck), ("", ""))

    def test_clicky_switch_plays_chosen_sound_immediately_and_only_once(self):
        self.key.update(sound="pop", switch="clicky")
        self.canvas.refresh()
        runtime = self.canvas._runtime[self.key["id"]]
        self.canvas._press_runtime(self.key, runtime, None)
        self.assertEqual(self.bank.play.call_count, 1)
        self.assertEqual(Path(self.bank.play.call_args.args[0]).name, "pop.wav")
        self.canvas._emit_switch_sound(runtime, EVENT_CLICK)
        self.assertEqual(self.bank.play.call_count, 1)

    def test_hidden_inactive_canvas_can_audition_physical_sound(self):
        self.deck.update(sound_enabled=False, sound_volume=0)
        self.canvas.set_runtime_active(False)
        self.canvas.press_visual(self.key["id"], force_sound=True)
        QTest.qWait(210)
        self.assertGreater(self.bank.play.call_count, 0)
        self.assertTrue(
            any("bottom_" in Path(c.args[0]).name for c in self.bank.play.call_args_list)
        )
        self.assertFalse(self.canvas._timer.isActive())
        self.assertFalse(self.canvas._sound_preview_timer.isActive())

    def test_global_preview_ignores_selection_and_does_not_unmute_live_keys(self):
        self.deck.update(sound="glass", sound_enabled=False, sound_volume=0)
        self.key["sound"] = "pop"
        self.canvas.refresh()
        self.canvas.preview_deck_sound()
        self.assertEqual(Path(self.bank.play.call_args.args[0]).name, "glass.wav")
        self.assertEqual(self.bank.play.call_args.args[1], 0.25)
        count = self.bank.play.call_count
        self.canvas._play(str(keycap_sound("pop").path()))
        self.assertEqual(self.bank.play.call_count, count)
        self.assertFalse(self.deck["sound_enabled"])
        self.assertEqual(self.deck["sound_volume"], 0)

    def test_custom_global_wav_is_embedded_and_restored_with_deck(self):
        with tempfile.TemporaryDirectory() as folder:
            self.deck.update(sound="custom", sound_path=str(keycap_sound("pop").path()))
            doc, skipped = library.build_document(self.deck, kind="deck", name="sound")
            self.assertEqual(skipped, [])
            self.assertTrue(doc["deck"]["sound_path"].startswith(library.ASSET_PREFIX))
            parsed = library.parse_document(json.dumps(doc).encode("utf-8", errors="strict"))
            restored = library.materialize(parsed, asset_root=Path(folder))["deck"]
            self.assertEqual(restored["sound"], "custom")
            self.assertTrue(Path(restored["sound_path"]).is_file())
            self.assertEqual(
                Path(restored["sound_path"]).read_bytes(), keycap_sound("pop").path().read_bytes()
            )

    def test_packaged_build_without_qt_multimedia_uses_native_backend(self):
        with (
            patch.object(resources, "QSoundEffect", None),
            patch.object(resources, "NativeSoundBank") as native,
        ):
            bank = resources.SoundBank()
            path = str(keycap_sound("pop").path())
            bank.preload([path], voices=1)
            bank.play(path, 0.42, voices=1)
            native.assert_called_once_with()
            native.return_value.preload.assert_called_once_with([path], voices=1)
            native.return_value.play.assert_called_once_with(path, 0.42, voices=1)

    def test_shared_page_keeps_effective_sound_without_changing_receivers_default(self):
        with tempfile.TemporaryDirectory() as folder:
            self.deck.update(sound="custom", sound_path=str(keycap_sound("glass").path()))
            self.key["sound"] = "pop"
            doc, skipped = library.build_document(self.deck, kind="page", name="sound page")
            self.assertEqual(skipped, [])
            self.assertEqual(doc["page"]["keys"][0]["sound"], "pop")
            inherited = doc["page"]["keys"][1]
            self.assertEqual(inherited["sound"], "custom")
            self.assertTrue(inherited["sound_path"].startswith(library.ASSET_PREFIX))
            content = library.materialize(doc, asset_root=Path(folder))
            receiver = m.build_template_deck("macro_3x3")
            receiver["sound"] = "chime"
            result = library.apply_content(receiver, content)
            self.assertEqual(result["sound"], "chime")
            imported = result["pages"][0]["keys"][1]
            self.assertEqual(
                Path(resources.key_sound_paths(imported, result)[0]).read_bytes(),
                keycap_sound("glass").path().read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
