# -*- coding: utf-8 -*-
"""Let clicks pass through the locked calendar to the desktop underneath.

While lock mode is on (and the option is enabled) the main window and any
floating panel windows ignore the mouse: clicks, scrolls and drags reach the
desktop icons and files behind the calendar. The window gets no mouse events,
so the cursor is polled instead. Resting it on the on-screen "unlock" button
for a moment makes the window take clicks again until the cursor leaves it,
so the lock can still be released by mouse. The tray menu and the lock
shortcut (when the app is active) also release it.

Optionally ("behind desktop icons") the locked window is also placed between
the wallpaper and the desktop icons, so icons draw on top of the calendar. That
uses the desktop window structure (infrastructure/runtime/desktop_embed.py);
when it is unavailable the lock falls back to plain click-through.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor

logger = logging.getLogger(__name__)

LOCK_CLICK_THROUGH_KEY = "lock_click_through"
LOCK_BEHIND_ICONS_KEY = "lock_behind_desktop_icons"
# Re-check an embedded window (Explorer restarts drop it) every this many polls (~1 s).
_EMBED_CHECK_TICKS = 25
# Polling the cursor is cheap; a short interval makes the button answer at once.
_POLL_MS = 40
# Long enough that sweeping across the button on the way to a desktop icon does
# not make the calendar catch the click, short enough to feel like a hover.
# The button shows an "arming" outline as soon as the pointer touches it.
_PEEK_DWELL_MS = 200
_LEAVE_MARGIN = 16


def _bool_setting(settings, key, default):
    if settings is None:
        return default
    try:
        value = settings.value(key, default)
    except Exception:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def click_through_enabled(settings) -> bool:
    """On unless turned off in the tray menu."""
    return _bool_setting(settings, LOCK_CLICK_THROUGH_KEY, True)


def behind_icons_enabled(settings) -> bool:
    """Off unless chosen in the tray menu: it relies on the desktop's internals."""
    return _bool_setting(settings, LOCK_BEHIND_ICONS_KEY, False)


class _DesktopEmbedder:
    """Thin seam over desktop_embed so tests can stand in for the Windows desktop."""

    @staticmethod
    def supported() -> bool:
        from PyQt6.QtGui import QGuiApplication

        from calendar_app.infrastructure.runtime import desktop_embed

        return desktop_embed.AVAILABLE and QGuiApplication.platformName() == "windows"

    @staticmethod
    def embed(hwnd) -> bool:
        from calendar_app.infrastructure.runtime import desktop_embed

        return desktop_embed.embed(hwnd)

    @staticmethod
    def unembed(hwnd) -> bool:
        from calendar_app.infrastructure.runtime import desktop_embed

        return desktop_embed.unembed(hwnd)

    @staticmethod
    def alive(hwnd) -> bool:
        from calendar_app.infrastructure.runtime import desktop_embed

        return desktop_embed.embedding_alive(hwnd)


embedder = _DesktopEmbedder()


def _input_windows(window):
    """The native windows that make up the calendar: main window and floating panels."""
    handles = []
    handle = window.windowHandle()
    if handle is not None:
        handles.append(handle)
    for name in ("left_dock", "center_dock", "routine_dock", "directive_dock"):
        dock = getattr(window, name, None)
        if dock is None or not dock.isFloating():
            continue
        dock_handle = dock.windowHandle()
        if dock_handle is not None and dock_handle not in handles:
            handles.append(dock_handle)
    return handles


_WS_EX_TRANSPARENT = 0x20
_GWL_EXSTYLE = -20


def _native_styles_available() -> bool:
    import sys

    from PyQt6.QtGui import QGuiApplication

    return sys.platform == "win32" and QGuiApplication.platformName() == "windows"


def _user32():
    import ctypes

    return ctypes.windll.user32


def _native_transparent(handle) -> bool:
    return bool(_user32().GetWindowLongW(int(handle.winId()), _GWL_EXSTYLE) & _WS_EX_TRANSPARENT)


