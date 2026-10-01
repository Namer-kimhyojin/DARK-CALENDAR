# -*- coding: utf-8 -*-
"""Zoomed gestures, group geometry, locks, layers and preview composition."""

from copy import deepcopy

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.widgets.widget_free_layout import (
    seed_free_layout,
    validate_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_editor_canvas import (
    LayoutEditorCanvas,
    align_selection,
    distribute_selection,
    overlap_pairs,
    selection_bounds,
)
from tests.test_widget_mode_ux import _APP  # noqa: F401


def data():
    draft = seed_free_layout("stacked")
    draft["canvas"] = [640, 800]
    draft["snap"] = False
    rects = {"date": [24, 24, 240, 80], "clock": [400, 40, 120, 64], "work": [24, 300, 220, 120]}
    for block in draft["blocks"]:
        block["enabled"] = block["id"] in rects
        block["locked"] = False
        if block["id"] in rects:
            block["rect"] = rects[block["id"]]
    return validate_free_layout(draft)


@pytest.fixture
def canvas():
    widget = LayoutEditorCanvas(data())
    widget.guides_enabled = False
    widget.show()
    _APP.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    _APP.processEvents()


def drag(canvas, start, end, modifiers=Qt.KeyboardModifier.NoModifier):
    start = canvas.logical_to_screen(start)
    end = canvas.logical_to_screen(end)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, modifiers, start)
    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(end),
        QPointF(canvas.mapToGlobal(end)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )
    QApplication.sendEvent(canvas, event)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, modifiers, end)
    _APP.processEvents()


@pytest.mark.parametrize("zoom", [0.25, 0.5, 1.0, 1.5, 2.0])
def test_zoomed_move_is_in_logical_coordinates_and_one_commit(canvas, zoom):
    canvas.set_zoom(zoom)
    before = canvas.block_rect("date")
    committed = QSignalSpy(canvas.editCommitted)
    drag(canvas, before.center(), before.center() + QPoint(20, 12))
    assert canvas.block_rect("date").topLeft() == before.topLeft() + QPoint(20, 12)
    assert len(committed) == 1
    assert canvas.width() == round(640 * zoom)
    assert canvas.zoom == zoom


@pytest.mark.parametrize("handle", ["nw", "n", "ne", "e", "se", "s", "sw", "w"])
def test_all_eight_handles_resize_while_preserving_opposite_edge(canvas, handle):
    canvas.select_block("date")
    before = canvas.block_rect("date")
    point = canvas.handle_rects()[handle].center().toPoint()
    delta = QPoint(
        -12 if "w" in handle else 12 if "e" in handle else 0,
        -16 if "n" in handle else 16 if "s" in handle else 0,
    )
    drag(canvas, point, point + delta)
    after = canvas.block_rect("date")
    if "w" in handle:
        assert after.right() == before.right()
        assert after.left() == before.left() - 12
    if "e" in handle:
        assert after.left() == before.left()
        assert after.right() == before.right() + 12
    if "n" in handle:
        assert after.bottom() == before.bottom()
        assert after.top() == before.top() - 16
    if "s" in handle:
        assert after.top() == before.top()
        assert after.bottom() == before.bottom() + 16


def test_ctrl_click_and_group_move_keep_relative_positions(canvas):
    QTest.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.block_rect("date").center(),
    )
    QTest.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        canvas.block_rect("clock").center(),
    )
    assert canvas.selected_ids == {"date", "clock"}
    before_date, before_clock = canvas.block_rect("date"), canvas.block_rect("clock")
    drag(canvas, before_date.center(), before_date.center() + QPoint(16, 12))
    assert canvas.block_rect("date").topLeft() == before_date.topLeft() + QPoint(16, 12)
    assert canvas.block_rect("clock").topLeft() == before_clock.topLeft() + QPoint(16, 12)
    assert not canvas.handle_rects()


def test_empty_marquee_selects_enabled_blocks_and_escape_clears(canvas):
    drag(canvas, QPoint(8, 8), QPoint(540, 130))
    assert canvas.selected_ids == {"date", "clock"}
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.selected_ids == set()
    assert canvas.selected_id == ""


