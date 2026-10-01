# -*- coding: utf-8 -*-
import unittest

from calendar_app.infrastructure.runtime.hotkey_sender import (
    is_modifier_only,
    parse_hotkey,
    send_hotkey,
)


class LauncherHotkeySenderTests(unittest.TestCase):
    def test_parses_modifiers_named_keys_and_function_keys(self):
        self.assertEqual(parse_hotkey("Ctrl+Shift+K"), [0x11, 0x10, ord("K")])
        self.assertEqual(parse_hotkey("Alt+F12"), [0x12, 0x7B])
        self.assertEqual(parse_hotkey("Win+VolumeUp"), [0x5B, 0xAF])

    def test_rejects_unknown_duplicate_or_oversized_sequences(self):
        self.assertEqual(parse_hotkey("Ctrl+Ctrl+K"), [])
        self.assertEqual(parse_hotkey("Ctrl+NotAKey"), [])
        self.assertEqual(parse_hotkey("Ctrl+Alt+Shift+Win+A+B"), [])

    def test_keyboard_layout_keys_are_supported(self):
        self.assertEqual(parse_hotkey("Backquote"), [0xC0])
        self.assertEqual(parse_hotkey("Shift+Equal"), [0x10, 0xBB])
        self.assertEqual(parse_hotkey("Ctrl+-"), [0x11, 0xBD])
        self.assertEqual(parse_hotkey("\\"), [0xDC])
        self.assertEqual(parse_hotkey("Hangul"), [0x15])
        self.assertEqual(parse_hotkey("Hanja"), [0x19])
        self.assertEqual(parse_hotkey("Num7"), [0x67])
        self.assertEqual(parse_hotkey("NumAdd"), [0x6B])
        self.assertEqual(parse_hotkey("PrintScreen"), [0x2C])
        self.assertEqual(parse_hotkey("Apps"), [0x5D])

    def test_lone_modifiers_are_detected(self):
        self.assertTrue(is_modifier_only("Shift"))
        self.assertTrue(is_modifier_only(" ctrl "))
        self.assertFalse(is_modifier_only("Shift+A"))
        self.assertFalse(is_modifier_only("A"))

    def test_non_windows_send_is_safe(self):
        if __import__("sys").platform != "win32":
            self.assertFalse(send_hotkey("Ctrl+K"))


if __name__ == "__main__":
    unittest.main()