def _set_native_transparent(handle, transparent: bool) -> None:
    """Toggle only WS_EX_TRANSPARENT on the existing layered window.

    Qt's WindowTransparentForInput flag re-initialises the native window (frame
    change, layered/opacity setup, HWND_BOTTOM) at the very moment lock mode
    relayouts the window, and parts of the calendar were left unpainted on
    screen. The extended style alone only changes hit-testing.
    """
    user32 = _user32()
    hwnd = int(handle.winId())
    style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    wanted = (style | _WS_EX_TRANSPARENT) if transparent else (style & ~_WS_EX_TRANSPARENT)
    if wanted != style:
        user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, wanted)


def set_input_transparent(window, transparent: bool) -> None:
    native = _native_styles_available()
    flag = Qt.WindowType.WindowTransparentForInput
    for handle in _input_windows(window):
        try:
            if native:
                _set_native_transparent(handle, transparent)
            elif bool(handle.flags() & flag) != transparent:
                # Platforms without Win32 styles (tests): Qt's own flag.
                handle.setFlag(flag, transparent)
        except (RuntimeError, OSError, ValueError):
            continue


def input_transparent(window) -> bool:
    handles = _input_windows(window)
    if not handles:
        return False
    if _native_styles_available():
        return all(_native_transparent(handle) for handle in handles)
    flag = Qt.WindowType.WindowTransparentForInput
    return all(bool(handle.flags() & flag) for handle in handles)


def _repaint_window(window) -> None:
    """Repaint everything once the lock relayout has settled."""
    try:
        window.update()
        for name in ("left_dock", "center_dock", "routine_dock", "directive_dock"):
            dock = getattr(window, name, None)
            if dock is not None and dock.isVisible():
                dock.update()
        rail = getattr(window, "navigation_rail", None)
        if rail is not None and rail.isVisible():
            rail.update()
    except RuntimeError:
        pass