def test_group_arrows_clamp_as_a_group_and_delete_only_disables_unlocked(canvas):
    canvas.set_selection({"date", "clock"})
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.block_rect("date").topLeft() == QPoint(25, 34)
    assert canvas.block_rect("clock").topLeft() == QPoint(401, 50)
    original_ids = [block["id"] for block in canvas.data["blocks"]]
    next(block for block in canvas.data["blocks"] if block["id"] == "clock")["locked"] = True
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert [block["id"] for block in canvas.data["blocks"]] == original_ids
    assert not next(block for block in canvas.data["blocks"] if block["id"] == "date")["enabled"]
    assert next(block for block in canvas.data["blocks"] if block["id"] == "clock")["enabled"]


def test_locked_block_can_be_selected_but_cannot_move_resize_or_delete(canvas):
    next(block for block in canvas.data["blocks"] if block["id"] == "date")["locked"] = True
    before = canvas.block_rect("date")
    drag(canvas, before.center(), before.center() + QPoint(40, 40))
    assert canvas.selected_id == "date"
    assert canvas.block_rect("date") == before
    assert not canvas.handle_rects()
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert canvas.block_rect("date") == before
    assert next(block for block in canvas.data["blocks"] if block["id"] == "date")["enabled"]


@pytest.mark.parametrize(
    "snap,modifier,expected",
    [
        (False, Qt.KeyboardModifier.NoModifier, (41, 37)),
        (True, Qt.KeyboardModifier.NoModifier, (40, 40)),
        (True, Qt.KeyboardModifier.AltModifier, (41, 37)),
    ],
)
def test_optional_grid_snap_and_alt_bypass(canvas, snap, modifier, expected):
    canvas.data["snap"] = snap
    before = canvas.block_rect("date")
    drag(canvas, before.center(), before.center() + QPoint(17, 13), modifier)
    assert canvas.block_rect("date").topLeft() == QPoint(*expected)


def test_smart_guides_align_canvas_center_and_alt_bypasses(canvas):
    canvas.guides_enabled = True
    before = canvas.block_rect("date")
    # Logical left198 is2px from center alignment: left200 + halfwidth120 == canvascenter320.
    drag(canvas, before.center(), before.center() + QPoint(174, 150))
    assert canvas.block_rect("date").x() == 200
    canvas.set_data(data())
    drag(
        canvas, before.center(), before.center() + QPoint(174, 150), Qt.KeyboardModifier.AltModifier
    )
    assert canvas.block_rect("date").x() == 198


def test_hit_testing_uses_reverse_saved_order_and_preview_image_is_visible(canvas):
    draft = data()
    for block in draft["blocks"]:
        if block["id"] in {"date", "clock"}:
            block["rect"] = [24, 24, 240, 80]
    order = [block["id"] for block in draft["blocks"] if block["id"] != "date"] + ["date"]
    draft["order"] = order
    canvas.set_data(draft)
    assert canvas._hit(QPoint(100, 60)) == "date"
    pixmap = QPixmap(640, 800)
    pixmap.fill(Qt.GlobalColor.blue)
    canvas.set_preview_image(pixmap)
    assert canvas.grab().toImage().pixelColor(300, 200).blue() == 255
    canvas.set_preview_image(None)


def test_alignment_helpers_are_pure_and_use_canvas_for_single_selection():
    draft = data()
    before = deepcopy(draft)
    single = align_selection(draft, {"date"}, "right")
    assert next(block for block in single["blocks"] if block["id"] == "date")["rect"][0] == 400
    multiple = align_selection(draft, {"date", "clock"}, "top")
    assert {
        block["rect"][1] for block in multiple["blocks"] if block["id"] in {"date", "clock"}
    } == {24}
    assert selection_bounds(draft, {"date", "clock"}).getRect() == (24, 24, 496, 80)
    assert draft == before


def test_equal_gap_distribution_preserves_outer_elements_and_lock():
    draft = data()
    for block in draft["blocks"]:
        if block["id"] in {"date", "clock", "work"}:
            block["rect"] = {
                "date": [0, 40, 160, 100],
                "clock": [180, 40, 100, 100],
                "work": [440, 40, 180, 100],
            }[block["id"]]
    result = distribute_selection(draft, {"date", "clock", "work"}, "x")
    rects = {block["id"]: block["rect"] for block in result["blocks"]}
    assert rects["date"] == [0, 40, 160, 100]
    assert rects["work"] == [440, 40, 180, 100]
    assert rects["clock"][0] == 250
    next(block for block in draft["blocks"] if block["id"] == "clock")["locked"] = True
    assert distribute_selection(draft, {"date", "clock", "work"}, "x") == draft


