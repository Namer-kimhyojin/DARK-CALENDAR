# -*- coding: utf-8 -*-
"""Lock mode lets clicks through to the desktop and can still be released by mouse."""

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window import lock_click_through as ct
from tests.test_lock_mode_ui import LockModeHost

FLAG = Qt.WindowType.WindowTransparentForInput


@pytest.fixture
def host():
    app = QApplication.instance() or QApplication([])
    window = LockModeHost()
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    window.deleteLater()
    app.processEvents()


def _lock(window, locked=True):
    window.lock_btn.setChecked(locked)
    window.toggle_lock_mode()
    QApplication.processEvents()


def _transparent(window):
    return bool(window.windowHandle().flags() & FLAG)


def test_locking_passes_clicks_through_and_unlocking_restores_input(host):
    _app, window = host
    assert not _transparent(window)
    _lock(window)
    assert _transparent(window)
    assert window._lock_click_through.active
    _lock(window, False)
    assert not _transparent(window)
    assert not window._lock_click_through.active


def test_option_off_keeps_the_old_blocking_lock(host):
    _app, window = host
    window.settings.setValue(ct.LOCK_CLICK_THROUGH_KEY, False)
    _lock(window)
    assert not _transparent(window)
    # Turning the tray option on while locked applies it at once.
    window.set_lock_click_through(True)
    assert _transparent(window)
    window.set_lock_click_through(False)
    assert not _transparent(window)


def _cursor_at(point):
    return patch.object(ct.QCursor, "pos", return_value=point)


