# -*- coding: utf-8 -*-
"""Appearance drafts preserve a directly selected background until style selection."""

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QColorDialog, QDialog, QWidget
import pytest

from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
    PanelColorPickerDialog,
)
from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin
from calendar_app.shared.system_theme import set_runtime_system_text_theme
from calendar_app.shared.theme_snapshot import build_theme_snapshot

_CUSTOM_ACCENT = "#4da6ff"


class _Settings:
    def __init__(self):
        self.values = {
            "text_theme": "light",
            "panel_base_color": "#24413f",
            "theme_color": "#bd9be9",
            "appearance_style_family": "navy_lilac",
            "appearance_base_source": "custom",
            "appearance_accent_source": "family",
            "appearance_family_dark_base": "#24314f",
            "appearance_family_dark_accent": "#bd9be9",
            "appearance_family_light_base": "#f7f6ff",
            "appearance_family_light_accent": "#7454ac",
            "last_opacity": 151,
            "last_opacity_unit": "byte",
            "last_border_opacity": 90,
            "last_text_opacity": 240,
            "ui_shape_preset": "round",
            "widget_mode_layout": "focus_vertical",
        }

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)

    def contains(self, key):
        return key in self.values

    def allKeys(self):
        return list(self.values)


class _Host(MainWindowUiActionsMixin, QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.settings = _Settings()
        self.applied = 0

    def apply_theme_settings(self):
        self.applied += 1

    def update_panel_color_recent_menu(self):
        pass


@pytest.fixture
def host():
    app = QApplication.instance() or QApplication([])
    set_runtime_system_text_theme("dark")
    widget = _Host()
    yield widget
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    set_runtime_system_text_theme(None)


@pytest.mark.parametrize("action", ["cancel", "unchanged", "accent", "family"])
def test_reopened_custom_background_draft_preserves_origin_and_saved_pairs(
    host, monkeypatch, action
):
    before = dict(host.settings.values)
    dialogs = []

    def execute(dialog):
        dialogs.append(dialog)
        assert dialog.selected_base_hex() == "#24413f"
        assert dialog.selected_base_source() == "custom"
        assert dialog.selected_style_family() == "navy_lilac"
        assert dialog._appearance_change_categories() == []
        assert QColor(dialog._base_hex).lightnessF() >= 0.94
        assert dialog.selected_point_hex() == "#7454ac"
        if action == "accent":
            dialog._apply_custom_point_color(_CUSTOM_ACCENT)
        elif action == "family":
            dialog._select_style_family("navy_lilac")
        return QDialog.DialogCode.Rejected if action == "cancel" else QDialog.DialogCode.Accepted

    monkeypatch.setattr(PanelColorPickerDialog, "exec", execute)
    host.open_panel_background_color_dialog()
    if action == "cancel":
        assert host.settings.values == before
        assert host.applied == 0
        return

    assert host.applied == 1
    assert host.settings.value("appearance_style_family") == "navy_lilac"
    for key in (
        "last_opacity",
        "last_border_opacity",
        "last_text_opacity",
        "ui_shape_preset",
        "widget_mode_layout",
    ):
        assert host.settings.value(key) == before[key]
    if action == "family":
        assert host.settings.value("appearance_base_source") == "family"
        for key, value in dialogs[0].selected_style_family_variants().items():
            assert host.settings.value(f"appearance_family_{key}") == value
    else:
        assert host.settings.value("panel_base_color") == "#24413f"
        assert host.settings.value("appearance_base_source") == "custom"
        for key, value in before.items():
            if key.startswith("appearance_family_"):
                assert host.settings.value(key) == value
        assert host.settings.value("appearance_accent_source") == (
            "custom" if action == "accent" else "family"
        )
        if action == "accent":
            assert host.settings.value("theme_color") == _CUSTOM_ACCENT
        snapshot = build_theme_snapshot(host.settings, persist_opacity=False)
        assert QColor(snapshot.panel_base_color).lightnessF() >= 0.94


def test_custom_base_draft_mode_switch_and_os_event_keep_raw_color(host, monkeypatch):
    host.settings.values["text_theme"] = "auto"

    def execute(dialog):
        assert dialog.selected_point_hex() == "#bd9be9"
        set_runtime_system_text_theme("light")
        dialog.handle_system_theme_change("light")
        assert dialog._appearance_change_categories() == []
        assert not dialog.point_color_changed()
        assert dialog.selected_point_hex() == "#7454ac"
        assert dialog.selected_base_hex() == "#24413f"
        assert QColor(dialog._base_hex).lightnessF() >= 0.94
        dialog._set_appearance_mode("dark")
        assert dialog.selected_base_source() == "custom"
        assert dialog.selected_base_hex() == "#24413f"
        assert dialog._base_hex == "#24413f"
        assert dialog.selected_point_hex() == "#bd9be9"
        dialog._set_appearance_mode("light")
        assert dialog.selected_base_source() == "custom"
        assert dialog.selected_base_hex() == "#24413f"
        assert dialog.selected_point_hex() == "#7454ac"
        return QDialog.DialogCode.Rejected

    before = dict(host.settings.values)
    monkeypatch.setattr(PanelColorPickerDialog, "exec", execute)
    host.open_panel_background_color_dialog()
    assert host.settings.values == before


def test_background_picker_keeps_family_accent_link_independent(host, monkeypatch):
    host.settings.values.update(
        appearance_base_source="family", text_theme="dark", panel_base_color="#24314f"
    )
    before = dict(host.settings.values)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *_args: QColor("#375562"))

    def execute(dialog):
        dialog._open_custom_color()
        assert dialog.selected_base_source() == "custom"
        assert dialog.selected_accent_source() == "family"
        assert dialog.selected_point_hex() == "#bd9be9"
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PanelColorPickerDialog, "exec", execute)
    host.open_panel_background_color_dialog()
    assert host.settings.value("panel_base_color") == "#375562"
    assert host.settings.value("appearance_base_source") == "custom"
    assert host.settings.value("appearance_accent_source") == "family"
    for key, value in before.items():
        if key.startswith("appearance_family_"):
            assert host.settings.value(key) == value
    host.settings.values["text_theme"] = "light"
    assert build_theme_snapshot(host.settings, persist_opacity=False).theme_color == "#7454ac"


