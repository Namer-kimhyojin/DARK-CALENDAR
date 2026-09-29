# -*- coding: utf-8 -*-
import unittest

from calendar_app.infrastructure.runtime.hotkey_sender import parse_hotkey, send_hotkey


class LauncherHotkeySenderTests(unittest.TestCase):
    def test_parses_modifiers_named_keys_and_function_keys(self):
        self.assertEqual(parse_hotkey("Ctrl+Shift+K"), [0x11, 0x10, ord("K")])
        self.assertEqual(parse_hotkey("Alt+F12"), [0x12, 0x7B])
        self.assertEqual(parse_hotkey("Win+VolumeUp"), [0x5B, 0xAF])

    def test_rejects_unknown_duplicate_or_oversized_sequences(self):
        self.assertEqual(parse_hotkey("Ctrl+Ctrl+K"), [])
        self.assertEqual(parse_hotkey("Ctrl+NotAKey"), [])
        self.assertEqual(parse_hotkey("Ctrl+Alt+Shift+Win+A+B"), [])

    def test_non_windows_send_is_safe(self):
        if __import__("sys").platform != "win32":
            self.assertFalse(send_hotkey("Ctrl+K"))


if __name__ == "__main__":
    unittest.main()
