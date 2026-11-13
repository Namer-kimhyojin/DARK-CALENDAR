# -*- coding: utf-8 -*-
"""Compact appearance/settings glyphs keep transparent space at every edge."""

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.shared.icon_map import ICON, icon

_APP = None


@pytest.mark.parametrize("key", [ICON.SETTINGS, ICON.DISPLAY_STYLE])
@pytest.mark.parametrize("logical_size", [16, 20, 24])
@pytest.mark.parametrize("dpr", [1.0, 1.25, 2.0])
def test_toolbar_glyph_does_not_touch_the_icon_canvas(key, logical_size, dpr):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    bitmap = icon(key, color="#c5a3f5").pixmap(QSize(logical_size, logical_size), dpr).toImage()
    assert not bitmap.isNull()
    visible = [
        (x, y)
        for y in range(bitmap.height())
        for x in range(bitmap.width())
        if bitmap.pixelColor(x, y).alpha() > 24
    ]
    assert visible
    assert min(x for x, _ in visible) >= 1
    assert min(y for _, y in visible) >= 1
    assert max(x for x, _ in visible) < bitmap.width() - 1
    assert max(y for _, y in visible) < bitmap.height() - 1