def test_resting_on_the_unlock_button_makes_the_window_clickable(host):
    _app, window = host
    _lock(window)
    controller = window._lock_click_through
    button = window._lock_overlay_toggle_btn
    inside = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))

    # Passing over briefly is not enough: the click must still reach the desktop.
    with _cursor_at(inside):
        controller._tick()
    assert _transparent(window) and not controller.peeking

    with _cursor_at(inside):
        for _ in range(ct._PEEK_DWELL_MS // ct._POLL_MS):
            controller._tick()
    assert controller.peeking
    assert not _transparent(window)
    assert button.text() == t("lock.overlay_unlock_ready", "클릭하면 잠금 해제")

    # Clicking the button now releases the lock as before.
    button.click()
    QApplication.processEvents()
    assert not window.is_locked
    assert not _transparent(window)


def test_leaving_the_window_returns_to_click_through(host):
    _app, window = host
    _lock(window)
    controller = window._lock_click_through
    button = window._lock_overlay_toggle_btn
    inside = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
    with _cursor_at(inside):
        for _ in range(ct._PEEK_DWELL_MS // ct._POLL_MS):
            controller._tick()
    assert controller.peeking

    outside = window.frameGeometry().bottomRight() + QPoint(200, 200)
    with _cursor_at(outside):
        controller._tick()
    assert not controller.peeking
    assert _transparent(window)
    assert button.text() == t("lock.overlay_unlock", "고정 해제")


def test_click_through_is_reapplied_after_window_flags_reset(host):
    _app, window = host
    _lock(window)
    window.windowHandle().setFlag(FLAG, False)  # e.g. an always-on-top toggle
    outside = window.frameGeometry().bottomRight() + QPoint(200, 200)
    with _cursor_at(outside):
        window._lock_click_through._tick()
    assert _transparent(window)


class FakeDesktop:
    """Stands in for the Windows desktop so embedding runs on any platform."""

    def __init__(self, works=True):
        self.works = works
        self.alive_result = True
        self.calls = []

    def supported(self):
        return True

    def embed(self, hwnd):
        self.calls.append("embed")
        return self.works

    def unembed(self, hwnd):
        self.calls.append("unembed")
        return True

    def alive(self, hwnd):
        return self.alive_result


@pytest.fixture
def desktop(monkeypatch):
    fake = FakeDesktop()
    monkeypatch.setattr(ct, "embedder", fake)
    return fake


def test_behind_icons_embeds_while_locked_and_restores_on_unlock(host, desktop):
    _app, window = host
    window.settings.setValue(ct.LOCK_BEHIND_ICONS_KEY, True)
    _lock(window)
    controller = window._lock_click_through
    assert desktop.calls == ["embed"]
    assert controller.embedded and window._desktop_embedded
    assert _transparent(window)
    _lock(window, False)
    assert desktop.calls == ["embed", "unembed"]
    assert not controller.embedded and not window._desktop_embedded


def test_peeking_lifts_the_window_above_the_icons_and_leaving_puts_it_back(host, desktop):
    _app, window = host
    window.settings.setValue(ct.LOCK_BEHIND_ICONS_KEY, True)
    _lock(window)
    controller = window._lock_click_through
    button = window._lock_overlay_toggle_btn
    inside = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
    with _cursor_at(inside):
        for _ in range(ct._PEEK_DWELL_MS // ct._POLL_MS):
            controller._tick()
    assert controller.peeking and not controller.embedded
    assert desktop.calls == ["embed", "unembed"]
    outside = window.frameGeometry().bottomRight() + QPoint(200, 200)
    with _cursor_at(outside):
        controller._tick()
    assert not controller.peeking and controller.embedded
    assert desktop.calls == ["embed", "unembed", "embed"]


def test_explorer_restart_re_embeds(host, desktop):
    _app, window = host
    window.settings.setValue(ct.LOCK_BEHIND_ICONS_KEY, True)
    _lock(window)
    controller = window._lock_click_through
    desktop.alive_result = False  # the desktop window we lived in is gone
    outside = window.frameGeometry().bottomRight() + QPoint(200, 200)
    with _cursor_at(outside):
        for _ in range(ct._EMBED_CHECK_TICKS):
            controller._tick()
    assert desktop.calls == ["embed", "embed"]
    assert controller.embedded


def test_failed_embedding_falls_back_to_click_through(host, monkeypatch):
    _app, window = host
    fake = FakeDesktop(works=False)
    monkeypatch.setattr(ct, "embedder", fake)
    window.settings.setValue(ct.LOCK_BEHIND_ICONS_KEY, True)
    window.settings.setValue(ct.LOCK_CLICK_THROUGH_KEY, False)
    _lock(window)
    controller = window._lock_click_through
    assert not controller.embedded
    # Behind-icons implies click-through even with that option off.
    assert controller.active and _transparent(window)


def test_window_is_not_sent_to_the_bottom_while_embedded(monkeypatch):
    from calendar_app.infrastructure.runtime import desktop_embed
    from calendar_app.presentation.main_window import window_events

    calls = []
    monkeypatch.setattr(window_events.win32_input, "set_window_bottom", calls.append)
    monkeypatch.setattr(desktop_embed, "is_embedded", lambda hwnd: True)
    window_events._set_window_bottom(1234)
    assert calls == []
    monkeypatch.setattr(desktop_embed, "is_embedded", lambda hwnd: False)
    window_events._set_window_bottom(1234)
    assert calls == [1234]


def test_windows_uses_only_the_native_click_through_style(host, monkeypatch):
    """On Windows the Qt flag is never touched: it re-initialised the window mid-relayout."""
    _app, window = host
    styles = {}

    class FakeUser32:
        def GetWindowLongW(self, hwnd, index):
            return styles.get(hwnd, 0x80000)

        def SetWindowLongW(self, hwnd, index, value):
            styles[hwnd] = value
            return 1

    monkeypatch.setattr(ct, "_native_styles_available", lambda: True)
    monkeypatch.setattr(ct, "_user32", lambda: FakeUser32())
    hwnd = int(window.winId())
    _lock(window)
    assert styles[hwnd] & ct._WS_EX_TRANSPARENT
    assert styles[hwnd] & 0x80000  # layered style kept
    assert not _transparent(window)  # Qt flag untouched
    assert ct.input_transparent(window)
    _lock(window, False)
    assert not styles[hwnd] & ct._WS_EX_TRANSPARENT
    assert not ct.input_transparent(window)


def test_unlock_button_answers_quickly(host):
    """The pointer touching the button shows an outline at once; ready within ~0.2 s."""
    _app, window = host
    _lock(window)
    controller = window._lock_click_through
    button = window._lock_overlay_toggle_btn
    inside = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
    assert ct._PEEK_DWELL_MS + ct._POLL_MS <= 300
    with _cursor_at(inside):
        controller._tick()
    assert "dashed" in button.styleSheet() and not controller.peeking
    outside = window.frameGeometry().bottomRight() + QPoint(200, 200)
    with _cursor_at(outside):
        controller._tick()
    assert button.styleSheet() == ""
