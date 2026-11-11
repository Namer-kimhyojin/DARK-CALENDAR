# -*- coding: utf-8 -*-
"""Four equally visible outer modal edges on equal-color light/dark backdrops."""

from math import ceil
from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.dialogs.dialog_shadow import (
    _SPREAD,
    _shadow_buffer_fits,
    rounded_window_region,
)
from tests.test_dialog_shadow import modal  # noqa: F401


def _render(dialog, ratio):
    surface = dialog._dc_dialog_shadow_controller.surface
    image = QImage(
        ceil(surface.width() * ratio),
        ceil(surface.height() * ratio),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    surface.render(painter)
    painter.end()
    return image


def _edges(dialog, ratio, distance):
    left, top = round(_SPREAD * ratio), round(_SPREAD * ratio)
    right = round((_SPREAD + dialog.width()) * ratio)
    bottom = round((_SPREAD + dialog.height()) * ratio)
    away = ceil(distance * ratio)
    return (
        (left - away, (top + bottom) // 2),
        (right + away - 1, (top + bottom) // 2),
        ((left + right) // 2, top - away),
        ((left + right) // 2, bottom + away - 1),
    )


@pytest.mark.parametrize("ratio", [1, 1.25, 2])
@pytest.mark.parametrize("dark", [False, True])
def test_all_four_shadow_edges_are_strong_and_symmetric(modal, ratio, dark):
    dialog, settings, _, _ = modal
    settings.setValue("text_theme", "dark" if dark else "light")
    settings.setValue("panel_base_color", "#121827" if dark else "#f6f7fb")
    dialog._dc_dialog_shadow_controller.refresh_style(settings=settings)
    image = _render(dialog, ratio)
    alphas = [image.pixelColor(x, y).alpha() for x, y in _edges(dialog, ratio, 3)]
    assert min(alphas) >= (160 if dark else 90), alphas
    assert max(alphas) - min(alphas) <= 8, alphas
    assert (
        image.pixelColor(round((_SPREAD + 10) * ratio), round((_SPREAD + 10) * ratio)).alpha() == 0
    )


def test_dark_shadow_still_has_four_visible_edges_on_an_all_black_backdrop(modal):
    dialog, settings, _, _ = modal
    settings.setValue("text_theme", "dark")
    settings.setValue("panel_base_color", "#000000")
    dialog._dc_dialog_shadow_controller.refresh_style(settings=settings)
    shadow = _render(dialog, 1)
    composited = QImage(shadow.size(), QImage.Format.Format_ARGB32_Premultiplied)
    composited.fill(QColor("#000000"))
    painter = QPainter(composited)
    painter.drawImage(0, 0, shadow)
    painter.end()
    contrasts = [max(composited.pixelColor(x, y).getRgb()[:3]) for x, y in _edges(dialog, 1, 1)]
    assert min(contrasts) >= 15, contrasts


@pytest.mark.parametrize(
    "width,height,ratio,expected",
    [
        (4096, 4096, 1, True),
        (4097, 4096, 1, False),
        (2048, 2048, 2, True),
        (2049, 2048, 2, False),
        (640, 480, 1.25, True),
        (4000, 3000, 2, False),
        (640, 480, float("nan"), False),
        (640, 480, float("inf"), False),
        (0, 480, 1, False),
    ],
)
def test_shadow_argb_buffer_budget_is_checked_without_allocating_an_image(
    width, height, ratio, expected
):
    assert _shadow_buffer_fits(width, height, ratio) is expected


def test_oversized_shadow_is_hidden_before_tool_geometry_can_allocate_a_large_buffer(
    modal, monkeypatch
):
    dialog, _, _, _ = modal
    controller = dialog._dc_dialog_shadow_controller
    monkeypatch.setattr(dialog, "geometry", lambda: QRect(0, 0, 16000, 16000))
    monkeypatch.setattr(dialog, "devicePixelRatioF", lambda: 2.0)
    resize = Mock()
    monkeypatch.setattr(controller.surface, "setGeometry", resize)
    controller.sync_geometry()
    resize.assert_not_called()
    assert not controller.surface.isVisible()


def test_moving_without_size_change_does_not_schedule_a_full_shadow_repaint(modal, monkeypatch):
    dialog, _, _, _ = modal
    controller = dialog._dc_dialog_shadow_controller
    update = Mock()
    monkeypatch.setattr(controller.surface, "update", update)
    dialog.move(dialog.x() + 30, dialog.y() + 20)
    controller.sync_geometry()
    update.assert_not_called()


def test_strengthened_surface_preserves_modal_exec_result_and_input_value(modal):
    from PyQt6.QtWidgets import QApplication, QDialog

    dialog, _, _, field = modal
    surface = dialog._dc_dialog_shadow_controller.surface
    dialog.hide()  # Real exec() entry starts with a hidden, constructed dialog.
    observed = []

    def finish():
        observed.append(
            (
                QApplication.activeModalWidget() is dialog,
                surface.windowModality() == Qt.WindowModality.NonModal,
                surface.focusPolicy() == Qt.FocusPolicy.NoFocus,
                field.text(),
            )
        )
        dialog.reject()

    QTimer.singleShot(0, finish)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    assert observed == [(True, True, True, "변경하지 않는 값")]
    assert not surface.isVisible()


@pytest.mark.parametrize("kind", ["message", "input"])
def test_standard_owned_modals_reuse_the_same_outer_attachment_contract(modal, kind):
    from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

    from calendar_app.presentation.dialogs.dialog_chrome import ensure_dialog_chrome
    from calendar_app.presentation.dialogs.dialog_styles import _CommonDialogStyleFilter

    owner, settings, _, _ = modal
    if kind == "message":
        child = QMessageBox(owner)
        child.setText("Temporary confirmation")
        child.setStandardButtons(QMessageBox.StandardButton.Ok)
    else:
        child = QInputDialog(owner)
        child.setLabelText("Temporary input")
        child.setTextValue("Preserve this value")
    app = QApplication.instance()
    style_filter = _CommonDialogStyleFilter(app)
    app.installEventFilter(style_filter)
    try:
        # QInputDialog creates its client layout only during the Show path.
        child.show()
        QApplication.processEvents()
        assert ensure_dialog_chrome(child, settings=settings)
        surface = child._dc_dialog_shadow_controller.surface
        assert surface.parentWidget() is child and surface.isVisible()
        assert surface.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert surface.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert ensure_dialog_chrome(child, settings=settings)
        assert len(child.findChildren(type(surface), "CommonDialogShadow")) == 1
    finally:
        app.removeEventFilter(style_filter)
        child.hide()
        child.deleteLater()


def _profile(dialog, ratio=1):
    image = _render(dialog, ratio)
    y = round((_SPREAD + dialog.height() / 2) * ratio)
    return {d: image.pixelColor(round((_SPREAD - d) * ratio), y) for d in (3, 8, 16, 24)}


def _set_mode(dialog, settings, dark):
    settings.setValue("text_theme", "dark" if dark else "light")
    settings.setValue("panel_base_color", "#121827" if dark else "#f6f7fb")
    dialog._dc_dialog_shadow_controller.refresh_style(settings=settings)


def test_light_and_dark_shadows_are_visibly_different_looks(modal):  # noqa: F811
    dialog, settings, _, _ = modal
    _set_mode(dialog, settings, dark=False)
    light = _profile(dialog)
    _set_mode(dialog, settings, dark=True)
    dark = _profile(dialog)

    # Dark mode: deeper near the edge, and pure black.
    assert dark[3].alpha() >= light[3].alpha() + 50, (dark[3], light[3])
    assert max(dark[8].red(), dark[8].green(), dark[8].blue()) == 0
    # Light mode: a cool slate tint rather than black, and a softer, wider falloff.
    assert light[8].blue() > light[8].red() + 8, light[8].getRgb()
    light_falloff = light[16].alpha() / light[3].alpha()
    dark_falloff = dark[16].alpha() / dark[3].alpha()
    assert light_falloff > dark_falloff + 0.08, (light_falloff, dark_falloff)
    # Both fade out smoothly to nothing at the outer edge.
    assert light[3].alpha() > light[8].alpha() > light[16].alpha() > light[24].alpha()
    assert dark[3].alpha() > dark[8].alpha() > dark[16].alpha() > dark[24].alpha()
    assert light[24].alpha() <= 12 and dark[24].alpha() <= 12


@pytest.mark.parametrize("dark", [False, True])
def test_window_is_really_rounded_not_only_its_shadow(modal, dark):  # noqa: F811
    dialog, settings, _, _ = modal
    _set_mode(dialog, settings, dark)
    controller = dialog._dc_dialog_shadow_controller
    radius = controller.surface.radius
    assert radius >= 6
    mask = dialog.mask()
    assert not mask.isEmpty()
    width, height = dialog.width(), dialog.height()
    # The four extreme corner pixels are outside the window...
    for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        assert not mask.contains(QPoint(*point)), point
    # ...while the middle of every edge and a point on the arc are inside it.
    for point in (
        (width // 2, 0),
        (0, height // 2),
        (width - 1, height // 2),
        (width // 2, height - 1),
        (radius, radius // 3),
    ):
        assert mask.contains(QPoint(*point)), point


def test_rounded_mask_is_released_when_the_window_fills_the_screen(modal):  # noqa: F811
    dialog, _, _, _ = modal
    assert not dialog.mask().isEmpty()
    dialog.showMaximized()
    QApplication.processEvents()
    assert dialog.mask().isEmpty()
    dialog.showNormal()
    QApplication.processEvents()
    assert not dialog.mask().isEmpty()


def test_rounded_window_region_is_an_exact_rounded_rectangle():
    region = rounded_window_region(120, 80, 16)
    assert region.contains(QPoint(60, 40)) and region.contains(QPoint(16, 0))
    assert not region.contains(QPoint(0, 0)) and not region.contains(QPoint(119, 79))
    # Radius larger than half the size is clamped instead of inverting the shape.
    clamped = rounded_window_region(40, 30, 99)
    assert clamped.contains(QPoint(20, 15)) and not clamped.contains(QPoint(0, 0))
    # A zero radius is the plain rectangle.
    square = rounded_window_region(50, 50, 0)
    assert square.contains(QPoint(0, 0)) and square.contains(QPoint(49, 49))
