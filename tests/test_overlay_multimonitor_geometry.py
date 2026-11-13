# -*- coding: utf-8 -*-
"""Actual overlay placement on logical screen islands, without native buffers."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QRect, QSettings, QSize
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget

_APP = QApplication.instance() or QApplication([])


def screen(rect, available=None):
    area = QRect(rect)
    usable = QRect(available if available is not None else rect)
    return SimpleNamespace(geometry=lambda: area, availableGeometry=lambda: usable)


@pytest.fixture
def clock(tmp_path, monkeypatch):
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "screens.ini"), QSettings.Format.IniFormat)
    host.resize(1200, 900)
    widget = OverlayClockWidget(host)
    widget._timer.stop()
    widget._release_layout_constraints()
    widget.resize(400, 240)
    areas = [screen(QRect(0, 0, 1536, 864)), screen(QRect(1920, 0, 1920, 1080))]
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: areas))
    yield widget, areas
    widget.close()
    widget.deleteLater()
    host.deleteLater()
    _APP.processEvents()


def test_restored_center_in_dpi_gap_does_not_jump_to_owner_primary(clock):
    widget, areas = clock
    # x=1899 center lies in the Windows logical gap; right intersection is real.
    primary = Mock(return_value=areas[0])
    widget.owner.screen = primary
    target = widget._clamp_restored_position(QPoint(1700, 80))
    assert target == QPoint(1920, 80)
    assert widget.size() == QSize(400, 240)
    primary.assert_not_called()


def test_restore_fits_actual_outer_size_before_clamping_on_small_negative_screen(clock):
    widget, areas = clock
    areas[:] = [screen(QRect(-800, -600, 800, 600), QRect(-800, -600, 800, 552))]
    widget.resize(1500, 900)
    font = widget.font_size()
    widget._set("fixed_w", 1500)
    widget._set("fixed_h", 900)
    target = widget._clamp_restored_position(QPoint(-760, -560))
    assert widget.size() == QSize(800, 552)
    assert QRect(areas[0].availableGeometry()).contains(QRect(target, widget.size()))
    assert widget.font_size() == font
    assert widget._get("fixed_w") == 1500 and widget._get("fixed_h") == 900


def test_dpr_like_size_changes_do_not_accumulate_during_drag_and_escape_is_intact(clock):
    widget, areas = clock
    origin = QRect(100, 100, 400, 240)
    widget.setGeometry(origin)
    widget._placement_origin = widget._capture_placement()
    widget._gesture_active = True
    widget._drag_offset = QPoint(100, 60)
    for pointer in [QPoint(2200, 160), QPoint(400, 200)] * 8:
        widget.resize(500, 300)  # Simulated platform proposal, not a user resize.
        widget._move_placement_to(pointer)
        assert widget.size() == origin.size()
        assert widget.pos() == pointer - QPoint(100, 60)
    widget._cancel_placement_gesture()
    assert widget.geometry() == origin
    assert widget._placement_origin is None
    assert widget._last_placement is None


def test_keydeck_screen_fit_changes_only_live_zoom_and_restores_user_size(clock):
    widget, areas = clock
    deck = OverlayLauncherDeckWidget(widget.owner)
    try:
        deck._set_scale(200)
        original_size = QSize(deck.size())
        original_scale = deck.deck()["scale"]
        keys = [dict(key) for key in deck.deck()["pages"][0]["keys"]]
        target_width, target_height = (
            round(original_size.width() * 0.6),
            round(original_size.height() * 0.6),
        )
        small = screen(QRect(1920, 0, target_width, target_height))
        areas[:] = [small]
        deck._fit_screen_rect(QRect(QPoint(1920, 0), original_size), clamp_position=True)
        assert deck.width() <= target_width and deck.height() <= target_height
        assert deck.deck()["scale"] == original_scale == 200
        assert 60 <= deck._live_scale_percent <= 220
        areas[:] = [screen(QRect(0, 0, 3840, 2160))]
        deck._fit_screen_rect(QRect(QPoint(100, 100), original_size), clamp_position=True)
        assert deck.size() == original_size
        assert deck.deck()["scale"] == original_scale
        assert deck.deck()["pages"][0]["keys"] == keys
    finally:
        deck.close()
        deck.deleteLater()
