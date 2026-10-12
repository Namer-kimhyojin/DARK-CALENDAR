# -*- coding: utf-8 -*-
"""Intentional gestures, reversible geometry and instance-scoped placement locks."""

from unittest.mock import Mock, patch

from PyQt6.QtCore import QPoint, QPointF, QRect, QSettings, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QWidget
import pytest

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.presentation.widgets.widget_placement import WidgetPlacementDialog
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


@pytest.fixture
def clock(tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "placement.ini"), QSettings.Format.IniFormat)
    widget = OverlayClockWidget(owner)
    widget._set("fixed_w", 240)
    widget._set("fixed_h", 100)
    widget._apply_and_resize()
    widget.move(100, 100)
    widget.show()
    _APP.processEvents()
    yield widget
    widget.close()
    owner.close()


def mouse_move(target, point, modifiers=Qt.KeyboardModifier.NoModifier, *, pressed=True):
    QApplication.sendEvent(
        target,
        QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(point),
            QPointF(target.mapToGlobal(point)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton,
            modifiers,
        ),
    )


def gesture(widget, start, end, modifiers=Qt.KeyboardModifier.NoModifier):
    face = widget.face
    QTest.mousePress(face, Qt.MouseButton.LeftButton, modifiers, start)
    mouse_move(face, end, modifiers)
    QTest.mouseRelease(face, Qt.MouseButton.LeftButton, modifiers, end)
    _APP.processEvents()


def settings_snapshot(widget):
    return {key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()}


def test_hover_keeps_content_clear_and_only_nearby_corner_is_marked(clock):
    clock._update_hover_cursor(clock.face.rect().center())
    assert not clock.face.hover_grip
    clock._update_hover_cursor(clock.face.rect().bottomRight() - QPoint(4, 4))
    assert clock.face.hover_grip and clock.face.grip_corner == "bottom_right"
    assert clock._resize_corner_at(QPoint(-100, -100)) is None
    clock._set_placement_locked(True)
    clock._update_hover_cursor(QPoint(4, 4))
    assert not clock.face.hover_grip


@pytest.mark.parametrize("corner", [False, True])
def test_click_and_small_jitter_never_change_geometry_settings_or_history(clock, corner):
    before = QRect(clock.geometry())
    settings = settings_snapshot(clock)
    start = clock.face.rect().bottomRight() - QPoint(4, 4) if corner else clock.face.rect().center()
    clock._overlay_manager_snap = Mock(return_value=QPoint(200, 200))
    gesture(clock, start, start + QPoint(1, 1))
    assert clock.geometry() == before
    assert settings_snapshot(clock) == settings
    assert clock._last_placement is None
    clock._overlay_manager_snap.assert_not_called()


def test_move_can_bypass_snap_and_be_undone_without_changing_content(clock):
    before = QRect(clock.geometry())
    clock._overlay_manager_snap = Mock(return_value=QPoint(5, 5))
    start = clock.face.rect().center()
    gesture(clock, start, start + QPoint(40, 25), Qt.KeyboardModifier.AltModifier)
    assert clock.pos() == before.topLeft() + QPoint(40, 25)
    clock._overlay_manager_snap.assert_not_called()
    clock._undo_placement()
    assert clock.geometry() == before
    assert clock._last_placement is None


@pytest.mark.parametrize(
    "corner,delta",
    [
        ("bottom_right", QPoint(40, 14)),
        ("bottom_left", QPoint(-40, 14)),
        ("top_right", QPoint(40, -14)),
        ("top_left", QPoint(-40, -14)),
    ],
)
def test_proportional_resize_anchors_opposite_corner_and_undo_restores_font(clock, corner, delta):
    before = QRect(clock.geometry())
    font = clock.font_size()
    corners = {
        "bottom_right": clock.face.rect().bottomRight() - QPoint(4, 4),
        "bottom_left": clock.face.rect().bottomLeft() + QPoint(4, -4),
        "top_right": clock.face.rect().topRight() + QPoint(-4, 4),
        "top_left": QPoint(4, 4),
    }
    anchor = clock._anchor_point_for_corner(corner, clock.pos(), (clock.width(), clock.height()))
    gesture(clock, corners[corner], corners[corner] + delta, Qt.KeyboardModifier.ShiftModifier)
    assert abs(clock.width() / clock.height() - before.width() / before.height()) < 0.02
    assert (
        clock._anchor_point_for_corner(corner, clock.pos(), (clock.width(), clock.height()))
        == anchor
    )
    clock._undo_placement()
    assert clock.geometry() == before
    assert clock.font_size() == font


