# -*- coding: utf-8 -*-
"""Place a window between the desktop wallpaper and the desktop icons (Windows).

This is the technique wallpaper apps use. The desktop is not a public API, so
every step checks its result and the caller falls back to an ordinary window
when anything is missing.

Two desktop layouts exist:
- Windows 11 24H2 and later: ``Progman`` holds the icon view
  (``SHELLDLL_DefView``) and, after message 0x052C, a ``WorkerW`` that draws
  the wallpaper. The window becomes a child of ``Progman`` placed right below
  the icon view, so it sits above the wallpaper and under the icons.
- Older Windows: message 0x052C creates a top-level ``WorkerW`` behind the one
  that holds the icon view; the window becomes a child of that ``WorkerW``.

While embedded the icon view covers the window, so it receives no mouse input;
it is meant for the locked, view-only calendar.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

_SPAWN_WORKERW = 0x052C
_GWL_STYLE = -16
_WS_CHILD = 0x40000000
_WS_POPUP = 0x80000000
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040
_SWP_FRAMECHANGED = 0x0020
_HWND_TOP = 0
_HWND_BOTTOM = 1
_SMTO_NORMAL = 0

_user32 = None
if sys.platform == "win32":
    from ctypes import wintypes

    try:
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
        _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        _user32.FindWindowW.restype = wintypes.HWND
        _user32.FindWindowExW.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
        ]
        _user32.FindWindowExW.restype = wintypes.HWND
        _user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        _user32.SendMessageTimeoutW.restype = ctypes.c_size_t
        _user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        _user32.SetParent.restype = wintypes.HWND
        _user32.GetParent.argtypes = [wintypes.HWND]
        _user32.GetParent.restype = wintypes.HWND
        _user32.IsWindow.argtypes = [wintypes.HWND]
        _user32.IsWindow.restype = wintypes.BOOL
        _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
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
        _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        _user32.GetWindowRect.restype = wintypes.BOOL
        _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        _user32.ClientToScreen.restype = wintypes.BOOL
        _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        _user32.GetWindow.restype = wintypes.HWND
        _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        _user32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]
        _user32.EnumWindows.restype = wintypes.BOOL
    except (OSError, AttributeError):
        logger.warning("Desktop embedding APIs are unavailable", exc_info=True)
        _user32 = None

AVAILABLE = _user32 is not None

# hwnd -> (host hwnd, original style, original screen rect)
_EMBEDDED: dict[int, tuple[int, int, tuple[int, int, int, int]]] = {}


def _handle(value) -> int:
    return int(value or 0)


def _spawn_workerw(progman: int) -> None:
    result = ctypes.c_size_t(0)
    for wparam, lparam in ((0xD, 0x1), (0, 0)):
        _user32.SendMessageTimeoutW(
            progman, _SPAWN_WORKERW, wparam, lparam, _SMTO_NORMAL, 1000, ctypes.byref(result)
        )


def icon_layer_host() -> tuple[int, int] | None:
    """(parent, insert-after) that puts a child under the icons, or None."""
    if not AVAILABLE:
        return None
    progman = _handle(_user32.FindWindowW("Progman", None))
    if not progman:
        return None
    _spawn_workerw(progman)
    defview = _handle(_user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None))
    if defview:
        # 24H2+: siblings inside Progman; "insert after" the icon view = just below it.
        return progman, defview

    found = []

    @_EnumProc
    def _find(hwnd, _lparam):
        if _user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            found.append(_handle(hwnd))
            return False
        return True

    _user32.EnumWindows(_find, 0)
    if not found:
        return None
    workerw = _handle(_user32.FindWindowExW(None, found[0], "WorkerW", None))
    if not workerw:
        return None
    return workerw, _HWND_TOP


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def is_embedded(hwnd) -> bool:
    return _handle(hwnd) in _EMBEDDED


def embedding_alive(hwnd) -> bool:
    """False when Explorer restarted (host gone) or something reparented the window."""
    hwnd = _handle(hwnd)
    entry = _EMBEDDED.get(hwnd)
    if entry is None or not AVAILABLE:
        return False
    host = entry[0]
    return bool(_user32.IsWindow(host)) and _handle(_user32.GetParent(hwnd)) == host


def embed(hwnd) -> bool:
    """Move ``hwnd`` under the desktop icons, keeping its on-screen position."""
    hwnd = _handle(hwnd)
    if not AVAILABLE or not hwnd:
        return False
    if is_embedded(hwnd):
        if embedding_alive(hwnd):
            return True
        _EMBEDDED.pop(hwnd, None)  # Explorer restarted: embed into the new desktop.
    target = icon_layer_host()
    if target is None:
        logger.info("Desktop icon layer not found; staying a normal window")
        return False
    host, insert_after = target
    style = int(_user32.GetWindowLongPtrW(hwnd, _GWL_STYLE))
    rect = _window_rect(hwnd)
    _user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, (style & ~_WS_POPUP) | _WS_CHILD)
    if not _user32.SetParent(hwnd, host) and _handle(_user32.GetParent(hwnd)) != host:
        _user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, style)
        logger.info("SetParent into the desktop failed (error %s)", ctypes.get_last_error())
        return False
    origin = wintypes.POINT(0, 0)
    _user32.ClientToScreen(host, ctypes.byref(origin))
    x, y, width, height = rect
    _user32.SetWindowPos(
        hwnd,
        insert_after,
        x - origin.x,
        y - origin.y,
        width,
        height,
        _SWP_NOACTIVATE | _SWP_SHOWWINDOW | _SWP_FRAMECHANGED,
    )
    _EMBEDDED[hwnd] = (host, style, rect)
    return True


def unembed(hwnd) -> bool:
    """Return ``hwnd`` to an ordinary bottom-most top-level window where it was."""
    hwnd = _handle(hwnd)
    entry = _EMBEDDED.pop(hwnd, None)
    if entry is None or not AVAILABLE:
        return False
    _host, style, _rect = entry
    screen_rect = _window_rect(hwnd)  # still the position the user sees
    _user32.SetParent(hwnd, None)
    _user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, style)
    x, y, width, height = screen_rect
    _user32.SetWindowPos(
        hwnd,
        _HWND_BOTTOM,
        x,
        y,
        width,
        height,
        _SWP_NOACTIVATE | _SWP_SHOWWINDOW | _SWP_FRAMECHANGED,
    )
    return True


def z_order_below(hwnd, sibling) -> bool:
    """True when ``hwnd`` comes after ``sibling`` among the same parent's children."""
    if not AVAILABLE:
        return False
    current = _handle(_user32.GetWindow(_handle(sibling), 2))  # GW_HWNDNEXT
    while current:
        if current == _handle(hwnd):
            return True
        current = _handle(_user32.GetWindow(current, 2))
    return False
