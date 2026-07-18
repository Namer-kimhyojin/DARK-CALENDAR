import ctypes
from ctypes import wintypes
import logging

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QGuiApplication

logger = logging.getLogger(__name__)

# Windows API constants
ABM_NEW = 0x0
ABM_REMOVE = 0x1
ABM_QUERYPOS = 0x2
ABM_SETPOS = 0x3
ABM_GETSTATE = 0x4
ABM_GETTASKBARPOS = 0x5
ABM_ACTIVATE = 0x6
ABM_GETAUTOHIDEBAR = 0x7
ABM_SETAUTOHIDEBAR = 0x8
ABM_WINDOWPOSCHANGED = 0x9
ABM_SETSTATE = 0xA

ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]


class WindowsAppBarHandler(QObject):
    """Manages workspace reservation (AppBar) on Windows."""

    def __init__(self, hwnd: int, parent=None):
        super().__init__(parent)
        self._hwnd = hwnd
        self._is_registered = False
        self._reserved_width = 380  # Standard panel width + small margin
        self._edge = ABE_RIGHT

    def register(self, enabled: bool):
        if enabled:
            self._do_register()
        else:
            self._do_unregister()

    def _do_register(self):
        if self._is_registered:
            self._update_pos()
            return

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(abd)
        abd.hWnd = self._hwnd
        abd.uCallbackMessage = 0  # Not using callbacks for now

        res = ctypes.windll.shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
        if res:
            self._is_registered = True
            self._update_pos()
            logger.info("AppBar registered successfully.")
        else:
            logger.error("Failed to register AppBar.")

    def _do_unregister(self):
        if not self._is_registered:
            return

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(abd)
        abd.hWnd = self._hwnd

        ctypes.windll.shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        self._is_registered = False
        logger.info("AppBar unregistered.")

    def _update_pos(self):
        if not self._is_registered:
            return

        # Get screen geometry
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geom = screen.geometry()

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(abd)
        abd.hWnd = self._hwnd
        abd.uEdge = self._edge

        # 1. Query area
        abd.rc.left = geom.left()
        abd.rc.top = geom.top()
        abd.rc.right = geom.right()
        abd.rc.bottom = geom.bottom()

        # For ABE_RIGHT, we restrict the left edge
        if self._edge == ABE_RIGHT:
            abd.rc.left = abd.rc.right - self._reserved_width

        ctypes.windll.shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

        # 2. Set area
        ctypes.windll.shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        # After SETPOS, abd.rc is updated with the actual assigned area