def test_lost_mouse_release_restores_uncommitted_resize(clock):
    before = QRect(clock.geometry())
    start = clock.face.rect().bottomRight() - QPoint(4, 4)
    QTest.mousePress(clock.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    mouse_move(clock.face, start + QPoint(40, 20))
    mouse_move(clock.face, clock.face.rect().center(), pressed=False)
    assert clock.geometry() == before
    assert not clock._resizing
    assert not clock.face.show_grip


def test_placement_lock_survives_restart_and_global_unlock_does_not_override_it(clock):
    before = QRect(clock.geometry())
    clock._set_placement_locked(True)
    clock.set_interaction_locked(True)
    clock.set_interaction_locked(False)
    gesture(clock, clock.face.rect().center(), clock.face.rect().center() + QPoint(40, 25))
    assert clock.geometry() == before
    restored = OverlayClockWidget(clock.owner)
    assert restored.placement_is_locked()
    restored.close()


def test_precision_dialog_is_staged_scroll_safe_and_keyboard_adjustable(clock):
    before = QRect(clock.geometry())
    settings = settings_snapshot(clock)
    dialog = WidgetPlacementDialog(clock)
    field = dialog.fields["x"]
    field.setValue(450)
    wheel = QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(field, wheel)
    assert field.value() == 450
    QTest.keyClick(field, Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier)
    assert field.value() == 460
    dialog.aspect.setChecked(True)
    dialog.fields["width"].setValue(480)
    assert dialog.fields["height"].value() == 200
    dialog.reject()
    assert clock.geometry() == before
    assert settings_snapshot(clock) == settings
    dialog.close()


def test_precision_apply_and_undo_preserve_instance_settings(clock):
    before = QRect(clock.geometry())

    def accept(dialog):
        dialog._set_rect(QRect(170, 130, 320, 150))
        dialog.lock.setChecked(True)
        return QDialog.DialogCode.Accepted

    with patch.object(WidgetPlacementDialog, "exec", accept):
        clock._open_placement_dialog()
    assert clock.geometry() == QRect(170, 130, 320, 150)
    assert clock.placement_is_locked()
    clock._undo_placement()
    assert clock.geometry() == before
    assert clock.placement_is_locked()


def test_keydeck_resize_undo_restores_zoom_and_keys(clock):
    deck = OverlayLauncherDeckWidget(clock.owner)
    deck.show()
    _APP.processEvents()
    original_scale = deck.deck()["scale"]
    keys = [key["id"] for key in deck.deck()["pages"][0]["keys"]]
    start = deck.face.rect().bottomRight() - QPoint(4, 4)
    gesture(deck, start, start + QPoint(120, 90))
    assert deck.deck()["scale"] != original_scale
    deck._undo_placement()
    assert deck.deck()["scale"] == original_scale
    assert [key["id"] for key in deck.deck()["pages"][0]["keys"]] == keys
    deck.close()


def test_snap_ignores_far_neighbors_and_aligns_nearby_right_edges(clock):
    manager = OverlayWidgetManager(clock.owner)
    first = manager.add_instance("clock")
    second = manager.add_instance("clock")
    a, b = manager.get_widget(first), manager.get_widget(second)
    a.resize(240, 100)
    b.resize(200, 100)
    b.move(300, 700)
    b.show()
    screen = Mock()
    screen.availableGeometry.return_value = QRect(-1000, -1000, 3000, 3000)
    with patch(
        "calendar_app.presentation.widgets.overlay_manager.QApplication.screenAt",
        return_value=screen,
    ):
        assert manager.snap_widget_position(first, QPoint(307, 100)) == QPoint(307, 100)
        aligned = b.frameGeometry().right() - a.width() + 1
        assert manager.snap_widget_position(first, QPoint(aligned + 7, 710)).x() == aligned
    manager.remove_all()


def test_unified_window_lock_undo_and_cancel_are_independent_of_work_actions(workspace):
    host, coordinator, widget = workspace
    before = QRect(widget.geometry())
    widget._begin_placement_edit()
    widget.move(before.topLeft() + QPoint(30, 25))
    widget._finish_placement_edit()
    widget._set_placement_locked(True)
    assert not widget.size_grip.isEnabled()
    assert widget.add_btn.isEnabled()
    widget._undo_placement()
    assert widget.geometry() == before
    widget._set_placement_locked(False)
    start = widget.toolbar.rect().center()
    QTest.mousePress(
        widget.toolbar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    mouse_move(widget.toolbar, start + QPoint(1, 1))
    QTest.mouseRelease(
        widget.toolbar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    assert widget.geometry() == before
    widget._begin_placement_edit()
    widget.resize(before.width() + 50, before.height() + 40)
    widget._cancel_placement_edit()
    assert widget.geometry() == before


def test_unified_history_cannot_restore_geometry_from_another_layout(workspace):
    host, coordinator, widget = workspace
    widget._begin_placement_edit()
    widget.move(widget.pos() + QPoint(30, 20))
    widget._finish_placement_edit()
    coordinator.controller.set_layout("dashboard")
    after_switch = QRect(widget.geometry())
    widget._undo_placement()
    assert widget.geometry() == after_switch


def test_unified_grip_shift_resize_is_deliberate_proportional_and_reversible(workspace):
    host, coordinator, widget = workspace
    widget.resize(420, 560)
    _APP.processEvents()
    before = QRect(widget.geometry())
    grip = widget.size_grip
    start = grip.rect().center()
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, start)
    mouse_move(grip, start + QPoint(1, 1), Qt.KeyboardModifier.ShiftModifier)
    assert widget.geometry() == before
    mouse_move(grip, start + QPoint(84, 20), Qt.KeyboardModifier.ShiftModifier)
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, start)
    assert widget.width() > before.width()
    assert abs(widget.width() / widget.height() - before.width() / before.height()) < 0.005
    widget._undo_placement()
    assert widget.geometry() == before
