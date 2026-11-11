# -*- coding: utf-8 -*-
"""Dialogs that Qt creates internally keep a working shared header."""

import gc

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QColorDialog, QWidget

from calendar_app.presentation.dialogs import dialog_chrome
from calendar_app.presentation.dialogs.dialog_styles import install_common_dialog_style_filter


def test_static_color_dialog_header_spans_the_dialog_and_shows_its_title():
    app = QApplication.instance() or QApplication([])
    install_common_dialog_style_filter(app)
    host = QWidget()
    host.resize(400, 300)
    host.show()
    seen = {}

    def inspect(attempt=0):
        dialog = next(
            (w for w in app.topLevelWidgets() if isinstance(w, QColorDialog) and w.isVisible()),
            None,
        )
        if dialog is None and attempt < 100:
            QTimer.singleShot(20, lambda: inspect(attempt + 1))
            return
        # Qt-created dialogs get a fresh Python wrapper per event; drop this one too.
        gc.collect()
        app.processEvents()
        controller = dialog_chrome.dialog_chrome_controller(dialog)
        seen["controllers"] = len(dialog_chrome._controllers_for(dialog))
        seen["dialog_width"] = dialog.width()
        seen["header_width"] = controller.header.width()
        seen["title_width"] = controller.title_label.width()
        seen["title"] = controller.title_label.text()
        dialog.reject()

    QTimer.singleShot(0, inspect)
    QColorDialog.getColor(
        QColor("#bd93f9"), host, "포인트 색상 선택", QColorDialog.ColorDialogOption.DontUseNativeDialog
    )
    host.close()

    assert seen["controllers"] == 1
    assert seen["header_width"] == seen["dialog_width"]
    assert seen["title"] == "포인트 색상 선택"
    assert seen["title_width"] > 100
