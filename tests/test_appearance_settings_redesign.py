# -*- coding: utf-8 -*-
"""Actual Qt picker geometry and draft surfaces, isolated from persisted themes."""

from collections import Counter
import os
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QPoint, QSettings, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPalette
from PyQt6.QtWidgets import QApplication, QColorDialog, QWidget
import pytest

from calendar_app.presentation.dialogs.dialog_styles import install_common_dialog_style_filter
from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
    PanelColorPickerDialog,
    _contrast_ratio,
)


@pytest.fixture(scope="session", autouse=True)
def application_lifetime():
    application = QApplication.instance() or QApplication([])
    application.setFont(QFont("Malgun Gothic", 11))
    install_common_dialog_style_filter(application)
    yield application


@pytest.fixture
def picker(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    settings.setValue("font_size", 11)
    settings.setValue("unrelated_preference", "preserved")
    owner = QWidget()
    owner.settings = settings
    dialogs = []
    monkeypatch.setattr(
        "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
        lambda *_args, **_kwargs: (1600, 1000),
    )

    def create(**kwargs):
        dialog = PanelColorPickerDialog(owner, current_font_size=11, **kwargs)
        dialogs.append(dialog)
        dialog.show()
        settle()
        dialog.setProperty("_dc_preferred_size", QSize(960, 740))
        dialog.resize(960, 740)
        settle()
        assert dialog.width() == 960
        return dialog

    yield create, settings
    for dialog in dialogs:
        dialog.reject()
        dialog.deleteLater()
    owner.deleteLater()
    settle()


def settle():
    for _ in range(4):
        QApplication.instance().processEvents()


def surface(widget, background):
    result = QImage(widget.size(), QImage.Format.Format_ARGB32)
    result.fill(QColor(background))
    painter = QPainter(result)
    widget.render(painter)
    painter.end()
    return result


@pytest.mark.parametrize("mode", ["light", "dark", "auto", "custom"])
def test_mode_surfaces_cards_and_preview_follow_draft_without_settings_writes(picker, mode):
    create, settings = picker
    options = (
        {"current_base": "#16443a", "current_base_source": "custom"} if mode == "custom" else {}
    )
    before = {key: settings.value(key) for key in settings.allKeys()}
    dialog = create(**options)
    dialog._system_mode_variant = lambda: "light"
    dialog._set_appearance_mode("dark" if mode == "custom" else mode)
    if mode != "custom":
        dialog._select_style_family("navy_lilac")
    dialog._flush_preview_refresh()
    settle()
    light = mode in {"light", "auto"}
    button = next(
        button for button in dialog._appearance_mode_btns.values() if not button.isChecked()
    )
    image = surface(button, dialog._ui_tokens["bg_main"])
    background = image.pixelColor(image.width() - 6, image.height() // 2)
    foreground = button.palette().color(QPalette.ColorRole.ButtonText)
    assert (background.lightnessF() > 0.5) is light
    assert _contrast_ratio(foreground.name(), background.name()) >= 4.5
    assert dialog.is_light_mode() is light
    assert dialog._preview_panel.styleSheet().find(dialog._ui_tokens["content_bg"]) >= 0
    preview_background = dialog._preview_frame.palette().color(QPalette.ColorRole.Window)
    assert preview_background.name() == dialog._base_hex.lower()
    assert (preview_background.lightnessF() > 0.5) is light
    chrome = dialog._dc_dialog_chrome_controller
    assert (
        chrome.header.palette().color(QPalette.ColorRole.Window).lightnessF() > 0.5
        if light
        else chrome.header.palette().color(QPalette.ColorRole.Window).lightnessF() < 0.5
    )
    assert dialog._dc_chrome_settings is dialog._draft_settings
    assert dialog._dc_dialog_shadow_controller.surface.dark is not light
    assert {key: settings.value(key) for key in settings.allKeys()} == before
    if mode == "custom":
        assert dialog.selected_base_hex() == "#16443a"
    output = os.environ.get("AIR_APPEARANCE_PREVIEW_DIR")
    if output:
        destination = Path(output)
        destination.mkdir(parents=True, exist_ok=True)
        rendered = surface(dialog, dialog._ui_tokens["bg_main"])
        assert rendered.save(str(destination / (mode + "-wide.png")))
    dialog.reject()
    assert {key: settings.value(key) for key in settings.allKeys()} == before


def test_compact_first_view_reaches_accent_and_keeps_equal_mode_segments(picker):
    dialog = picker[0]()
    dialog.resize(960, 740)
    settle()
    assert dialog._point_columns == len(dialog._family_btns) == 9
    assert max(button.height() for button in dialog._family_btns.values()) < 72
    widths = [button.width() for button in dialog._appearance_mode_btns.values()]
    assert max(widths) - min(widths) <= 1
    viewport = dialog._settings_scroll.viewport()
    first_accent = next(iter(dialog._family_btns.values()))
    assert viewport.rect().contains(first_accent.mapTo(viewport, first_accent.rect().center()))


def test_enabled_custom_actions_and_icons_keep_contrast_when_switching_draft_modes(picker):
    dialog = picker[0]()
    dialog._section_toggles["readability"].setChecked(True)
    original = {key: picker[1].value(key) for key in picker[1].allKeys()}
    for mode in ("dark", "light", "dark", "light"):
        dialog._set_appearance_mode(mode)
        dialog._select_style_family("navy_lilac")
        dialog._flush_preview_refresh()
        settle()
        expected = QColor(dialog._ui_tokens["text_primary"]).name()
        # The background choice is a segmented control drawn over its section; this
        # helper paints an opaque backdrop, so check the inactive (opaque) segment.
        segment = dialog._btn_custom
        assert segment.isEnabled() and not segment.isChecked()
        image = surface(segment, dialog._ui_tokens["bg_main"])
        background = image.pixelColor(image.width() - 6, image.height() // 2)
        foreground = segment.palette().color(QPalette.ColorRole.ButtonText)
        assert _contrast_ratio(foreground.name(), background.name()) >= 4.5
        for button in (
            dialog._point_custom_btn,
            dialog._btn_apply_preset_text,
        ):
            assert button.isEnabled()
            image = surface(button, dialog._ui_tokens["bg_main"])
            background = image.pixelColor(image.width() - 6, image.height() // 2)
            foreground = button.palette().color(QPalette.ColorRole.ButtonText)
            assert foreground.name() == expected
            assert _contrast_ratio(foreground.name(), background.name()) >= 4.5
            if not button.icon().isNull():
                icon = button.icon().pixmap(24, 24).toImage()
                opaque_colors = Counter(
                    icon.pixelColor(x, y).name()
                    for x in range(icon.width())
                    for y in range(icon.height())
                    if icon.pixelColor(x, y).alpha() >= 240
                )
                assert opaque_colors.most_common(1)[0][0] == expected
        output = os.environ.get("AIR_APPEARANCE_PREVIEW_DIR")
        if output:
            destination = Path(output)
            destination.mkdir(parents=True, exist_ok=True)
            assert surface(dialog, dialog._ui_tokens["bg_main"]).save(
                str(destination / (mode + "-expanded.png"))
            )
    assert {key: picker[1].value(key) for key in picker[1].allKeys()} == original


def test_form_width_reflows_existing_cards_and_keeps_keyboard_columns_and_draft(picker):
    dialog = picker[0]()
    dialog._select_style_family("ocean")
    dialog._slider.setValue(153)
    cards = list(dialog._family_btns.values())
    original = dialog._appearance_state()
    for width, columns in ((900, 9), (420, 7), (230, 3), (900, 9)):
        dialog._reflow_family_grid(width)
        assert dialog._point_columns == columns
        assert all(button.property("navigation_columns") == columns for button in cards)
        assert list(dialog._family_btns.values()) == cards
        assert dialog._appearance_state() == original


@pytest.mark.parametrize("font_size", [11, 24])
def test_footer_controls_fit_and_remain_outside_the_settings_scroll(picker, font_size):
    dialog = picker[0]()
    if font_size == 24:
        dialog.reject()
        dialog = PanelColorPickerDialog(dialog.parentWidget(), current_font_size=24)
        dialog.show()
    try:
        dialog.resize(680, 740)
        settle()
        buttons = (
            dialog._details_btn,
            dialog._revert_all_btn,
            dialog._cancel_btn,
            dialog._apply_btn,
        )
        for button in buttons:
            bounds = button.rect().translated(button.mapTo(dialog, QPoint()))
            assert dialog.rect().contains(bounds)
            assert button.width() >= button.minimumSizeHint().width()
            assert not dialog._settings_scroll.isAncestorOf(button)
        assert dialog._appearance_workspace.itemAt(0).widget() is dialog._preview_panel
        output = os.environ.get("AIR_APPEARANCE_PREVIEW_DIR")
        if output:
            destination = Path(output)
            destination.mkdir(parents=True, exist_ok=True)
            assert surface(dialog, dialog._ui_tokens["bg_main"]).save(
                str(destination / f"narrow-{font_size}pt.png")
            )
    finally:
        dialog.reject()
        if font_size == 24:
            dialog.deleteLater()


@pytest.mark.parametrize("target", ["background", "accent", "text"])
def test_picker_color_dialogs_use_qt_and_cancel_without_changing_the_draft(picker, target):
    dialog = picker[0]()
    original = dialog._appearance_state()
    callback = {
        "background": dialog._open_custom_color,
        "accent": dialog._open_custom_point_color,
        "text": dialog._row_primary._pick,
    }[target]
    with patch.object(QColorDialog, "getColor", Mock(return_value=QColor())) as choose:
        callback()
    assert choose.call_args.args[3] & QColorDialog.ColorDialogOption.DontUseNativeDialog
    assert dialog._appearance_state() == original


def test_parentless_picker_keeps_a_readonly_draft_profile_and_cancel_does_not_persist():
    source = QSettings("kimhyojin", "Dark Calendar")
    before = {key: source.value(key) for key in source.allKeys()}
    dialog = PanelColorPickerDialog(current_font_size=11)
    try:
        dialog._set_appearance_mode("light")
        assert dialog._draft_settings.source is dialog._appearance_settings
        assert dialog._draft_settings.value("text_theme") == "light"
        assert dialog._draft_settings.value("unrelated_not_set", "fallback") == "fallback"
        assert not hasattr(dialog._draft_settings, "setValue")
        view = dialog._draft_settings.source
        dialog._draft_settings.source = None
        assert dialog._draft_settings.value("missing", "fallback") == "fallback"
        assert dialog._draft_settings.allKeys() == []
        dialog._draft_settings.source = view
        raw_source = view.source
        view.source = None
        assert view.value("missing", "fallback") == "fallback" and view.allKeys() == []
        view.source = raw_source
        dialog.reject()
        assert {key: source.value(key) for key in source.allKeys()} == before
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("kind", ["uppercase", "invalid_color", "invalid_metric"])
def test_opening_and_cancelling_does_not_normalize_or_delete_original_override_values(picker, kind):
    create, settings = picker
    key, value = {
        "uppercase": ("dialog_token.accent", "#AABBCC"),
        "invalid_color": ("dialog_token.text_primary", "not-a-color"),
        "invalid_metric": ("dialog_token.metric.button_height", "invalid-number"),
    }[kind]
    settings.setValue(key, value)
    original = {name: settings.value(name) for name in settings.allKeys()}
    with (
        patch.object(settings, "setValue", wraps=settings.setValue) as write,
        patch.object(settings, "remove", wraps=settings.remove) as remove,
    ):
        dialog = create()
        dialog._set_appearance_mode("light")
        dialog.reject()
        assert {name: settings.value(name) for name in settings.allKeys()} == original
        write.assert_not_called()
        remove.assert_not_called()
        if kind == "uppercase":
            assert dialog.selected_dialog_color_overrides()["accent"] == "#aabbcc"
