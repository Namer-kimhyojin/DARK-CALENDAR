# -*- coding: utf-8 -*-
"""Independent alpha, migration, preview and persisted preference regressions."""

import re

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController
from calendar_app.presentation.widgets.widget_mode_opacity import (
    BACKGROUND_OPACITY_KEY,
    TEXT_OPACITY_KEY,
    apply_widget_opacity,
    read_widget_opacities,
)
from tests.test_widget_mode_ux import _APP, Settings, workspace  # noqa: F401


def _render(widget):
    widget.ensurePolished()
    widget.layout().activate() if widget.layout() else None
    pixmap = QPixmap(widget.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap, flags=QWidget.RenderFlag.DrawChildren)
    return pixmap.toImage()


def _max_alpha(image):
    return max(
        image.pixelColor(x, y).alpha() for y in range(image.height()) for x in range(image.width())
    )


def test_alpha_changes_adjacent_declarations_and_gradients_without_changing_fonts():
    css = 'QLabel {color:#ffffff;background:qlineargradient(x1:0,stop:0 #123456,stop:1 rgba(1,2,3,100));border:1px solid #ffffff;font-family:"#abc";}'
    result = apply_widget_opacity(css, 20, 50)
    assert "color:rgba(255, 255, 255, 51)" in result
    assert "stop:0 rgba(18, 52, 86, 128)" in result
    assert "stop:1 rgba(1, 2, 3, 50)" in result
    assert "border:1px solid rgba(255, 255, 255, 128)" in result
    assert 'font-family:"#abc"' in result


def test_legacy_opacity_is_background_only_and_invalid_values_are_safe():
    settings = Settings()
    settings.setValue("widget_mode_opacity", 71)
    assert read_widget_opacities(settings) == (100, 71)
    settings.setValue(TEXT_OPACITY_KEY, "bad")
    settings.setValue(BACKGROUND_OPACITY_KEY, None)
    assert read_widget_opacities(settings) == (100, 71)
    settings.setValue(TEXT_OPACITY_KEY, 0)
    settings.setValue(BACKGROUND_OPACITY_KEY, 150)
    assert read_widget_opacities(settings) == (20, 100)
    settings.setValue(BACKGROUND_OPACITY_KEY, 0)
    assert read_widget_opacities(settings) == (20, 0)


def test_actual_render_keeps_text_alpha_independent_from_background(workspace):
    host, coordinator, widget = workspace
    host.settings.setValue(TEXT_OPACITY_KEY, 100)
    host.settings.setValue(BACKGROUND_OPACITY_KEY, 100)
    coordinator.controller.force_refresh()
    _APP.processEvents()
    original_text = _render(widget.clock_label)
    original_bg = _render(widget).pixelColor(5, widget.height() // 2)
    host.settings.setValue(BACKGROUND_OPACITY_KEY, 0)
    coordinator.controller.force_refresh()
    _APP.processEvents()
    assert _render(widget.clock_label) == original_text
    assert _render(widget).pixelColor(5, widget.height() // 2).alpha() == 0
    assert original_bg.alpha() > 0
    host.settings.setValue(TEXT_OPACITY_KEY, 20)
    coordinator.controller.force_refresh()
    _APP.processEvents()
    assert _max_alpha(_render(widget.clock_label)) < _max_alpha(original_text) * 0.3
    assert widget.windowOpacity() == 1.0
    assert "51)" in widget.cal_grid._buttons[0].styleSheet()


def test_month_calendar_cells_follow_background_opacity(workspace):
    host, coordinator, widget = workspace
    host.settings.setValue(BACKGROUND_OPACITY_KEY, 0)
    coordinator.controller.set_layout("dashboard")
    widget._style_signature = None
    widget.apply_theme()
    _APP.processEvents()

    selected = next(
        button
        for day, button in zip(
            widget.cal_grid.month_calendar._dates,
            widget.cal_grid.month_calendar.day_buttons,
            strict=True,
        )
        if day == host.current_date
    )
    background = re.search(r"background:\s*rgba\([^)]*,\s*(\d+)\)", selected.styleSheet())
    assert background is not None
    assert int(background.group(1)) == 0
    assert "background: transparent" in widget.cal_grid.month_calendar.styleSheet()


def test_preview_cancel_and_apply_restore_independent_values(workspace, tmp_path):
    host, coordinator, widget = workspace
    path = str(tmp_path / "opacity.ini")
    host.settings = QSettings(path, QSettings.Format.IniFormat)
    host.settings.setValue("widget_mode_opacity", 71)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    assert dialog.text_opacity.value() == 100
    assert dialog.background_opacity.value() == 71
    before = dialog._preview_pixmap.toImage()
    dialog.background_opacity.setValue(0)
    assert dialog._preview_pixmap.toImage() != before
    assert _render(dialog.preview).pixelColor(5, dialog.preview.height() // 2).alpha() == 0
    clear_text = _max_alpha(_render(dialog.preview.clock_label))
    dialog.text_opacity.setValue(35)
    assert _max_alpha(_render(dialog.preview.clock_label)) < clear_text * 0.4
    assert host.settings.value(TEXT_OPACITY_KEY) is None
    assert host.settings.value(BACKGROUND_OPACITY_KEY) is None
    dialog.reject()
    dialog.deleteLater()
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    assert read_widget_opacities(dialog.draft) == (100, 71)
    dialog.background_opacity.setValue(25)
    dialog.text_opacity.setValue(80)
    dialog._apply()
    restored = QSettings(path, QSettings.Format.IniFormat)
    assert read_widget_opacities(restored) == (80, 25)
    assert widget.windowOpacity() == 1.0
    assert "color:rgba(" in widget.styleSheet().replace(" ", "")
    assert _max_alpha(_render(widget.clock_label)) == _max_alpha(
        _render(dialog.preview.clock_label)
    )
    coordinator.close_for_shutdown()
    host.settings = restored
    fresh = UnifiedWidgetController(host)
    fresh.show_widget()
    assert fresh.widget.windowOpacity() == 1.0
    assert _max_alpha(_render(fresh.widget.clock_label)) == _max_alpha(
        _render(dialog.preview.clock_label)
    )
    fresh.hide_widget()
    fresh.widget.deleteLater()
    dialog.deleteLater()
