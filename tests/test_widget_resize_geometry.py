# -*- coding: utf-8 -*-
"""Resize borders stay reachable, and geometry keeps the opposite anchor."""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
import pytest

from calendar_app.presentation.widgets.widget_placement import (
    anchor_resize_rect,
    proportional_size,
    resize_cursor,
    resize_rect,
    resize_region_at,
)

REGIONS = (
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "left",
    "right",
    "top",
    "bottom",
)


@pytest.mark.parametrize(
    "point,region",
    [
        ((4, 4), "top_left"),
        ((235, 4), "top_right"),
        ((4, 115), "bottom_left"),
        ((235, 115), "bottom_right"),
        ((4, 60), "left"),
        ((235, 60), "right"),
        ((120, 4), "top"),
        ((120, 115), "bottom"),
    ],
)
def test_rectangle_has_eight_distinct_accessible_controls(point, region):
    assert resize_region_at(QPoint(*point), QRect(0, 0, 240, 120)) == region


@pytest.mark.parametrize(
    "shape,points",
    [
        (
            "circle",
            (
                (32, 32),
                (168, 32),
                (32, 168),
                (168, 168),
                (1, 100),
                (199, 100),
                (100, 1),
                (100, 199),
            ),
        ),
        (
            "capsule",
            (
                (17, 17),
                (223, 17),
                (17, 83),
                (223, 83),
                (1, 50),
                (239, 50),
                (120, 1),
                (120, 99),
            ),
        ),
    ],
)
def test_round_controls_follow_the_real_curve_instead_of_masked_box_corners(shape, points):
    rect = QRect(0, 0, 200, 200) if shape == "circle" else QRect(0, 0, 240, 100)
    for point, region in zip(points, REGIONS, strict=True):
        assert resize_region_at(QPoint(*point), rect, shape=shape) == region
    for point in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
        assert resize_region_at(point, rect, shape=shape) is None
    assert resize_region_at(rect.center(), rect, shape=shape) is None


def test_vertical_capsule_has_reachable_curved_corners_and_cardinal_edges():
    points = (
        (17, 17),
        (83, 17),
        (17, 223),
        (83, 223),
        (1, 120),
        (99, 120),
        (50, 1),
        (50, 239),
    )
    for point, region in zip(points, REGIONS, strict=True):
        assert resize_region_at(QPoint(*point), QRect(0, 0, 100, 240), "capsule") == region


@pytest.mark.parametrize("shape", ["card", "poster", "circle", "capsule"])
def test_hit_testing_uses_rect_coordinates_and_never_accepts_a_point_outside(shape):
    rect = QRect(100, 200, 240, 120)
    assert resize_region_at(QPoint(220, 202), rect, shape) == "top"
    for point in (QPoint(99, 260), QPoint(340, 260), QPoint(220, 199), QPoint(220, 320)):
        assert resize_region_at(point, rect, shape) is None


@pytest.mark.parametrize("shape", ["card", "circle", "capsule"])
@pytest.mark.parametrize("size", [(80, 40), (16, 8), (8, 8)])
def test_small_widgets_retain_a_center_move_area_with_large_requested_controls(shape, size):
    rect = QRect(0, 0, *size)
    assert resize_region_at(rect.center(), rect, shape, corner_size=100, edge_width=100) is None


def test_small_rectangle_adapts_controls_and_preserves_middle_of_all_edges():
    rect = QRect(0, 0, 80, 40)
    for point, region in (
        ((0, 0), "top_left"),
        ((79, 0), "top_right"),
        ((0, 39), "bottom_left"),
        ((79, 39), "bottom_right"),
        ((0, 20), "left"),
        ((79, 20), "right"),
        ((40, 0), "top"),
        ((40, 39), "bottom"),
    ):
        assert resize_region_at(QPoint(*point), rect, corner_size=100, edge_width=100) == region
    assert resize_region_at(QPoint(14, 14), rect) is None


def test_empty_rectangle_has_no_resize_controls():
    assert resize_region_at(QPoint(), QRect()) is None


@pytest.mark.parametrize(
    "region,cursor",
    [
        ("top_left", Qt.CursorShape.SizeFDiagCursor),
        ("bottom_right", Qt.CursorShape.SizeFDiagCursor),
        ("top_right", Qt.CursorShape.SizeBDiagCursor),
        ("bottom_left", Qt.CursorShape.SizeBDiagCursor),
        ("left", Qt.CursorShape.SizeHorCursor),
        ("right", Qt.CursorShape.SizeHorCursor),
        ("top", Qt.CursorShape.SizeVerCursor),
        ("bottom", Qt.CursorShape.SizeVerCursor),
        (None, Qt.CursorShape.ArrowCursor),
        ("unknown", Qt.CursorShape.ArrowCursor),
    ],
)
def test_resize_cursor_matches_the_direction(region, cursor):
    assert resize_cursor(region) == cursor


