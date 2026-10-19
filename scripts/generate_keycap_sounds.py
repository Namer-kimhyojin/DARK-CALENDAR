# -*- coding: utf-8 -*-
"""Generate compact, royalty-free WAV feedback sounds for launcher keycaps."""

from __future__ import annotations

import math
from pathlib import Path
import random
import struct
import wave

SAMPLE_RATE = 44_100


def _tone(
    duration: float,
    start_hz: float,
    *,
    end_hz: float | None = None,
    gain: float = 0.5,
    attack: float = 0.004,
    decay_power: float = 2.4,
) -> list[float]:
    count = max(1, int(duration * SAMPLE_RATE))
    end_hz = start_hz if end_hz is None else end_hz
    phase = 0.0
    samples = []
    for index in range(count):
        progress = index / max(1, count - 1)
        frequency = start_hz + (end_hz - start_hz) * progress
        phase += math.tau * frequency / SAMPLE_RATE
        attack_gain = min(1.0, index / max(1.0, attack * SAMPLE_RATE))
        envelope = attack_gain * ((1.0 - progress) ** decay_power)
        samples.append(math.sin(phase) * envelope * gain)
    return samples


def _noise(duration: float, *, gain: float = 0.2, seed: int = 0) -> list[float]:
    count = max(1, int(duration * SAMPLE_RATE))
    rng = random.Random(seed)
    return [
        rng.uniform(-1.0, 1.0) * gain * ((1.0 - index / count) ** 3.2) for index in range(count)
    ]


def _soft_noise(duration: float, *, gain: float, cutoff_hz: float, seed: int) -> list[float]:
    """Low-pass an impact so the new material sounds have no harsh hiss."""
    count = max(1, int(duration * SAMPLE_RATE))
    rng = random.Random(seed)
    alpha = 1.0 - math.exp(-math.tau * cutoff_hz / SAMPLE_RATE)
    filtered = 0.0
    samples = []
    for index in range(count):
        filtered += alpha * (rng.uniform(-1.0, 1.0) - filtered)
        progress = index / max(1, count - 1)
        attack = min(1.0, index / (0.0015 * SAMPLE_RATE))
        samples.append(filtered * gain * attack * ((1.0 - progress) ** 3.0))
    return samples


def _mix(*tracks: tuple[list[float], float]) -> list[float]:
    length = max((int(offset * SAMPLE_RATE) + len(track) for track, offset in tracks), default=1)
    output = [0.0] * length
    for track, offset in tracks:
        start = int(offset * SAMPLE_RATE)
        for index, sample in enumerate(track):
            output[start + index] += sample
    peak = max((abs(sample) for sample in output), default=1.0)
    scale = 0.88 / max(0.88, peak)
    return [sample * scale for sample in output]


def _write(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767)) for sample in samples
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)


