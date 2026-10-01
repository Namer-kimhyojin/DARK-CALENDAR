# -*- coding: utf-8 -*-
"""Week strip navigation and independently rendered text/background alpha."""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget
import pytest

from calendar_app.presentation.widgets.unified_widget_mode import CompactCalendarGrid
from calendar_app.presentation.widgets.week_day_button import ModernWeekDayButton
from tests.test_widget_mode_ux import _APP  # noqa: F401


def _render(button):
    pixmap = QPixmap(button.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    button.render(pixmap, flags=QWidget.RenderFlag.DrawChildren)
    return pixmap.toImage()


def _max_alpha(image):
    return max(
        image.pixelColor(x, y).alpha() for y in range(image.height()) for x in range(image.width())
    )


def test_month_boundary_and_keyboard_click_select_original_dates():
    grid = CompactCalendarGrid()
    grid.resize(320, 64)
    grid.apply_layout_metrics(cell_size=(42, 54), spacing=4, margins=(0, 0, 0, 0))
    grid.update_grid(QDate(2026, 10, 1))
    assert grid._dates[0] == QDate(2026, 9, 28)
    assert grid._dates[-1] == QDate(2026, 10, 4)
    assert all(button.accessibleName() == button.toolTip() for button in grid._buttons)
    selected = []
    grid.dateClicked.connect(selected.append)
    grid.show()
    _APP.processEvents()
    widths = [button.width() for button in grid._buttons]
    assert max(widths) - min(widths) <= 1
    grid._buttons[-1].setFocus()
    QTest.keyClick(grid._buttons[-1], Qt.Key.Key_Space)
    assert selected == [QDate(2026, 10, 4)]
    grid.close()
    grid.deleteLater()
    _APP.processEvents()


@pytest.mark.parametrize("background_opacity", [0, 100])
def test_painted_week_text_honors_opacity_independently(background_opacity):
    button = ModernWeekDayButton()
    button.resize(44, 60)
    button.setFont(QFont("Segoe UI", 12))
    button.setStyleSheet("QToolButton { background: transparent; border: 0; }")
    tokens = {
        "text_primary": "#ffffff",
        "text_secondary": "#ffffff",
        "accent_deep": "#ffffff",
        "hero_bg_strong": "rgba(0,0,0,80)",
        "_background_opacity": background_opacity,
        "_text_opacity": 100,
    }
    button.configure("목", 1, tokens, selected=True, today=True)
    full = _render(button)
    tokens["_text_opacity"] = 20
    button.configure("목", 1, tokens, selected=True, today=True)
    faded = _render(button)
    # Premultiplied white intensity isolates foreground even over a black fill.
    full_white = max(
        full.pixelColor(x, y).red() * full.pixelColor(x, y).alpha() / 255
        for y in range(4, 49)
        for x in range(5, 39)
    )
    faded_white = max(
        faded.pixelColor(x, y).red() * faded.pixelColor(x, y).alpha() / 255
        for y in range(4, 49)
        for x in range(5, 39)
    )
    assert faded_white < full_white * 0.3
    assert faded.pixelColor(2, 30).alpha() == (0 if background_opacity == 0 else 80)
    button.deleteLater()
    _APP.processEvents()


@pytest.mark.parametrize("width,font_size", [(28, 18), (44, 12), (100, 18)])
def test_large_fonts_and_narrow_dates_render_without_filling_tile_edges(width, font_size):
    button = ModernWeekDayButton()
    button.resize(width, 54)
    button.setFont(QFont("Segoe UI", font_size))
    button.setStyleSheet("QToolButton { background: transparent; border: 0; }")
    button.configure("Wed", 30, {"text_primary": "#ffffff", "text_secondary": "#ffffff"})
    image = _render(button)
    assert _max_alpha(image) > 0
    assert all(
        image.pixelColor(0, y).alpha() == image.pixelColor(width - 1, y).alpha() == 0
        for y in range(image.height())
    )
    assert all(
        image.pixelColor(x, 0).alpha() == image.pixelColor(x, 53).alpha() == 0 for x in range(width)
    )
    button.deleteLater()
    _APP.processEvents()
