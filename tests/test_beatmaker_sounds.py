# -*- coding: utf-8 -*-
"""Verify the generated musical assets independently of audio hardware or settings."""

from array import array
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from scripts.generate_beatmaker_sounds import PEAK_LIMIT, SAMPLE_RATE, synthesize_sound, write_sound

from calendar_app.presentation.widgets.launcher_keycap_sounds import (
    BEATMAKER_SOUNDS,
    FEEDBACK_SOUNDS,
    KEYCAP_SOUNDS,
    keycap_sound,
)
from calendar_app.shared.beatmaker_sound_catalog import (
    BEATMAKER_DRUMS,
    BEATMAKER_KITS,
    BEATMAKER_NOTES,
)


class BeatmakerSoundTests(unittest.TestCase):
    def test_all_three_kits_have_sixteen_drums_and_sixteen_pentatonic_notes(self):
        self.assertEqual(len(BEATMAKER_KITS), 3)
        self.assertEqual(len(BEATMAKER_DRUMS), 16)
        self.assertEqual(len(BEATMAKER_NOTES), 16)
        self.assertEqual(len(FEEDBACK_SOUNDS), 24)
        self.assertEqual(len(BEATMAKER_SOUNDS), 96)
        self.assertEqual(len(KEYCAP_SOUNDS), 120)
        note_values = [midi for _voice, _label, midi in BEATMAKER_NOTES]
        self.assertEqual(note_values, sorted(set(note_values)))
        self.assertTrue(all(midi % 12 in {0, 2, 4, 7, 9} for midi in note_values))
        self.assertEqual((note_values[0], note_values[-1]), (48, 84))
        voices = {voice for voice, _label in BEATMAKER_DRUMS}
        voices.update(voice for voice, _label, _midi in BEATMAKER_NOTES)
        for kit, _label in BEATMAKER_KITS:
            for voice in voices:
                sound = keycap_sound(f"beat_{kit}_{voice}")
                self.assertIsNotNone(sound)
                self.assertEqual(sound.filename, f"beatmaker/{kit}-{voice}.wav")

    def test_every_asset_is_bounded_audible_and_faded_pcm16(self):
        digests = set()
        loudness = []
        for sound in BEATMAKER_SOUNDS:
            with self.subTest(sound=sound.sound_id):
                with wave.open(str(sound.path()), "rb") as source:
                    self.assertEqual(
                        (source.getnchannels(), source.getsampwidth(), source.getframerate()),
                        (1, 2, SAMPLE_RATE),
                    )
                    duration = source.getnframes() / SAMPLE_RATE
                    self.assertTrue(0.10 <= duration <= 1.30, duration)
                    pcm = source.readframes(source.getnframes())
                samples = array("h")
                samples.frombytes(pcm)
                if sys.byteorder != "little":
                    samples.byteswap()
                self.assertEqual((samples[0], samples[-1]), (0, 0))
                peak = max(abs(value) for value in samples)
                self.assertTrue(3000 < peak <= math.ceil(PEAK_LIMIT * 32767), peak)
                rms = math.sqrt(math.fsum(value * value for value in samples) / len(samples))
                self.assertTrue(0.07 <= rms / 32767 <= 0.141, rms / 32767)
                loudness.append(rms)
                digests.add(hashlib.sha256(pcm).digest())
        self.assertEqual(len(digests), 96)
        self.assertLess(max(loudness) / min(loudness), 2.0)

    def test_generator_exactly_reproduces_bundled_sound_bytes(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            for sound in BEATMAKER_SOUNDS:
                with self.subTest(sound=sound.sound_id):
                    kit, voice = Path(sound.filename).stem.split("-", 1)
                    path = Path(temporary_dir) / Path(sound.filename).name
                    write_sound(path, kit, voice)
                    self.assertEqual(path.read_bytes(), sound.path().read_bytes())

    def test_note_fundamental_tracks_the_declared_midi_pitch(self):
        for kit, _kit_label in BEATMAKER_KITS:
            for voice, _label, midi in BEATMAKER_NOTES:
                with self.subTest(kit=kit, voice=voice):
                    pcm = synthesize_sound(kit, voice)
                    samples = array("h")
                    samples.frombytes(pcm)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    frequency = 440 * 2 ** ((midi - 69) / 12)
                    # Count a settled section; the neon attack intentionally includes FM.
                    start, stop = int(0.12 * SAMPLE_RATE), int(0.32 * SAMPLE_RATE)
                    crossings = sum(
                        1
                        for index in range(start + 1, stop)
                        if samples[index - 1] < 0 <= samples[index]
                    )
                    measured = crossings / ((stop - start) / SAMPLE_RATE)
                    self.assertLess(abs(measured - frequency) / frequency, 0.035)

    def test_invalid_sound_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            synthesize_sound("unknown", "kick")
        with self.assertRaises(ValueError):
            synthesize_sound("lofi", "missing")


if __name__ == "__main__":
    unittest.main()
