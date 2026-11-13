# -*- coding: utf-8 -*-
"""Standard color chooser keeps a full-width title and an intact picker grid."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QColorDialog, QDialog, QDialogButtonBox
import pytest

from calendar_app.presentation.dialogs import dialog_chrome
from calendar_app.presentation.dialogs.dialog_chrome import prepare_dialog_chrome
from calendar_app.presentation.dialogs.dialog_styles import (
    _dialog_settings,
    install_common_dialog_style_filter,
)

_APP = None


def test_nested_selector_uses_its_owners_readonly_appearance_draft():
    global _APP
    _APP = QApplication.instance() or QApplication([])

    class Draft:
        def value(self, key, default=None):
            return {"text_theme": "light"}.get(key, default)

        def contains(self, key):
            return key == "text_theme"

        def allKeys(self):  # noqa: N802
            return ["text_theme"]

    owner = QDialog()
    owner._dc_chrome_settings = Draft()
    selector = QColorDialog(owner)
    try:
        assert _dialog_settings(selector) is owner._dc_chrome_settings
        assert _dialog_settings(selector).value("text_theme") == "light"
    finally:
        selector.close()
        owner.close()


def test_native_color_picker_is_owned_by_the_operating_system():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    dialog = QColorDialog()
    try:
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, False)
        assert not prepare_dialog_chrome(dialog)
        assert not hasattr(dialog, "_dc_dialog_chrome_controller")
    finally:
        dialog.close()


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("font_size", [11, 24])
def test_color_picker_title_stays_horizontal_and_does_not_cover_color_controls(mode, font_size):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    style_filter = install_common_dialog_style_filter(_APP)
    _APP.installEventFilter(style_filter)
    with TemporaryDirectory() as folder:
        settings = QSettings(str(Path(folder) / "picker.ini"), QSettings.Format.IniFormat)
        settings.setValue("text_theme", mode)
        settings.setValue("theme_color", "#c5a3f5")
        settings.setValue("font_size", font_size)
        settings.setValue("panel_base_color", "#1c2132" if mode == "dark" else "#f6f7fb")
        dialog = QColorDialog(QColor("#37aabb"))
        dialog._dc_chrome_settings = settings
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowTitle("배경 색상 선택")
        try:
            dialog.show()
            _APP.processEvents()
            controller = dialog._dc_dialog_chrome_controller
            assert controller.header.width() >= dialog.width() - 20
            assert controller.title_label.width() >= 140
            assert (
                controller.title_label.height() < controller.title_label.fontMetrics().height() * 2
            )
            assert controller.header.height() < 100
            box = dialog.findChild(QDialogButtonBox)
            assert box is not None and box.isVisible()
            assert (
                box.mapTo(dialog, box.rect().topLeft()).y() > controller.header.geometry().bottom()
            )
            assert dialog.currentColor().name() == "#37aabb"
            dialog.setCurrentColor(QColor("#bbaa37"))
            assert dialog.currentColor().name() == "#bbaa37"
        finally:
            dialog.close()
            dialog.deleteLater()
            _APP.processEvents()
    # Keep the app-owned filter installed for subsequent modal tests.
    _APP.installEventFilter(style_filter)


@pytest.mark.parametrize("accept", [True, False])
def test_static_qt_color_picker_preserves_alpha_and_cancel_result(accept):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    style_filter = install_common_dialog_style_filter(_APP)
    _APP.installEventFilter(style_filter)
    observed = {}

    def finish():
        active = _APP.activeModalWidget()
        observed["color_dialog"] = isinstance(active, QColorDialog)
        if isinstance(active, QColorDialog):
            controller = dialog_chrome.dialog_chrome_controller(active)
            observed["header_width"] = controller.header.width() if controller else 0
            observed["width"] = active.width()
            active.setCurrentColor(QColor(20, 40, 60, 91))
            active.accept() if accept else active.reject()
        else:
            _APP.closeAllWindows()

    QTimer.singleShot(0, finish)
    try:
        picked = QColorDialog.getColor(
            QColor("#37aabb"),
            None,
            "배경 색상 선택",
            QColorDialog.ColorDialogOption.DontUseNativeDialog
            | QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        assert observed["color_dialog"]
        assert observed["header_width"] >= observed["width"] - 20
        assert picked.isValid() is accept
        if accept:
            assert picked.getRgb() == (20, 40, 60, 91)
    finally:
        _APP.installEventFilter(style_filter)
