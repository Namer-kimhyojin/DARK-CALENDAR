# -*- coding: utf-8 -*-
"""Stable identities shared by beatmaker layouts and generated sound assets."""

BEATMAKER_KITS: tuple[tuple[str, str], ...] = (
    ("lofi", "로파이"),
    ("neon", "네온"),
    ("arcade", "아케이드"),
)

# Visual order: top row first, left to right; the kick stays at bottom left.
BEATMAKER_DRUMS: tuple[tuple[str, str], ...] = (
    ("crash", "크래시"),
    ("ride", "라이드"),
    ("tambourine", "탬버린"),
    ("fx", "효과음"),
    ("tom_low", "로우 탐"),
    ("tom_mid", "미드 탐"),
    ("tom_high", "하이 탐"),
    ("cowbell", "카우벨"),
    ("closed_hat", "닫힌 하이햇"),
    ("open_hat", "열린 하이햇"),
    ("rim", "림샷"),
    ("shaker", "셰이커"),
    ("kick", "킥"),
    ("snare", "스네어"),
    ("clap", "클랩"),
    ("snap", "핑거 스냅"),
)

# C major pentatonic, ascending pitch. Layouts place the low four on the bottom row.
BEATMAKER_NOTES: tuple[tuple[str, str, int], ...] = (
    ("note_c3", "C3", 48),
    ("note_d3", "D3", 50),
    ("note_e3", "E3", 52),
    ("note_g3", "G3", 55),
    ("note_a3", "A3", 57),
    ("note_c4", "C4", 60),
    ("note_d4", "D4", 62),
    ("note_e4", "E4", 64),
    ("note_g4", "G4", 67),
    ("note_a4", "A4", 69),
    ("note_c5", "C5", 72),
    ("note_d5", "D5", 74),
    ("note_e5", "E5", 76),
    ("note_g5", "G5", 79),
    ("note_a5", "A5", 81),
    ("note_c6", "C6", 84),
)

__all__ = ["BEATMAKER_DRUMS", "BEATMAKER_KITS", "BEATMAKER_NOTES"]
