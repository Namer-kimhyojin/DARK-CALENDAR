# -*- coding: utf-8 -*-
"""What the desktop wallpaper looks like behind a window.

The main window is translucent, so its text is read against the panel color
mixed with whatever wallpaper sits underneath. This module finds the current
wallpaper (Windows only), maps the window onto it the way Windows draws it, and
reports the brightest (or darkest) color in that area.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import sys

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage

logger = logging.getLogger(__name__)

_SPI_GETDESKWALLPAPER = 0x0073
# Measuring a thumbnail is plenty for "how bright is it here" and keeps a
# refresh well under a millisecond once the image is loaded.
_SAMPLE_WIDTH = 160
# The 90th percentile, not the maximum: a few bright specks (snow, stars)
# should not make the panel opaque, a bright sky behind text should.
_PERCENTILE = 0.90
# At most this many samples per side of the window's area are measured.
_REGION_SAMPLES = 48

# HKCU\Control Panel\Desktop WallpaperStyle values.
_STYLE_CENTER = "0"
_STYLE_STRETCH = "2"
_STYLE_FIT = "6"
_STYLE_FILL = "10"
_STYLE_SPAN = "22"


@dataclass(frozen=True)
class WallpaperInfo:
    path: str
    mtime: float
    style: str
    tile: bool
    solid: str  # "#rrggbb" behind (or instead of) the picture

    @property
    def signature(self) -> tuple:
        return (self.path, self.mtime, self.style, self.tile, self.solid)


def _read_desktop_value(name: str, default: str = "") -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return default


def _read_solid_color() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Colors") as key:
            parts = str(winreg.QueryValueEx(key, "Background")[0]).split()
        r, g, b = (max(0, min(255, int(p))) for p in parts[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    except (OSError, ValueError):
        return "#000000"


def _spi_wallpaper_path() -> str:
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.user32.SystemParametersInfoW(_SPI_GETDESKWALLPAPER, len(buf), buf, 0):
            return buf.value
    except Exception:
        logger.debug("SystemParametersInfoW(SPI_GETDESKWALLPAPER) failed", exc_info=True)
    return ""


def current_wallpaper() -> WallpaperInfo | None:
    """The wallpaper Windows is showing now, or None off Windows."""
    if sys.platform != "win32":
        return None
    path = _spi_wallpaper_path()
    if not path or not os.path.isfile(path):
        # Slideshows and Spotlight leave the shown picture here.
        appdata = os.environ.get("APPDATA", "")
        transcoded = os.path.join(appdata, "Microsoft", "Windows", "Themes", "TranscodedWallpaper")
        path = transcoded if path and os.path.isfile(transcoded) else ""
    try:
        mtime = os.path.getmtime(path) if path else 0.0
    except OSError:
        path, mtime = "", 0.0
    return WallpaperInfo(
        path=path,
        mtime=mtime,
        style=_read_desktop_value("WallpaperStyle", _STYLE_FILL).strip() or _STYLE_FILL,
        tile=_read_desktop_value("TileWallpaper", "0").strip() == "1",
        solid=_read_solid_color(),
    )


_THUMB_CACHE: dict[tuple, tuple[QImage, int, int]] = {}


def _thumbnail(info: WallpaperInfo) -> tuple[QImage, int, int] | None:
    """The wallpaper scaled down, with the original size; cached per file version."""
    key = (info.path, info.mtime)
    cached = _THUMB_CACHE.get(key)
    if cached is not None:
        return cached
    image = QImage(info.path)
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return None
    width, height = image.width(), image.height()
    if width > _SAMPLE_WIDTH:
        image = image.scaledToWidth(_SAMPLE_WIDTH, Qt.TransformationMode.SmoothTransformation)
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    _THUMB_CACHE.clear()
    _THUMB_CACHE[key] = (image, width, height)
    return _THUMB_CACHE[key]


def _image_region(style: str, tile: bool, window: QRect, screen: QRect, iw: int, ih: int):
    """The part of the original image (x0, y0, x1, y1) drawn under ``window``."""
    sw, sh = max(1, screen.width()), max(1, screen.height())
    wx0, wy0 = window.left() - screen.left(), window.top() - screen.top()
    wx1, wy1 = wx0 + window.width(), wy0 + window.height()
    if tile or style == _STYLE_SPAN:
        return 0.0, 0.0, float(iw), float(ih)
    if style == _STYLE_STRETCH:
        sx, sy = iw / sw, ih / sh
        return wx0 * sx, wy0 * sy, wx1 * sx, wy1 * sy
    if style == _STYLE_CENTER:
        scale = 1.0
    elif style == _STYLE_FIT:
        scale = min(sw / iw, sh / ih)
    else:  # Fill, and anything unknown
        scale = max(sw / iw, sh / ih)
    offx, offy = (sw - iw * scale) / 2.0, (sh - ih * scale) / 2.0
    return (
        (wx0 - offx) / scale,
        (wy0 - offy) / scale,
        (wx1 - offx) / scale,
        (wy1 - offy) / scale,
    )


def _relative_luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def sample_backdrop(
    info: WallpaperInfo, window: QRect, screen: QRect, *, brightest: bool
) -> QColor | None:
    """The bright (or dark) end of the wallpaper behind ``window``.

    ``brightest`` is what light text has to stand out against; dark text needs
    the dark end. None when the wallpaper cannot be read.
    """
    solid = QColor(info.solid)
    if not info.path:
        return solid
    thumb = _thumbnail(info)
    if thumb is None:
        return None
    image, iw, ih = thumb
    x0, y0, x1, y1 = _image_region(info.style, info.tile, window, screen, iw, ih)
    colors: list[QColor] = []
    # Parts of the window outside the picture (Fit, Center) show the solid color.
    if x0 < 0 or y0 < 0 or x1 > iw or y1 > ih:
        colors.append(solid)
    fx, fy = image.width() / iw, image.height() / ih
    left = max(0, min(image.width() - 1, int(x0 * fx)))
    right = max(left + 1, min(image.width(), int(round(x1 * fx))))
    top = max(0, min(image.height() - 1, int(y0 * fy)))
    bottom = max(top + 1, min(image.height(), int(round(y1 * fy))))
    region = image.copy(left, top, right - left, bottom - top)
    if region.width() > _REGION_SAMPLES or region.height() > _REGION_SAMPLES:
        region = region.scaled(
            min(region.width(), _REGION_SAMPLES),
            min(region.height(), _REGION_SAMPLES),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    for y in range(region.height()):
        for x in range(region.width()):
            colors.append(region.pixelColor(x, y))
    if not colors:
        return solid
    colors.sort(key=_relative_luminance)
    fraction = _PERCENTILE if brightest else 1.0 - _PERCENTILE
    return colors[min(len(colors) - 1, int(fraction * (len(colors) - 1) + 0.5))]
