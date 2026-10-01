# -*- coding: utf-8 -*-
"""Preference scrolling, discoverability and isolated draft regressions."""

from unittest.mock import patch

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


@pytest.fixture
def preferences(workspace):
    _, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.show()
    _APP.processEvents()
    yield dialog
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def _control_value(control):
    if isinstance(control, QComboBox):
        return control.currentIndex()
    if isinstance(control, (QSlider, QSpinBox)):
        return control.value()
    raise AssertionError("unsupported preference control")


@pytest.mark.parametrize("focused", [False, True])
@pytest.mark.parametrize(
    "control_name,tab_index",
    [
        ("skin_combo", 1),
        ("font_family", 1),
        ("font_family.lineEdit", 1),
        ("font_size", 1),
        ("font_size.lineEdit", 1),
        ("font_weight", 1),
        ("text_opacity", 1),
        ("background_opacity", 1),
        ("density_combo", 2),
    ],
)
def test_wheel_scrolls_preferences_without_changing_draft(
    preferences, control_name, tab_index, focused
):
    dialog = preferences
    dialog.preferences_tabs.setCurrentIndex(tab_index)
    dialog.controls_scroll.setFixedHeight(180)
    _APP.processEvents()
    control = getattr(dialog, control_name.split(".")[0])
    target = control.lineEdit() if "." in control_name else control
    if focused:
        target.setFocus()
    else:
        dialog.cancel_btn.setFocus()
    _APP.processEvents()
    scrollbar = dialog.controls_scroll.verticalScrollBar()
    scrollbar.setValue(0)
    before = _control_value(control)
    before_draft = dict(dialog.draft.values)
    event = QWheelEvent(
        QPointF(target.rect().center()),
        QPointF(target.mapToGlobal(target.rect().center())),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(target, event)
    _APP.processEvents()
    assert _control_value(control) == before
    assert dialog.draft.values == before_draft
    assert scrollbar.value() > 0


def test_keyboard_changes_draft_but_cancel_preserves_live_widget_and_settings(
    workspace, preferences
):
    host, _, widget = workspace
    dialog = preferences
    before = dict(host.settings.values)
    before_geometry = widget.geometry()
    before_font_size = widget.font().pointSize()
    dialog.preferences_tabs.setCurrentIndex(1)
    dialog.font_size.setFocus()
    original_size = dialog.font_size.value()
    QTest.keyClick(dialog.font_size, Qt.Key.Key_Up)
    assert dialog.font_size.value() == original_size + 1
    assert dialog.draft.value("widget_mode_font_size") == original_size + 1
    assert host.settings.values == before
    assert widget.geometry() == before_geometry
    assert widget.font().pointSize() == before_font_size
    dialog.cancel_btn.click()
    assert host.settings.values == before


def test_all_layouts_disclosure_removes_finished_action_and_preserves_focus(preferences):
    dialog = preferences
    dialog.all_layouts_btn.click()
    _APP.processEvents()
    assert dialog.all_layouts_btn.isHidden()
    assert all(not button.isHidden() for button in dialog.layout_buttons.values())
    assert dialog.layout_buttons[dialog.draft.value("widget_mode_layout")].hasFocus()


def test_calendar_label_describes_all_periods_and_layout_specific_scope(preferences):
    checkbox = preferences.calendar_visibility_checkbox
    assert checkbox.text()
    assert "주간" not in checkbox.text()
    assert checkbox.accessibleDescription()
    for control in (
        preferences.skin_combo,
        preferences.font_family,
        preferences.font_size,
        preferences.font_weight,
    ):
        assert control.accessibleName()


@pytest.mark.parametrize("all_layouts", [False, True])
def test_layout_cards_and_disclosure_never_overlap_at_short_dialog_height(preferences, all_layouts):
    dialog = preferences
    dialog.resize(940, 520)
    if all_layouts:
        dialog.all_layouts_btn.click()
    for _ in range(3):
        _APP.processEvents()
    controls = [button for button in dialog.layout_buttons.values() if not button.isHidden()]
    if not dialog.all_layouts_btn.isHidden():
        controls.append(dialog.all_layouts_btn)
    for control, following in zip(controls, controls[1:], strict=False):
        assert control.geometry().bottom() < following.geometry().top()
    scrollbar = dialog.controls_scroll.verticalScrollBar()
    if controls[-1].geometry().bottom() > dialog.controls_scroll.viewport().height():
        assert scrollbar.maximum() > 0


def test_layout_cards_size_for_long_translated_labels(workspace):
    from calendar_app.presentation.dialogs import widget_customization_dialog as module

    _, coordinator, widget = workspace
    translate = module.t

    def long_labels(key, fallback):
        return (
            "Layout mit ausführlicher Beschreibung"
            if key.startswith("widget_mode.layout_")
            else translate(key, fallback)
        )

    with patch.object(module, "t", side_effect=long_labels):
        dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    for button in dialog.layout_buttons.values():
        assert button.minimumWidth() >= button.fontMetrics().horizontalAdvance(button.text()) + 28
        assert button.minimumHeight() >= button.fontMetrics().height() + 54
    dialog.reject()
    dialog.deleteLater()
