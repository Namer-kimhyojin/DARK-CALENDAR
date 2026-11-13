# -*- coding: utf-8 -*-
"""Explicit appearance actions choose matching family surfaces and preserve intent."""

from PyQt6.QtGui import QColor
import pytest

from calendar_app.presentation.main_window.app_window import OverlayApp
from calendar_app.presentation.main_window.theme_actions import ThemeActionsMixin
from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin
from calendar_app.shared.system_theme import (
    resolve_effective_appearance,
    set_runtime_system_text_theme,
)
from calendar_app.shared.theme_snapshot import build_theme_snapshot


class _Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.writes = []

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.writes.append((key, value))
        self.values[key] = value

    def contains(self, key):
        return key in self.values

    def allKeys(self):
        return list(self.values)

    def remove(self, key):
        self.values.pop(key, None)


def _family_settings(*, accent_source="family"):
    return _Settings(
        {
            "text_theme": "dark",
            "panel_base_color": "#24314f",
            "theme_color": "#bd9be9",
            "appearance_style_family": "fixture_family",
            "appearance_accent_source": accent_source,
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
            "overlay_instances": "[]",
        }
    )


class _Host(ThemeActionsMixin):
    def __init__(self, settings):
        self.settings = settings
        self.snapshots = []
        self.toasts = []

    def apply_theme_settings(self):
        self.snapshots.append(build_theme_snapshot(self.settings, persist_opacity=False))

    def show_toast(self, title, message):
        self.toasts.append((title, message))


class _RecentBackgroundHost(MainWindowUiActionsMixin, _Host):
    def _apply_panel_background_color_refresh(self):
        self.apply_theme_settings()


@pytest.fixture(autouse=True)
def reset_system_appearance():
    set_runtime_system_text_theme("dark")
    yield
    set_runtime_system_text_theme(None)


def test_menu_light_mode_resolves_the_saved_light_family_variant():
    settings = _family_settings()
    before = dict(settings.values)
    host = _Host(settings)
    host.change_text_theme("light")
    snapshot = host.snapshots[-1]
    assert snapshot.text_theme == "light"
    assert snapshot.panel_base_color == "#f7f6ff"
    assert snapshot.theme_color == "#7454ac"
    assert snapshot.opacity_factor == 151 / 255
    assert settings.values == {**before, "text_theme": "light"}


def test_menu_dark_mode_resolves_dark_family_from_a_stored_light_selection():
    settings = _family_settings()
    settings.values.update(text_theme="light", panel_base_color="#f7f6ff", theme_color="#7454ac")
    host = _Host(settings)
    host.change_text_theme("dark")
    snapshot = host.snapshots[-1]
    assert snapshot.text_theme == "dark"
    assert snapshot.panel_base_color == "#24314f"
    assert snapshot.theme_color == "#bd9be9"


def test_explicit_light_family_preserves_a_custom_accent():
    settings = _family_settings(accent_source="custom")
    settings.values["theme_color"] = "#c17735"
    settings.values["text_theme"] = "light"
    snapshot = build_theme_snapshot(settings, persist_opacity=False)
    assert snapshot.panel_base_color == "#f7f6ff"
    assert snapshot.theme_color == "#c17735"
    assert settings.writes == []


def test_selecting_a_new_accent_marks_it_custom_instead_of_hiding_it_behind_family():
    settings = _family_settings()
    settings.values["text_theme"] = "auto"
    host = _Host(settings)
    host.change_theme_color("#d07139")
    assert host.snapshots[-1].theme_color == "#d07139"
    assert settings.value("appearance_accent_source") == "custom"


def test_explicit_color_arguments_remain_preview_overrides():
    settings = _family_settings()
    resolved = resolve_effective_appearance(
        settings,
        text_theme="light",
        panel_base_color="#e9f8ed",
        theme_color="#408254",
        allow_family_base=False,
        allow_family_accent=False,
    )
    assert resolved == ("light", "#e9f8ed", "#408254")
    assert settings.writes == []


def test_auto_switch_remains_read_only_and_custom_mode_keeps_original_colors():
    settings = _family_settings()
    settings.values["text_theme"] = "auto"
    before = dict(settings.values)
    set_runtime_system_text_theme("light")
    auto = build_theme_snapshot(settings, persist_opacity=False)
    assert auto.panel_base_color == "#f7f6ff"
    assert auto.theme_color == "#7454ac"
    assert settings.values == before
    assert settings.writes == []
    settings.values["text_theme"] = "custom"
    custom = build_theme_snapshot(settings, persist_opacity=False)
    assert custom.panel_base_color == "#24314f"
    assert custom.theme_color == "#bd9be9"


