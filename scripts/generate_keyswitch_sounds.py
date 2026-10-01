# -*- coding: utf-8 -*-
"""Synthesize the KeyDeck mechanical-switch sound set.

A real keystroke is not one click: the slider hits the housing floor (bottom-out),
the keycap and case resonate, and on release the stem snaps back against the top
housing (upstroke).  Clicky switches add a click-jacket tick at actuation and
tactile switches a faint leaf scrape.  Each sound is built from a noise transient
plus damped resonant modes, with several deterministic variants so consecutive
presses never sound identical.

    .venv\\Scripts\\python.exe scripts/generate_keyswitch_sounds.py
"""

from __future__ import annotations

import math
from pathlib import Path
import random
import struct
import wave

RATE = 44_100
VARIANTS = 4
PEAK = 0.62
OUT_DIR = Path(__file__).resolve().parents[1] / "Assets" / "keycaps" / "switch"

# freq Hz, decay ms, amplitude
Mode = tuple[float, float, float]

RECIPES: dict[str, dict] = {
    # 두꺼운 PBT·우드/아크릴 케이스: 낮고 둥근 "도각" (thock)
    "bottom_deep": {
        "ms": 85,
        "transient": (0.7, 1500.0, 0.55),
        "modes": [
            (190, 26, 1.0),
            (460, 15, 0.55),
            (1080, 8, 0.32),
            (2450, 3.5, 0.22),
            (4100, 1.8, 0.12),
        ],
        "glide": 0.10,
        "body": (900.0, 9.0, 0.25),
    },
    # PC 키캡·알루미늄 케이스: 밝고 짧은 "딸깍" (clack) + 케이스 공진
    "bottom_bright": {
        "ms": 70,
        "transient": (0.5, 2500.0, 0.7),
        "modes": [
            (380, 12, 0.65),
            (1250, 8, 0.8),
            (2800, 4.5, 0.55),
            (5300, 2.2, 0.35),
            (3150, 28, 0.06),
            (4700, 22, 0.04),
        ],
        "glide": 0.06,
        "body": (2500.0, 5.0, 0.2),
    },
    "top_deep": {
        "ms": 45,
        "transient": (0.4, 2000.0, 0.35),
        "modes": [(650, 6, 0.5), (1700, 4, 0.4), (3600, 2, 0.25)],
        "glide": 0.04,
        "body": (1400.0, 3.0, 0.12),
    },
    "top_bright": {
        "ms": 40,
        "transient": (0.35, 3000.0, 0.4),
        "modes": [(900, 5, 0.5), (2300, 3.2, 0.45), (4800, 1.6, 0.3), (3150, 14, 0.03)],
        "glide": 0.03,
        "body": (2800.0, 2.5, 0.1),
    },
    # 청축 클릭 재킷: 날카로운 틱 두 번 (눌림 → 재킷 복귀)
    "click": {
        "ms": 38,
        "transient": (0.25, 4000.0, 0.8),
        "modes": [(3600, 2.2, 0.6), (6100, 1.3, 0.4), (2200, 3.0, 0.15)],
        "glide": 0.0,
        "body": None,
        "echo": (3.8, 0.45),
    },
    # 갈축 택타일 리프 마찰: 아주 작은 긁힘
    "bump": {
        "ms": 24,
        "transient": None,
        "modes": [(1400, 3, 0.15)],
        "glide": 0.0,
        "body": None,
        "scrape": (1800.0, 4500.0, 2.0, 6.0, 0.3),
    },
    # 흑축 사일런트: 댐퍼에 먹힌 낮은 "툭"
    "silent": {
        "ms": 60,
        "transient": None,
        "modes": [(140, 20, 1.0), (330, 10, 0.45), (760, 5, 0.15)],
        "glide": 0.05,
        "body": (500.0, 8.0, 0.3),
    },
}


def _lowpass(samples: list[float], cutoff: float) -> list[float]:
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / RATE)
    out, state = [], 0.0
    for value in samples:
        state += alpha * (value - state)
        out.append(state)
    return out


