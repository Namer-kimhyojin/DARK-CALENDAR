# -*- coding: utf-8 -*-
"""Process-wide caches shared by every KeyDeck instance.

Images are decoded once (capped resolution), glyphs are rasterised once per
size/colour, and sounds are loaded once into a small playback pool.
"""

from __future__ import annotations

from collections import OrderedDict
import logging
import os
from pathlib import Path
import random

from PyQt6.QtCore import QFileInfo, QSize, Qt, QUrl
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QFileIconProvider

try:
    from PyQt6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - optional in minimal Qt installs
    QSoundEffect = None

from calendar_app.app_paths import get_resource_path
from calendar_app.presentation.widgets.keydeck.physics import switch_profile
from calendar_app.presentation.widgets.launcher_keycap_assets import keycap_asset
from calendar_app.presentation.widgets.launcher_keycap_icons import keycap_icon_asset
from calendar_app.presentation.widgets.launcher_keycap_sounds import keycap_sound
from calendar_app.shared.icon_map import ICON_MAPPING

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"})
ANIMATED_SUFFIXES = frozenset({".gif", ".webp"})
_MAX_SOURCE_PX = 1024
_MAX_PANORAMA_PX = 2048


class LruCache:
    """Tiny ordered LRU used for pixmaps and decoded images."""

    def __init__(self, capacity: int):
        self._capacity = max(1, int(capacity))
        self._data: OrderedDict = OrderedDict()

    def get(self, key):
        value = self._data.get(key)
        if value is not None:
            self._data.move_to_end(key)
        return value

    def put(self, key, value) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._capacity:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


def file_stamp(path: str) -> tuple[int, int] | None:
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


_SOURCES = LruCache(32)
_ANIMATED = LruCache(64)