def test_overlap_detection_ignores_disabled_elements_and_edge_touch():
    draft = data()
    next(block for block in draft["blocks"] if block["id"] == "clock")["rect"] = [200, 40, 120, 64]
    assert ("date", "clock") in overlap_pairs(draft)
    next(block for block in draft["blocks"] if block["id"] == "clock")["rect"] = [264, 40, 120, 64]
    assert not overlap_pairs(draft)


def test_first_press_on_bottom_right_grip_still_resizes_without_preselection(canvas):
    rect = canvas.block_rect("date")
    drag(canvas, rect.bottomRight() - QPoint(5, 5), rect.bottomRight() + QPoint(32, 18))
    assert canvas.block_rect("date").getRect() == (24, 24, 277, 103)


def test_resize_smart_guide_matches_neighbor_edge_and_alt_bypasses(canvas):
    canvas.guides_enabled = True
    canvas.select_block("date")
    point = canvas.handle_rects()["e"].center().toPoint()
    drag(canvas, point, point + QPoint(134, 0))
    assert canvas.block_rect("date").x() + canvas.block_rect("date").width() == 400
    canvas.set_data(data())
    canvas.select_block("date")
    drag(canvas, point, point + QPoint(134, 0), Qt.KeyboardModifier.AltModifier)
    assert canvas.block_rect("date").x() + canvas.block_rect("date").width() == 398


def test_minimum_height_block_center_remains_movable_at_quarter_zoom(canvas):
    draft = data()
    next(block for block in draft["blocks"] if block["id"] == "date")["rect"] = [24, 24, 240, 48]
    canvas.set_data(draft)
    canvas.set_zoom(0.25)
    canvas.select_block("date")
    before = canvas.block_rect("date")
    assert canvas._handle_hit(before.center()) == ""
    drag(canvas, before.center(), before.center() + QPoint(16, 16))
    assert canvas.block_rect("date").getRect() == (40, 40, 240, 48)


def test_alignment_uses_locked_block_as_reference_without_moving_it():
    draft = data()
    clock = next(block for block in draft["blocks"] if block["id"] == "clock")
    clock["locked"] = True
    result = align_selection(draft, {"date", "clock"}, "right")
    assert next(block for block in result["blocks"] if block["id"] == "date")["rect"][0] == 280
    assert next(block for block in result["blocks"] if block["id"] == "clock") == clock


def test_ten_percent_zoom_fits_large_canvas_without_changing_logical_data(canvas):
    draft = data()
    draft["canvas"] = [2400, 1800]
    canvas.set_data(draft)
    before = deepcopy(canvas.data)
    canvas.set_zoom(0.1)
    assert canvas.zoom == 0.1
    assert (canvas.width(), canvas.height()) == (240, 180)
    assert canvas.data == before


def test_wysiwyg_preview_has_no_unselected_wireframes_and_hover_resets(canvas):
    pixmap = QPixmap(640, 800)
    pixmap.fill(Qt.GlobalColor.blue)
    canvas.set_preview_image(pixmap)
    canvas.data["snap"] = False
    border = QPoint(100, 25)
    assert canvas.grab().toImage().pixelColor(border).blue() == 255
    assert canvas.grab().toImage().pixelColor(border).red() == 0
    QTest.mouseMove(canvas, canvas.block_rect("date").center())
    assert canvas._hovered_id == "date"
    image = canvas.grab().toImage()
    assert image.pixelColor(border).rgb() != pixmap.toImage().pixelColor(border).rgb()
    from PyQt6.QtCore import QEvent

    QApplication.sendEvent(canvas, QEvent(QEvent.Type.Leave))
    assert canvas._hovered_id == ""
    assert canvas.grab().toImage().pixelColor(border).red() == 0


def test_real_preview_selection_overlay_keeps_static_pixels_and_edit_only_signals(canvas):
    pixmap = QPixmap(640, 800)
    pixmap.fill(Qt.GlobalColor.blue)
    canvas.set_preview_image(pixmap)
    edits = QSignalSpy(canvas.previewChanged)
    commits = QSignalSpy(canvas.editCommitted)
    canvas.select_block("date")
    image = canvas.grab().toImage()
    assert image.pixelColor(canvas.block_rect("date").center()).blue() == 255
    assert len(edits) == 0
    assert len(commits) == 0
