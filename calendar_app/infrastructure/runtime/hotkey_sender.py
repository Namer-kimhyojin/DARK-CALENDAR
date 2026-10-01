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
    # 한국어 키보드: 한/영, 한자
    "HANGUL": 0x15,
    "HANJA": 0x19,
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
    "PRINTSCREEN": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "APPS": 0x5D,
    "MENU": 0x5D,
    "NUM0": 0x60,
    "NUM1": 0x61,
    "NUM2": 0x62,
    "NUM3": 0x63,
    "NUM4": 0x64,
    "NUM5": 0x65,
    "NUM6": 0x66,
    "NUM7": 0x67,
    "NUM8": 0x68,
    "NUM9": 0x69,
    "NUMMULTIPLY": 0x6A,
    "NUMADD": 0x6B,
    "NUMSUBTRACT": 0x6D,
    "NUMDECIMAL": 0x6E,
    "NUMDIVIDE": 0x6F,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
    "VOLUMEMUTE": 0xAD,
    "VOLUMEDOWN": 0xAE,
    "VOLUMEUP": 0xAF,
    "MEDIANEXT": 0xB0,
    "MEDIAPREVIOUS": 0xB1,
    "MEDIASTOP": 0xB2,
    "MEDIAPLAY": 0xB3,
    # 문장부호 키 (US 배열 위치 기준 가상 키)
    "SEMICOLON": 0xBA,
    "EQUAL": 0xBB,
    "COMMA": 0xBC,
    "MINUS": 0xBD,
    "PERIOD": 0xBE,
    "SLASH": 0xBF,
    "BACKQUOTE": 0xC0,
    "LBRACKET": 0xDB,
    "BACKSLASH": 0xDC,
    "RBRACKET": 0xDD,
    "QUOTE": 0xDE,
}
# 한 글자로 적어도 되는 문장부호 ('+'는 구분자라 제외: Equal/NumAdd 이름을 쓴다)
_SYMBOL_KEYS = {
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}
# 확장 키 플래그가 필요한 키 (없으면 일부 앱이 숫자패드 키로 받아들인다)
_EXTENDED_KEYS = frozenset(
    {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90}
)
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002
_MAPVK_VK_TO_VSC = 0


def parse_hotkey(sequence: str) -> list[int]:
    """Convert a portable Ctrl+Alt+K sequence to validated virtual-key codes."""
    parts = [part.strip().upper().replace(" ", "") for part in str(sequence).split("+")]
    if not parts or any(not part for part in parts) or len(parts) > 5:
        return []
    resolved: list[int] = []
    for part in parts:
        code = _MODIFIERS.get(part) or _NAMED_KEYS.get(part) or _SYMBOL_KEYS.get(part)
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


def is_modifier_only(sequence: str) -> bool:
    """True for a lone modifier such as ``Shift`` or ``Ctrl`` (sticky modifier keys)."""
    parts = [part.strip().upper() for part in str(sequence).split("+") if part.strip()]
    return len(parts) == 1 and parts[0] in _MODIFIERS


def send_hotkey(sequence: str) -> bool:
    """Send a validated key chord to the foreground app on Windows."""
    keys = parse_hotkey(sequence)
    if not keys or sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32

        def event(key: int, flags: int) -> None:
            scan = user32.MapVirtualKeyW(key, _MAPVK_VK_TO_VSC) & 0xFF
            if key in _EXTENDED_KEYS:
                flags |= _KEYEVENTF_EXTENDEDKEY
            user32.keybd_event(key, scan, flags, 0)

        for key in keys:
            event(key, 0)
        for key in reversed(keys):
            event(key, _KEYEVENTF_KEYUP)
        return True
    except (AttributeError, OSError):
        return False


__all__ = ["is_modifier_only", "parse_hotkey", "send_hotkey"]
