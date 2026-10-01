# -*- coding: utf-8 -*-
"""Free-layout gestures, draft isolation, precision edits and history."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPalette, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QWidget
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.dialogs.widget_free_layout_editor import WidgetFreeLayoutEditorDialog
from calendar_app.presentation.widgets.widget_free_layout import (
    FREE_LAYOUT_MODE_KEY,
    FREE_LAYOUT_SETTING_KEY,
    read_free_layout,
    seed_free_layout,
    write_free_layout,
)
from tests.test_widget_mode_ux import _APP, Settings, workspace  # noqa: F401


@pytest.fixture
def editor():
    settings = Settings()
    data = seed_free_layout("stacked")
    data["canvas"] = [640, 800]
    for block in data["blocks"]:
        block["enabled"] = block["id"] == "date"
        if block["id"] == "date":
            block["rect"] = [24, 24, 240, 80]
    write_free_layout(settings, data)
    live = QWidget()
    controller = SimpleNamespace(main_window=SimpleNamespace(settings=settings), widget=live)
    controller.apply_free_layout = Mock(
        side_effect=lambda layout: write_free_layout(settings, layout)
    )
    dialog = WidgetFreeLayoutEditorDialog(controller)
    dialog.show()
    _APP.processEvents()
    yield dialog, settings, live
    dialog.close()
    dialog.deleteLater()
    live.deleteLater()
    _APP.processEvents()


def _drag(canvas, start, end, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, modifiers, start)
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(end),
        QPointF(canvas.mapToGlobal(end)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )
    QApplication.sendEvent(canvas, move)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, modifiers, end)
    _APP.processEvents()


@pytest.mark.parametrize(
    "snap,modifier,expected",
    [
        (False, Qt.KeyboardModifier.NoModifier, (41, 37)),
        (True, Qt.KeyboardModifier.NoModifier, (40, 40)),
        (True, Qt.KeyboardModifier.AltModifier, (41, 37)),
    ],
)
def test_drag_uses_optional_snap_and_alt_bypass_without_saving(editor, snap, modifier, expected):
    dialog, settings, _ = editor
    before = deepcopy(settings.values)
    dialog.snap_checkbox.setChecked(snap)
    rect = dialog.canvas.block_rect("date")
    _drag(dialog.canvas, rect.center(), rect.center() + QPoint(17, 13), modifier)
    assert dialog.canvas.block_rect("date").topLeft() == QPoint(*expected)
    assert settings.values == before


def test_resize_grip_changes_size_and_undo_redo_restores_entire_gesture(editor):
    dialog, _, _ = editor
    dialog.snap_checkbox.setChecked(False)
    rect = dialog.canvas.block_rect("date")
    _drag(dialog.canvas, rect.bottomRight() - QPoint(5, 5), rect.bottomRight() + QPoint(32, 18))
    resized = dialog.canvas.block_rect("date")
    assert resized.width() == rect.width() + 37
    assert resized.height() == rect.height() + 23
    assert resized.topLeft() == rect.topLeft()
    dialog.undo_btn.click()
    assert dialog.canvas.block_rect("date") == rect
    dialog.redo_btn.click()
    assert dialog.canvas.block_rect("date") == resized


def test_numeric_position_dimensions_keyboard_and_canvas_bounds(editor):
    dialog, _, _ = editor
    dialog.canvas.select_block("date")
    dialog.rect_spins["x"].setValue(123)
    dialog.rect_spins["w"].setValue(280)
    assert dialog.canvas.block_rect("date").getRect() == (123, 24, 280, 80)
    dialog.canvas.setFocus()
    QTest.keyClick(dialog.canvas, Qt.Key.Key_Right)
    QTest.keyClick(dialog.canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert dialog.canvas.block_rect("date").topLeft() == QPoint(124, 34)
    dialog.rect_spins["x"].setValue(4000)
    rect = dialog.canvas.block_rect("date")
    assert rect.right() < dialog.draft["canvas"][0]
    dialog.canvas_width.setValue(320)
    assert dialog.canvas.block_rect("date").right() < 320


def test_components_reset_history_and_cancel_do_not_change_live_settings(editor):
    dialog, settings, live = editor
    before = deepcopy(settings.values)
    geometry = live.geometry()
    dialog.component_checks["work"].setChecked(True)
    assert next(block for block in dialog.draft["blocks"] if block["id"] == "work")["enabled"]
    before_reset = deepcopy(dialog.draft)
    dialog.preset_combo.setCurrentIndex(dialog.preset_combo.findData("minimal"))
    dialog.reset_btn.click()
    assert dialog.draft == seed_free_layout("minimal")
    dialog.undo_btn.click()
    assert dialog.draft == before_reset
    dialog.cancel_btn.click()
    assert settings.values == before
    assert live.geometry() == geometry
    dialog.controller.apply_free_layout.assert_not_called()


def test_apply_saves_only_edited_configuration_and_scroll_supports_large_canvas(editor):
    dialog, settings, _ = editor
    settings.setValue("widget_mode_filter", "directive")
    dialog.canvas_width.setValue(1800)
    dialog.canvas_height.setValue(1600)
    _APP.processEvents()
    assert dialog.canvas_scroll.horizontalScrollBar().maximum() > 0
    assert dialog.canvas_scroll.verticalScrollBar().maximum() > 0
    dialog.apply_btn.click()
    assert read_free_layout(settings) == dialog.draft
    assert settings.value(FREE_LAYOUT_MODE_KEY) == "free"
    assert settings.value("widget_mode_filter") == "directive"
    dialog.controller.apply_free_layout.assert_called_once()


def test_inspector_wheel_scrolls_without_changing_precision_or_preset(editor):
    dialog, _, _ = editor
    dialog.controls_scroll.setFixedHeight(180)
    dialog.canvas.select_block("date")
    _APP.processEvents()
    for control in (
        dialog.rect_spins["x"],
        dialog.rect_spins["x"].lineEdit(),
        dialog.canvas_width,
        dialog.preset_combo,
        dialog.calendar_mode_combo,
    ):
        before = deepcopy(dialog.draft)
        preset = dialog.preset_combo.currentData()
        scrollbar = dialog.controls_scroll.verticalScrollBar()
        scrollbar.setValue(0)
        control.setFocus()
        event = QWheelEvent(
            QPointF(control.rect().center()),
            QPointF(control.mapToGlobal(control.rect().center())),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(control, event)
        assert dialog.draft == before
        assert dialog.preset_combo.currentData() == preset
        assert scrollbar.value() > 0


def test_calendar_period_changes_in_draft_and_undo_redo_cancel_preserve_saved_period(editor):
    dialog, settings, _ = editor
    original = read_free_layout(settings)["calendar_mode"]
    selected = "month" if original == "week" else "week"
    dialog.calendar_mode_combo.setCurrentIndex(dialog.calendar_mode_combo.findData(selected))
    assert dialog.draft["calendar_mode"] == selected
    assert read_free_layout(settings)["calendar_mode"] == original
    dialog.undo_btn.click()
    assert dialog.draft["calendar_mode"] == original
    dialog.redo_btn.click()
    assert dialog.draft["calendar_mode"] == selected
    dialog.cancel_btn.click()
    assert read_free_layout(settings)["calendar_mode"] == original


def test_inspector_palette_and_native_preview_surfaces_are_both_configured(editor):
    dialog, _, _ = editor
    _APP.processEvents()
    palette = dialog.preferences_tabs.currentWidget().palette()
    assert (
        abs(
            palette.color(QPalette.ColorRole.Base).lightnessF()
            - palette.color(QPalette.ColorRole.Text).lightnessF()
        )
        > 0.3
    )
    dialog._refresh_preview()
    assert not dialog.canvas._preview_image.isNull()
    assert dialog.canvas._preview_image.size().width() == dialog.draft["canvas"][0]


def test_customization_free_display_draft_cancel_and_appearance_apply_preserve_mode(workspace):
    host, coordinator, widget = workspace
    data = seed_free_layout("stacked")
    write_free_layout(host.settings, data)
    before = host.settings.value(FREE_LAYOUT_SETTING_KEY)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.calendar_visibility_checkbox.setChecked(False)
    dialog._change("widget_mode_show_clock", False)
    assert not next(
        block for block in read_free_layout(dialog.draft)["blocks"] if block["id"] == "clock"
    )["enabled"]
    dialog.reject()
    assert host.settings.value(FREE_LAYOUT_SETTING_KEY) == before
    dialog.deleteLater()
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.calendar_visibility_checkbox.setChecked(False)
    dialog._change("widget_mode_show_clock", False)
    dialog._change("widget_mode_font_size", 15)
    dialog._apply()
    assert host.settings.value(FREE_LAYOUT_MODE_KEY) == "free"
    assert not next(
        block for block in read_free_layout(host.settings)["blocks"] if block["id"] == "calendar"
    )["enabled"]
    assert not next(
        block for block in read_free_layout(host.settings)["blocks"] if block["id"] == "clock"
    )["enabled"]
    dialog.deleteLater()


def test_customization_explicit_preset_selection_exits_free_and_editor_entry_discards_draft(
    workspace,
):
    host, coordinator, widget = workspace
    write_free_layout(host.settings, seed_free_layout("stacked"))
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.layout_buttons["minimal"].click()
    assert dialog.draft.value(FREE_LAYOUT_MODE_KEY) == "preset"
    dialog._apply()
    assert host.settings.value(FREE_LAYOUT_MODE_KEY) == "preset"
    dialog.deleteLater()
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    before = deepcopy(host.settings.values)
    dialog._change("widget_mode_font_size", 18)
    coordinator.controller.open_free_layout_editor = Mock()
    dialog.free_layout_btn.click()
    _APP.processEvents()
    assert host.settings.values == before
    coordinator.controller.open_free_layout_editor.assert_called_once()
    dialog.deleteLater()
