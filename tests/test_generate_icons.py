# -*- coding: utf-8 -*-
"""One immutable feather source must reach every Windows icon variant."""

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import generate_icons


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is an optional asset-build tool")
class GenerateIconsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image, ImageDraw

        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "Assets" / "brand_feather.png"
        cls.source.parent.mkdir()
        image = Image.new("RGBA", (1254, 1254), (0, 0, 0, 0))
        drawing = ImageDraw.Draw(image)
        drawing.ellipse((150, 300, 1100, 950), fill=(197, 163, 245, 128))
        drawing.rectangle((450, 450, 800, 800), fill=(197, 163, 245, 255))
        image.save(cls.source)
        cls.source_digest = hashlib.sha256(cls.source.read_bytes()).hexdigest()
        with patch.object(generate_icons, "ROOT", cls.root), redirect_stdout(io.StringIO()):
            generate_icons.generate(cls.source, False)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_source_and_primary_copies_remain_identical(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_digest)
        primary = (self.root / "app_icon.png").read_bytes()
        for relative in (
            "Assets/app_icon.png",
            "Assets/icon_512x512.png",
            "docs/assets/app_icon.png",
        ):
            self.assertEqual((self.root / relative).read_bytes(), primary)
        self.assertEqual(
            (self.root / "app_icon.ico").read_bytes(),
            (self.root / "Assets/app_icon.ico").read_bytes(),
        )

    def test_windows_scale_and_targetsize_variants_have_correct_size_and_alpha(self):
        from PIL import Image

        with Image.open(self.source) as image:
            source = image.convert("RGBA")
        for name, dimensions in generate_icons.STORE_SURFACES.items():
            for scale in generate_icons.SCALES:
                expected = tuple((value * scale + 99) // 100 for value in dimensions)
                with Image.open(self.root / "Assets" / f"{name}.scale-{scale}.png") as image:
                    self.assertEqual(image.size, expected)
                    self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
                    side = min(expected)
                    canvas = Image.new("RGBA", expected, (0, 0, 0, 0))
                    canvas.alpha_composite(
                        source.resize((side, side), Image.Resampling.LANCZOS),
                        ((expected[0] - side) // 2, (expected[1] - side) // 2),
                    )
                    self.assertEqual(image.tobytes(), canvas.tobytes())
                if scale == 100:
                    self.assertEqual(
                        (self.root / "Assets" / f"{name}.png").read_bytes(),
                        (self.root / "Assets" / f"{name}.scale-100.png").read_bytes(),
                    )
        for size in generate_icons.TARGET_SIZES:
            reference = (
                self.root / "Assets" / f"Square44x44Logo.targetsize-{size}.png"
            ).read_bytes()
            for suffix in ("", "_altform-unplated", "_altform-lightunplated"):
                path = self.root / "Assets" / f"Square44x44Logo.targetsize-{size}{suffix}.png"
                self.assertEqual(path.read_bytes(), reference)
                with Image.open(path) as image:
                    self.assertEqual(image.size, (size, size))
                    self.assertEqual(image.getchannel("A").getextrema()[0], 0)

    def test_canvas_compositing_preserves_partial_alpha(self):
        from PIL import Image

        image = Image.new("RGBA", (2, 2), (197, 163, 245, 128))
        canvas = generate_icons._resize_on_canvas(image, 4, 4, 2)
        self.assertEqual(canvas.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(canvas.getpixel((1, 1)), (197, 163, 245, 128))

    def test_default_and_compatibility_entrypoints_select_the_feather(self):
        from scripts import generate_brand_assets

        self.assertIs(generate_brand_assets.main, generate_icons.main)
        with (
            patch.object(generate_icons, "ROOT", self.root),
            patch.object(generate_icons, "generate") as generate,
            patch("sys.argv", ["generate_icons.py", "--dry-run"]),
            redirect_stdout(io.StringIO()),
        ):
            generate_icons.main()
        generate.assert_called_once_with(self.source, True)

    def test_ico_icns_and_dry_run_do_not_use_legacy_master(self):
        from PIL import Image

        with Image.open(self.root / "app_icon.ico") as image:
            self.assertEqual(image.ico.sizes(), {(size, size) for size in generate_icons.ICO_SIZES})
        with Image.open(self.root / "Assets/app_icon.icns") as image:
            self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
            with Image.open(self.source) as source:
                expected = source.resize(image.size, Image.Resampling.LANCZOS)
            self.assertEqual(image.tobytes(), expected.tobytes())
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        with patch.object(generate_icons, "ROOT", self.root), redirect_stdout(io.StringIO()):
            generate_icons.generate(self.source, True)
        self.assertEqual(
            {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*")
                if path.is_file()
            },
            before,
        )
