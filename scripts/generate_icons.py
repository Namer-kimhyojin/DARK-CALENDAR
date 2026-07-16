"""
Generate all app & store icons from a single master PNG.

Usage:
    python scripts/generate_icons.py [--master PATH] [--dry-run]

Master image requirements
--------------------------
- Format  : PNG (RGBA or RGB)
- Size    : 1240 x 1240 px minimum  (권장: 1240x1240 이상)
- Content : 아이콘 원본 이미지 (여백 최소화, 중앙 배치)
- Default : app_icon_original_highres_master.png  (프로젝트 루트)

Generated files
---------------
  app_icon.ico              — exe 임베드용 ICO (16/24/32/48/64/128/256)
  app_icon.png              — 512x512
  Assets/app_icon.ico       — 런타임 트레이/타이틀바용 ICO
  Assets/app_icon.png       — 512x512
  Assets/splash_icon.png    — 256x256
  Assets/SplashScreen.png   — 512x512
  Assets/icon_*.png         — 16/24/32/48/64/96/128/256/512/1024
  Assets/StoreLogo.png      — 256x256
  Assets/Square44x44Logo.png    — 256x256 (2x scale, @4x 호환)
  Assets/Square150x150Logo.png  — 512x512
  Assets/Square310x310Logo.png  — 620x620
  Assets/AppTile.png            — 620x620
  Assets/Wide310x150Logo.png    — 1240x600 (아이콘 중앙 배치, 배경 자동)
  Assets/PosterArt.png          — 1024x1024
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


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
    icon_w = int(img.width * scale)
    icon_resized = img.resize((icon_w, icon_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    x = (canvas_w - icon_w) // 2
    y = (canvas_h - icon_h) // 2
    canvas.paste(icon_resized, (x, y), icon_resized)
    return canvas


def _save(img, path: Path, dry_run: bool, extra: str = "") -> None:
    label = f"  {path.relative_to(ROOT)}  ({img.width}x{img.height}){extra}"
    if dry_run:
        print(f"[dry] {label}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    print(f"  OK  {label}")


def _save_ico(img, path: Path, dry_run: bool) -> None:
    from PIL import Image

    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]
    label = f"  {path.relative_to(ROOT)}  (ICO {sizes})"
    if dry_run:
        print(f"[dry] {label}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[1:])
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
    for size in [16, 24, 32, 48, 64, 96, 128, 256, 512, 1024]:
        _save(_resize(img, (size, size)), assets / f"icon_{size}x{size}.png", dry_run)

    _save(_resize(img, (512, 512)), ROOT / "app_icon.png", dry_run)
    _save(_resize(img, (512, 512)), assets / "app_icon.png", dry_run)
    _save(_resize(img, (256, 256)), assets / "splash_icon.png", dry_run)
    _save(_resize(img, (512, 512)), assets / "SplashScreen.png", dry_run)

    # Store tiles
    _save(_resize(img, (256, 256)), assets / "StoreLogo.png", dry_run)
    _save(_resize(img, (256, 256)), assets / "Square44x44Logo.png", dry_run)
    _save(_resize(img, (512, 512)), assets / "Square150x150Logo.png", dry_run)
    _save(_resize(img, (620, 620)), assets / "Square310x310Logo.png", dry_run)
    _save(_resize(img, (620, 620)), assets / "AppTile.png", dry_run)
    _save(_resize(img, (1024, 1024)), assets / "PosterArt.png", dry_run)

    # Wide logo — icon centered on transparent 1240x600 canvas
    wide = _resize_on_canvas(img, canvas_w=1240, canvas_h=600, icon_h=560)
    _save(wide, assets / "Wide310x150Logo.png", dry_run, extra="  (icon centered, transparent bg)")

    print()
    print(
        "  Done." if not dry_run else "  Dry-run complete. Re-run without --dry-run to write files."
    )


def main() -> None:
    default_master = ROOT / "app_icon_original_highres_master.png"

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
    print("  Dark Calendar - Icon Generator")
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
