# -*- coding: utf-8 -*-
"""Tooltips inside the see-through panels use the theme, not a black transparent box."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QToolTip, QVBoxLayout
import pytest

from calendar_app.presentation.theme.style_builder import (
    build_dock_frame_stylesheet,
    build_tooltip_stylesheet,
)
from calendar_app.shared.color_utils import contrast_ratio, parse_css_color


def _shown_tip(app, frame_qss):
    frame = QFrame()
    frame.setStyleSheet(frame_qss)
    cell = QLabel("13", frame)
    QVBoxLayout(frame).addWidget(cell)
    frame.resize(200, 120)
    frame.move(-5000, -5000)
    frame.show()
    app.processEvents()
    QToolTip.showText(cell.mapToGlobal(QPoint(4, 4)), "방향키: 날짜 이동", cell)
    app.processEvents()
    tips = [w for w in app.topLevelWidgets() if w.metaObject().className() == "QTipLabel"]
    assert tips and tips[0].isVisible()
    tip = tips[0]
    tip.ensurePolished()
    colours = (
        tip.palette().color(QPalette.ColorRole.Window),
        tip.palette().color(QPalette.ColorRole.WindowText),
    )
    QToolTip.hideText()
    frame.close()
    frame.deleteLater()
    app.processEvents()
    return colours


@pytest.mark.parametrize(
    ("text_theme", "base", "accent"),
    (("dark", "#0d1b2e", "#c5a3f5"), ("light", "#f3f1fa", "#7950b8")),
)
def test_tooltip_inside_a_panel_frame_follows_the_theme(tmp_path, text_theme, base, accent):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "tip.ini"), QSettings.Format.IniFormat)
    tooltip_qss = build_tooltip_stylesheet(11, accent, text_theme, base)
    previous = app.styleSheet()
    app.setStyleSheet(tooltip_qss)
    try:
        # The old frame rule: the tooltip inherited "background: transparent".
        old_bg, _old_text = _shown_tip(app, "background: transparent; border: none;")
        assert old_bg.alpha() == 0

        background, text = _shown_tip(app, build_dock_frame_stylesheet(tooltip_qss, settings))
        expected_bg = tooltip_qss.split("background-color:", 1)[1].split(";", 1)[0].strip()
        assert background.name() == parse_css_color(expected_bg).name()
        assert background.alpha() > 200
        opaque_bg = parse_css_color(background.name())
        assert contrast_ratio(parse_css_color(text.name()), opaque_bg) >= 4.5
    finally:
        app.setStyleSheet(previous)


def test_panel_content_stays_see_through():
    qss = build_dock_frame_stylesheet("QToolTip { background-color: #101820; }")
    assert qss.startswith("* { background: transparent; border: none; }")
