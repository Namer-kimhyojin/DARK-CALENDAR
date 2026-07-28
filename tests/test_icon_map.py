# -*- coding: utf-8 -*-
import ast
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from calendar_app.shared.icon_map import ICON, ICON_MAPPING, icon


class IconMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_magnet_icons_do_not_raise_and_return_icons(self):
        magnet = icon(ICON.MAGNET)
        magnet_off = icon(ICON.MAGNET_OFF)

        self.assertIsInstance(magnet, QIcon)
        self.assertIsInstance(magnet_off, QIcon)

    def test_all_icon_constant_references_exist_and_have_mappings(self):
        referenced_names = set()
        for path in Path("calendar_app").rglob("*.py"):
            tree = ast.parse(
                path.read_text(encoding="utf-8", errors="strict"),
                filename=str(path),
            )
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "ICON"
                ):
                    referenced_names.add(node.attr)

        missing_constants = sorted(name for name in referenced_names if not hasattr(ICON, name))
        self.assertEqual([], missing_constants)

        missing_mappings = sorted(
            name
            for name in referenced_names
            if hasattr(ICON, name) and getattr(ICON, name) not in ICON_MAPPING
        )
        self.assertEqual([], missing_mappings)


if __name__ == "__main__":
    unittest.main()
