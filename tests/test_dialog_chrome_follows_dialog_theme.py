# -*- coding: utf-8 -*-
"""A dialog's header and shadow follow the theme the dialog is painted with.

The appearance settings preview a draft theme while the *saved* theme is another one.
The header and outer shadow used to read the saved theme, which put a light header
(and a light shadow) under a dark body, with a light title unreadable on it.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout
import pytest

from calendar_app.presentation.dialogs.dialog_chrome import ensure_dialog_chrome
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_theme_tokens,
)

DARK = {"text_theme": "dark", "panel_base_color": "#121827", "theme_color": "#f1fa8c"}
LIGHT = {"text_theme": "light", "panel_base_color": "#f8f1e7", "theme_color": "#b7791f"}


@pytest.mark.parametrize(("saved", "draft"), [(LIGHT, DARK), (DARK, LIGHT)])
def test_header_and_shadow_use_the_dialogs_theme_not_the_saved_one(saved, draft):
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temporary:
        settings = QSettings(str(Path(temporary) / "theme.ini"), QSettings.Format.IniFormat)
        for key, value in saved.items():
            settings.setValue(key, value)
        dialog = QDialog()
        dialog.setWindowTitle("미리보기")
        QVBoxLayout(dialog).addWidget(QLabel("본문"))
        apply_common_dialog_style(
            dialog,
            theme_color=draft["theme_color"],
            text_theme=draft["text_theme"],
            panel_base_color=draft["panel_base_color"],
            settings=settings,
        )
        ensure_dialog_chrome(dialog, settings=settings)
        dialog.show()
        app.processEvents()
        try:
            body = get_dialog_theme_tokens(
                theme_color=draft["theme_color"],
                text_theme=draft["text_theme"],
                panel_base_color=draft["panel_base_color"],
                settings=settings,
            )
            stale = get_dialog_theme_tokens(settings=settings)
            assert body["floating_bg"] != stale["floating_bg"]  # the scenario is real

            header_style = dialog._dc_dialog_chrome_controller.header.styleSheet()
            assert body["floating_bg"] in header_style
            assert stale["floating_bg"] not in header_style
            surface = dialog._dc_dialog_shadow_controller.surface
            assert surface.dark is (draft["text_theme"] == "dark")
        finally:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            if not sip.isdeleted(dialog):
                app.processEvents()
