# -*- coding: utf-8 -*-
"""Problem situations around releasing the overlay lock by mouse while clicks pass through.

Each test is a situation that went wrong or could: the window takes clicks only
around the unlock button, never blocks the desktop for long, and never steals a
drag that merely crosses the button.
"""

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window import desktop_lock
from calendar_app.presentation.main_window import lock_click_through as ct
from tests.test_lock_click_through import _cursor_at, _lock, _transparent, host  # noqa: F401

READY_TICKS = -(-ct._PEEK_DWELL_MS // ct._POLL_MS)  # ceiling division


def _button(window):
    return window._lock_overlay_toggle_btn


def _on_button(window):
    button = _button(window)
    return button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))


def _rest(controller, point, ticks=READY_TICKS):
    with _cursor_at(point):
        for _ in range(ticks):
            controller._tick()


def _peek(window):
    controller = window._lock_click_through
    _rest(controller, _on_button(window))
    assert controller.peeking
    return controller


def _desktop_icon_point(window):
    """A spot inside the (large) window, far from the button: where an icon may be."""
    return window.mapToGlobal(QPoint(40, 40))


def test_reported_bug_icons_under_the_window_work_again_after_one_rollover(host):
    _app, window = host
    _lock(window)
    controller = _peek(window)
    # Moving to a desktop icon that lies under the calendar window...
    _rest(controller, _desktop_icon_point(window), ticks=1)
    # ...hands the clicks back to the desktop at once.
    assert not controller.peeking
    assert _transparent(window)
    assert _button(window).text() == desktop_lock.badge_text(desktop_lock.KIND_FULL)


def test_small_wobble_around_the_button_keeps_it_clickable(host):
    _app, window = host
    _lock(window)
    controller = _peek(window)
    button = _button(window)
    near = button.mapToGlobal(QPoint(-ct._LEAVE_MARGIN // 2, button.height() // 2))
    _rest(controller, near, ticks=1)
    assert controller.peeking and not _transparent(window)


def test_repeated_rollovers_keep_working(host):
    _app, window = host
    _lock(window)
    for _ in range(3):
        controller = _peek(window)
        _rest(controller, _desktop_icon_point(window), ticks=1)
        assert not controller.peeking and _transparent(window)


def test_dragging_across_the_button_does_not_catch_the_drop(host):
    _app, window = host
    _lock(window)
    controller = window._lock_click_through
    with patch.object(ct, "mouse_buttons_held", return_value=True):
        _rest(controller, _on_button(window), ticks=READY_TICKS * 3)
    assert not controller.peeking
    assert _transparent(window)
    assert _button(window).styleSheet() == ""


def test_a_press_started_on_the_button_finishes_before_handing_back(host):
    _app, window = host
    _lock(window)
    controller = _peek(window)
    with patch.object(ct, "mouse_buttons_held", return_value=True):
        _rest(controller, _desktop_icon_point(window), ticks=2)
    assert controller.peeking  # still pressed: no switch mid-click
    _rest(controller, _desktop_icon_point(window), ticks=1)
    assert not controller.peeking and _transparent(window)


def test_ready_text_is_not_clipped_and_stays_in_the_corner(host):
    _app, window = host
    _lock(window)
    button = _button(window)
    right_before = button.geometry().right()
    _peek(window)
    assert button.text() == t("lock.overlay_unlock_ready", "클릭하면 잠금 해제")
    assert button.width() >= button.sizeHint().width()
    assert button.geometry().right() == right_before


def test_hidden_button_ends_the_peek(host):
    _app, window = host
    _lock(window)
    controller = _peek(window)
    _button(window).hide()
    _rest(controller, _on_button(window), ticks=1)
    assert not controller.peeking and _transparent(window)


def test_click_elsewhere_while_peeking_does_not_unlock(host):
    _app, window = host
    _lock(window)
    _peek(window)
    # The lock overlay still covers the window; only the button unlocks.
    overlay_point = QPoint(40, 40)
    target = window.childAt(overlay_point)
    assert target is window.lock_overlay or window.lock_overlay.isAncestorOf(target)
    assert window.is_locked


def test_unlocking_from_the_tray_while_arming_leaves_no_outline(host):
    _app, window = host
    _lock(window)
    controller = window._lock_click_through
    _rest(controller, _on_button(window), ticks=1)
    assert "dashed" in _button(window).styleSheet()
    # Tray / shortcut path: toggles the lock without touching the button.
    _lock(window, False)
    assert _button(window).styleSheet() == ""
    _lock(window)
    assert _button(window).styleSheet() == ""
    assert _button(window).text() == desktop_lock.badge_text(desktop_lock.KIND_FULL)


def test_unlocking_while_peeking_restores_normal_input(host):
    _app, window = host
    _lock(window)
    _peek(window)
    _button(window).click()
    QApplication.processEvents()
    assert not window.is_locked
    assert not window._lock_click_through.peeking
    assert not _transparent(window)


def test_syncing_twice_while_locked_keeps_click_through(host):
    _app, window = host
    _lock(window)
    ct.sync_lock_click_through(window)
    ct.sync_lock_click_through(window)
    assert window._lock_click_through.active and _transparent(window)


def test_polling_stops_when_unlocked(host):
    _app, window = host
    _lock(window)
    controller = window._lock_click_through
    assert controller._timer.isActive()
    _lock(window, False)
    assert not controller._timer.isActive()


@pytest.mark.parametrize("held", (False, True))
def test_mouse_buttons_held_reads_the_platform(held):
    """Off Windows the helper falls back to Qt's own button state."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication

    QApplication.instance() or QApplication([])
    state = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
    with (
        patch.object(ct, "_native_styles_available", return_value=False),
        patch.object(QGuiApplication, "mouseButtons", return_value=state),
    ):
        assert ct.mouse_buttons_held() is held
