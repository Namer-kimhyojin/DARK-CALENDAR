# -*- coding: utf-8 -*-
"""Validation and native message glyphs follow the modal accent without changing results."""

import math
import re

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtGui import QColor, QFontMetricsF, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation.dialogs.dialog_styles import (
    _apply_message_box_palette_icon,
    _CommonDialogStyleFilter,
    apply_common_dialog_style,
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
)


@pytest.fixture
def host(tmp_path):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "feedback.ini"), QSettings.Format.IniFormat)
    parent.settings.setValue("theme_color", "#7653c4")
    parent.settings.setValue("text_theme", "light")
    parent.settings.setValue("panel_base_color", "#f6f7fb")
    yield app, parent
    parent.close()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_error_field_and_label_use_derived_modal_danger_and_keep_expert_button_color(host, mode):
    app, parent = host
    parent.settings.setValue("text_theme", mode)
    parent.settings.setValue("dialog_token.accent", "#008e82")
    parent.settings.setValue("dialog_token.button_danger_text", "#b12345")
    tokens = get_dialog_theme_tokens(settings=parent.settings)
    css = build_dialog_stylesheet(settings=parent.settings)
    selector = r'QLineEdit\[state="error"\], QTextEdit\[state="error"\], QComboBox\[state="error"\]\s*\{([^}]+)\}'
    assert f"border: 1px solid {tokens['danger_hex']}" in re.findall(selector, css)[-1]
    assert tokens["button_danger_text"] == "#b12345"
    dialog = QDialog(parent)
    layout = QVBoxLayout(dialog)
    field = QLineEdit("잘못된 입력")
    field.setProperty("state", "error")
    label = QLabel("입력값을 확인하세요")
    label.setProperty("role", "field_error")
    layout.addWidget(field)
    layout.addWidget(label)
    apply_common_dialog_style(dialog, settings=parent.settings)
    dialog.show()
    app.processEvents()
    assert label.palette().color(QPalette.ColorRole.WindowText).name() == tokens["danger_hex"]
    dialog.close()


@pytest.mark.parametrize(
    "kind",
    [
        QMessageBox.Icon.Warning,
        QMessageBox.Icon.Critical,
        QMessageBox.Icon.Information,
        QMessageBox.Icon.Question,
    ],
)
def test_message_box_standard_glyph_is_accent_colored_and_save_result_is_unchanged(host, kind):
    app, parent = host
    style_filter = _CommonDialogStyleFilter(app)
    app.installEventFilter(style_filter)
    box = QMessageBox(parent)
    box.setWindowTitle("확인")
    box.setText("기존 동작 확인")
    box.setIcon(kind)
    box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
    save = box.button(QMessageBox.StandardButton.Save)
    cancel = box.button(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(save)
    box.setEscapeButton(cancel)
    try:
        QTimer.singleShot(0, save.click)
        assert box.exec() == QMessageBox.StandardButton.Save
        assert box.clickedButton() is save
        assert box.defaultButton() is save and box.escapeButton() is cancel
        assert box._dc_message_icon_kind == kind
        pixmap = box.iconPixmap()
        assert not pixmap.isNull()
        expected = QColor(box._dc_message_icon_signature[1])
        image = pixmap.toImage()
        opaque = [
            image.pixelColor(x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 240
        ]
        assert opaque
        assert all(abs(color.hslHueF() - expected.hslHueF()) < 0.02 for color in opaque)
    finally:
        box.close()
        app.removeEventFilter(style_filter)


def test_custom_pixmaps_remain_unchanged_and_restyled_standard_icon_refreshes(host):
    _, parent = host
    box = QMessageBox(parent)
    custom = QPixmap(24, 24)
    custom.fill(QColor("#ff0000"))
    box.setIconPixmap(custom)
    before = box.iconPixmap().cacheKey()
    _apply_message_box_palette_icon(box, settings=parent.settings)
    assert box.iconPixmap().cacheKey() == before
    box.setIcon(QMessageBox.Icon.Warning)
    _apply_message_box_palette_icon(box, settings=parent.settings)
    first = box.iconPixmap().cacheKey()
    _apply_message_box_palette_icon(box, settings=parent.settings)
    assert box.iconPixmap().cacheKey() == first
    parent.settings.setValue("theme_color", "#008e82")
    _apply_message_box_palette_icon(box, settings=parent.settings)
    assert box.iconPixmap().cacheKey() != first
    box.setIconPixmap(custom)
    before = box.iconPixmap().cacheKey()
    _apply_message_box_palette_icon(box, settings=parent.settings)
    assert box.iconPixmap().cacheKey() == before
    box.close()


@pytest.mark.parametrize("font_size", [11, 24])
def test_standard_message_footer_fits_the_saved_body_font(host, font_size):
    app, parent = host
    parent.settings.setValue("font_size", font_size)
    style_filter = _CommonDialogStyleFilter(app)
    app.installEventFilter(style_filter)
    box = QMessageBox(parent)
    box.setWindowTitle("입력값 확인")
    box.setText("일정 정보를 확인하세요.")
    box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
    observations = []

    def inspect_and_close():
        for button in box.buttons():
            metrics = QFontMetricsF(button.font())
            observations.append((button.height(), math.ceil(metrics.height())))
        box.reject()

    try:
        QTimer.singleShot(100, inspect_and_close)
        box.exec()
        assert len(observations) == 2
        assert all(height >= text_height + 10 for height, text_height in observations)
    finally:
        box.close()
        app.removeEventFilter(style_filter)
