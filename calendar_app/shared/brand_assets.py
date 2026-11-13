# -*- coding: utf-8 -*-
"""Render the shared feather mark in the active UI accent without writing files."""

from functools import lru_cache
import math
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap

from calendar_app.app_paths import APP_ICON_TOAST_PATH, get_resource_path
from calendar_app.shared.color_utils import composite_color, contrast_safe_color, parse_css_color


def _source_mark_path() -> str:
    feather = Path(get_resource_path("Assets/brand_feather.png"))
    return str(feather if feather.is_file() else APP_ICON_TOAST_PATH)


@lru_cache(maxsize=96)
def _render_brand_mark(
    source_path: str, modified: int, color: str, width: int, height: int, dpr: float
) -> QPixmap:
    del modified  # The source mtime is part of the cache key, not a rendering input.
    source = QPixmap(source_path)
    if source.isNull():
        return source
    physical = QSize(max(1, round(width * dpr)), max(1, round(height * dpr)))
    source = source.scaled(
        physical, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    mark = QPixmap(physical)
    mark.fill(Qt.GlobalColor.transparent)
    painter = QPainter(mark)
    try:
        painter.drawPixmap(
            (physical.width() - source.width()) // 2,
            (physical.height() - source.height()) // 2,
            source,
        )
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(mark.rect(), QColor(color))
    finally:
        painter.end()
    mark.setDevicePixelRatio(dpr)
    return mark


def brand_mark_pixmap(
    accent: str | QColor,
    size: int | QSize = 32,
    *,
    background: str | QColor | None = None,
    base: str | QColor = "#121827",
    dpr: float = 1.0,
) -> QPixmap:
    """Keep the feather alpha while tinting it for the current reading surface."""
    color = parse_css_color(accent).name(QColor.NameFormat.HexRgb)
    if background is not None:
        surface = composite_color(background, base)
        color = contrast_safe_color(color, surface, minimum=3.0)
    if isinstance(size, QSize):
        width, height = size.width(), size.height()
    else:
        width = height = int(size)
    width, height = max(1, min(512, width)), max(1, min(512, height))
    dpr = float(dpr)
    dpr = max(1.0, min(4.0, dpr)) if math.isfinite(dpr) else 1.0
    source = _source_mark_path()
    try:
        modified = Path(source).stat().st_mtime_ns
    except OSError:
        modified = 0
    return _render_brand_mark(source, modified, color, width, height, dpr)


def clear_brand_mark_cache() -> None:
    _render_brand_mark.cache_clear()