def _library() -> dict[str, list[float]]:
    return {
        "soft-click.wav": _mix(
            (_tone(0.075, 520, end_hz=340, gain=0.30), 0.0),
            (_noise(0.035, gain=0.11, seed=11), 0.0),
        ),
        "crisp-click.wav": _mix(
            (_tone(0.055, 2100, end_hz=1350, gain=0.28), 0.0),
            (_noise(0.025, gain=0.18, seed=21), 0.0),
        ),
        "mechanical.wav": _mix(
            (_tone(0.090, 260, end_hz=170, gain=0.45), 0.0),
            (_noise(0.028, gain=0.22, seed=31), 0.0),
            (_tone(0.035, 760, end_hz=430, gain=0.18), 0.035),
        ),
        "pop.wav": _mix((_tone(0.105, 540, end_hz=1080, gain=0.55), 0.0)),
        "glass.wav": _mix(
            (_tone(0.180, 1580, gain=0.33, decay_power=2.0), 0.0),
            (_tone(0.190, 2390, gain=0.22, decay_power=2.2), 0.0),
        ),
        "toggle-on.wav": _mix(
            (_tone(0.095, 520, end_hz=620, gain=0.42), 0.0),
            (_tone(0.115, 790, end_hz=920, gain=0.40), 0.065),
        ),
        "toggle-off.wav": _mix(
            (_tone(0.090, 820, end_hz=720, gain=0.40), 0.0),
            (_tone(0.120, 510, end_hz=390, gain=0.42), 0.060),
        ),
        "success.wav": _mix(
            (_tone(0.135, 660, gain=0.34), 0.0),
            (_tone(0.150, 880, gain=0.32), 0.070),
            (_tone(0.175, 1100, gain=0.30), 0.140),
        ),
        "error.wav": _mix(
            (_tone(0.150, 420, end_hz=360, gain=0.48), 0.0),
            (_tone(0.190, 285, end_hz=245, gain=0.50), 0.105),
        ),
        "whoosh.wav": _mix(
            (_noise(0.260, gain=0.26, seed=51), 0.0),
            (_tone(0.260, 260, end_hz=1250, gain=0.22, decay_power=1.2), 0.0),
        ),
        "chime.wav": _mix(
            (_tone(0.310, 880, gain=0.27, decay_power=1.7), 0.0),
            (_tone(0.320, 1320, gain=0.22, decay_power=1.8), 0.0),
            (_tone(0.330, 1760, gain=0.15, decay_power=1.9), 0.0),
        ),
        "pulse.wav": _mix(
            (_tone(0.120, 135, end_hz=95, gain=0.64, decay_power=2.0), 0.0),
            (_tone(0.065, 920, end_hz=520, gain=0.16), 0.0),
        ),
        "wood-tap.wav": _mix(
            (_tone(0.105, 430, end_hz=360, gain=0.42, decay_power=3.0), 0.0),
            (_tone(0.060, 1190, gain=0.14, decay_power=3.6), 0.0),
            (_soft_noise(0.040, gain=0.32, cutoff_hz=1700, seed=61), 0.0),
        ),
        "bamboo.wav": _mix(
            (_tone(0.130, 960, end_hz=870, gain=0.34, decay_power=3.0), 0.0),
            (_tone(0.085, 2240, gain=0.11, decay_power=3.8), 0.0),
            (_soft_noise(0.030, gain=0.22, cutoff_hz=2500, seed=62), 0.0),
        ),
        "deep-thock.wav": _mix(
            (_tone(0.145, 185, end_hz=112, gain=0.57, decay_power=2.8), 0.0),
            (_tone(0.055, 405, end_hz=280, gain=0.16), 0.0),
            (_soft_noise(0.050, gain=0.28, cutoff_hz=650, seed=63), 0.0),
        ),
        "felt-key.wav": _mix(
            (_tone(0.070, 290, end_hz=210, gain=0.32, decay_power=3.5), 0.0),
            (_soft_noise(0.055, gain=0.48, cutoff_hz=900, seed=64), 0.0),
        ),
        "typewriter.wav": _mix(
            (_tone(0.040, 1320, end_hz=720, gain=0.24, attack=0.001), 0.0),
            (_soft_noise(0.025, gain=0.36, cutoff_hz=4200, seed=65), 0.0),
            (_tone(0.055, 410, end_hz=250, gain=0.35, attack=0.0015), 0.025),
            (_tone(0.040, 1820, gain=0.08), 0.048),
        ),
        "ceramic.wav": _mix(
            (_tone(0.220, 1140, gain=0.31, decay_power=2.5), 0.0),
            (_tone(0.175, 1820, gain=0.19, decay_power=2.9), 0.0),
            (_tone(0.105, 3140, gain=0.06, decay_power=3.4), 0.0),
        ),
        "marimba.wav": _mix(
            (_tone(0.240, 523.25, gain=0.45, decay_power=2.0), 0.0),
            (_tone(0.100, 2093, gain=0.12, decay_power=3.5), 0.0),
            (_tone(0.050, 5232.5, gain=0.035, decay_power=4.0), 0.0),
        ),
        "water-drop.wav": _mix(
            (_tone(0.135, 1600, end_hz=480, gain=0.37, attack=0.005), 0.0),
            (_tone(0.100, 730, end_hz=590, gain=0.18, decay_power=2.0), 0.035),
        ),
        "digital-blip.wav": _mix(
            (_tone(0.085, 740, end_hz=1480, gain=0.38, decay_power=1.5), 0.0),
            (_tone(0.055, 1480, end_hz=2220, gain=0.10, decay_power=2.0), 0.0),
        ),
        "retro-beep.wav": _mix(
            (_tone(0.095, 659.25, gain=0.33, attack=0.003, decay_power=1.0), 0.0),
            (_tone(0.095, 1977.75, gain=0.10, attack=0.003, decay_power=1.0), 0.0),
            (_tone(0.095, 3296.25, gain=0.05, attack=0.003, decay_power=1.0), 0.0),
        ),
        "warm-pluck.wav": _mix(
            (_tone(0.280, 392, gain=0.38, decay_power=2.2), 0.0),
            (_tone(0.180, 784, gain=0.15, decay_power=2.7), 0.0),
            (_tone(0.100, 1176, gain=0.07, decay_power=3.2), 0.0),
        ),
        "double-tap.wav": _mix(
            (_tone(0.045, 680, end_hz=470, gain=0.34, attack=0.002), 0.0),
            (_soft_noise(0.020, gain=0.18, cutoff_hz=2200, seed=66), 0.0),
            (_tone(0.060, 510, end_hz=330, gain=0.30, attack=0.002), 0.055),
            (_soft_noise(0.025, gain=0.15, cutoff_hz=1600, seed=67), 0.055),
        ),
    }


def main() -> int:
    output_dir = Path("Assets/keycaps/sounds")
    for filename, samples in _library().items():
        _write(output_dir / filename, samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
