# -*- coding: utf-8 -*-
"""KeyDeck zoom keeps rendered content, resize handles and input geometry aligned."""

from copy import deepcopy
from unittest.mock import patch

from PyQt6.QtCore import QPoint, QPointF, QRect, QSettings, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QWidget
import pytest

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.renderer import DeckGeometry
from calendar_app.presentation.widgets.overlay_launcher_deck import (
    DATA_KEY,
    OverlayLauncherDeckWidget,
)


@pytest.fixture
def deck_widget(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "keydeck-resize.ini"), QSettings.Format.IniFormat)
    widget = OverlayLauncherDeckWidget(owner)
    widget._set("enabled", True)
    widget.deck()["sound_enabled"] = False
    widget.apply_initial_settings()
    widget.move(160, 160)
    widget._canvas._armed_at = 0.0
    app.processEvents()
    yield widget
    widget.close()
    owner.close()
    app.processEvents()


def _snapshot(widget):
    return {key: widget.owner.settings.value(key) for key in widget.owner.settings.allKeys()}


def _assert_tight_bounds(widget):
    QApplication.processEvents()
    geometry = widget._canvas.renderer.geometry
    assert widget.size() == geometry.size()
    assert widget.face.size() == geometry.size()
    assert widget._canvas.size() == geometry.size()
    assert widget._canvas.content_offset() == QPointF()


@pytest.mark.parametrize("scale", [60, 100, 220])
@pytest.mark.parametrize("region", ["left", "right", "top", "bottom"])
def test_visible_case_edges_resize_without_searching_the_shadow_margin(deck_widget, scale, region):
    deck_widget._set_scale(scale)
    _assert_tight_bounds(deck_widget)
    rect = deck_widget._canvas.renderer.geometry.case_rect
    point = {
        "left": QPoint(round(rect.left()) + 1, round(rect.center().y())),
        "right": QPoint(round(rect.right()) - 1, round(rect.center().y())),
        "top": QPoint(round(rect.center().x()), round(rect.top()) + 1),
        "bottom": QPoint(round(rect.center().x()), round(rect.bottom()) - 1),
    }[region]
    assert not deck_widget._canvas.is_interactive_at(QPointF(point))
    assert deck_widget._resize_corner_at(point) == region
    before = QRect(deck_widget.geometry())
    QTest.mousePress(
        deck_widget._canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )
    assert deck_widget._resize_origin_global is not None
    QTest.mouseRelease(
        deck_widget._canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )
    assert deck_widget.geometry() == before