class LockClickThrough(QObject):
    """Owns the click-through state for one main window."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._active = False
        self._peeking = False
        self._dwell_ms = 0
        self._behind_icons = False
        self._embedded = False
        self._ticks = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def peeking(self) -> bool:
        return self._peeking

    @property
    def embedded(self) -> bool:
        return self._embedded

    def sync(self) -> None:
        window = self._window
        settings = getattr(window, "settings", None)
        locked = bool(getattr(window, "is_locked", False))
        behind = locked and behind_icons_enabled(settings) and embedder.supported()
        # Behind the icons the window cannot take clicks anyway, so it implies
        # click-through even when that option is off.
        wanted = locked and (click_through_enabled(settings) or behind)
        self._active = wanted
        self._behind_icons = behind
        self._dwell_ms = 0
        self._set_peeking(False)
        # A lock toggled while the pointer was arming must not keep the outline.
        _mark_unlock_button(window, "idle")
        if wanted:
            set_input_transparent(window, True)
            self._timer.start()
        else:
            self._timer.stop()
            set_input_transparent(window, False)
        self._sync_embedding()
        # Lock mode hides the top bar and the panels move up; make sure the whole
        # translucent window is pushed to the screen again once that settles.
        for delay in (0, 120):
            QTimer.singleShot(delay, lambda w=window: _repaint_window(w))

    def _hwnd(self) -> int:
        try:
            return int(self._window.winId())
        except (RuntimeError, TypeError, ValueError):
            return 0

    def _sync_embedding(self) -> None:
        """Embed while locked behind the icons and not peeking; otherwise restore."""
        want = self._active and self._behind_icons and not self._peeking
        if want and not self._embedded:
            self._embedded = bool(embedder.embed(self._hwnd()))
            if not self._embedded:
                logger.info("Could not place the calendar behind the desktop icons")
        elif not want and self._embedded:
            embedder.unembed(self._hwnd())
            self._embedded = False
        self._window._desktop_embedded = self._embedded

    def _unlock_button_rect(self) -> QRect | None:
        button = getattr(self._window, "_lock_overlay_toggle_btn", None)
        if button is None or not button.isVisible():
            return None
        return QRect(button.mapToGlobal(QPoint(0, 0)), button.size())

    def _tick(self) -> None:
        if not self._active:
            self._timer.stop()
            return
        window = self._window
        self._ticks += 1
        if self._behind_icons and not self._peeking and self._ticks % _EMBED_CHECK_TICKS == 0:
            # Explorer restarts recreate the desktop and drop the embedded window.
            if self._embedded and not embedder.alive(self._hwnd()):
                self._embedded = False
            self._sync_embedding()
        pos = QCursor.pos()
        rect = self._unlock_button_rect()
        if self._peeking:
            # Only the area around the button takes clicks. The window covers most
            # of the screen, so waiting for the pointer to leave the whole window
            # kept every desktop icon under it unclickable after one rollover.
            near = (
                rect.adjusted(-_LEAVE_MARGIN, -_LEAVE_MARGIN, _LEAVE_MARGIN, _LEAVE_MARGIN)
                if rect is not None
                else None
            )
            if near is None or (not near.contains(pos) and not mouse_buttons_held()):
                # A press that started on the button finishes before handing back.
                self._dwell_ms = 0
                self._set_peeking(False)
            return
        # Another code path (always-on-top, desktop mode) can reset window flags.
        if not input_transparent(window):
            set_input_transparent(window, True)
        # Dragging a desktop icon (or a selection box) across the button must not
        # make the calendar catch the drop.
        if rect is not None and rect.contains(pos) and not mouse_buttons_held():
            if self._dwell_ms == 0:
                _mark_unlock_button(self._window, "arming")
            self._dwell_ms += _POLL_MS
            if self._dwell_ms >= _PEEK_DWELL_MS:
                self._set_peeking(True)
        else:
            if self._dwell_ms:
                _mark_unlock_button(self._window, "idle")
            self._dwell_ms = 0

    def _set_peeking(self, peeking: bool) -> None:
        peeking = bool(peeking) and self._active
        changed = peeking != self._peeking
        self._peeking = peeking
        if changed:
            # Peeking lifts the window above the icons so the button can be clicked.
            self._sync_embedding()
        if self._active:
            set_input_transparent(self._window, not peeking)
        if changed:
            _mark_unlock_button(self._window, "ready" if peeking else "idle")


def _mark_unlock_button(window, state) -> None:
    """Show the unlock button's state: idle, arming (pointer on it) or ready to click."""
    if state is True:
        state = "ready"
    elif state is False:
        state = "idle"
    button = getattr(window, "_lock_overlay_toggle_btn", None)
    if button is None:
        return
    from calendar_app.infrastructure.i18n import t

    if state == "idle":
        style, text = "", t("lock.overlay_unlock", "고정 해제")
    else:
        from calendar_app.shared.ui_tokens import get_ui_tokens

        tokens = get_ui_tokens(settings=getattr(window, "settings", None))
        accent = tokens.get("accent", "#4da6ff")
        if state == "arming":
            style = f"QPushButton {{ border: 2px dashed {accent}; }}"
            text = button.text()
        else:
            style = f"QPushButton {{ border: 2px solid {accent}; font-weight: 700; }}"
            text = t("lock.overlay_unlock_ready", "클릭하면 잠금 해제")
    if button.styleSheet() == style and button.text() == text:
        return
    button.setStyleSheet(style)
    button.setText(text)
    # The ready text is longer; refit the button so it is not clipped. The button
    # is anchored to the bottom-right corner, so it grows to the left.
    refit = getattr(window, "_update_lock_overlay_geometry", None)
    if callable(refit):
        import contextlib

        with contextlib.suppress(RuntimeError):
            refit()


def mouse_buttons_held() -> bool:
    """True while a mouse button is down anywhere, even outside this app."""
    import sys

    if sys.platform == "win32" and _native_styles_available():
        user32 = _user32()
        # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON; the high bit means "down now".
        return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x01, 0x02, 0x04))
    from PyQt6.QtGui import QGuiApplication

    return QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton


def sync_lock_click_through(window) -> LockClickThrough:
    controller = getattr(window, "_lock_click_through", None)
    if controller is None:
        controller = LockClickThrough(window)
        window._lock_click_through = controller
    try:
        controller.sync()
    except Exception:
        logger.exception("Lock click-through could not be applied")
    return controller
