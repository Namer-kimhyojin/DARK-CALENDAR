# -*- coding: utf-8 -*-
from pathlib import Path
import tempfile
import unittest

from calendar_app.infrastructure.runtime.launcher_asset_store import import_launcher_asset


class LauncherAssetStoreTests(unittest.TestCase):
    def test_imports_supported_asset_with_content_addressed_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "custom icon.svg"
            source.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8", errors="strict"
            )
            imported = Path(import_launcher_asset(str(source), "image", root=root / "app"))
            self.assertTrue(imported.is_file())
            self.assertEqual(imported.suffix, ".svg")
            self.assertEqual(imported.parent.name, "image")
            self.assertEqual(
                imported,
                Path(import_launcher_asset(str(source), "image", root=root / "app")),
            )

    def test_rejects_unsupported_kind_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "unsafe.exe"
            source.write_bytes(b"MZ")
            self.assertEqual(import_launcher_asset(str(source), "image", root=root / "app"), "")
            self.assertEqual(import_launcher_asset(str(source), "sound", root=root / "app"), "")


if __name__ == "__main__":
    unittest.main()
