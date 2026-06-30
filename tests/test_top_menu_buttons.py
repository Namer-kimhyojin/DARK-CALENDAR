import unittest

from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.presentation.theme.style_builder import _build_top_menu_button_style


class TopMenuButtonTests(unittest.TestCase):
    def test_format_top_menu_button_text_adds_single_leading_space(self):
        self.assertEqual(format_top_menu_button_text("등록"), " 등록")
        self.assertEqual(format_top_menu_button_text("  작업  "), " 작업")
        self.assertEqual(format_top_menu_button_text(""), "")

    def test_top_menu_button_style_uses_normal_font_weight(self):
        style = _build_top_menu_button_style(10, "#4da6ff")

        self.assertIn("font-weight: normal;", style)
        self.assertNotIn("font-weight: bold;", style)


if __name__ == "__main__":
    unittest.main()