def test_palette_commands_use_the_same_switch_and_preserve_original_family_colors():
    settings = _family_settings()
    before = dict(settings.values)
    host = _Host(settings)
    for mode, expected in (("light", "#f7f6ff"), ("dark", "#24314f")):
        OverlayApp.handle_palette_command(host, f"theme_{mode}", {})
        assert host.snapshots[-1].panel_base_color == expected
        assert settings.value("panel_base_color") == before["panel_base_color"]
        assert settings.value("theme_color") == before["theme_color"]
    assert len(host.snapshots) == 2


def test_direct_background_selection_is_not_hidden_by_a_family_and_keeps_family_accent():
    settings = _family_settings()
    before = dict(settings.values)
    host = _RecentBackgroundHost(settings)
    host.apply_panel_background_color("#24413f", remember=False)
    assert host.snapshots[-1].panel_base_color == "#24413f"
    assert host.snapshots[-1].theme_color == "#bd9be9"
    assert settings.value("appearance_base_source") == "custom"
    for key in (
        "appearance_style_family",
        "appearance_accent_source",
        "appearance_family_dark_base",
        "appearance_family_dark_accent",
        "appearance_family_light_base",
        "appearance_family_light_accent",
        "last_opacity",
        "ui_shape_preset",
        "widget_mode_layout",
    ):
        assert settings.value(key) == before[key]


def test_custom_background_keeps_its_hue_through_light_dark_and_auto_family_accents():
    settings = _family_settings()
    host = _RecentBackgroundHost(settings)
    host.apply_panel_background_color("#24413f", remember=False)
    host.change_text_theme("light")
    light = QColor(host.snapshots[-1].panel_base_color)
    assert light.lightnessF() >= 0.94
    assert abs(light.hslHueF() - QColor("#24413f").hslHueF()) < 0.03
    assert host.snapshots[-1].theme_color == "#7454ac"
    host.change_text_theme("dark")
    assert host.snapshots[-1].panel_base_color == "#24413f"
    assert host.snapshots[-1].theme_color == "#bd9be9"
    settings.values["text_theme"] = "auto"
    set_runtime_system_text_theme("light")
    auto = build_theme_snapshot(settings, persist_opacity=False)
    assert auto.panel_base_color == light.name()
    assert auto.theme_color == "#7454ac"
    assert settings.value("panel_base_color") == "#24413f"
    assert settings.value("appearance_base_source") == "custom"


@pytest.mark.parametrize("mode", ["light", "dark", "auto"])
def test_saved_family_pairs_are_respected_without_migration(mode):
    settings = _family_settings()
    settings.values["text_theme"] = mode
    settings.values["appearance_family_light_base"] = "#eef8ed"
    settings.values["appearance_family_light_accent"] = "#407d47"
    before = dict(settings.values)
    set_runtime_system_text_theme("light")
    snapshot = build_theme_snapshot(settings, persist_opacity=False)
    if mode == "dark":
        assert snapshot.panel_base_color == "#24314f"
        assert snapshot.theme_color == "#bd9be9"
    else:
        assert snapshot.panel_base_color == "#eef8ed"
        assert snapshot.theme_color == "#407d47"
    assert settings.values == before
    assert settings.writes == []


@pytest.mark.parametrize("base", ["#000000", "#1c1c1c", "#333333"])
def test_legacy_neutral_dark_base_gets_the_pearl_canvas_without_replacing_saved_base(base):
    settings = _Settings({"text_theme": "light", "panel_base_color": base})
    assert build_theme_snapshot(settings, persist_opacity=False).panel_base_color == "#f6f7fb"
    assert settings.value("panel_base_color") == base
    assert settings.writes == []


@pytest.mark.parametrize("base", ["#16394b", "#24413f", "#492d45"])
def test_legacy_hued_dark_base_gets_a_light_counterpart_and_roundtrips(base):
    settings = _Settings({"text_theme": "light", "panel_base_color": base})
    light = QColor(build_theme_snapshot(settings, persist_opacity=False).panel_base_color)
    original = QColor(base)
    assert light.lightnessF() >= 0.94
    assert abs(light.hslHueF() - original.hslHueF()) < 0.03
    settings.values["text_theme"] = "dark"
    assert build_theme_snapshot(settings, persist_opacity=False).panel_base_color == base
    assert settings.value("panel_base_color") == base
    assert settings.writes == []


@pytest.mark.parametrize("base", ["#ffffff", "#e8f6f5", "#f1eafa"])
def test_legacy_light_base_gets_a_dark_counterpart_and_roundtrips(base):
    settings = _Settings({"text_theme": "dark", "panel_base_color": base})
    dark = QColor(build_theme_snapshot(settings, persist_opacity=False).panel_base_color)
    assert 0.10 <= dark.lightnessF() <= 0.15
    settings.values["text_theme"] = "light"
    assert build_theme_snapshot(settings, persist_opacity=False).panel_base_color == base
    assert settings.value("panel_base_color") == base
    assert settings.writes == []
