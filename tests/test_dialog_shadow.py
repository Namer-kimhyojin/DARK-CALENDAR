# -*- coding: utf-8 -*-
"""Outer modal shadows leave layout, focus/input flags, and lifecycle intact."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QVBoxLayout
import pytest

from calendar_app.presentation.dialogs.dialog_chrome import ensure_dialog_chrome
from calendar_app.presentation.dialogs.dialog_shadow import (
    _BOTTOM_MARGIN,
    _SPREAD,
    ensure_dialog_shadow,
)
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style


@pytest.fixture
def modal():
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temporary:
        settings = QSettings(str(Path(temporary) / "shadow.ini"), QSettings.Format.IniFormat)
        settings.setValue("text_theme", "light")
        settings.setValue("panel_base_color", "#f6f7fb")
        dialog = QDialog()
        dialog.setWindowTitle("그림자 모달")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("읽기 영역"))
        field = QLineEdit("변경하지 않는 값")
        layout.addWidget(field)
        apply_common_dialog_style(dialog, settings=settings)
        ensure_dialog_chrome(dialog, settings=settings)
        dialog.resize(420, 300)
        dialog.show()
        app.processEvents()
        yield dialog, settings, layout, field
        if not sip.isdeleted(dialog):
            dialog.close()
            dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_shadow_is_one_owned_input_transparent_surface_and_preserves_the_client(modal):
    dialog, settings, layout, field = modal
    surface = dialog._dc_dialog_shadow_controller.surface
    original_margins = dialog.contentsMargins()
    for _ in range(3):
        ensure_dialog_shadow(dialog, settings=settings)
        ensure_dialog_chrome(dialog, settings=settings)
    assert dialog.layout() is layout
    assert dialog.contentsMargins() == original_margins
    assert field.text() == "변경하지 않는 값"
    assert dialog.graphicsEffect() is None
    assert surface.parentWidget() is dialog
    assert surface.isWindow() and surface.isVisible()
    assert surface.windowModality() == Qt.WindowModality.NonModal
    assert surface.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert surface.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert not surface.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert surface.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert surface.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert len(dialog.findChildren(type(surface), "CommonDialogShadow")) == 1


@pytest.mark.parametrize("ratio", [1, 1.25, 2])
def test_shadow_has_real_outer_pixels_and_a_fully_clear_owner_rect(modal, ratio):
    dialog, _, _, _ = modal
    surface = dialog._dc_dialog_shadow_controller.surface
    image = QImage(
        round(surface.width() * ratio),
        round(surface.height() * ratio),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    surface.render(painter)
    painter.end()

    def alpha(x, y):
        return image.pixelColor(round(x * ratio), round(y * ratio)).alpha()

    middle = _SPREAD + dialog.height() // 2
    assert alpha(_SPREAD - 2, middle) > 0
    assert alpha(0, middle) == 0
    assert alpha(_SPREAD + dialog.width() + 2, middle) > 0
    for x, y in (
        (_SPREAD, _SPREAD),
        (_SPREAD + 10, middle),
        (_SPREAD + dialog.width() - 1, middle),
    ):
        assert alpha(x, y) == 0


def test_move_resize_hide_show_and_delete_follow_the_owner(modal):
    dialog, _, _, _ = modal
    surface = dialog._dc_dialog_shadow_controller.surface
    dialog.move(180, 120)
    dialog.resize(560, 360)
    QApplication.processEvents()
    assert surface.geometry() == dialog.geometry().adjusted(
        -_SPREAD, -_SPREAD, _SPREAD, _BOTTOM_MARGIN
    )
    dialog.hide()
    assert not surface.isVisible()
    dialog.show()
    QApplication.processEvents()
    assert surface.isVisible()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(surface)


def test_nested_modal_gets_its_own_shadow_and_embedded_page_gets_none(modal):
    outer, settings, _, _ = modal
    child = QDialog(outer)
    QVBoxLayout(child).addWidget(QLabel("중첩 모달"))
    ensure_dialog_chrome(child, settings=settings)
    child.show()
    QApplication.processEvents()
    child_surface = child._dc_dialog_shadow_controller.surface
    assert child_surface.parentWidget() is child
    assert child_surface.isVisible()
    child.close()
    assert not child_surface.isVisible()
    assert outer._dc_dialog_shadow_controller.surface.isVisible()
    page = QDialog(outer)
    page.setWindowFlags(Qt.WindowType.Widget)
    QVBoxLayout(page).addWidget(QLabel("내부 관리 페이지"))
    assert not ensure_dialog_chrome(page, settings=settings)
    assert not ensure_dialog_shadow(page, settings=settings)
    assert not hasattr(page, "_dc_dialog_shadow_controller")


def test_rejected_close_does_not_hide_shadow(modal):
    outer, settings, _, _ = modal

    class GuardedDialog(QDialog):
        def closeEvent(self, event):
            event.ignore()

    dialog = GuardedDialog(outer)
    QVBoxLayout(dialog).addWidget(QLabel("미저장 내용"))
    ensure_dialog_chrome(dialog, settings=settings)
    dialog.show()
    QApplication.processEvents()
    surface = dialog._dc_dialog_shadow_controller.surface
    dialog.close()
    assert dialog.isVisible() and surface.isVisible()
    dialog.hide()
    dialog.deleteLater()
