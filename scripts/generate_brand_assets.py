# -*- coding: utf-8 -*-
"""Render the editable A-1 SVG identity and all application icon surfaces."""

import math
from pathlib import Path
import sys

from generate_icons import generate
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent


def render_svg(source: Path, destination: Path, size: int) -> None:
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"Invalid brand SVG: {source}")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(destination)):
        raise OSError(f"Could not save {destination}")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    branding = ROOT / "Assets" / "branding"
    master = branding / "air-calendar-a1-master.png"
    render_svg(branding / "air-calendar-a1.svg", master, 2048)
    generate(master, False)
    render_svg(branding / "air-calendar-a1-symbol.svg", ROOT / "Assets" / "splash_icon.png", 512)
    from PIL import Image

    assets = ROOT / "Assets"
    tile = Image.open(master).convert("RGBA")
    symbol = Image.open(assets / "splash_icon.png").convert("RGBA")

    def fitted(size: tuple[int, int], splash: bool = False):
        canvas = Image.new("RGBA", size, (17, 29, 43, 255))
        height = round(size[1] * (0.60 if splash else 0.86))
        image = (symbol if splash else tile).resize((height, height), Image.Resampling.LANCZOS)
        canvas.alpha_composite(image, ((size[0] - height) // 2, (size[1] - height) // 2))
        return canvas

    sizes = {
        "StoreLogo": (50, 50),
        "Square44x44Logo": (44, 44),
        "Square150x150Logo": (150, 150),
        "Square310x310Logo": (310, 310),
        "Wide310x150Logo": (310, 150),
        "SplashScreen": (620, 300),
    }
    for name, dimensions in sizes.items():
        for scale in (100, 125, 150, 200, 250, 300, 400):
            size = tuple(math.ceil(value * scale / 100) for value in dimensions)
            image = fitted(size, name == "SplashScreen")
            image.save(assets / f"{name}.scale-{scale}.png", optimize=True)
            if scale == 100:
                image.save(assets / f"{name}.png", optimize=True)
    for size in (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256):
        icon = tile.resize((size, size), Image.Resampling.LANCZOS)
        for suffix in ("", "_altform-unplated", "_altform-lightunplated"):
            icon.save(assets / f"Square44x44Logo.targetsize-{size}{suffix}.png", optimize=True)
    for size in (71, 150, 300):
        tile.resize((size, size), Image.Resampling.LANCZOS).save(
            assets / f"icon_{size}x{size}.png", optimize=True
        )
    tile.save(assets / "app_icon.icns", format="ICNS")
    listing = assets / "store-listing"
    listing.mkdir(exist_ok=True)
    for size in (300, 512):
        fitted((size, size)).save(listing / f"StoreListing-{size}x{size}.png", optimize=True)
    from shutil import copyfile

    copyfile(ROOT / "app_icon.png", ROOT / "docs" / "assets" / "app_icon.png")
    # Keep the application alive while all Qt rendering has completed.
    del app


if __name__ == "__main__":
    main()
