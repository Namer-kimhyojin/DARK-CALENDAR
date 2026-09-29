# -*- coding: utf-8 -*-
"""Bundled decorative illustration packs for date and D-Day widgets."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import functools

from PyQt6.QtCore import QBuffer, QIODevice, QRect, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap

from calendar_app.app_paths import get_resource_path


@dataclass(frozen=True, slots=True)
class MomentAssetPack:
    pack_id: str
    label_key: str
    label_default: str
    filename: str | None


DEFAULT_MOMENT_ASSET_PACK_ID = "air_moments"

_PACKS = (
    MomentAssetPack(
        "air_moments",
        "widget.moment_pack.air_moments",
        "Air Moments · Soft 3D",
        "air-moments-sprites.png",
    ),
    MomentAssetPack(
        "paper_seasons",
        "widget.moment_pack.paper_seasons",
        "Paper Seasons · Layered paper",
        "paper-seasons-sprites.png",
    ),
    MomentAssetPack(
        "none",
        "widget.moment_pack.none",
        "None · Text only",
        None,
    ),
)
_PACK_BY_ID = {pack.pack_id: pack for pack in _PACKS}

# 4 x 4 sprite sheets. The final two cells are intentionally empty.
_MOMENT_TO_CELL = {
    "spring": 0,
    "summer": 1,
    "autumn": 2,
    "winter": 3,
    "birthday": 4,
    "anniversary": 5,
    "deadline": 6,
    "launch": 7,
    "travel": 8,
    "study": 9,
    "health": 10,
    "celebration": 11,
    "calm": 12,
    "sparkle": 13,
}


def moment_asset_packs() -> tuple[MomentAssetPack, ...]:
    return _PACKS


def get_moment_asset_pack(pack_id: object) -> MomentAssetPack:
    normalized = str(pack_id or "").strip().lower()
    return _PACK_BY_ID.get(normalized, _PACK_BY_ID[DEFAULT_MOMENT_ASSET_PACK_ID])


def season_moment_id(month: int) -> str:
    month = max(1, min(int(month), 12))
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "autumn"
    return "winter"


@functools.lru_cache(maxsize=len(_PACKS))
def _load_sprite(pack_id: str) -> QPixmap:
    pack = get_moment_asset_pack(pack_id)
    if not pack.filename:
        return QPixmap()
    return QPixmap(get_resource_path("moments", pack.filename))


def _sprite_cell(pack_id: str, moment_id: str) -> QPixmap:
    sprite = _load_sprite(pack_id)
    if sprite.isNull():
        return QPixmap()
    index = _MOMENT_TO_CELL.get(str(moment_id), _MOMENT_TO_CELL["sparkle"])
    row, column = divmod(index, 4)
    left = round(column * sprite.width() / 4)
    right = round((column + 1) * sprite.width() / 4)
    top = round(row * sprite.height() / 4)
    bottom = round((row + 1) * sprite.height() / 4)
    return sprite.copy(QRect(left, top, right - left, bottom - top))


def moment_asset_pixmap(pack_id: object, moment_id: str, size: int) -> QPixmap:
    pack = get_moment_asset_pack(pack_id)
    if not pack.filename:
        return QPixmap()
    target_size = max(16, min(int(size), 320))
    cell = _sprite_cell(pack.pack_id, moment_id)
    if cell.isNull():
        return QPixmap()
    scaled = cell.scaled(
        QSize(target_size, target_size),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QPixmap(target_size, target_size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(
        (target_size - scaled.width()) // 2,
        (target_size - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas


def moment_asset_html(pack_id: object, moment_id: str, size: int) -> str:
    pixmap = moment_asset_pixmap(pack_id, moment_id, size)
    if pixmap.isNull():
        return ""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        buffer.close()
        return ""
    png_b64 = base64.b64encode(bytes(buffer.data())).decode("utf-8", errors="strict")
    buffer.close()
    rendered_size = max(16, min(int(size), 320))
    return (
        f'<img src="data:image/png;base64,{png_b64}" '
        f'width="{rendered_size}" height="{rendered_size}" />'
    )


def moment_pack_preview_pixmap(pack_id: object, size: QSize) -> QPixmap:
    canvas = QPixmap(size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    samples = ("spring", "summer", "autumn", "winter")
    tile_size = min(72, max(38, size.height() - 18))
    gap = max(3, (size.width() - tile_size * len(samples)) // (len(samples) + 1))
    x = gap
    for moment_id in samples:
        pixmap = moment_asset_pixmap(pack_id, moment_id, tile_size)
        painter.drawPixmap(x, (size.height() - pixmap.height()) // 2, pixmap)
        x += tile_size + gap
    painter.end()
    return canvas


def moment_pack_icon(pack_id: object) -> QIcon:
    return QIcon(moment_asset_pixmap(pack_id, "celebration", 48))


__all__ = [
    "DEFAULT_MOMENT_ASSET_PACK_ID",
    "MomentAssetPack",
    "get_moment_asset_pack",
    "moment_asset_html",
    "moment_asset_packs",
    "moment_asset_pixmap",
    "moment_pack_icon",
    "moment_pack_preview_pixmap",
    "season_moment_id",
]
