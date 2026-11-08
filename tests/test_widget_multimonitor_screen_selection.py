# -*- coding: utf-8 -*-
"""Pure Qt rectangle selection across mixed-DPI islands; no application is created."""

from PyQt6.QtCore import QPoint, QRect
import pytest

from calendar_app.presentation.widgets.widget_mode_geometry import (
    best_available_geometry,
    best_screen_for_rect,
)


class Screen:
    def __init__(self, name, rect, available=None):
        self._name = name
        self.rect = QRect(rect)
        self.available = QRect(available if available is not None else rect)

    def name(self):
        return self._name

    def geometry(self):
        return QRect(self.rect)

    def availableGeometry(self):  # noqa: N802
        return QRect(self.available)


def _islands():
    # Logical widths change with DPI while Windows retains native screen origins.
    return [
        Screen("200-left", QRect(-3840, 0, 1920, 1080)),
        Screen("125-primary", QRect(0, 0, 1536, 864)),
        Screen("100-right", QRect(1920, 0, 1920, 1080)),
    ]


def test_live_pointer_screen_wins_over_the_largest_window_intersection():
    screens = _islands()
    target = QRect(100, 80, 2500, 600)
    assert best_screen_for_rect(screens, target) is screens[1]
    assert best_screen_for_rect(screens, target, QPoint(2000, 100)) is screens[2]


def test_pointer_over_taskbar_still_selects_its_actual_monitor():
    first = Screen("first", QRect(0, 0, 1000, 800))
    second = Screen("second", QRect(1000, 0, 1000, 800), QRect(1000, 0, 1000, 740))
    assert (
        best_screen_for_rect([first, second], QRect(500, 0, 1000, 700), QPoint(1200, 780)) is second
    )


def test_gap_pointer_defers_to_real_window_overlap():
    screens = _islands()
    target = QRect(1700, 80, 400, 300)
    assert best_screen_for_rect(screens, target, QPoint(1800, 100)) is screens[2]


def test_center_in_a_dpi_gap_uses_the_intersected_neighbor_instead_of_primary():
    screens = _islands()
    target = QRect(1700, 80, 400, 300)
    assert all(not screen.geometry().contains(target.center()) for screen in screens)
    assert best_screen_for_rect(screens, target) is screens[2]


def test_largest_intersection_wins_even_when_its_screen_does_not_contain_window_center():
    first = Screen("first", QRect(0, 0, 600, 800))
    second = Screen("second", QRect(900, 0, 1200, 800))
    target = QRect(400, 40, 1000, 500)
    # Center is x=899, outside both monitors; the right monitor owns more area.
    assert best_screen_for_rect([first, second], target) is second


@pytest.mark.parametrize(
    "target,index",
    [
        (QRect(-5000, 100, 200, 200), 0),
        (QRect(5000, 200, 300, 300), 2),
        (QRect(2200, -1500, 400, 300), 2),
        (QRect(-3000, 1800, 200, 200), 0),
        (QRect(1750, 100, 40, 40), 2),
    ],
)
def test_offscreen_and_gap_rectangles_choose_nearest_screen_instead_of_first(target, index):
    screens = _islands()
    assert best_screen_for_rect(screens, target) is screens[index]
    assert best_screen_for_rect(reversed(screens), target) is screens[index]


def test_nearest_uses_rectangle_edges_instead_of_distance_between_screen_centers():
    narrow_near = Screen("near-edge", QRect(0, 0, 100, 100))
    wide_far = Screen("far-edge", QRect(200, 0, 5000, 100))
    assert best_screen_for_rect([wide_far, narrow_near], QRect(110, 20, 20, 20)) is narrow_near


def test_equal_intersection_or_distance_uses_stable_enumeration_order():
    left = Screen("left", QRect(-200, 0, 100, 100))
    right = Screen("right", QRect(100, 0, 100, 100))
    target = QRect(-50, 20, 100, 20)
    assert best_screen_for_rect([left, right], target) is left
    assert best_screen_for_rect([right, left], target) is right


def test_empty_screen_list_and_unusable_screens_return_none():
    class Removed:
        def geometry(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    assert best_screen_for_rect([], QRect(0, 0, 100, 100)) is None
    assert best_screen_for_rect([Removed(), Screen("empty", QRect())], QRect()) is None


def test_fake_screen_with_available_geometry_only_is_supported_without_changing_inputs():
    class AvailableOnly:
        def availableGeometry(self):  # noqa: N802
            return QRect(1920, -200, 800, 600)

    screen = AvailableOnly()
    target = QRect(2100, -100, 400, 300)
    original = QRect(target)
    assert best_screen_for_rect(iter([screen]), target) is screen
    assert target == original


def test_zero_sized_rect_uses_its_position_for_nearest_selection():
    screens = _islands()
    assert best_screen_for_rect(screens, QRect(2500, 100, 0, 0)) is screens[2]


def test_existing_named_geometry_contract_keeps_its_explicit_screen_and_first_fallback():
    screens = _islands()
    assert best_available_geometry(screens, screen_name="100-right") == (
        screens[2].availableGeometry(),
        "100-right",
    )
    assert best_available_geometry(screens) == (screens[0].availableGeometry(), "200-left")
