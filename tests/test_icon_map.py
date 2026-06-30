import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from calendar_app.shared.icon_map import ICON, icon


class IconMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_magnet_icons_do_not_raise_and_return_icons(self):
        magnet = icon(ICON.MAGNET)
        magnet_off = icon(ICON.MAGNET_OFF)

        self.assertIsInstance(magnet, QIcon)
        self.assertIsInstance(magnet_off, QIcon)


if __name__ == "__main__":
    unittest.main()
