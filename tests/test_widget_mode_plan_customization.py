# -*- coding: utf-8 -*-
"""Preference scrolling, discoverability and isolated draft regressions."""

import json
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QSlider, QSpinBox
import pytest

from calendar_app.infrastructure.i18n import t
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
        ("surface_combo", 1),
        ("font_family", 1),
        ("font_family.lineEdit", 1),
        ("font_size", 1),
        ("font_size.lineEdit", 1),
        ("font_weight", 1),
        ("calendar_style_combo", 2),
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


_LAYOUT_IDS = ("stacked", "dashboard", "work_board", "minimal")


def _open_preferences(workspace, layout_id):
    host, coordinator, widget = workspace
    host.settings.setValue("widget_mode_layout", layout_id)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.show()
    _APP.processEvents()
    return dialog


def _close(dialog):
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


@pytest.mark.parametrize("layout_id", _LAYOUT_IDS)
def test_all_four_layout_cards_are_always_shown_without_a_disclosure(workspace, layout_id):
    dialog = _open_preferences(workspace, layout_id)
    try:
        assert tuple(dialog.layout_buttons) == _LAYOUT_IDS
        assert all(button.isVisibleTo(dialog) for button in dialog.layout_buttons.values())
        assert dialog.layout_buttons[layout_id].isChecked()
        assert not hasattr(dialog, "all_layouts_btn")
        disclosure = t("widget_mode.all_layouts", "전체 배치 보기")
        assert all(button.text() != disclosure for button in dialog.findChildren(QPushButton))
    finally:
        _close(dialog)


def test_calendar_label_describes_all_periods_and_layout_specific_scope(preferences):
    checkbox = preferences.calendar_visibility_checkbox
    assert checkbox.text()
    assert "주간" not in checkbox.text()
    assert checkbox.accessibleDescription()
    for control in (
        preferences.surface_combo,
        preferences.font_family,
        preferences.font_size,
        preferences.font_weight,
    ):
        assert control.accessibleName()


@pytest.mark.parametrize("layout_id", ["stacked", "dashboard"])
def test_four_layout_cards_never_overlap_at_short_dialog_height(workspace, layout_id):
    dialog = _open_preferences(workspace, layout_id)
    try:
        dialog.resize(940, 520)
        for _ in range(3):
            _APP.processEvents()
        controls = list(dialog.layout_buttons.values())
        assert len(controls) == 4 and all(not control.isHidden() for control in controls)
        for index, control in enumerate(controls):
            for following in controls[index + 1 :]:
                assert not control.geometry().intersects(following.geometry())
        scrollbar = dialog.controls_scroll.verticalScrollBar()
        bottom = max(control.geometry().bottom() for control in controls)
        if bottom > dialog.controls_scroll.viewport().height():
            assert scrollbar.maximum() > 0
    finally:
        _close(dialog)


def test_customization_text_does_not_use_the_retired_skin_wording(preferences):
    texts = [label.text() for label in preferences.findChildren(QLabel)]
    assert texts and not any("스킨" in text for text in texts)


def test_theme_note_and_hub_description_avoid_skin_wording_in_ko_and_en():
    root = Path(__file__).resolve().parents[1] / "locales"
    for code, word in (("ko", "스킨"), ("en", "skin")):
        data = json.loads((root / f"{code}.json").read_text(encoding="utf-8", errors="strict"))
        for group, key in (("widget_mode", "main_theme_note"), ("widget_hub", "mode_desc")):
            assert word not in data[group][key].lower(), (code, key)


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
