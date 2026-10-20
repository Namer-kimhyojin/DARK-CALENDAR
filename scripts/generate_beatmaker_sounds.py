# -*- coding: utf-8 -*-
"""Synthesize the bundled beatmaker one-shots without recordings or dependencies.

Run from any directory: python scripts/generate_beatmaker_sounds.py
Every source is an oscillator or seeded noise; no third-party samples are used.
"""

from __future__ import annotations

import argparse
from array import array
import math
from pathlib import Path
import random
import sys
import wave

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calendar_app.shared.beatmaker_sound_catalog import (  # noqa: E402
    BEATMAKER_DRUMS,
    BEATMAKER_KITS,
    BEATMAKER_NOTES,
)

SAMPLE_RATE = 44_100
PEAK_LIMIT = 0.70
_DURATIONS = {
    "crash": 1.20,
    "ride": 0.80,
    "tambourine": 0.38,
    "fx": 0.58,
    "tom_low": 0.48,
    "tom_mid": 0.40,
    "tom_high": 0.34,
    "cowbell": 0.36,
    "closed_hat": 0.12,
    "open_hat": 0.50,
    "rim": 0.16,
    "shaker": 0.18,
    "kick": 0.48,
    "snare": 0.30,
    "clap": 0.28,
    "snap": 0.17,
}
_KIT_PITCH = {"lofi": 0.93, "neon": 1.03, "arcade": 1.12}
_NOTE_MIDI = {voice: midi for voice, _label, midi in BEATMAKER_NOTES}


def _filtered_noise(count: int, seed: int, *, low: float, high: float) -> list[float]:
    rng = random.Random(seed)
    low_alpha = 1.0 - math.exp(-math.tau * low / SAMPLE_RATE)
    high_alpha = 1.0 - math.exp(-math.tau * high / SAMPLE_RATE)
    slow = fast = 0.0
    output = []
    for _index in range(count):
        value = rng.uniform(-1.0, 1.0)
        slow += low_alpha * (value - slow)
        fast += high_alpha * (value - fast)
        output.append(fast - slow)
    return output


