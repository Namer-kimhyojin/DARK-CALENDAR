# -*- coding: utf-8 -*-
"""The few Win32 calls the app needs, through ctypes (works on x64 and ARM64)."""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

# RegisterHotKey modifiers and the message it posts.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_user32 = None
_kernel32 = None

if sys.platform == "win32":
    from ctypes import wintypes

    class _LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    try:
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
        _user32.GetLastInputInfo.restype = wintypes.BOOL
        _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        _user32.GetCursorPos.restype = wintypes.BOOL
        _user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        _user32.SetWindowPos.restype = wintypes.BOOL
        _kernel32.GetTickCount.argtypes = []
        _kernel32.GetTickCount.restype = wintypes.DWORD
    except (OSError, AttributeError):
        logger.warning("Win32 input APIs are unavailable", exc_info=True)
        _user32 = _kernel32 = None

AVAILABLE = _user32 is not None and _kernel32 is not None

HOTKEYS_AVAILABLE = False
if _user32 is not None:
    try:
        _user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        _user32.RegisterHotKey.restype = wintypes.BOOL
        _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        _user32.UnregisterHotKey.restype = wintypes.BOOL
        HOTKEYS_AVAILABLE = True
    except AttributeError:
        logger.warning("Win32 hotkey APIs are unavailable", exc_info=True)

_HOTKEY_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "meta": MOD_WIN,
    "win": MOD_WIN,
}
_NAMED_VIRTUAL_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "return": 0x0D,
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pgup": 0x21,
    "pageup": 0x21,
    "pgdown": 0x22,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "ins": 0x2D,
    "insert": 0x2D,
    "del": 0x2E,
    "delete": 0x2E,
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


def last_input_tick() -> int | None:
    """Tick count (ms) of the last keyboard or mouse input, or None."""
    if not AVAILABLE:
        return None
    info = _LastInputInfo(ctypes.sizeof(_LastInputInfo), 0)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return int(info.dwTime) & 0xFFFFFFFF


def tick_count() -> int | None:
    if not AVAILABLE:
        return None
    return int(_kernel32.GetTickCount()) & 0xFFFFFFFF


def cursor_pos() -> tuple[int, int] | None:
    if not AVAILABLE:
        return None
    point = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(point)):
        return None
    return (int(point.x), int(point.y))


def set_window_bottom(hwnd) -> bool:
    """Send a window to the bottom of the z-order without moving or activating it."""
    if not AVAILABLE or not hwnd:
        return False
    return bool(
        _user32.SetWindowPos(
            int(hwnd), HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )
    )


def _virtual_key(name: str) -> int | None:
    upper = name.upper()
    if len(upper) == 1 and ("A" <= upper <= "Z" or "0" <= upper <= "9"):
        return ord(upper)
    if upper.startswith("F") and upper[1:].isdigit() and 1 <= int(upper[1:]) <= 24:
        return 0x6F + int(upper[1:])  # VK_F1 = 0x70
    return _NAMED_VIRTUAL_KEYS.get(name.lower())


def parse_hotkey(key_text: str) -> tuple[int, int] | None:
    """Turn Qt key text such as ``Ctrl+F1`` into RegisterHotKey (modifiers, vk).

    Holding the keys does not repeat (``MOD_NOREPEAT``). Returns None for keys that
    have no virtual-key mapping here; those stay in-app shortcuts.
    """
    parts = [part.strip() for part in str(key_text or "").split("+")]
    if not parts or not parts[-1]:
        return None
    modifiers = MOD_NOREPEAT
    for name in parts[:-1]:
        flag = _HOTKEY_MODIFIERS.get(name.lower())
        if flag is None:
            return None
        modifiers |= flag
    vk = _virtual_key(parts[-1])
    return None if vk is None else (modifiers, vk)


def register_hotkey(hwnd, hotkey_id: int, modifiers: int, vk: int) -> tuple[bool, int]:
    """RegisterHotKey for ``hwnd``; returns (ok, Win32 error code).

    Error 1409 (ERROR_HOTKEY_ALREADY_REGISTERED) means another program owns the key.
    """
    if not HOTKEYS_AVAILABLE or not hwnd:
        return False, 0
    ctypes.set_last_error(0)
    if _user32.RegisterHotKey(int(hwnd), int(hotkey_id), int(modifiers), int(vk)):
        return True, 0
    return False, int(ctypes.get_last_error())


def unregister_hotkey(hwnd, hotkey_id: int) -> bool:
    if not HOTKEYS_AVAILABLE or not hwnd:
        return False
    return bool(_user32.UnregisterHotKey(int(hwnd), int(hotkey_id)))


def hotkey_id_from_message(address) -> int | None:
    """Hotkey id of a native ``MSG`` at ``address`` when it is WM_HOTKEY, else None."""
    if sys.platform != "win32" or not address:
        return None
    msg = wintypes.MSG.from_address(int(address))
    if msg.message != WM_HOTKEY:
        return None
    return int(msg.wParam)