def _highpass(samples: list[float], cutoff: float) -> list[float]:
    low = _lowpass(samples, cutoff)
    return [value - smooth for value, smooth in zip(samples, low, strict=True)]


def _noise(count: int, rng: random.Random) -> list[float]:
    return [rng.uniform(-1.0, 1.0) for _ in range(count)]


def _envelope(count: int, decay_ms: float, attack_ms: float = 0.0) -> list[float]:
    decay = max(1e-4, decay_ms / 1000.0)
    attack = max(1, int(attack_ms / 1000.0 * RATE))
    values = []
    for index in range(count):
        t = index / RATE
        rise = min(1.0, index / attack) if attack_ms else 1.0
        values.append(rise * math.exp(-t / decay))
    return values


def _synthesize(recipe: dict, rng: random.Random) -> list[float]:
    count = int(recipe["ms"] / 1000.0 * RATE)
    signal = [0.0] * count
    jitter_f = rng.uniform(0.96, 1.04)
    for freq, decay_ms, amp in recipe["modes"]:
        freq *= jitter_f * rng.uniform(0.985, 1.015)
        decay = decay_ms * rng.uniform(0.85, 1.15) / 1000.0
        amp *= rng.uniform(0.9, 1.1)
        phase = rng.uniform(0.0, 2 * math.pi)
        glide = recipe.get("glide", 0.0)
        acc = phase
        for index in range(count):
            t = index / RATE
            inst = freq * (1.0 + glide * math.exp(-t / 0.004))
            acc += 2 * math.pi * inst / RATE
            signal[index] += amp * math.exp(-t / decay) * math.sin(acc)
    transient = recipe.get("transient")
    if transient:
        decay_ms, hp_cut, amp = transient
        burst = _highpass(_noise(count, rng), hp_cut)
        env = _envelope(count, decay_ms * rng.uniform(0.8, 1.2))
        for index in range(count):
            signal[index] += amp * burst[index] * env[index]
    body = recipe.get("body")
    if body:
        lp_cut, decay_ms, amp = body
        thud = _lowpass(_noise(count, rng), lp_cut)
        env = _envelope(count, decay_ms * rng.uniform(0.85, 1.15), attack_ms=0.3)
        scale = 3.0  # 저역 통과 후 줄어든 진폭 보정
        for index in range(count):
            signal[index] += amp * scale * thud[index] * env[index]
    scrape = recipe.get("scrape")
    if scrape:
        hp_cut, lp_cut, attack_ms, decay_ms, amp = scrape
        band = _lowpass(_highpass(_noise(count, rng), hp_cut), lp_cut)
        env = _envelope(count, decay_ms, attack_ms=attack_ms)
        for index in range(count):
            signal[index] += amp * 2.5 * band[index] * env[index]
    echo = recipe.get("echo")
    if echo:
        delay_ms, gain = echo
        offset = int(delay_ms * rng.uniform(0.9, 1.1) / 1000.0 * RATE)
        original = list(signal)
        for index in range(offset, count):
            signal[index] += gain * original[index - offset]
    # 클릭 잡음 방지: 0.2ms 페이드인, 마지막 15% 페이드아웃
    fade_in = int(0.0002 * RATE)
    for index in range(min(fade_in, count)):
        signal[index] *= index / fade_in
    tail = int(count * 0.15)
    for index in range(tail):
        signal[count - tail + index] *= 1.0 - index / tail
    peak = max(abs(value) for value in signal) or 1.0
    return [value / peak * PEAK for value in signal]


def _write(path: Path, samples: list[float]) -> None:
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767)) for value in samples
    )
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(frames)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for kind_index, (kind, recipe) in enumerate(RECIPES.items()):
        for variant in range(VARIANTS):
            rng = random.Random(1000 * (kind_index + 1) + variant)
            _write(OUT_DIR / f"{kind}_{variant + 1}.wav", _synthesize(recipe, rng))
    print(f"wrote {len(RECIPES) * VARIANTS} switch sounds to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
