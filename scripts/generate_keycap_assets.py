# -*- coding: utf-8 -*-
"""Generate bundled transparent PNG decals used by launcher keycaps."""

from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication

SIZE = 128
INK = QColor(255, 255, 255, 178)
SOFT = QColor(255, 255, 255, 92)


def _canvas() -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pixmap, painter


def _save(name: str, draw) -> None:
    pixmap, painter = _canvas()
    draw(painter)
    painter.end()
    output = Path("Assets/keycaps")
    output.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(output / f"{name}.png"), "PNG"):
        raise RuntimeError(f"Failed to save keycap asset: {name}")


def _spark(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(64, 17, 64, 111)
    painter.drawLine(17, 64, 111, 64)
    painter.drawLine(35, 35, 93, 93)
    painter.drawLine(93, 35, 35, 93)
    painter.setBrush(QColor(255, 255, 255, 45))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(64, 64), 25, 25)


def _orbit(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 4))
    painter.drawEllipse(QRectF(18, 43, 92, 42))
    painter.save()
    painter.translate(64, 64)
    painter.rotate(58)
    painter.translate(-64, -64)
    painter.drawEllipse(QRectF(18, 43, 92, 42))
    painter.restore()
    painter.setBrush(INK)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(64, 64), 8, 8)
    painter.drawEllipse(QPointF(105, 54), 5, 5)


def _grid(painter: QPainter) -> None:
    painter.setPen(QPen(SOFT, 3))
    for position in (26, 51, 76, 101):
        painter.drawLine(position, 14, position, 114)
        painter.drawLine(14, position, 114, position)
    painter.setPen(QPen(INK, 4))
    painter.drawRoundedRect(QRectF(39, 39, 50, 50), 9, 9)


