# -*- coding: utf-8 -*-
import unittest
import wave

from calendar_app.presentation.widgets.launcher_keycap_sounds import (
    KEYCAP_SOUNDS,
    keycap_sound,
)


class LauncherKeycapSoundTests(unittest.TestCase):
    def test_bundled_library_contains_twelve_valid_short_wav_files(self):
        self.assertEqual(len(KEYCAP_SOUNDS), 12)
        for sound in KEYCAP_SOUNDS:
            path = sound.path()
            self.assertTrue(path.is_file(), sound.sound_id)
            with wave.open(str(path), "rb") as source:
                self.assertEqual(source.getnchannels(), 1)
                self.assertEqual(source.getsampwidth(), 2)
                self.assertEqual(source.getframerate(), 44_100)
                duration = source.getnframes() / source.getframerate()
                self.assertGreaterEqual(duration, 0.04)
                self.assertLessEqual(duration, 0.35)

    def test_unknown_sound_returns_none(self):
        self.assertIsNone(keycap_sound("missing"))


if __name__ == "__main__":
    unittest.main()