@pytest.mark.parametrize(
    "region,expected",
    [
        ("top_left", (120, 210, 180, 90)),
        ("top_right", (100, 210, 220, 90)),
        ("bottom_left", (120, 200, 180, 110)),
        ("bottom_right", (100, 200, 220, 110)),
        ("left", (120, 200, 180, 100)),
        ("right", (100, 200, 220, 100)),
        ("top", (100, 210, 200, 90)),
        ("bottom", (100, 200, 200, 110)),
    ],
)
def test_free_resize_follows_only_the_dragged_edges_and_keeps_opposite_edges(region, expected):
    origin = QRect(100, 200, 200, 100)
    assert resize_rect(origin, QPoint(20, 10), region) == QRect(*expected)
    assert origin == QRect(100, 200, 200, 100)


@pytest.mark.parametrize(
    "region,expected",
    [
        ("top_left", (40, 170, 260, 130)),
        ("top_right", (100, 170, 260, 130)),
        ("bottom_left", (40, 200, 260, 130)),
        ("bottom_right", (100, 200, 260, 130)),
        ("left", (40, 185, 260, 130)),
        ("right", (100, 185, 260, 130)),
        ("top", (70, 170, 260, 130)),
        ("bottom", (70, 200, 260, 130)),
    ],
)
def test_final_content_fitted_size_keeps_corner_or_opposite_edge_center(region, expected):
    origin = QRect(100, 200, 200, 100)
    assert anchor_resize_rect(origin, QSize(260, 130), region) == QRect(*expected)
    assert anchor_resize_rect(origin, (260, 130), region) == QRect(*expected)


@pytest.mark.parametrize(
    "region,opposite",
    [
        ("top_left", "bottomRight"),
        ("top_right", "bottomLeft"),
        ("bottom_left", "topRight"),
        ("bottom_right", "topLeft"),
    ],
)
def test_proportional_corner_resize_preserves_opposite_corner_even_when_drag_crosses_it(
    region, opposite
):
    origin = QRect(100, 200, 200, 100)
    for delta in (QPoint(40, 5), QPoint(-50, -40), QPoint(1000, 1000), QPoint(-1000, -1000)):
        result = resize_rect(origin, delta, region, proportional=True)
        assert getattr(result, opposite)() == getattr(origin, opposite)()
        assert result.width() == result.height() * 2
        assert result.width() >= 80 and result.height() >= 40


@pytest.mark.parametrize(
    "region,expected",
    [
        ("left", (140, 210, 160, 80)),
        ("right", (100, 190, 240, 120)),
        ("top", (105, 205, 190, 95)),
        ("bottom", (95, 200, 210, 105)),
    ],
)
def test_proportional_side_drag_retains_opposite_side_and_cross_axis_center(region, expected):
    origin = QRect(100, 200, 200, 100)
    result = resize_rect(origin, QPoint(40, 5), region, proportional=True)
    assert result == QRect(*expected)
    if region in {"left", "right"}:
        assert result.center().y() == origin.center().y()
    else:
        assert result.center().x() == origin.center().x()


def test_size_limits_apply_without_flipping_or_distorting_the_aspect_ratio():
    origin = QRect(100, 200, 200, 100)
    minimum = resize_rect(
        origin, QPoint(1000, 1000), "top_left", proportional=True, min_size=(90, 60)
    )
    assert minimum == QRect(180, 240, 120, 60)
    maximum = resize_rect(
        origin,
        QPoint(1000, 1000),
        "bottom_right",
        proportional=True,
        min_size=(90, 60),
        max_size=(260, 110),
    )
    assert maximum == QRect(100, 200, 220, 110)
    free = resize_rect(
        origin, QPoint(1000, 1000), "top_left", min_size=(90, 60), max_size=(260, 110)
    )
    assert free == QRect(210, 240, 90, 60)
    contradictory = resize_rect(
        origin,
        QPoint(1000, 1000),
        "bottom_right",
        proportional=True,
        min_size=(120, 60),
        max_size=(100, 50),
    )
    assert contradictory.size() == QSize(120, 60)


def test_rounding_retains_integer_center_when_fitted_dimensions_change_parity():
    origin = QRect(-70, -90, 101, 51)
    for size in ((150, 80), (151, 81), (80, 40)):
        assert anchor_resize_rect(origin, size, "left").center().y() == origin.center().y()
        assert anchor_resize_rect(origin, size, "top").center().x() == origin.center().x()


def test_unknown_region_is_safe_and_legacy_proportional_helper_keeps_its_contract():
    origin = QRect(100, 200, 200, 100)
    assert resize_rect(origin, QPoint(100, 100), "unknown") == origin
    assert resize_rect(QRect(), QPoint(100, 100), "bottom_right") == QRect()
    assert anchor_resize_rect(origin, (260, 130), None) == QRect(100, 200, 260, 130)
    assert anchor_resize_rect(origin, (260, 130), "unknown") == QRect(100, 200, 260, 130)
    assert proportional_size(240, 105, (200, 100)) == (240, 120)
    assert proportional_size(30, 20, (200, 100)) == (80, 40)
    assert proportional_size(240, 105, (0, 100)) == (240, 105)