def _mouse_move(widget, global_point, *, pressed=True):
    face = widget.face
    QApplication.sendEvent(
        face,
        QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(face.mapFromGlobal(global_point)),
            QPointF(global_point),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def _corner(widget, corner):
    rect = widget.face.rect()
    return {
        "bottom_right": rect.bottomRight() - QPoint(4, 4),
        "bottom_left": rect.bottomLeft() + QPoint(4, -4),
        "top_right": rect.topRight() + QPoint(-4, 4),
        "top_left": rect.topLeft() + QPoint(4, 4),
    }[corner]


def _edge_anchor(rect, edge):
    return {
        "left": QPoint(rect.right() + 1, rect.center().y()),
        "right": QPoint(rect.left(), rect.center().y()),
        "top": QPoint(rect.center().x(), rect.bottom() + 1),
        "bottom": QPoint(rect.center().x(), rect.top()),
    }[edge]


def _edge_point(widget, edge):
    rect = widget.face.rect()
    return {
        "left": QPoint(2, rect.center().y()),
        "right": QPoint(rect.right() - 2, rect.center().y()),
        "top": QPoint(rect.center().x(), 2),
        "bottom": QPoint(rect.center().x(), rect.bottom() - 2),
    }[edge]


@pytest.mark.parametrize("target", [(842, 462), (930, 120), (160, 960), (9999, 8888), (12, 8)])
def test_live_irregular_requests_keep_intrinsic_geometry_and_do_not_save(deck_widget, target):
    before = deepcopy(deck_widget.deck())
    settings = _snapshot(deck_widget)
    deck_widget._fit_font_to_size(*target, live=True)
    _assert_tight_bounds(deck_widget)
    assert 0.6 <= deck_widget._canvas.renderer.geometry.scale <= 2.2
    assert deck_widget.deck() == before
    assert _snapshot(deck_widget) == settings
    assert deck_widget._canvas._live_box is None


@pytest.mark.parametrize("percent", [60, 75, 133, 175, 220])
def test_committing_the_exact_preview_never_jumps_a_pixel_or_changes_keys(deck_widget, percent):
    probe = DeckGeometry(deck_widget.deck(), scale=percent / 100.0)
    deck_widget._fit_font_to_size(probe.width, probe.height, live=True)
    geometry = QRect(deck_widget.geometry())
    keys = deepcopy(deck_widget.deck()["pages"])
    preview_percent = deck_widget._live_scale_percent
    deck_widget._fit_font_to_size(deck_widget.width(), deck_widget.height())
    assert deck_widget.geometry() == geometry
    assert deck_widget.deck()["scale"] == preview_percent
    assert deck_widget.deck()["pages"] == keys
    assert deck_widget._canvas._live_scale is None
    assert deck_widget._canvas._live_box is None
    assert deck_widget._get("fixed_w") is None
    assert deck_widget._get("fixed_h") is None
    _assert_tight_bounds(deck_widget)


@pytest.mark.parametrize("percent", [10, 60, 100, 220, 500])
def test_zoom_reset_and_hidden_window_always_fit_rendered_bounds(deck_widget, percent):
    deck_widget.hide()
    origin = QPoint(deck_widget.pos())
    deck_widget._set_scale(percent)
    assert deck_widget.deck()["scale"] == max(60, min(percent, 220))
    _assert_tight_bounds(deck_widget)
    deck_widget.set_enabled(True)
    _assert_tight_bounds(deck_widget)
    assert deck_widget.pos() == origin
    deck_widget._fit_font_to_size(980, 830, live=True)
    deck_widget._action_reset_size()
    assert deck_widget.deck()["scale"] == 100
    assert deck_widget._live_scale_percent is None
    assert deck_widget._canvas._live_scale is None
    _assert_tight_bounds(deck_widget)


@pytest.mark.parametrize(
    "corner,delta",
    [
        ("bottom_right", QPoint(260, 35)),
        ("bottom_left", QPoint(-260, 35)),
        ("top_right", QPoint(260, -35)),
        ("top_left", QPoint(-260, -35)),
    ],
)
def test_drag_preview_commit_and_undo_preserve_opposite_corner(deck_widget, corner, delta):
    before = QRect(deck_widget.geometry())
    original_deck = deepcopy(deck_widget.deck())
    anchor = deck_widget._anchor_point_for_corner(
        corner, deck_widget.pos(), (deck_widget.width(), deck_widget.height())
    )
    start = _corner(deck_widget, corner)
    destination = deck_widget.face.mapToGlobal(start) + delta
    QTest.mousePress(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    _mouse_move(deck_widget, destination)
    _assert_tight_bounds(deck_widget)
    assert (
        deck_widget._anchor_point_for_corner(
            corner, deck_widget.pos(), (deck_widget.width(), deck_widget.height())
        )
        == anchor
    )
    assert deck_widget.deck()["scale"] == original_deck["scale"]
    QTest.mouseRelease(
        deck_widget.face,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        deck_widget.face.mapFromGlobal(destination),
    )
    _assert_tight_bounds(deck_widget)
    assert (
        deck_widget._anchor_point_for_corner(
            corner, deck_widget.pos(), (deck_widget.width(), deck_widget.height())
        )
        == anchor
    )
    assert deck_widget._last_placement is not None
    deck_widget._undo_placement()
    assert deck_widget.geometry() == before
    assert deck_widget.deck() == original_deck
    _assert_tight_bounds(deck_widget)


@pytest.mark.parametrize("cancel", ["escape", "lost_release", "lock"])
def test_canceled_drag_restores_saved_zoom_position_content_and_bounds(deck_widget, cancel):
    before = QRect(deck_widget.geometry())
    deck = deepcopy(deck_widget.deck())
    start = _corner(deck_widget, "bottom_right")
    destination = deck_widget.face.mapToGlobal(start) + QPoint(110, 88)
    QTest.mousePress(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    _mouse_move(deck_widget, destination)
    assert deck_widget._canvas._live_scale is not None
    if cancel == "escape":
        QTest.keyClick(deck_widget, Qt.Key.Key_Escape)
    elif cancel == "lost_release":
        _mouse_move(deck_widget, destination, pressed=False)
    else:
        deck_widget._set_placement_locked(True)
    assert deck_widget.geometry() == before
    assert deck_widget.deck() == deck
    assert deck_widget._live_scale_percent is None
    assert deck_widget._canvas._live_scale is None
    _assert_tight_bounds(deck_widget)


def test_click_jitter_and_locked_corner_never_start_zoom(deck_widget):
    before = QRect(deck_widget.geometry())
    settings = _snapshot(deck_widget)
    start = _corner(deck_widget, "bottom_right")
    destination = deck_widget.face.mapToGlobal(start) + QPoint(1, 1)
    QTest.mousePress(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    _mouse_move(deck_widget, destination)
    QTest.mouseRelease(
        deck_widget.face,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start + QPoint(1, 1),
    )
    assert deck_widget.geometry() == before
    assert _snapshot(deck_widget) == settings
    deck_widget._set_placement_locked(True)
    QTest.mousePress(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    _mouse_move(deck_widget, destination + QPoint(80, 90))
    QTest.mouseRelease(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    assert deck_widget.geometry() == before
    assert deck_widget._canvas._live_scale is None


@pytest.mark.parametrize("accept", [False, True])
def test_precise_dialog_cancel_and_accept_remain_proportional_and_reversible(deck_widget, accept):
    before = QRect(deck_widget.geometry())
    deck = deepcopy(deck_widget.deck())

    def edit(dialog):
        dialog.fields["x"].setValue(120)
        dialog.fields["y"].setValue(135)
        dialog.fields["width"].setValue(before.width() + 150)
        assert deck_widget.geometry() == before
        assert deck_widget.deck() == deck
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    with patch("calendar_app.presentation.widgets.overlay_base.WidgetPlacementDialog.exec", edit):
        deck_widget._open_placement_dialog()
    if accept:
        assert deck_widget.pos() == QPoint(120, 135)
        assert deck_widget.deck()["scale"] > deck["scale"]
        _assert_tight_bounds(deck_widget)
        deck_widget._undo_placement()
    assert deck_widget.geometry() == before
    assert deck_widget.deck() == deck
    _assert_tight_bounds(deck_widget)


def test_new_deck_and_restart_do_not_inherit_stale_preview_scale(deck_widget):
    deck_widget._fit_font_to_size(960, 780, live=True)
    replacement = m.build_template_deck("command_bar", "walnut_studio")
    deck_widget._apply_deck(replacement)
    assert deck_widget._live_scale_percent is None
    assert deck_widget._canvas._live_scale is None
    _assert_tight_bounds(deck_widget)
    deck_widget._fit_font_to_size(900, 800)
    deck_widget.save_position()
    stored = m.deck_from_json(deck_widget._get(DATA_KEY))
    restored = OverlayLauncherDeckWidget(deck_widget.owner)
    try:
        restored.apply_initial_settings()
        assert restored.deck() == stored
        _assert_tight_bounds(restored)
    finally:
        restored.close()


def test_key_and_header_controls_keep_priority_after_live_zoom(deck_widget):
    canvas = deck_widget._canvas
    deck_widget._fit_font_to_size(960, 830, live=True)
    _assert_tight_bounds(deck_widget)
    key = deck_widget.deck()["pages"][0]["keys"][0]
    point = canvas.renderer.geometry.key_rect(key).center().toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert canvas.is_pressing()
    assert deck_widget._resize_origin_global is None
    assert deck_widget._drag_offset is None
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert not canvas.is_pressing()
    deck_widget._set_scale(150)
    with patch.object(deck_widget, "_open_settings") as settings:
        gear = canvas.renderer.geometry.gear_rect.center().toPoint()
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, gear)
        assert deck_widget._resize_origin_global is None
        settings.assert_called_once()


@pytest.mark.parametrize("edge", ["left", "right", "top", "bottom"])
@pytest.mark.parametrize("growth,expected", [(80, None), (9000, 220), (-9000, 60)])
def test_side_drag_is_proportional_anchored_and_stable_at_scale_limits(
    deck_widget, edge, growth, expected
):
    before = QRect(deck_widget.geometry())
    pages = deepcopy(deck_widget.deck()["pages"])
    anchor = _edge_anchor(before, edge)
    point = _edge_point(deck_widget, edge)
    assert deck_widget._resize_corner_at(point) == edge
    start_global = deck_widget.face.mapToGlobal(point)
    delta = {
        "left": QPoint(-growth, 0),
        "right": QPoint(growth, 0),
        "top": QPoint(0, -growth),
        "bottom": QPoint(0, growth),
    }[edge]
    destination = start_global + delta
    QTest.mousePress(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )
    _mouse_move(deck_widget, destination)
    _assert_tight_bounds(deck_widget)
    preview = QRect(deck_widget.geometry())
    assert _edge_anchor(preview, edge) == anchor
    assert abs(preview.width() / preview.height() - before.width() / before.height()) < 0.02
    assert 60 <= deck_widget._live_scale_percent <= 220
    if expected is not None:
        assert deck_widget._live_scale_percent == expected
    QTest.mouseRelease(
        deck_widget.face,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        deck_widget.face.mapFromGlobal(destination),
    )
    assert deck_widget.geometry() == preview
    assert _edge_anchor(deck_widget.geometry(), edge) == anchor
    assert deck_widget.deck()["pages"] == pages
    if expected is not None:
        assert deck_widget.deck()["scale"] == expected
    _assert_tight_bounds(deck_widget)


def test_throttled_rapid_moves_never_restore_an_arbitrary_letterbox(deck_widget):
    start = _corner(deck_widget, "bottom_right")
    origin = deck_widget.face.mapToGlobal(start)
    QTest.mousePress(
        deck_widget.face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    with patch("calendar_app.presentation.widgets.overlay_base.time.monotonic", return_value=100.0):
        _mouse_move(deck_widget, origin + QPoint(80, 60))
        first = QRect(deck_widget.geometry())
        _assert_tight_bounds(deck_widget)
        for delta in (QPoint(500, 1), QPoint(5, 600), QPoint(9000, 300), QPoint(200, 100)):
            _mouse_move(deck_widget, origin + delta)
            assert deck_widget.geometry() == first
            _assert_tight_bounds(deck_widget)
    deck_widget._cancel_placement_gesture()
    _assert_tight_bounds(deck_widget)


def test_small_floating_outer_key_keeps_priority_over_resize_border(deck_widget):
    replacement = m.build_template_deck("macro_3x3", "floating_glass")
    replacement["case"]["header"] = False
    replacement["scale"] = 60
    deck_widget._apply_deck(replacement)
    canvas = deck_widget._canvas
    canvas._armed_at = 0.0
    _assert_tight_bounds(deck_widget)
    key = deck_widget.deck()["pages"][0]["keys"][0]
    rect = canvas.renderer.geometry.key_rect(key)
    point = QPoint(int(rect.left()) + 1, int(rect.center().y()))
    assert canvas.key_at(point) is key
    assert deck_widget._resize_corner_at(point) is not None
    with patch.object(deck_widget, "_on_key_activated"):
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        assert canvas.is_pressing()
        assert deck_widget._resize_origin_global is None
        assert deck_widget._drag_offset is None
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert not canvas.is_pressing()
