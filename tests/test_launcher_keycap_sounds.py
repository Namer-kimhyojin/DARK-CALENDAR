# -*- coding: utf-8 -*-
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from scripts.generate_keycap_sounds import _library, _write

from calendar_app.presentation.widgets.launcher_keycap_sounds import (
    KEYCAP_SOUNDS,
    keycap_sound,
    keycap_sound_ids,
)


class LauncherKeycapSoundTests(unittest.TestCase):
    def test_bundled_library_contains_twenty_four_valid_short_wav_files(self):
        self.assertEqual(len(KEYCAP_SOUNDS), 24)
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
                pcm = source.readframes(source.getnframes())
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
            peak = max(abs(sample) for sample in samples)
            self.assertGreater(peak, 3000, sound.sound_id)
            self.assertLessEqual(peak, int(32767 * 0.88), sound.sound_id)
            self.assertGreater(sum(sample * sample for sample in samples) / len(samples), 100_000)

    def test_catalog_has_unique_ids_files_and_audible_samples(self):
        self.assertEqual(len(keycap_sound_ids()), len(KEYCAP_SOUNDS))
        self.assertEqual(len({sound.filename for sound in KEYCAP_SOUNDS}), len(KEYCAP_SOUNDS))
        digests = set()
        for sound in KEYCAP_SOUNDS:
            self.assertIs(keycap_sound(sound.sound_id), sound)
            digests.add(hashlib.sha256(sound.path().read_bytes()).digest())
        self.assertEqual(len(digests), len(KEYCAP_SOUNDS))

    def test_generator_reproduces_every_bundled_wav(self):
        generated = _library()
        self.assertEqual(set(generated), {sound.filename for sound in KEYCAP_SOUNDS})
        with tempfile.TemporaryDirectory() as temporary_dir:
            for sound in KEYCAP_SOUNDS:
                path = Path(temporary_dir) / sound.filename
                _write(path, generated[sound.filename])
                self.assertEqual(path.read_bytes(), sound.path().read_bytes(), sound.sound_id)

    def test_unknown_sound_returns_none(self):
        self.assertIsNone(keycap_sound("missing"))


if __name__ == "__main__":
    unittest.main()
