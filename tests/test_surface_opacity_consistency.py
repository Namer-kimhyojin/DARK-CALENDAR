# -*- coding: utf-8 -*-
"""Panels keep one opacity while the window moves, and top-bar buttons share one size."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect, QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation.main_window import wallpaper_contrast
from calendar_app.presentation.main_window.theme_actions import ThemeActionsMixin
from calendar_app.presentation.main_window.top_bar_shelf import TOP_BAR_BUTTON_SIZE
from calendar_app.shared.theme_settings import set_wallpaper_opacity_floor, wallpaper_opacity_floor
from tests.test_wallpaper_contrast import _wallpaper


@pytest.fixture(autouse=True)
def _app_and_floor():
    app = QApplication.instance() or QApplication([])
    set_wallpaper_opacity_floor(0.0)
    yield app
    set_wallpaper_opacity_floor(0.0)


@pytest.fixture
def settings(tmp_path):
    cfg = QSettings(str(tmp_path / "surfaces.ini"), QSettings.Format.IniFormat)
    for key, value in {
        "text_theme": "dark",
        "panel_base_color": "#0d1b2e",
        "appearance_base_source": "custom",
        "last_opacity": 90,
        "last_opacity_unit": "byte",
    }.items():
        cfg.setValue(key, value)
    return cfg


def _window(settings, geometry, applied):
    screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 400, 200))
    return SimpleNamespace(
        settings=settings,
        _ui_fully_initialized=True,
        windowHandle=lambda: SimpleNamespace(screen=lambda: screen),
        frameGeometry=lambda: geometry,
        apply_theme_settings=lambda **kw: applied.append(kw),
    )


def test_moving_or_resizing_on_one_screen_keeps_the_wallpaper_floor(
    tmp_path, settings, monkeypatch
):
    from calendar_app.infrastructure.runtime import wallpaper_backdrop

    # Dark left half, bright right half: the old per-position check gave the
    # window a different opacity on each side of the screen.
    split = _wallpaper(tmp_path, "#101010", "#f4f4f4")
    monkeypatch.setattr(wallpaper_backdrop, "current_wallpaper", lambda: split)
    settings.setValue(wallpaper_contrast.ADAPTIVE_WALLPAPER_KEY, True)
    applied = []
    geometry = QRect(0, 0, 150, 200)
    window = _window(settings, geometry, applied)
    assert wallpaper_contrast.refresh_wallpaper_contrast(window) is True
    floor = wallpaper_opacity_floor()
    assert floor > 0

    for moved in (QRect(250, 0, 150, 200), QRect(10, 10, 380, 180), QRect(0, 0, 90, 90)):
        window.frameGeometry = lambda rect=moved: rect
        assert wallpaper_contrast.refresh_wallpaper_contrast(window) is False
        assert wallpaper_opacity_floor() == floor
    assert len(applied) == 1


class SurfaceHost(ThemeActionsMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("kimhyojin", "Dark Calendar")
        layout = QHBoxLayout(self)
        self.center_frame = QFrame(self)
        center_layout = QVBoxLayout(self.center_frame)
        self.calendar_surface = QFrame(self.center_frame)
        self.calendar_surface.setObjectName("calendar_surface")
        center_layout.addWidget(self.calendar_surface)
        self.panel_surface = QFrame(self)
        self.panel_surface.setObjectName("panel_surface")
        layout.addWidget(self.center_frame)
        layout.addWidget(self.panel_surface)


def _background_alpha(style, selector):
    block = style.split(selector, 1)[1].split("}", 1)[0]
    colour = block.split("background-color:", 1)[1].split(";", 1)[0].strip()
    return int(colour.rstrip(")").split(",")[-1])


def test_calendar_and_panel_surfaces_repaint_together():
    store = QSettings("kimhyojin", "Dark Calendar")
    for key, value in {
        "text_theme": "dark",
        "panel_base_color": "#0d1b2e",
        "last_opacity": 230,
        "last_opacity_unit": "byte",
    }.items():
        store.setValue(key, value)
    host = SurfaceHost()
    try:
        alphas = []
        for floor in (0.0, 0.95):
            set_wallpaper_opacity_floor(floor)
            host._refresh_surface_opacity()
            calendar = _background_alpha(
                host.calendar_surface.styleSheet(), "QFrame#calendar_surface"
            )
            panel = _background_alpha(host.panel_surface.styleSheet(), "QFrame#panel_surface")
            # The month calendar and the side panels always show the same opacity.
            assert calendar == panel
            alphas.append(calendar)
        assert alphas[1] > alphas[0]
    finally:
        host.deleteLater()


def test_top_bar_buttons_share_one_square_size(settings):
    from calendar_app.presentation.main_window.top_bar_builder import (
        build_top_bar_runtime_styles,
    )
    from calendar_app.presentation.theme.style_builder import build_global_stylesheet

    styles = build_top_bar_runtime_styles(settings, 11, "#c5a3f5")
    window = QWidget()
    # The global sheet's QPushButton min-width (60px) used to widen lock/magnet.
    window.setStyleSheet(
        build_global_stylesheet(
            family="Pretendard, sans-serif",
            base_pt=11,
            theme_color="#c5a3f5",
            text_theme="dark",
            panel_base_color="#0d1b2e",
        )
    )
    layout = QHBoxLayout(window)
    lock, magnet = QPushButton(""), QPushButton("")
    magnet.setCheckable(True)
    magnet.setChecked(True)
    tool = QToolButton()
    for button, style in ((lock, "mode_button"), (magnet, "mode_button"), (tool, "tool_button")):
        button.setFixedSize(TOP_BAR_BUTTON_SIZE, TOP_BAR_BUTTON_SIZE)
        button.setStyleSheet(styles[style])
        layout.addWidget(button)
    window.show()
    QApplication.processEvents()
    try:
        sizes = {(b.width(), b.height()) for b in (lock, magnet, tool)}
        assert sizes == {(TOP_BAR_BUTTON_SIZE, TOP_BAR_BUTTON_SIZE)}
    finally:
        window.close()
        window.deleteLater()