def _waves(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for y in (35, 64, 93):
        points = [QPointF(10 + index * 9, y + (10 if index % 2 else -10)) for index in range(13)]
        painter.drawPolyline(points)


def _circuit(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    lines = (
        (12, 32, 48, 32),
        (48, 32, 48, 63),
        (48, 63, 85, 63),
        (85, 63, 85, 96),
        (20, 94, 55, 94),
        (55, 94, 55, 78),
        (55, 78, 108, 78),
    )
    for line in lines:
        painter.drawLine(*line)
    painter.setBrush(INK)
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in ((12, 32), (48, 63), (85, 96), (20, 94), (108, 78)):
        painter.drawEllipse(QPointF(x, y), 6, 6)


def _blossom(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 3))
    painter.setBrush(QColor(255, 255, 255, 58))
    for angle in range(0, 360, 60):
        painter.save()
        painter.translate(64, 64)
        painter.rotate(angle)
        painter.drawEllipse(QRectF(-13, -52, 26, 47))
        painter.restore()
    painter.setBrush(INK)
    painter.drawEllipse(QPointF(64, 64), 10, 10)


def _speed(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for index, y in enumerate((29, 47, 65, 83, 101)):
        painter.drawLine(14 + index * 7, y, 111 - index * 5, y - 14)


def _pixels(painter: QPainter) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    for row in range(5):
        for column in range(5):
            if row == 2 or column == 2 or (row + column) % 4 == 0:
                painter.setBrush(INK if row == 2 or column == 2 else SOFT)
                painter.drawRoundedRect(QRectF(18 + column * 19, 18 + row * 19, 14, 14), 3, 3)


def _constellation(painter: QPainter) -> None:
    points = [QPointF(18, 88), QPointF(39, 38), QPointF(64, 68), QPointF(88, 24), QPointF(108, 84)]
    painter.setPen(QPen(SOFT, 3))
    painter.drawPolyline(points)
    painter.setBrush(INK)
    painter.setPen(Qt.PenStyle.NoPen)
    for index, point in enumerate(points):
        radius = 6 if index in (1, 3) else 4
        painter.drawEllipse(point, radius, radius)


def _rings(painter: QPainter) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for radius, alpha, width in ((45, 58, 3), (31, 110, 4), (17, 178, 5)):
        painter.setPen(QPen(QColor(255, 255, 255, alpha), width))
        painter.drawEllipse(QPointF(64, 64), radius, radius)


def _hexmesh(painter: QPainter) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(SOFT, 3))
    for row in range(4):
        for column in range(4):
            cx = 24 + column * 28 + (14 if row % 2 else 0)
            cy = 22 + row * 28
            points = QPolygonF(
                [
                    QPointF(
                        cx + math.cos(math.radians(angle)) * 15,
                        cy + math.sin(math.radians(angle)) * 15,
                    )
                    for angle in range(0, 360, 60)
                ]
            )
            painter.drawPolygon(points)
    painter.setPen(QPen(INK, 4))
    painter.drawEllipse(QPointF(66, 64), 12, 12)


def _chevrons(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for y in (34, 64, 94):
        painter.drawPolyline([QPointF(24, y - 14), QPointF(64, y + 10), QPointF(104, y - 14)])


def _equalizer(painter: QPainter) -> None:
    heights = (30, 54, 78, 48, 88, 64, 38)
    painter.setPen(Qt.PenStyle.NoPen)
    for index, height in enumerate(heights):
        painter.setBrush(INK if index in (2, 4) else SOFT)
        painter.drawRoundedRect(QRectF(15 + index * 14, 108 - height, 9, height), 4, 4)


def _scanlines(painter: QPainter) -> None:
    for index, y in enumerate(range(20, 112, 11)):
        painter.setPen(QPen(INK if index % 3 == 1 else SOFT, 4))
        inset = (index % 4) * 8
        painter.drawLine(12 + inset, y, 116 - inset, y)


def _prism(painter: QPainter) -> None:
    triangle = QPolygonF([QPointF(64, 16), QPointF(108, 101), QPointF(20, 101)])
    painter.setBrush(QColor(255, 255, 255, 36))
    painter.setPen(QPen(INK, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPolygon(triangle)
    painter.setPen(QPen(SOFT, 3))
    painter.drawLine(8, 65, 48, 62)
    painter.drawLine(79, 58, 120, 34)
    painter.drawLine(79, 63, 120, 63)
    painter.drawLine(79, 68, 120, 92)


def _target(painter: QPainter) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(INK, 4))
    for radius in (15, 30, 46):
        painter.drawEllipse(QPointF(64, 64), radius, radius)
    painter.drawLine(64, 8, 64, 36)
    painter.drawLine(64, 92, 64, 120)
    painter.drawLine(8, 64, 36, 64)
    painter.drawLine(92, 64, 120, 64)


def _confetti(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    strokes = (
        (20, 28, 32, 38),
        (52, 16, 50, 32),
        (87, 23, 77, 39),
        (108, 48, 92, 53),
        (22, 82, 38, 77),
        (49, 102, 54, 87),
        (85, 96, 78, 82),
        (108, 79, 94, 72),
    )
    for stroke in strokes:
        painter.drawLine(*stroke)
    painter.setBrush(SOFT)
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in ((35, 55), (65, 48), (81, 66), (50, 75), (67, 89)):
        painter.drawEllipse(QPointF(x, y), 5, 5)


def _rain(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for column, x in enumerate(range(18, 116, 16)):
        start = 12 + (column * 17) % 38
        painter.drawLine(x, start, x - 10, min(116, start + 35 + (column % 3) * 9))


def _sunburst(painter: QPainter) -> None:
    painter.setPen(QPen(INK, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for angle in range(0, 360, 30):
        radians = math.radians(angle)
        painter.drawLine(
            QPointF(64 + math.cos(radians) * 22, 64 + math.sin(radians) * 22),
            QPointF(64 + math.cos(radians) * 52, 64 + math.sin(radians) * 52),
        )
    painter.setBrush(QColor(255, 255, 255, 70))
    painter.drawEllipse(QPointF(64, 64), 15, 15)


def _portal(painter: QPainter) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for index in range(5):
        painter.save()
        painter.translate(64, 64)
        painter.rotate(index * 21)
        painter.setPen(QPen(QColor(255, 255, 255, 58 + index * 24), 4))
        painter.drawArc(
            QRectF(-48 + index * 6, -48 + index * 6, 96 - index * 12, 96 - index * 12),
            15 * 16,
            230 * 16,
        )
        painter.restore()


def _blocks(painter: QPainter) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    blocks = (
        (15, 18, 28, 21),
        (48, 18, 63, 21),
        (15, 44, 47, 28),
        (67, 44, 46, 28),
        (15, 77, 24, 33),
        (44, 77, 39, 33),
        (88, 77, 25, 33),
    )
    for index, rect in enumerate(blocks):
        painter.setBrush(INK if index in (1, 3, 5) else SOFT)
        painter.drawRoundedRect(QRectF(*rect), 6, 6)


def main() -> int:
    _app = QApplication.instance() or QApplication([])
    for name, draw in (
        ("spark", _spark),
        ("orbit", _orbit),
        ("grid", _grid),
        ("waves", _waves),
        ("circuit", _circuit),
        ("blossom", _blossom),
        ("speed", _speed),
        ("pixels", _pixels),
        ("constellation", _constellation),
        ("rings", _rings),
        ("hexmesh", _hexmesh),
        ("chevrons", _chevrons),
        ("equalizer", _equalizer),
        ("scanlines", _scanlines),
        ("prism", _prism),
        ("target", _target),
        ("confetti", _confetti),
        ("rain", _rain),
        ("sunburst", _sunburst),
        ("portal", _portal),
        ("blocks", _blocks),
    ):
        _save(name, draw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
