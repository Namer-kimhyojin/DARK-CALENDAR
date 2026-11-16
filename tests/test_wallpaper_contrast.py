# -*- coding: utf-8 -*-
"""Dark-mode text stays readable over a bright wallpaper."""

from types import SimpleNamespace

from PyQt6.QtCore import QRect, QSettings
from PyQt6.QtGui import QColor, QImage
import pytest

from calendar_app.infrastructure.runtime import wallpaper_backdrop
from calendar_app.infrastructure.runtime.wallpaper_backdrop import WallpaperInfo, sample_backdrop
from calendar_app.presentation.main_window import wallpaper_contrast
from calendar_app.shared.color_utils import (
    PANEL_SURFACE_ALPHA_OFFSET,
    _mix_colors,
    contrast_ratio,
    panel_opacity_floor_for_backdrop,
)
from calendar_app.shared.theme_settings import (
    get_opacity_factor,
    set_wallpaper_opacity_floor,
    wallpaper_opacity_floor,
)


@pytest.fixture(scope="module", autouse=True)
def application():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _reset_floor():
    set_wallpaper_opacity_floor(0.0)
    yield
    set_wallpaper_opacity_floor(0.0)


@pytest.fixture
def settings(tmp_path):
    cfg = QSettings(str(tmp_path / "wallpaper.ini"), QSettings.Format.IniFormat)
    cfg.setValue("text_theme", "dark")
    cfg.setValue("panel_base_color", "#0d1b2e")
    cfg.setValue("appearance_base_source", "custom")
    cfg.setValue("last_opacity", 90)
    cfg.setValue("last_opacity_unit", "byte")
    return cfg


def _wallpaper(tmp_path, left: str, right: str) -> WallpaperInfo:
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor(left))
    for x in range(200, 400):
        for y in range(200):
            image.setPixelColor(x, y, QColor(right))
    path = tmp_path / "wall.png"
    assert image.save(str(path))
    wallpaper_backdrop._THUMB_CACHE.clear()
    return WallpaperInfo(str(path), 1.0, "10", False, "#000000")


def test_dark_wallpaper_needs_no_floor_and_bright_one_does():
    assert panel_opacity_floor_for_backdrop("#0d1b2e", "#c5cfda", QColor("#000000")) == 0.0
    floor = panel_opacity_floor_for_backdrop("#0d1b2e", "#c5cfda", QColor("#ffffff"))
    assert 0.3 < floor < 1.0
    # At the floor the panel surface (drawn 30 below the slider) keeps 4.5:1.
    surface_alpha = (floor * 255 - PANEL_SURFACE_ALPHA_OFFSET) / 255
    shown = _mix_colors(QColor("#ffffff"), QColor("#0d1b2e"), surface_alpha)
    assert contrast_ratio(QColor("#c5cfda"), shown) >= 4.5


def test_floor_raises_the_visible_opacity_but_not_the_saved_one(settings):
    assert get_opacity_factor(settings) == pytest.approx(90 / 255)
    set_wallpaper_opacity_floor(0.8)
    assert get_opacity_factor(settings) == pytest.approx(0.8)
    assert int(settings.value("last_opacity")) == 90
    set_wallpaper_opacity_floor(0.1)
    assert get_opacity_factor(settings) == pytest.approx(90 / 255)


def test_only_the_wallpaper_behind_the_window_counts(tmp_path):
    info = _wallpaper(tmp_path, "#101010", "#f4f4f4")
    screen = QRect(0, 0, 400, 200)
    left = sample_backdrop(info, QRect(0, 0, 150, 200), screen, brightest=True)
    right = sample_backdrop(info, QRect(250, 0, 150, 200), screen, brightest=True)
    assert left.name() == "#101010"
    assert right.name() == "#f4f4f4"


def test_fill_crops_the_wallpaper_like_windows(tmp_path):
    # A 2:1 image on a 1:1 screen is cropped at the sides under Fill, so the
    # whole screen sees only the middle of the picture.
    info = _wallpaper(tmp_path, "#101010", "#f4f4f4")
    screen = QRect(0, 0, 200, 200)
    left_half = sample_backdrop(info, QRect(0, 0, 90, 200), screen, brightest=True)
    assert left_half.name() == "#101010"


def test_solid_color_desktop_is_used_directly():
    info = WallpaperInfo("", 0.0, "10", False, "#fafafa")
    color = sample_backdrop(info, QRect(0, 0, 10, 10), QRect(0, 0, 100, 100), brightest=True)
    assert color.name() == "#fafafa"


def test_window_reapplies_theme_only_when_the_floor_changes(tmp_path, settings, monkeypatch):
    bright = _wallpaper(tmp_path, "#f4f4f4", "#f4f4f4")
    monkeypatch.setattr(wallpaper_backdrop, "current_wallpaper", lambda: bright)
    settings.setValue(wallpaper_contrast.ADAPTIVE_WALLPAPER_KEY, True)
    screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 400, 200))
    applied = []
    window = SimpleNamespace(
        settings=settings,
        _ui_fully_initialized=True,
        windowHandle=lambda: SimpleNamespace(screen=lambda: screen),
        frameGeometry=lambda: QRect(0, 0, 400, 200),
        apply_theme_settings=lambda **kw: applied.append(kw),
    )
    assert wallpaper_contrast.refresh_wallpaper_contrast(window) is True
    assert wallpaper_opacity_floor() > 90 / 255
    assert applied == [{"persist_opacity": False}]
    # Nothing changed: no second theme pass.
    assert wallpaper_contrast.refresh_wallpaper_contrast(window) is False
    assert len(applied) == 1

    settings.setValue(wallpaper_contrast.ADAPTIVE_WALLPAPER_KEY, False)
    assert wallpaper_contrast.refresh_wallpaper_contrast(window) is True
    assert wallpaper_opacity_floor() == 0.0


def test_option_is_off_by_default_so_panels_stay_as_set(tmp_path, settings, monkeypatch):
    bright = _wallpaper(tmp_path, "#f4f4f4", "#f4f4f4")
    monkeypatch.setattr(wallpaper_backdrop, "current_wallpaper", lambda: bright)
    assert wallpaper_contrast.adaptive_wallpaper_enabled(settings) is False
    window = SimpleNamespace(settings=settings, _ui_fully_initialized=True)
    assert wallpaper_contrast.refresh_wallpaper_contrast(window) is False
    assert wallpaper_opacity_floor() == 0.0


def test_appearance_dialog_offers_the_option():
    from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog

    dialog = PanelColorPickerDialog()
    try:
        assert dialog.selected_adaptive_wallpaper() is False
        dialog._chk_adaptive_wallpaper.setChecked(True)
        assert dialog.selected_adaptive_wallpaper() is True
    finally:
        dialog.deleteLater()
    on = PanelColorPickerDialog(current_adaptive_wallpaper=True)
    try:
        assert on._chk_adaptive_wallpaper.isChecked()
    finally:
        on.deleteLater()
