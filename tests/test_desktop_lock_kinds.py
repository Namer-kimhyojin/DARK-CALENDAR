# -*- coding: utf-8 -*-
"""Desktop lock redesign: layout lock vs full lock, the status badge, the one-time intro."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QDockWidget, QSizeGrip
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window import desktop_lock
from tests.test_lock_mode_ui import LockModeHost

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    host = LockModeHost()
    host.size_grip = QSizeGrip(host)
    host.show_toast = MagicMock(name="show_toast")
    host.show()
    app.processEvents()
    yield host
    host.close()
    host.deleteLater()
    app.processEvents()


def _lock(host, locked=True):
    host.lock_btn.setChecked(locked)
    host.toggle_lock_mode()
    QApplication.processEvents()


def _top_widget_at(host, widget):
    centre = widget.mapTo(host, widget.rect().center())
    return host.childAt(centre)


def _blocked_by_lock(host, widget):
    top = _top_widget_at(host, widget)
    blockers = [host.lock_overlay] + [
        getattr(dock, "_lock_mode_blocker", None) for dock in host._iter_lock_mode_docks()
    ]
    return any(b is not None and (top is b or b.isAncestorOf(top)) for b in blockers)


def test_full_lock_is_the_default_and_blocks_input(window):
    assert desktop_lock.lock_kind(window.settings) == desktop_lock.KIND_FULL
    _lock(window)
    assert window.lock_overlay.isVisible()
    assert _blocked_by_lock(window, window.center_dock)
    assert window._lock_click_through.active
    assert not window.search_edit.isEnabled()
    badge = window._lock_overlay_toggle_btn
    assert badge.isVisible()
    assert badge.text() == desktop_lock.badge_text(desktop_lock.KIND_FULL)
    assert not window.size_grip.isEnabled()


def test_layout_lock_freezes_the_layout_but_keeps_the_calendar_usable(window):
    window.settings.setValue(desktop_lock.LOCK_KIND_KEY, desktop_lock.KIND_LAYOUT)
    _lock(window)
    # Nothing blocks the panels or the top bar...
    assert not window.lock_overlay.isVisible()
    assert not _blocked_by_lock(window, window.center_dock)
    assert window.search_edit.isEnabled() and window.add_menu_btn.isEnabled()
    assert not window._lock_click_through.active
    # ...but nothing can be moved, docked or resized.
    for dock in window._iter_lock_mode_docks():
        assert dock.features() == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        assert dock.allowedAreas() == Qt.DockWidgetArea.NoDockWidgetArea
    assert not window.size_grip.isEnabled()
    badge = window._lock_overlay_toggle_btn
    assert badge.isVisible()
    assert badge.text() == desktop_lock.badge_text(desktop_lock.KIND_LAYOUT)
    assert badge.toolTip() == desktop_lock.badge_tooltip(desktop_lock.KIND_LAYOUT, False)


def test_badge_unlocks_in_both_kinds(window):
    for kind in (desktop_lock.KIND_LAYOUT, desktop_lock.KIND_FULL):
        window.settings.setValue(desktop_lock.LOCK_KIND_KEY, kind)
        _lock(window)
        badge = window._lock_overlay_toggle_btn
        badge.click()
        QApplication.processEvents()
        assert not window.is_locked
        assert not badge.isVisible()
        assert window.size_grip.isEnabled()
        for dock in window._iter_lock_mode_docks():
            assert dock.features() != QDockWidget.DockWidgetFeature.NoDockWidgetFeatures


def test_badge_sits_on_the_window_above_the_overlay(window):
    _lock(window)
    badge = window._lock_overlay_toggle_btn
    assert badge.parent() is window
    assert _top_widget_at(window, badge) is badge
    assert badge.accessibleName() == badge.text()
    assert not badge.icon().isNull() or badge.text()


def test_intro_explains_each_kind_once(window):
    _lock(window)
    assert window.show_toast.call_count == 1
    title, message = window.show_toast.call_args.args
    assert message == desktop_lock.intro_message(desktop_lock.KIND_FULL, True)
    _lock(window, False)
    _lock(window)
    assert window.show_toast.call_count == 1  # not again for the same kind
    _lock(window, False)
    window.settings.setValue(desktop_lock.LOCK_KIND_KEY, desktop_lock.KIND_LAYOUT)
    _lock(window)
    assert window.show_toast.call_count == 2
    assert window.show_toast.call_args.args[1] == desktop_lock.intro_message(
        desktop_lock.KIND_LAYOUT, False
    )


def test_intro_matches_the_blocking_full_lock(window):
    window.settings.setValue("lock_click_through", False)
    _lock(window)
    assert window.show_toast.call_args.args[1] == desktop_lock.intro_message(
        desktop_lock.KIND_FULL, False
    )


def test_restoring_a_lock_at_startup_shows_no_intro(window):
    window.is_locked = True  # app_initializer restores the saved state first
    window.lock_btn.setChecked(True)
    window.toggle_lock_mode()
    window.show_toast.assert_not_called()


def test_switching_kind_while_locked_applies_at_once(window):
    _lock(window)
    assert window.lock_overlay.isVisible() and window._lock_click_through.active
    window.set_lock_kind(desktop_lock.KIND_LAYOUT)
    QApplication.processEvents()
    assert window.is_locked
    assert not window.lock_overlay.isVisible()
    assert not window._lock_click_through.active
    assert window._lock_overlay_toggle_btn.text() == desktop_lock.badge_text(
        desktop_lock.KIND_LAYOUT
    )
    window.set_lock_kind(desktop_lock.KIND_FULL)
    QApplication.processEvents()
    assert window.lock_overlay.isVisible() and window._lock_click_through.active


def test_lock_menu_offers_both_kinds_and_full_lock_options(window):
    menu = window.show_lock_menu(window.lock_btn.mapToGlobal(QPoint(2, 2)))
    try:
        actions = [a for a in menu.actions() if not a.isSeparator()]
        texts = [a.text() for a in actions]
        assert texts[0] == t("lock.kind_menu", "고정 방식")
        kinds = [a for a in actions if a.text() in (t("lock.kind_layout"), t("lock.kind_full"))]
        assert len(kinds) == 2 and all(a.isCheckable() for a in kinds)
        assert [a.isChecked() for a in kinds] == [False, True]  # full is the default
        options = actions[-2:]
        assert all(a.isEnabled() for a in options)
        kinds[0].trigger()
        assert desktop_lock.lock_kind(window.settings) == desktop_lock.KIND_LAYOUT
    finally:
        menu.close()
    menu = window.show_lock_menu(window.lock_btn.mapToGlobal(QPoint(2, 2)))
    try:
        options = [a for a in menu.actions() if not a.isSeparator()][-2:]
        # Click-through and behind-icons only apply to full lock.
        assert not any(a.isEnabled() for a in options)
    finally:
        menu.close()


def test_unknown_kind_falls_back_to_full_lock():
    settings = MagicMock()
    settings.value.return_value = "something-else"
    assert desktop_lock.lock_kind(settings) == desktop_lock.KIND_FULL
    assert desktop_lock.lock_kind(None) == desktop_lock.KIND_FULL


def test_desktop_lock_wording_is_unified_in_korean():
    ko = json.loads((ROOT / "locales" / "ko.json").read_text(encoding="utf-8", errors="strict"))
    lock_strings = [
        ko["lock"]["on_hint"],
        ko["lock"]["off_hint"],
        ko["lock"]["overlay_unlock"],
        ko["lock"]["overlay_unlock_hint"],
        ko["lock"]["overlay_unlock_ready"],
        ko["tray"]["lock_mode"],
        ko["topbar"]["lock_mode"],
        ko["shortcut"]["entries"]["lock_mode"]["label"],
        ko["panel"]["help"]["lock"],
    ]
    for text in lock_strings:
        assert "잠금 모드" not in text and "오버레이 잠금" not in text, text
        assert "고정" in text, text
    assert "🔒" not in ko["tray"]["lock_mode"]
