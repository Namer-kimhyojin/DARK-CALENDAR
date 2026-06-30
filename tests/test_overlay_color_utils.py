import unittest
from unittest.mock import patch

from PyQt6.QtGui import QColor

from calendar_app.presentation.widgets import overlay_color_utils as cu


class OverlayColorUtilsTests(unittest.TestCase):
    def test_parse_and_to_rgba_roundtrip(self):
        color, alpha = cu._parse_rgba("#80aabbcc")
        self.assertEqual(alpha, 0x80)
        self.assertEqual((color.red(), color.green(), color.blue()), (0xAA, 0xBB, 0xCC))
        self.assertEqual(cu._to_rgba_str(color, alpha), "#80aabbcc")

    def test_rgba_css_format(self):
        css = cu._rgba_css(QColor(10, 20, 30), 128)
        self.assertEqual(css, "rgba(10,20,30,128)")

    def test_pick_rgba_color_returns_none_on_cancel(self):
        invalid = QColor()
        with patch(
            "calendar_app.presentation.widgets.overlay_color_utils.QColorDialog.getColor",
            return_value=invalid,
        ):
            self.assertIsNone(cu._pick_rgba_color(None, "Pick", "#ff000000"))


if __name__ == "__main__":
    unittest.main()