def _finish(samples: list[float]) -> bytes:
    """Remove DC, match RMS with bounded peaks, and fade both sample boundaries."""
    count = len(samples)
    dc = math.fsum(samples) / count
    attack = int(0.0015 * SAMPLE_RATE)
    release = int(0.012 * SAMPLE_RATE)
    samples = [
        (value - dc) * min(1.0, index / attack) * min(1.0, (count - 1 - index) / release)
        for index, value in enumerate(samples)
    ]
    rms = math.sqrt(math.fsum(value * value for value in samples) / count)
    scale = 0.15 / max(1e-9, rms)
    # A smooth saturator contains isolated noisy transients without hard clipping.
    samples = [math.tanh(value * scale * 1.2) / 1.2 for value in samples]
    rms = math.sqrt(math.fsum(value * value for value in samples) / count)
    peak = max(abs(value) for value in samples)
    scale = min(0.14 / max(1e-9, rms), PEAK_LIMIT / max(1e-9, peak))
    pcm = array("h", (round(value * scale * 32767) for value in samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def _drum(kit: str, voice: str) -> list[float]:
    count = int(_DURATIONS[voice] * SAMPLE_RATE)
    kit_index = next(index for index, item in enumerate(BEATMAKER_KITS) if item[0] == kit)
    voice_index = next(index for index, item in enumerate(BEATMAKER_DRUMS) if item[0] == voice)
    pitch = _KIT_PITCH[kit]
    noise = _filtered_noise(
        count,
        71_021 + kit_index * 1009 + voice_index * 53,
        low=250 if voice in {"snare", "clap", "fx"} else 1800,
        high=5200 if kit == "lofi" else 11_000,
    )
    output = []
    phase = 0.0
    for index in range(count):
        time = index / SAMPLE_RATE
        hiss = noise[index]
        if voice == "kick":
            frequency = pitch * (48 + (145 if kit == "neon" else 105) * math.exp(-time / 0.025))
            phase += math.tau * frequency / SAMPLE_RATE
            value = math.sin(phase) * math.exp(-time / 0.105)
            value += 0.14 * hiss * math.exp(-time / 0.008)
            if kit == "arcade":
                value += 0.14 * math.sin(phase * 3) * math.exp(-time / 0.055)
        elif voice in {"tom_low", "tom_mid", "tom_high"}:
            base = {"tom_low": 95, "tom_mid": 140, "tom_high": 205}[voice] * pitch
            phase += math.tau * base * (1 + 0.55 * math.exp(-time / 0.025)) / SAMPLE_RATE
            value = (math.sin(phase) + 0.18 * math.sin(phase * 1.51)) * math.exp(-time / 0.095)
            value += hiss * 0.12 * math.exp(-time / 0.018)
        elif voice == "snare":
            value = hiss * 1.6 * math.exp(-time / (0.055 if kit == "lofi" else 0.07))
            value += 0.42 * math.sin(math.tau * 185 * pitch * time) * math.exp(-time / 0.035)
        elif voice == "clap":
            burst = sum(
                math.exp(-(time - start) / 0.010) if time >= start else 0.0
                for start in (0.0, 0.012, 0.025)
            )
            value = hiss * (burst + 0.55 * math.exp(-max(0.0, time - 0.025) / 0.045))
        elif voice == "snap":
            value = 0.8 * hiss * math.exp(-time / 0.012)
            value += math.sin(math.tau * 1250 * pitch * time) * math.exp(-time / 0.009)
        elif voice in {"closed_hat", "open_hat", "crash", "ride", "tambourine"}:
            decay = {
                "closed_hat": 0.022,
                "open_hat": 0.11,
                "crash": 0.28,
                "ride": 0.20,
                "tambourine": 0.085,
            }[voice]
            metallic = (
                sum(
                    math.sin(math.tau * frequency * pitch * time)
                    for frequency in (3610, 4721, 5789, 7433)
                )
                / 4
            )
            noise_mix = 0.25 if voice == "ride" else 0.8
            value = (hiss * noise_mix + metallic * (1 - noise_mix)) * math.exp(-time / decay)
            if voice == "ride":
                value += 0.30 * math.sin(math.tau * 2080 * pitch * time) * math.exp(-time / 0.12)
            if voice == "tambourine":
                value *= 0.65 + 0.35 * math.cos(math.tau * 37 * time)
        elif voice == "cowbell":
            value = (
                math.sin(math.tau * 540 * pitch * time)
                + 0.65 * math.sin(math.tau * 810 * pitch * time)
                + 0.20 * math.sin(math.tau * 1620 * pitch * time)
            ) * math.exp(-time / 0.07)
        elif voice == "rim":
            value = (
                math.sin(math.tau * 790 * pitch * time)
                + 0.55 * math.sin(math.tau * 1740 * pitch * time)
                + hiss * 0.25
            ) * math.exp(-time / 0.015)
        elif voice == "shaker":
            value = hiss * math.exp(-time / 0.035) * (0.6 + 0.4 * math.cos(math.tau * 65 * time))
        else:  # Short falling sci-fi hit; each kit uses a different pitch/noise colour.
            frequency = (1700 * math.exp(-time / 0.13) + 140) * pitch
            phase += math.tau * frequency / SAMPLE_RATE
            value = (math.sin(phase) + hiss * 0.35) * math.exp(-time / 0.13)
        if kit == "lofi":
            value = math.tanh(value * 1.35) / 1.35
        elif kit == "arcade":
            # A modest sample-and-hold colour, followed by the common final fades.
            value = round(value * 31) / 31
        output.append(value)
    return output


def _melody(kit: str, midi: int) -> list[float]:
    frequency = 440.0 * 2 ** ((midi - 69) / 12)
    duration = {"lofi": 0.80, "neon": 0.68, "arcade": 0.48}[kit]
    count = int(duration * SAMPLE_RATE)
    output = []
    for index in range(count):
        time = index / SAMPLE_RATE
        phase = math.tau * frequency * time
        attack = min(1.0, time / 0.004)
        if kit == "lofi":
            value = math.sin(phase) * math.exp(-time / 0.21)
            value += 0.26 * math.sin(phase * 2) * math.exp(-time / 0.10)
            value += 0.08 * math.sin(phase * 3) * math.exp(-time / 0.045)
        elif kit == "neon":
            modulation = 1.1 * math.sin(phase * 2) * math.exp(-time / 0.06)
            value = math.sin(phase + modulation) * math.exp(-time / 0.16)
            value += 0.12 * math.sin(phase * 3) * math.exp(-time / 0.08)
        else:
            # Additive pulse avoids aliasing from discontinuous square-wave edges.
            value = sum(
                math.sin(phase * harmonic) / harmonic
                for harmonic in (1, 3, 5, 7, 9)
                if frequency * harmonic < SAMPLE_RATE * 0.45
            ) * math.exp(-time / 0.14)
        output.append(value * attack)
    return output


def synthesize_sound(kit: str, voice: str) -> bytes:
    """Return deterministic little-endian mono PCM16 at SAMPLE_RATE."""
    if kit not in _KIT_PITCH:
        raise ValueError(f"Unknown beatmaker kit: {kit}")
    if voice in _NOTE_MIDI:
        return _finish(_melody(kit, _NOTE_MIDI[voice]))
    if voice in _DURATIONS:
        return _finish(_drum(kit, voice))
    raise ValueError(f"Unknown beatmaker voice: {voice}")


def write_sound(path: Path, kit: str, voice: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(synthesize_sound(kit, voice))


def generate_library(output_dir: Path) -> int:
    voices = [voice for voice, _label in BEATMAKER_DRUMS]
    voices.extend(voice for voice, _label, _midi in BEATMAKER_NOTES)
    for kit, _label in BEATMAKER_KITS:
        for voice in voices:
            write_sound(output_dir / f"{kit}-{voice}.wav", kit, voice)
    return len(BEATMAKER_KITS) * len(voices)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "Assets/keycaps/sounds/beatmaker",
    )
    arguments = parser.parse_args()
    count = generate_library(arguments.output_dir)
    print(f"Generated {count} mono PCM16 beatmaker sounds at {SAMPLE_RATE} Hz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
