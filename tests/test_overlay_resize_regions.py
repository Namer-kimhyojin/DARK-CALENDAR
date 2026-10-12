# -*- coding: utf-8 -*-
"""Resize targets must be reachable inside shaped native windows."""

import math
from unittest.mock import Mock

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QSettings, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget

_APP = QApplication.instance() or QApplication([])
_REGIONS = (
    "top_left",
    "top",
    "top_right",
    "right",
    "bottom_right",
    "bottom",
    "bottom_left",
    "left",
)
_CURSORS = {
    "top_left": Qt.CursorShape.SizeFDiagCursor,
    "bottom_right": Qt.CursorShape.SizeFDiagCursor,
    "top_right": Qt.CursorShape.SizeBDiagCursor,
    "bottom_left": Qt.CursorShape.SizeBDiagCursor,
    "left": Qt.CursorShape.SizeHorCursor,
    "right": Qt.CursorShape.SizeHorCursor,
    "top": Qt.CursorShape.SizeVerCursor,
    "bottom": Qt.CursorShape.SizeVerCursor,
}


@pytest.mark.parametrize(
    "point,delta,cursor",
    [
        (QPoint(315, 90), QPoint(70, 0), Qt.CursorShape.SizeHorCursor),
        (QPoint(315, 175), QPoint(70, 30), Qt.CursorShape.SizeFDiagCursor),
    ],
)
def test_active_resize_keeps_cursor_after_leaving_and_escape_restores(
    make_clock, point, delta, cursor
):
    widget = make_clock()
    before = QRect(widget.geometry())
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    _move(widget.face, point + delta)
    assert widget._gesture_active
    QApplication.sendEvent(widget.face, QEvent(QEvent.Type.Leave))
    assert widget.cursor().shape() == cursor
    assert widget.face.show_grip
    QTest.keyClick(widget, Qt.Key.Key_Escape)
    assert widget.geometry() == before
    assert not widget.face.show_grip
    assert widget._last_placement is None


@pytest.fixture
def make_clock(tmp_path):
    widgets = []
    owners = []

    def make(shape="card"):
        owner = QWidget()
        owner.settings = QSettings(
            str(tmp_path / f"resize-{len(widgets)}.ini"), QSettings.Format.IniFormat
        )
        widget = OverlayClockWidget(owner)
        widget._timer.stop()
        widget._set("widget_shape", shape)
        width, height = {
            "card": (320, 180),
            "circle": (320, 320),
            "capsule": (420, 210),
            "poster": (240, 334),
        }[shape]
        widget._set("fixed_w", width)
        widget._set("fixed_h", height)
        widget._apply_and_resize()
        widget.move(300, 200)
        widget.show()
        _APP.processEvents()
        widgets.append(widget)
        owners.append(owner)
        return widget

    yield make
    for widget in widgets:
        widget.close()
        widget.deleteLater()
    for owner in owners:
        owner.close()
        owner.deleteLater()
    _APP.processEvents()


def _point_on_visible_border(widget, region):
    """Choose geometric points independently from the production hit helper."""
    width, height = widget.face.width(), widget.face.height()
    cx, cy = (width - 1) / 2, (height - 1) / 2
    if "_" not in region:
        return {
            "left": QPoint(5, round(cy)),
            "right": QPoint(width - 6, round(cy)),
            "top": QPoint(round(cx), 5),
            "bottom": QPoint(round(cx), height - 6),
        }[region]
    radius = (min(width, height) - 1) / 2
    offset = (radius - 6) / math.sqrt(2)
    center_x = cx
    if widget.widget_shape_id() == "capsule":
        center_x = radius if region.endswith("left") else width - 1 - radius
    return QPoint(
        round(center_x + (-offset if region.endswith("left") else offset)),
        round(cy + (-offset if region.startswith("top") else offset)),
    )


def _move(target, point, modifiers=Qt.KeyboardModifier.NoModifier, *, pressed=True):
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