def test_legacy_family_pair_survives_accent_only_accept_and_later_mode_switch(host, monkeypatch):
    host.settings.values.update(
        appearance_style_family="ocean",
        appearance_base_source="family",
        text_theme="dark",
        panel_base_color="#24314f",
        appearance_family_light_base="#eef8ed",
    )
    before = dict(host.settings.values)

    def execute(dialog):
        assert dialog._appearance_change_categories() == []
        assert dialog.selected_base_source() == "family"
        assert dialog.selected_style_family() == "ocean"
        dialog._apply_custom_point_color(_CUSTOM_ACCENT)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PanelColorPickerDialog, "exec", execute)
    host.open_panel_background_color_dialog()
    assert host.settings.value("appearance_base_source") == "family"
    assert host.settings.value("appearance_style_family") == "ocean"
    for key, value in before.items():
        if key.startswith("appearance_family_"):
            assert host.settings.value(key) == value
    host.settings.values["text_theme"] = "light"
    snapshot = build_theme_snapshot(host.settings, persist_opacity=False)
    assert snapshot.panel_base_color == "#eef8ed"
    assert snapshot.theme_color == _CUSTOM_ACCENT


@pytest.mark.parametrize("action", ["untouched", "opacity", "custom", "custom_then_auto"])
def test_border_settings_are_saved_only_once_a_border_is_chosen(host, monkeypatch, action):
    def execute(dialog):
        dialog._slider.setValue(dialog._slider.value() - 1)  # some unrelated change
        if action == "opacity":
            dialog._border_slider.setValue(dialog._border_slider.value() + 20)
        elif action in {"custom", "custom_then_auto"}:
            monkeypatch.setattr(QColorDialog, "getColor", lambda *_a, **_k: QColor("#335577"))
            dialog._open_custom_border_color()
            if action == "custom_then_auto":
                dialog._use_auto_border()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PanelColorPickerDialog, "exec", execute)
    host.open_panel_background_color_dialog()
    expected_source = {
        "untouched": None,
        "opacity": "auto",
        "custom": "custom",
        "custom_then_auto": None,  # back to where it started: nothing to save
    }[action]
    assert host.settings.value("appearance_border_source") == expected_source
    expected_color = "#335577" if action == "custom" else None
    assert host.settings.value("panel_border_color") == expected_color


def test_readability_text_opacity_is_saved_on_its_own_key(host, monkeypatch):
    def execute(dialog):
        dialog._section_toggles["readability"].setChecked(True)
        dialog._text_slider.setValue(200)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PanelColorPickerDialog, "exec", execute)
    host.open_panel_background_color_dialog()
    assert host.settings.value("text_opacity") == 200
    assert host.settings.value("last_text_opacity") == 240  # the retired key is left alone
