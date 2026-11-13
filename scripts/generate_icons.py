# -*- coding: utf-8 -*-
"""
Generate all app & store icons from a single master PNG.

Usage:
    python scripts/generate_icons.py [--master PATH] [--dry-run]

Master image requirements
--------------------------
- Format  : PNG (RGBA or RGB)
- Size    : 1240 x 1240 px minimum  (권장: 1240x1240 이상)
- Content : 아이콘 원본 이미지 (여백 최소화, 중앙 배치)
- Default : Assets/brand_feather.png

Generated files
---------------
  app_icon.ico              — exe 임베드용 ICO (16/24/32/48/64/128/256)
  app_icon.png              — 512x512
  Assets/app_icon.ico       — 런타임 트레이/타이틀바용 ICO
  Assets/app_icon.png       — 512x512
  Assets/splash_icon.png    — 256x256
  Assets/SplashScreen.png   — 620x300 (100% scale)
  Assets/icon_*.png         — 16/24/32/48/64/96/128/256/512/1024
  Assets/StoreLogo.png      — 50x50 (100% scale)
  Assets/Square44x44Logo.png    — 44x44 (100% scale)
  Assets/Square150x150Logo.png  — 150x150 (100% scale)
  Assets/Square310x310Logo.png  — 310x310 (100% scale)
  Assets/AppTile.png            — 620x620
  Assets/Wide310x150Logo.png    — 310x150 (100% scale)
  Assets/PosterArt.png          — 1024x1024
  Assets/*Logo.scale-*.png / SplashScreen.scale-*.png — 100–400% scale
  Assets/Square44x44Logo.targetsize-*.png — Windows shell icon variants
  Assets/app_icon.icns / docs/assets/app_icon.png / Store listing PNGs
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
ICON_SIZES = (16, 24, 32, 48, 64, 71, 96, 128, 150, 256, 300, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SCALES = (100, 125, 150, 200, 250, 300, 400)
TARGET_SIZES = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256)
STORE_SURFACES = {
    "StoreLogo": (50, 50),
    "Square44x44Logo": (44, 44),
    "Square150x150Logo": (150, 150),
    "Square310x310Logo": (310, 310),
    "Wide310x150Logo": (310, 150),
    "SplashScreen": (620, 300),
}


def _require_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        sys.exit(1)


def _load_master(path: Path):
    from PIL import Image

    if not path.exists():
        print(f"ERROR: master image not found: {path}")
        print()
        print("Master image requirements")
        print("  Format  : PNG (RGBA or RGB)")
        print("  Size    : 1240 x 1240 px minimum")
        print("  Content : 아이콘 원본 이미지 (중앙 배치, 여백 최소화)")
        print(f"  Path    : {path}")
        sys.exit(1)

    img = Image.open(path).convert("RGBA")
    w, h = img.size
    if w < 1240 or h < 1240:
        print(f"WARNING: master is {w}x{h} — recommend 1240x1240+. Wide logo may be blurry.")
    return img


def _resize(img, size: tuple[int, int], resample=None):
    from PIL import Image

    resample = resample or Image.LANCZOS
    return img.resize(size, resample)


def _resize_on_canvas(img, canvas_w: int, canvas_h: int, icon_h: int):
    """Scale img to icon_h, center on canvas_w x canvas_h with transparent bg."""
    from PIL import Image

    scale = icon_h / img.height
    icon_w = max(1, round(img.width * scale))
    icon_resized = img.resize((icon_w, icon_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    x = (canvas_w - icon_w) // 2
    y = (canvas_h - icon_h) // 2
    canvas.alpha_composite(icon_resized, (x, y))
    return canvas


def _save(img, path: Path, dry_run: bool, extra: str = "", **save_options) -> None:
    label = f"  {path.relative_to(ROOT)}  ({img.width}x{img.height}){extra}"
    if dry_run:
        print(f"[dry] {label}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True, **save_options)
    print(f"  OK  {label}")


def _save_ico(img, path: Path, dry_run: bool) -> None:
    from PIL import Image

    label = f"  {path.relative_to(ROOT)}  (ICO {list(ICO_SIZES)})"
    if dry_run:
        print(f"[dry] {label}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(
        path, format="ICO", sizes=[(s, s) for s in ICO_SIZES]
    )
    print(f"  OK  {label}")


def generate(master: Path, dry_run: bool) -> None:
    _require_pillow()
    img = _load_master(master)
    assets = ROOT / "Assets"

    print()
    print(f"  master : {master}  ({img.width}x{img.height})")
    print(f"  dry-run: {dry_run}")
    print()

    # ICO (exe embed + runtime)
    _save_ico(img, ROOT / "app_icon.ico", dry_run)
    _save_ico(img, assets / "app_icon.ico", dry_run)

    # Square PNG sizes
    for size in ICON_SIZES:
        _save(_resize(img, (size, size)), assets / f"icon_{size}x{size}.png", dry_run)

    _save(_resize(img, (512, 512)), ROOT / "app_icon.png", dry_run)
    _save(_resize(img, (512, 512)), assets / "app_icon.png", dry_run)
    _save(_resize(img, (256, 256)), assets / "splash_icon.png", dry_run)
    _save(_resize(img, (620, 620)), assets / "AppTile.png", dry_run)
    _save(_resize(img, (1024, 1024)), assets / "PosterArt.png", dry_run)

    # Windows prefers qualified variants to the unqualified fallback. Generate
    # every variant from the same source and preserve alpha on the clear canvas.
    for name, dimensions in STORE_SURFACES.items():
        for scale in SCALES:
            width, height = (math.ceil(value * scale / 100) for value in dimensions)
            image = _resize_on_canvas(img, width, height, min(width, height))
            _save(image, assets / f"{name}.scale-{scale}.png", dry_run)
            if scale == 100:
                _save(image, assets / f"{name}.png", dry_run)

    for size in TARGET_SIZES:
        image = _resize(img, (size, size))
        for suffix in ("", "_altform-unplated", "_altform-lightunplated"):
            _save(image, assets / f"Square44x44Logo.targetsize-{size}{suffix}.png", dry_run)

    _save(
        img,
        assets / "app_icon.icns",
        dry_run,
        append_images=[_resize(img, (size, size)) for size in (32, 64, 128, 256, 512, 1024)],
    )
    _save(_resize(img, (512, 512)), ROOT / "docs" / "assets" / "app_icon.png", dry_run)
    for size in (300, 512):
        _save(
            _resize(img, (size, size)),
            assets / "store-listing" / f"StoreListing-{size}x{size}.png",
            dry_run,
        )

    print()
    print(
        "  Done." if not dry_run else "  Dry-run complete. Re-run without --dry-run to write files."
    )


def main() -> None:
    default_master = ROOT / "Assets" / "brand_feather.png"

    parser = argparse.ArgumentParser(
        description="Generate all app & store icons from a master PNG.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--master",
        "-m",
        default=str(default_master),
        help=f"Master PNG path (default: {default_master.name})",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview output without writing files.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Air Calendar - Icon Generator")
    print("=" * 60)
    print()
    print("  [Master image requirements]")
    print("  Format  : PNG  (RGBA or RGB)")
    print("  Size    : 1240 x 1240 px  minimum")
    print("  Content : 아이콘 원본 (중앙 배치, 여백 최소화)")
    print(f"  Path    : {args.master}")
    print()

    generate(Path(args.master), args.dry_run)


if __name__ == "__main__":
    main()