def _gesture(widget, start, delta, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, modifiers, start)
    _move(widget.face, start + delta, modifiers)
    QTest.mouseRelease(widget.face, Qt.MouseButton.LeftButton, modifiers, start + delta)
    _APP.processEvents()


def _opposite_edge_center(rect, region):
    return {
        "left": QPoint(rect.right(), rect.center().y()),
        "right": QPoint(rect.left(), rect.center().y()),
        "top": QPoint(rect.center().x(), rect.bottom()),
        "bottom": QPoint(rect.center().x(), rect.top()),
    }[region]


@pytest.mark.parametrize("shape", ["circle", "capsule"])
@pytest.mark.parametrize("region", _REGIONS)
def test_all_shaped_resize_targets_are_inside_actual_window_mask(make_clock, shape, region):
    widget = make_clock(shape)
    point = _point_on_visible_border(widget, region)
    assert not widget.mask().isEmpty()
    # Direct Qt event delivery bypasses the OS input mask; check reachability first.
    assert widget.mask().contains(widget.face.mapTo(widget, point))
    assert widget._resize_corner_at(point) == region
    widget._update_hover_cursor(point)
    assert widget.cursor().shape() == _CURSORS[region]
    assert widget.face.hover_grip and widget.face.grip_corner == region


@pytest.mark.parametrize("shape", ["circle", "capsule"])
def test_curved_grip_is_painted_in_the_visible_mask(make_clock, shape):
    widget = make_clock(shape)
    point = _point_on_visible_border(widget, "bottom_right")

    def image():
        pixmap = QPixmap(widget.face.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        widget.face.render(pixmap)
        return pixmap.toImage()

    widget._update_hover_cursor(widget.face.rect().center())
    before = image()
    widget._update_hover_cursor(point)
    after = image()
    area = QRect(point - QPoint(24, 24), point + QPoint(24, 24)).intersected(widget.face.rect())
    visible_changes = sum(
        before.pixel(x, y) != after.pixel(x, y)
        for x in range(area.left(), area.right() + 1)
        for y in range(area.top(), area.bottom() + 1)
        if widget.mask().contains(widget.face.mapTo(widget, QPoint(x, y)))
    )
    assert visible_changes > 0, "The resize mark must appear on the curve, inside the native mask."


_EDGE_DELTAS = (
    ("left", QPoint(-40, 0)),
    ("right", QPoint(40, 0)),
    ("top", QPoint(0, -30)),
    ("bottom", QPoint(0, 30)),
)


@pytest.mark.parametrize("region,delta", _EDGE_DELTAS)
def test_card_edge_drag_changes_only_requested_dimension_and_can_be_undone(
    make_clock, region, delta
):
    widget = make_clock()
    before = QRect(widget.geometry())
    original_font = widget.font_size()
    point = _point_on_visible_border(widget, region)
    assert widget._resize_corner_at(point) == region
    _gesture(widget, point, delta)
    if region in {"left", "right"}:
        assert widget.width() == before.width() + 40
        assert widget.height() == before.height()
    else:
        assert widget.height() == before.height() + 30
        assert widget.width() == before.width()
    assert _opposite_edge_center(widget.geometry(), region) == _opposite_edge_center(before, region)
    assert widget._last_placement is not None
    widget._undo_placement()
    assert widget.geometry() == before
    assert widget.font_size() == original_font


@pytest.mark.parametrize("region,delta", _EDGE_DELTAS)
def test_shift_edge_drag_preserves_ratio_and_opposite_edge_center(make_clock, region, delta):
    widget = make_clock()
    before = QRect(widget.geometry())
    _gesture(
        widget, _point_on_visible_border(widget, region), delta, Qt.KeyboardModifier.ShiftModifier
    )
    assert abs(widget.width() / widget.height() - before.width() / before.height()) < 0.02
    assert _opposite_edge_center(widget.geometry(), region) == _opposite_edge_center(before, region)


@pytest.mark.parametrize("shape", ["circle", "capsule", "poster"])
@pytest.mark.parametrize("region,delta", [("right", QPoint(50, 0)), ("bottom", QPoint(0, 40))])
def test_shaped_edge_drag_keeps_shape_ratio_without_shift(make_clock, shape, region, delta):
    widget = make_clock(shape)
    before = QRect(widget.geometry())
    _gesture(widget, _point_on_visible_border(widget, region), delta)
    assert abs(widget.width() / widget.height() - before.width() / before.height()) < 0.02
    assert _opposite_edge_center(widget.geometry(), region) == _opposite_edge_center(before, region)


@pytest.mark.parametrize("shape", ["card", "circle", "capsule"])
def test_center_stays_a_move_target_and_preserves_dimensions(make_clock, shape):
    widget = make_clock(shape)
    before = QRect(widget.geometry())
    center = widget.face.rect().center()
    assert widget._resize_corner_at(center) is None
    widget._update_hover_cursor(center)
    assert widget.cursor().shape() == Qt.CursorShape.OpenHandCursor
    assert not widget.face.hover_grip
    widget._overlay_manager_snap = Mock(return_value=QPoint(1, 1))
    _gesture(widget, center, QPoint(35, 25), Qt.KeyboardModifier.AltModifier)
    assert widget.geometry().size() == before.size()
    assert widget.pos() == before.topLeft() + QPoint(35, 25)
    widget._overlay_manager_snap.assert_not_called()


@pytest.mark.parametrize("shape", ["card", "circle", "capsule"])
def test_placement_lock_clears_edge_hover_and_prevents_resize(make_clock, shape):
    widget = make_clock(shape)
    before = QRect(widget.geometry())
    point = _point_on_visible_border(widget, "right")
    widget._update_hover_cursor(point)
    assert widget.face.hover_grip
    widget._set_placement_locked(True)
    widget._update_hover_cursor(point)
    assert not widget.face.hover_grip
    assert widget.face.grip_corner is None
    assert widget.cursor().shape() not in _CURSORS.values()
    _gesture(widget, point, QPoint(50, 0))
    assert widget.geometry() == before


@pytest.mark.parametrize("shape", ["card", "circle", "capsule"])
def test_outside_window_is_not_a_resize_target(make_clock, shape):
    widget = make_clock(shape)
    for point in (
        QPoint(-1, 30),
        QPoint(30, -1),
        QPoint(widget.face.width(), 30),
        QPoint(30, widget.face.height()),
    ):
        assert widget._resize_corner_at(point) is None
    if shape != "card":
        assert not widget.mask().contains(QPoint(4, 4))
        assert widget._resize_corner_at(QPoint(4, 4)) is None


@pytest.mark.parametrize("region", ["right", "bottom"])
def test_edge_click_and_small_jitter_leave_geometry_and_history_unchanged(make_clock, region):
    widget = make_clock()
    before = QRect(widget.geometry())
    settings = {key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()}
    _gesture(widget, _point_on_visible_border(widget, region), QPoint(1, 1))
    assert widget.geometry() == before
    assert widget._last_placement is None
    assert {
        key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()
    } == settings


def test_lost_release_on_new_edge_restores_the_opening_placement(make_clock):
    widget = make_clock()
    before = QRect(widget.geometry())
    point = _point_on_visible_border(widget, "left")
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    _move(widget.face, point + QPoint(-40, 0))
    assert widget.geometry() != before
    _move(widget.face, widget.face.rect().center(), pressed=False)
    assert widget.geometry() == before
    assert not widget._resizing
    assert not widget.face.show_grip


@pytest.mark.parametrize("shape", ["card", "circle", "capsule", "poster"])
def test_oversized_drag_reaches_screen_limit_before_release_without_geometry_jump(
    make_clock, monkeypatch, shape
):
    widget = make_clock(shape)
    monkeypatch.setattr(widget, "_screen_bounds", lambda: (1024, 768))
    before = QRect(widget.geometry())
    start = (
        widget.face.rect().bottomRight() - QPoint(5, 5)
        if shape == "card"
        else _point_on_visible_border(widget, "right")
    )
    destination = widget.face.mapToGlobal(start) + QPoint(1000, 1000 if shape == "card" else 0)
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    _move(widget.face, widget.face.mapFromGlobal(destination))
    live = QRect(widget.geometry())
    assert live.width() <= int(1024 * 0.9)
    assert live.height() <= int(768 * 0.85)
    if shape != "card":
        assert abs(live.width() / live.height() - before.width() / before.height()) < 0.02
    QTest.mouseRelease(
        widget.face,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        widget.face.mapFromGlobal(destination),
    )
    _APP.processEvents()
    assert widget.geometry() == live, "Releasing the mouse must keep the previewed size and anchor."
    widget._undo_placement()
    assert widget.geometry() == before


def test_poster_shape_rounding_does_not_cross_screen_limit_and_jump_on_release(
    make_clock, monkeypatch
):
    widget = make_clock("poster")
    monkeypatch.setattr(widget, "_screen_bounds", lambda: (1024, 768))
    widget._set("fixed_w", 250)
    widget._set("fixed_h", 347)
    widget._apply_and_resize()
    start = _point_on_visible_border(widget, "right")
    destination = widget.face.mapToGlobal(start) + QPoint(1000, 0)
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    _move(widget.face, widget.face.mapFromGlobal(destination))
    live = QRect(widget.geometry())
    assert live.width() <= int(1024 * 0.9)
    assert live.height() <= int(768 * 0.85)
    QTest.mouseRelease(
        widget.face,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        widget.face.mapFromGlobal(destination),
    )
    assert widget.geometry() == live


@pytest.mark.parametrize(
    "shape,stored_size,ratio",
    [("circle", (1400, 1400), 1.0), ("capsule", (2400, 1200), 2.0), ("poster", (900, 1250), 0.72)],
)
def test_oversized_saved_shape_is_stable_after_restart_show_and_reapply(
    make_clock, monkeypatch, shape, stored_size, ratio
):
    original = make_clock(shape)
    original._set("fixed_w", stored_size[0])
    original._set("fixed_h", stored_size[1])
    original.close()
    monkeypatch.setattr(OverlayClockWidget, "_screen_bounds", lambda self: (1024, 768))
    restored = OverlayClockWidget(original.owner)
    restored._timer.stop()
    try:
        restored._apply_and_resize()
        expected = restored.size()
        assert expected.width() <= int(1024 * 0.9)
        assert expected.height() <= int(768 * 0.85)
        assert abs(expected.width() / expected.height() - ratio) < 0.01
        for apply in (
            restored._show_with_correct_size,
            restored._apply_and_resize,
            restored._apply_and_resize,
        ):
            apply()
            _APP.processEvents()
            assert restored.size() == expected
            assert restored._get("fixed_w") == expected.width()
            assert restored._get("fixed_h") == expected.height()
    finally:
        restored.close()
        restored.deleteLater()
        _APP.processEvents()


@pytest.mark.parametrize(
    "limits,stored_size,expected",
    [
        ((972, 1632), (1500, 2083), (972, 1350)),
        ((400, 1000), (500, 694), (400, 556)),
        ((470, 652), (500, 694), (469, 652)),
    ],
)
def test_poster_width_limit_has_a_stable_canonical_size_during_drag_and_reapply(
    make_clock, monkeypatch, limits, stored_size, expected
):
    widget = make_clock("poster")
    monkeypatch.setattr(widget, "_fixed_size_limits", lambda: limits)
    assert widget._bounded_shape_size(*stored_size) == expected
    assert widget._bounded_shape_size(*expected) == expected
    widget._set("fixed_w", stored_size[0])
    widget._set("fixed_h", stored_size[1])
    for _ in range(3):
        widget._apply_and_resize()
        assert (widget.width(), widget.height()) == expected
        assert (widget._get("fixed_w"), widget._get("fixed_h")) == expected

    widget._set("fixed_w", 250)
    widget._set("fixed_h", 347)
    widget._apply_and_resize()
    start = _point_on_visible_border(widget, "right")
    destination = widget.face.mapToGlobal(start) + QPoint(1000, 0)
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    _move(widget.face, widget.face.mapFromGlobal(destination))
    live = QRect(widget.geometry())
    assert (live.width(), live.height()) == expected
    QTest.mouseRelease(
        widget.face,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        widget.face.mapFromGlobal(destination),
    )
    assert widget.geometry() == live
    widget._apply_and_resize()
    assert widget.geometry() == live


@pytest.mark.parametrize("finish", ["escape", "release", "lock", "lost_input", "hide", "undo"])
def test_active_placement_temporarily_grabs_keyboard_and_always_releases_it(make_clock, finish):
    widget = make_clock()
    before = QRect(widget.geometry())
    original_font = widget.font_size()
    start = _point_on_visible_border(widget, "right")
    destination = widget.face.mapToGlobal(start) + QPoint(50, 0)
    assert QWidget.keyboardGrabber() is None
    QTest.mousePress(widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    assert QWidget.keyboardGrabber() is None, "A simple press must keep the user's keyboard focus."
    _move(widget.face, widget.face.mapFromGlobal(destination))
    assert QWidget.keyboardGrabber() is widget
    if finish == "escape":
        QTest.keyClick(widget, Qt.Key.Key_Escape)
    elif finish == "lock":
        widget._set_placement_locked(True)
    elif finish == "lost_input":
        _move(widget.face, widget.face.rect().center(), pressed=False)
    elif finish == "hide":
        widget.hide()
        _APP.processEvents()
        assert widget._get("fixed_w") == before.width()
        assert widget._get("fixed_h") == before.height()
        assert widget.font_size() == original_font
        assert QWidget.keyboardGrabber() is None
        # Qt can flush a queued live size while hidden; the supported show path
        # reapplies the restored pair before the widget is visible to the user.
        widget._show_with_correct_size()
        _APP.processEvents()
    else:
        QTest.mouseRelease(
            widget.face,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            widget.face.mapFromGlobal(destination),
        )
        assert QWidget.keyboardGrabber() is None
        if finish == "undo":
            widget._undo_placement()
    assert QWidget.keyboardGrabber() is None
    assert not widget._resizing and not widget._gesture_active
    if finish != "release":
        assert widget.geometry() == before


def test_keydeck_normal_key_click_and_grip_jitter_never_take_keyboard_focus(tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "keyboard-priority.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    widget.deck()["sound_enabled"] = False
    widget._canvas.keyActivated.disconnect()
    widget.apply_initial_settings()
    widget.show()
    _APP.processEvents()
    widget._canvas._armed_at = 0.0
    try:
        assert widget.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        canvas = widget._canvas
        key = canvas.renderer.geometry.keys[0]
        point = canvas.renderer.geometry.key_rect(key).center().toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        assert canvas.is_pressing()
        assert QWidget.keyboardGrabber() is None
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        assert QWidget.keyboardGrabber() is None

        start = widget.face.rect().bottomRight() - QPoint(4, 4)
        QTest.mousePress(
            widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
        )
        _move(widget.face, start + QPoint(1, 1))
        assert QWidget.keyboardGrabber() is None
        QTest.mouseRelease(
            widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
        )
        assert QWidget.keyboardGrabber() is None
    finally:
        widget.close()
        widget.deleteLater()
        owner.close()
        owner.deleteLater()
        _APP.processEvents()
