from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from PyQt6.QtGui import QColor

_FALLBACK_EVENT_PALETTE = [
    {"id": "1", "name": "Lavender", "hex": "#a4bdfc"},
    {"id": "2", "name": "Sage", "hex": "#7ae7bf"},
    {"id": "3", "name": "Grape", "hex": "#dbadff"},
    {"id": "4", "name": "Flamingo", "hex": "#ff887c"},
    {"id": "5", "name": "Banana", "hex": "#fbd75b"},
    {"id": "6", "name": "Tangerine", "hex": "#ffb878"},
    {"id": "7", "name": "Peacock", "hex": "#46d6db"},
    {"id": "8", "name": "Graphite", "hex": "#e1e1e1"},
    {"id": "9", "name": "Blueberry", "hex": "#5484ed"},
    {"id": "10", "name": "Basil", "hex": "#51b749"},
    {"id": "11", "name": "Tomato", "hex": "#dc2127"},
]


def _normalize_hex(value: str | None) -> str | None:
    color = QColor(str(value or ""))
    if not color.isValid():
        return None
    return color.name().lower()


@lru_cache(maxsize=1)
def _fallback_palette() -> tuple:
    return tuple(
        (entry["id"], entry["name"], entry["hex"].lower()) for entry in _FALLBACK_EVENT_PALETTE
    )


def get_google_event_palette(sync_service=None) -> list[dict]:
    # Use a fixed Google event palette to avoid runtime API fetches while the user
    # is creating/editing items repeatedly.
    return [
        {"id": color_id, "name": name, "hex": hex_color}
        for color_id, name, hex_color in _fallback_palette()
    ]


def color_id_to_hex(color_id: str | None, sync_service=None) -> str | None:
    if not color_id:
        return None
    for entry in get_google_event_palette(sync_service):
        if str(entry["id"]) == str(color_id):
            return entry["hex"]
    return None


def hex_to_color_id(color_hex: str | None, sync_service=None) -> str | None:
    normalized = _normalize_hex(color_hex)
    if not normalized:
        return None

    palette = get_google_event_palette(sync_service)
    direct = next((entry["id"] for entry in palette if entry["hex"] == normalized), None)
    if direct:
        return direct

    src = QColor(normalized)
    best_id = None
    best_dist = None
    for entry in palette:
        target = QColor(entry["hex"])
        dist = (
            (src.red() - target.red()) ** 2
            + (src.green() - target.green()) ** 2
            + (src.blue() - target.blue()) ** 2
        )
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_id = entry["id"]
    return best_id


def palette_hexes(sync_service=None) -> list[str]:
    return [entry["hex"] for entry in get_google_event_palette(sync_service)]


def ordered_palette_from_theme(theme_color: str | None, sync_service=None) -> list[str]:
    palette = get_google_event_palette(sync_service)
    theme = QColor(str(theme_color or ""))
    if not theme.isValid():
        return [entry["hex"] for entry in palette]

    def _dist(entry):
        color = QColor(entry["hex"])
        return (
            (theme.red() - color.red()) ** 2
            + (theme.green() - color.green()) ** 2
            + (theme.blue() - color.blue()) ** 2
        )

    return [entry["hex"] for entry in sorted(palette, key=_dist)]


def is_google_palette_color(color_hex: str | None, sync_service=None) -> bool:
    normalized = _normalize_hex(color_hex)
    if not normalized:
        return False
    return normalized in set(palette_hexes(sync_service))


def dedupe_palette_sequence(colors: Iterable[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for color in colors:
        normalized = _normalize_hex(color)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out