def source_image(path: str, *, max_px: int = _MAX_SOURCE_PX) -> QImage | None:
    """Decode an image once (auto-rotated, capped) and reuse it until the file changes."""
    stamp = file_stamp(path)
    if stamp is None or Path(path).suffix.lower() not in IMAGE_SUFFIXES:
        return None
    cache_key = (path, max_px)
    cached = _SOURCES.get(cache_key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_px:
        reader.setScaledSize(size.scaled(max_px, max_px, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    _SOURCES.put(cache_key, (stamp, image))
    return image


def panorama_image(path: str) -> QImage | None:
    return source_image(path, max_px=_MAX_PANORAMA_PX)


def has_transparency(image: QImage | None) -> bool:
    """True when a picture has see-through areas (logos, cut-outs), sampled at 48×48."""
    if image is None or image.isNull() or not image.hasAlphaChannel():
        return False
    small = image.scaled(48, 48, Qt.AspectRatioMode.IgnoreAspectRatio)
    return any(
        small.pixelColor(x, y).alpha() < 250
        for y in range(small.height())
        for x in range(small.width())
    )


def is_animated(path: str) -> bool:
    if Path(path).suffix.lower() not in ANIMATED_SUFFIXES:
        return False
    stamp = file_stamp(path)
    if stamp is None:
        return False
    cached = _ANIMATED.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    reader = QImageReader(path)
    animated = bool(reader.supportsAnimation()) and reader.imageCount() != 1
    _ANIMATED.put(path, (stamp, animated))
    return animated


_PATTERNS = LruCache(96)


def pattern_image(pattern_id: str, tint: str, size: int) -> QImage | None:
    """Return a bundled line-art decal recoloured to ``tint`` at ``size`` px."""
    size = max(8, int(size))
    cache_key = (pattern_id, tint, size)
    cached = _PATTERNS.get(cache_key)
    if cached is not None:
        return cached
    asset = keycap_asset(pattern_id)
    if not asset.filename:
        return None
    source = source_image(str(asset.path()))
    if source is None:
        return None
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawImage(image.rect(), source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), QColor(tint))
    painter.end()
    _PATTERNS.put(cache_key, image)
    return image


_GLYPHS = LruCache(384)


def _qta_name(glyph_id: str) -> str:
    icon_key = keycap_icon_asset(glyph_id).icon_key
    if not icon_key:
        return ""
    entry = ICON_MAPPING.get(icon_key)
    if entry:
        return str(entry[0])
    return icon_key if "." in icon_key else ""


def glyph_pixmap(glyph_id: str, color: str, size: int, dpr: float = 1.0) -> QPixmap | None:
    """Rasterise a vector glyph once per id/colour/size/DPR."""
    size = max(6, int(size))
    cache_key = (glyph_id, color, size, round(dpr, 2))
    cached = _GLYPHS.get(cache_key)
    if cached is not None:
        return cached if not cached.isNull() else None
    name = _qta_name(glyph_id)
    pixmap = QPixmap()
    if name:
        try:
            import qtawesome as qta  # type: ignore[import]

            icon = qta.icon(name, color=QColor(color))
            physical = max(1, int(round(size * dpr)))
            pixmap = icon.pixmap(QSize(physical, physical))
            pixmap.setDevicePixelRatio(dpr)
        except Exception:  # pragma: no cover - qtawesome optional/font issues
            logger.debug("KeyDeck glyph %s could not be rendered", glyph_id, exc_info=True)
            pixmap = QPixmap()
    _GLYPHS.put(cache_key, pixmap)
    return pixmap if not pixmap.isNull() else None


_FILE_ICONS = LruCache(64)
_ICON_PROVIDER: QFileIconProvider | None = None


def file_icon_pixmap(path: str, size: int, dpr: float = 1.0) -> QPixmap | None:
    """System icon of an app/file target, cached per path and size."""
    if not path or file_stamp(path) is None:
        return None
    global _ICON_PROVIDER
    cache_key = (path, int(size), round(dpr, 2))
    cached = _FILE_ICONS.get(cache_key)
    if cached is not None:
        return cached if not cached.isNull() else None
    if _ICON_PROVIDER is None:
        _ICON_PROVIDER = QFileIconProvider()
    icon = _ICON_PROVIDER.icon(QFileInfo(path))
    physical = max(1, int(round(size * dpr)))
    pixmap = icon.pixmap(QSize(physical, physical))
    pixmap.setDevicePixelRatio(dpr)
    _FILE_ICONS.put(cache_key, pixmap)
    return pixmap if not pixmap.isNull() else None


def _bundled_sound_path(sound_id: str) -> str:
    sound = keycap_sound(sound_id)
    if sound is None:
        return ""
    path = sound.path()
    return str(path) if path.is_file() else ""


def key_sound_paths(key: dict) -> tuple[str, str]:
    """Resolve (press, release) WAV paths for a key's sound choice."""
    choice = str(key.get("sound", "auto") or "auto")
    if choice == "none":
        return ("", "")
    if choice == "custom":
        path = str(key.get("sound_path", "") or "")
        valid = path.lower().endswith(".wav") and file_stamp(path) is not None
        return (path if valid else "", "")
    if choice == "auto":
        profile = switch_profile(key.get("switch"))
        return (
            _bundled_sound_path(profile.press_sound) if profile.press_sound else "",
            _bundled_sound_path(profile.release_sound) if profile.release_sound else "",
        )
    return (_bundled_sound_path(choice), "")


SWITCH_SOUND_KINDS = (
    "bottom_deep",
    "bottom_bright",
    "top_deep",
    "top_bright",
    "click",
    "bump",
    "silent",
)
_SWITCH_SOUND_DIR = "Assets/keycaps/switch"
_SWITCH_VARIANTS: dict[str, list[str]] = {}
_LAST_VARIANT: dict[str, str] = {}
# 알루미늄 케이스와 PC(투명 계열) 키캡은 밝은 "딸깍", PBT·우드·아크릴은 낮은 "도각".
_CASE_TONE = {"anodized": 1.0, "silver": 1.0}
_MATERIAL_TONE = {"crystal": 1.0, "frosted": 1.0, "smoke": 1.0, "pudding": 0.5, "solid": -1.0}


def switch_sound_variants(kind: str) -> list[str]:
    """Synthesized variants of one switch sound (see scripts/generate_keyswitch_sounds.py)."""
    cached = _SWITCH_VARIANTS.get(kind)
    if cached is None:
        folder = Path(get_resource_path(_SWITCH_SOUND_DIR))
        cached = [str(path) for path in sorted(folder.glob(f"{kind}_*.wav"))]
        _SWITCH_VARIANTS[kind] = cached
    return cached


def pick_switch_sound(kind: str) -> str:
    """Random variant that differs from the previous one (real presses never sound identical)."""
    variants = switch_sound_variants(kind)
    if not variants:
        return ""
    last = _LAST_VARIANT.get(kind)
    choices = [path for path in variants if path != last] or variants
    chosen = random.choice(choices)
    _LAST_VARIANT[kind] = chosen
    return chosen


def key_tone(key: dict, deck: dict | None) -> str:
    style = str(((deck or {}).get("case") or {}).get("style", ""))
    material = str(key.get("cap", {}).get("material", ""))
    score = _CASE_TONE.get(style, 0.0) + _MATERIAL_TONE.get(material, 0.0)
    return "bright" if score >= 1.0 else "deep"


def physical_sound_plan(key: dict, deck: dict | None) -> dict[str, tuple[str, float]] | None:
    """Switch event → (sound kind, gain) for keys using the automatic switch sound."""
    if str(key.get("sound", "auto") or "auto") != "auto":
        return None
    switch = str(key.get("switch", "tactile"))
    if switch == "silent":
        return {"bottom": ("silent", 0.55)}
    tone = key_tone(key, deck)
    bottom, top = f"bottom_{tone}", f"top_{tone}"
    if switch == "clicky":
        return {
            "click": ("click", 0.85),
            "bottom": (bottom, 0.6),
            "click_up": ("click", 0.3),
            "top": (top, 0.45),
        }
    plan = {"bottom": (bottom, 1.0), "top": (top, 0.5)}
    if switch == "tactile":
        plan["bump"] = ("bump", 0.28)
        plan["bottom"] = (bottom, 0.95)
    return plan


class SoundBank:
    """Loads each WAV once and plays it from a small voice pool (overlapping taps)."""

    _VOICES = 2

    def __init__(self):
        self._pools: dict[str, list] = {}
        self._cursor: dict[str, int] = {}

    def _pool(self, path: str, voices: int | None = None) -> list:
        pool = self._pools.get(path)
        if pool is None:
            app = QApplication.instance()
            pool = []
            for _ in range(max(1, voices or self._VOICES)):
                effect = QSoundEffect(app)
                effect.setSource(QUrl.fromLocalFile(path))
                pool.append(effect)
            self._pools[path] = pool
        return pool

    def preload(self, paths, voices: int | None = None) -> None:
        if QSoundEffect is None or QApplication.instance() is None:
            return
        for path in paths:
            if path:
                self._pool(path, voices)

    def play(self, path: str, volume: float, voices: int | None = None) -> None:
        if not path or volume <= 0.0 or QSoundEffect is None or QApplication.instance() is None:
            return
        pool = self._pool(path, voices)
        index = self._cursor.get(path, 0)
        effect = pool[index % len(pool)]
        self._cursor[path] = index + 1
        effect.setVolume(max(0.0, min(1.0, volume)))
        effect.play()


_SOUND_BANK: SoundBank | None = None


def sound_bank() -> SoundBank:
    global _SOUND_BANK
    if _SOUND_BANK is None:
        _SOUND_BANK = SoundBank()
    return _SOUND_BANK


def clear_caches() -> None:
    for cache in (_SOURCES, _ANIMATED, _PATTERNS, _GLYPHS, _FILE_ICONS):
        cache.clear()


__all__ = [
    "ANIMATED_SUFFIXES",
    "IMAGE_SUFFIXES",
    "SWITCH_SOUND_KINDS",
    "LruCache",
    "SoundBank",
    "clear_caches",
    "file_icon_pixmap",
    "file_stamp",
    "glyph_pixmap",
    "is_animated",
    "key_sound_paths",
    "key_tone",
    "physical_sound_plan",
    "pick_switch_sound",
    "has_transparency",
    "panorama_image",
    "pattern_image",
    "sound_bank",
    "source_image",
    "switch_sound_variants",
]
