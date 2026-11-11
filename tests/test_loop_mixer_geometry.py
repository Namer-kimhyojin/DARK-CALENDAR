# -*- coding: utf-8 -*-
"""Bound native geometry before allocation; no giant image/window is created."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize
from PyQt6.QtWidgets import QApplication
import pytest

from tests.test_loop_mixer_widget import mixer  # noqa: F401


@pytest.mark.parametrize("entry", ["initial", "force", "fit"])
def test_oversized_saved_or_requested_geometry_is_bounded_before_qwidget_resize(
    mixer, monkeypatch, entry
):
    _host, _manager, _iid, widget, _devices = mixer
    assert not widget.isVisible()
    widget._set("fixed_w", 25479)
    widget._set("fixed_h", 20938)
    widget._set("project_path", "preserve-project.airloop")
    monkeypatch.setattr(
        widget, "screen", lambda: SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 1600, 900))
    )
    monkeypatch.setattr(widget, "devicePixelRatioF", lambda: 1.25)
    requested = []
    monkeypatch.setattr(widget, "resize", lambda width, height: requested.append((width, height)))
    if entry == "initial":
        widget._init_loop_deck_instance()
    elif entry == "force":
        widget._force_resize()
    else:
        widget._fit_font_to_size(25479, 20938)
    assert requested and all(0 < width <= 1600 and 0 < height <= 900 for width, height in requested)
    assert widget._get("project_path") == "preserve-project.airloop"
    assert not widget.isVisible()


def test_repeated_dpr_like_requests_never_feed_exponential_size_back_to_qt(mixer, monkeypatch):
    _host, _manager, _iid, widget, _devices = mixer
    monkeypatch.setattr(
        widget, "screen", lambda: SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 1920, 1080))
    )
    monkeypatch.setattr(widget, "devicePixelRatioF", lambda: 1.25)
    requested = []
    monkeypatch.setattr(widget, "resize", lambda width, height: requested.append((width, height)))
    width, height = 1120, 920
    for _ in range(20):
        widget._fit_font_to_size(round(width * 1.25), round(height * 1.25))
        width, height = requested[-1]
    assert max(max(size) for size in requested) <= 1920
    assert max(width * height * 1.25**2 for width, height in requested) < 16 * 1024 * 1024


def test_reflow_only_repositions_tracks_when_breakpoint_changes(mixer, monkeypatch):
    _host, _manager, _iid, widget, _devices = mixer
    widget.resize(1120, 820)
    widget._reflow_for_width()
    original = widget.grid.removeWidget
    spy = Mock(side_effect=original)
    monkeypatch.setattr(widget.grid, "removeWidget", spy)
    widget.resize(1090, 820)
    for _ in range(20):
        widget._reflow_for_width()
    assert spy.call_count == 0
    widget.resize(520, 820)
    widget._reflow_for_width()
    assert spy.call_count == 6


def test_screen_and_dpr_changes_restore_user_dip_size_instead_of_current_qt_size(
    mixer, monkeypatch
):
    _host, _manager, _iid, widget, _devices = mixer
    state = {"area": QRect(0, 0, 1920, 1032), "dpr": 1.0}
    screen = SimpleNamespace(
        geometry=lambda: state["area"], availableGeometry=lambda: state["area"]
    )
    monkeypatch.setattr(widget, "screen", lambda: screen)
    monkeypatch.setattr(widget, "devicePixelRatioF", lambda: state["dpr"])
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))
    widget._set("fixed_w", 1120)
    widget._set("fixed_h", 920)
    for _ in range(8):
        for area, dpr, expected in (
            (QRect(1018, 1080, 1536, 816), 1.25, QSize(1120, 776)),
            (QRect(1920, 0, 1920, 1032), 1.0, QSize(1120, 920)),
        ):
            state.update(area=area, dpr=dpr)
            # Emulate an unwanted platform geometry suggestion, within safe limits.
            widget.resize(1400, 992)
            widget._apply_screen_geometry_fit()
            assert widget.size() == expected
            widget.save_position()
            assert widget._get("fixed_w") == 1120
            assert widget._get("fixed_h") == 920
    assert widget._mixer.snapshot()["mode"] == "idle"


def test_public_dpr_event_defers_one_fit_and_keeps_explicit_dimensions(mixer, monkeypatch):
    _host, _manager, _iid, widget, _devices = mixer
    widget._set("fixed_w", 960)
    widget._set("fixed_h", 760)
    widget.resize(1200, 900)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.DevicePixelRatioChange))
    assert widget._screen_fit_pending
    QApplication.processEvents()
    assert widget.size() == QSize(960, 760)
    assert not widget._screen_fit_pending


def test_move_uses_original_dip_size_and_stable_fractional_grab_point(mixer, monkeypatch):
    _host, _manager, _iid, widget, _devices = mixer
    screen = SimpleNamespace(
        geometry=lambda: QRect(1018, 1080, 1536, 864),
        availableGeometry=lambda: QRect(1018, 1080, 1536, 816),
    )
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))
    monkeypatch.setattr(widget, "screen", lambda: screen)
    widget._set("fixed_w", 1120)
    widget._set("fixed_h", 920)
    origin = QRect(200, 200, 1120, 920)
    widget._placement_origin = {"rect": origin}
    widget._drag_offset = QPoint(560, 100)
    pointer = QPoint(1700, 1300)
    for _ in range(12):
        widget.resize(1400, 992)
        widget._move_placement_to(pointer)
        assert widget.size() == QSize(1120, 776)
        assert widget.pos() == pointer - QPoint(560, round(100 * 776 / 920))
    widget._placement_origin = None
    widget._drag_offset = None
