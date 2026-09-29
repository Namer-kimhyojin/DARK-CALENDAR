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
    }


def main() -> int:
    output_dir = Path("Assets/keycaps/sounds")
    for filename, samples in _library().items():
        _write(output_dir / filename, samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
