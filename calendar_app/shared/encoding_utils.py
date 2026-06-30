"""Utilities for strict text decoding with controlled legacy fallbacks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

LEGACY_TEXT_ENCODINGS: tuple[str, ...] = ("utf-8", "cp949", "euc-kr")


@dataclass(frozen=True)
class DecodeResult:
    text: str
    encoding: str


def decode_legacy_bytes(
    raw: bytes, encodings: Iterable[str] = LEGACY_TEXT_ENCODINGS
) -> DecodeResult:
    """Decode bytes using the configured strict fallback chain."""
    for encoding in encodings:
        try:
            return DecodeResult(text=raw.decode(encoding, errors="strict"), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "unknown", raw, 0, len(raw), "unable to decode bytes with configured encodings"
    )


def read_text_with_legacy_fallback(path: str | Path) -> DecodeResult:
    """Read file bytes and decode with UTF-8-first strict fallback chain."""
    raw = Path(path).read_bytes()
    return decode_legacy_bytes(raw)
