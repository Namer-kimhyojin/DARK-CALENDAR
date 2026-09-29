# -*- coding: utf-8 -*-
"""Validated Windows hotkey dispatch for launcher-deck keys."""

from __future__ import annotations

import ctypes
import sys

_MODIFIERS = {
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "SHIFT": 0x10,
    "META": 0x5B,
    "WIN": 0x5B,
    "WINDOWS": 0x5B,
}
_NAMED_KEYS = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "VOLUMEMUTE": 0xAD,
    "VOLUMEDOWN": 0xAE,
    "VOLUMEUP": 0xAF,
    "MEDIANEXT": 0xB0,
    "MEDIAPREVIOUS": 0xB1,
    "MEDIASTOP": 0xB2,
    "MEDIAPLAY": 0xB3,
}
_KEYEVENTF_KEYUP = 0x0002


def parse_hotkey(sequence: str) -> list[int]:
    """Convert a portable Ctrl+Alt+K sequence to validated virtual-key codes."""
    parts = [part.strip().upper().replace(" ", "") for part in str(sequence).split("+")]
    if not parts or any(not part for part in parts) or len(parts) > 5:
        return []
    resolved: list[int] = []
    for part in parts:
        code = _MODIFIERS.get(part) or _NAMED_KEYS.get(part)
        if code is None and len(part) == 1 and (part.isascii() and part.isalnum()):
            code = ord(part)
        if code is None and part.startswith("F") and part[1:].isdigit():
            number = int(part[1:])
            if 1 <= number <= 24:
                code = 0x6F + number
        if code is None or code in resolved:
            return []
        resolved.append(code)
    return resolved


def send_hotkey(sequence: str) -> bool:
    """Send a validated key chord to the foreground app on Windows."""
    keys = parse_hotkey(sequence)
    if not keys or sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        for key in keys:
            user32.keybd_event(key, 0, 0, 0)
        for key in reversed(keys):
            user32.keybd_event(key, 0, _KEYEVENTF_KEYUP, 0)
        return True
    except (AttributeError, OSError):
        return False


__all__ = ["parse_hotkey", "send_hotkey"]
