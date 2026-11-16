# -*- coding: utf-8 -*-
"""Desktop overlay widgets follow the app theme: accent, family and panel base.

Every overlay's owner is a ``_SettingsProxy`` that puts the instance id in front of
each key, so a theme key read through it (``oi_clock_0_theme_color``) was always
missing: templates, date cards and the weather caption drew the default blue accent
and dark palette under every theme. A theme change also never redrew the widgets,
because ``apply_theme_settings`` called four methods that do not exist.

Reading and state roles keep today's colours wherever the theme does not change
them: a widget with light text under a theme with dark text (light, or a dark
custom theme) gets the dark text theme's roles with the user's accent.
"""

from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QCoreApplication, QEvent, QRect, QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app import app_paths
from calendar_app.infrastructure.runtime import loop_mixer_audio
from calendar_app.presentation.widgets import overlay_base
from calendar_app.presentation.widgets.overlay_base import _overlay_theme_snapshot
from calendar_app.presentation.widgets.overlay_color_utils import _parse_rgba
from calendar_app.presentation.widgets.overlay_display_presets import overlay_display_presets
from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager, _SettingsProxy
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from calendar_app.shared import system_theme
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY
from calendar_app.shared.color_utils import parse_css_color
from calendar_app.shared.system_theme import set_runtime_system_text_theme
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens

_APP = QApplication.instance() or QApplication([])

_DEFAULT_ACCENT = "#4da6ff"
_THEMES = {
    "dark": {"theme_color": "#ff7a1a", "text_theme": "dark", "panel_base_color": "#14261f"},
    "light": {"theme_color": "#d6336c", "text_theme": "light", "panel_base_color": "#f4efe6"},
    "auto": {"theme_color": "#2fb8a0", "text_theme": "auto", "panel_base_color": "#f4efe6"},
    "custom": {
        "theme_color": "#2fb8a0",
        "text_theme": "custom",
        "panel_base_color": "#1e1a2e",
        "custom_text_primary": "#fff4d6",
        "custom_text_secondary": "#f0c27a",
        "custom_text_muted": "#d9a441",
        "custom_text_faint": "#8f7a52",
    },
    "custom_dark_text": {
        "theme_color": "#7a4fd6",
        "text_theme": "custom",
        "panel_base_color": "#f2efe8",
        "custom_text_primary": "#1d1a14",
        "custom_text_secondary": "#4a3f2a",
        "custom_text_muted": "#6a5a3a",
        "custom_text_faint": "#8a7a5a",
    },
    "family": {
        "theme_color": "#ff7a1a",
        "text_theme": "auto",
        "appearance_style_family": "ocean",
        "appearance_accent_source": "family",
        "appearance_family_dark_accent": "#33ccff",
        "appearance_family_light_accent": "#005f99",
        "appearance_family_dark_base": "#0b1a24",
        "appearance_family_light_base": "#eef6fa",
    },
}
_LIGHT_TEXT = "pure_type"  # the default preset: near-white text
_DARK_TEXT = "pearl_mist"  # dark text on a light card
_ALIAS_TEMPLATES = {
    "clock": ("clock_template", "{time:%H:%M|size=30|color=accent}\n{date:%Y|color=muted}"),
    "stopwatch": ("sw_template", "{minutes|size=30}:{seconds|size=30}.{tenths|color=accent}"),
    "countdown": ("cd_template", "D-{days|size=30}\n{target:%Y.%m.%d|color=muted}"),
    "dday": ("dd_template", "{dday|size=40|color=accent}\n{label|color=muted}"),
    "text": ("label_text", "{task_count|size=20|color=accent} tasks"),
    "weather": ("weather_template", "{temp|size=28|color=accent}\n{city|color=muted}"),
    "date_card": ("dc_template", "{day|size=42|color=accent}\n{weekday|color=muted}"),
}
_SAMPLE_WEATHER = {
    "city": "서울",
    "temp": "18.2",
    "unit": "°C",
    "desc": "흐림",
    "humidity": "72",
    "wind": "2.8",
    "_wmo": 3,
    "error": "",
}


def _settings_for(path, theme):
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    for key, value in _THEMES[theme].items():
        settings.setValue(key, value)
    return settings


@pytest.fixture
def system_tone():
    previous = system_theme._runtime_system_text_theme
    set_runtime_system_text_theme("dark")
    yield set_runtime_system_text_theme
    set_runtime_system_text_theme(previous)


@pytest.fixture
def host(tmp_path, monkeypatch, system_tone):
    monkeypatch.setattr(OverlayWeatherWidget, "request_update", lambda self: None)
    holder = QWidget()
    holder.resize(800, 600)
    holder.settings = _settings_for(tmp_path / "host.ini", "dark")
    yield holder
    holder.close()
    holder.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def manager(host):
    mgr = OverlayWidgetManager(host)
    host.overlay_manager = mgr
    yield mgr
    mgr.shutdown()
    for _iid, _name, _kind, widget in mgr.live_instances():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _use_theme(host, theme):
    settings = host.settings
    for key in list(settings.allKeys()):
        if not key.startswith("oi_") and key != "overlay_instances":
            settings.remove(key)
    for key, value in _THEMES[theme].items():
        settings.setValue(key, value)


def _make(manager, kind, preset=_LIGHT_TEXT):
    widget = manager.get_widget(manager.add_instance(kind))
    widget._set_runtime_active(False)
    if kind == "weather":
        widget._weather_data = dict(_SAMPLE_WEATHER)
    if preset is not None:
        widget._set_display_preset(preset)
    return widget


def _roles(tokens):
    return {
        "secondary": tokens["text_secondary"],
        "muted": tokens["text_muted"],
        "faint": tokens["text_faint"],
        "accent": tokens["accent"],
        "info": tokens.get("info_hex", tokens["accent"]),
        "warning": tokens["warning_hex"],
        "success": tokens["success_hex"],
        "danger": tokens["danger_hex"],
    }


def _owner_rule_snapshot(settings, text_rgba):
    """The owner's rule written out plainly: when the widget's text tone is the opposite
    of the plain theme's primary text, the text theme of the widget's own tone."""
    plain = build_theme_snapshot(settings)
    if not text_rgba:
        return plain
    widget_text, _alpha = _parse_rgba(str(text_rgba), fallback_alpha=255)
    plain_text = parse_css_color(plain.text_palette["text_primary"])
    if widget_text.lightnessF() >= 0.5 and plain_text.lightnessF() < 0.5:
        return build_theme_snapshot(settings, text_theme="dark")
    if widget_text.lightnessF() < 0.5 and plain_text.lightnessF() >= 0.5:
        return build_theme_snapshot(settings, text_theme="light")
    return plain


# --------------------------------------------------------------------------- keys


@pytest.mark.parametrize(
    "case",
    [*sorted(_ALIAS_TEMPLATES), "date_card/mini_grid", "date_card/week_strip", "weather/status"],
)
def test_theme_keys_are_never_read_through_the_instance_proxy(manager, monkeypatch, case):
    kind, _, variant = case.partition("/")
    widget = _make(manager, kind)
    key, template = _ALIAS_TEMPLATES[kind]
    widget._set(key, template)
    if variant:
        widget._set(key, "")
    if variant in ("mini_grid", "week_strip"):
        widget._set("display_style", variant)
    if variant == "status":
        widget._weather_data = dict(_SAMPLE_WEATHER, error="network")
    reads = []
    original = _SettingsProxy.value

    def recording_value(proxy, key, default=None, type=None):  # noqa: A002
        reads.append(str(key))
        return original(proxy, key, default, type)

    monkeypatch.setattr(_SettingsProxy, "value", recording_value)
    widget._apply_and_resize()
    if hasattr(widget, "_tick"):
        widget._tick()
    widget._apply_appearance()

    prefix = f"{widget._settings_prefix()}_"
    assert reads
    assert [key for key in reads if not key.startswith(prefix)] == []


# --------------------------------------------------------------------------- template aliases


def test_template_accent_follows_the_app_theme(manager):
    clock = _make(manager, "clock")
    clock._set("clock_template", "{time:%H:%M|size=30|color=accent}")
    clock._apply_and_resize()

    html = clock._template_label.text().lower()
    assert "#ff7a1a" in html
    assert _DEFAULT_ACCENT not in html


@pytest.mark.parametrize(
    ("theme", "preset", "expected"),
    [
        # Dark-theme reading roles are light: a dark-text card takes the light ones.
        ("dark", _LIGHT_TEXT, "plain"),
        ("dark", _DARK_TEXT, "light"),
        # Light-theme reading roles are dark: a light-text widget keeps the dark ones.
        ("light", _LIGHT_TEXT, "dark"),
        ("light", _DARK_TEXT, "plain"),
        ("custom", _LIGHT_TEXT, "plain"),
        ("custom", _DARK_TEXT, "light"),
        ("custom_dark_text", _LIGHT_TEXT, "dark"),
        ("custom_dark_text", _DARK_TEXT, "plain"),
    ],
)
def test_reading_roles_change_only_where_the_theme_changes_them(
    manager, host, theme, preset, expected
):
    _use_theme(host, theme)
    clock = _make(manager, "clock", preset)

    alias_map = clock._template_color_alias_map()

    settings = host.settings
    tokens = (
        get_ui_tokens(settings, text_theme=expected)
        if expected in ("dark", "light")
        else get_ui_tokens(settings)
    )
    assert {name: alias_map[name] for name in _roles(tokens)} == _roles(tokens)
    assert alias_map["accent"] == _THEMES[theme]["theme_color"]


def test_custom_theme_colours_reach_light_text_widgets(manager, host):
    _use_theme(host, "custom")
    clock = _make(manager, "clock", _LIGHT_TEXT)

    alias_map = clock._template_color_alias_map()

    assert parse_css_color(alias_map["muted"]).name() == "#d9a441"
    assert parse_css_color(alias_map["secondary"]).name() == "#f0c27a"


@pytest.mark.parametrize("theme", sorted(_THEMES))
@pytest.mark.parametrize("tone", ["light", "dark"])
@pytest.mark.parametrize("text_opacity", [255, 120])
def test_theme_snapshot_helper_matches_the_owner_rule(
    tmp_path, system_tone, theme, tone, text_opacity
):
    system_tone(tone)
    settings = _settings_for(tmp_path / "rule.ini", theme)
    settings.setValue("text_opacity", text_opacity)

    for preset in overlay_display_presets():
        for text_rgba in (preset.text_rgba, None):
            expected = _owner_rule_snapshot(settings, text_rgba)
            actual = _overlay_theme_snapshot(settings, text_rgba)
            assert get_ui_tokens(settings, snapshot=actual) == get_ui_tokens(
                settings, snapshot=expected
            ), (preset.preset_id, text_rgba)


def test_family_accent_follows_the_tone_used_for_the_widget(tmp_path, system_tone):
    system_tone("light")
    settings = _settings_for(tmp_path / "family.ini", "family")

    light_text = get_ui_tokens(settings, snapshot=_overlay_theme_snapshot(settings, "#fff5f7fb"))
    dark_text = get_ui_tokens(settings, snapshot=_overlay_theme_snapshot(settings, "#ff1b2430"))

    assert light_text["accent"] == "#33ccff"
    assert dark_text["accent"] == "#005f99"


@pytest.mark.parametrize(
    ("theme", "preset"),
    [
        ("light", _LIGHT_TEXT),
        ("light", _DARK_TEXT),
        ("dark", _LIGHT_TEXT),
        ("dark", _DARK_TEXT),
        ("auto", _LIGHT_TEXT),
        ("auto", _DARK_TEXT),
    ],
)
def test_alias_map_takes_one_theme_snapshot(manager, host, theme, preset):
    _use_theme(host, theme)
    clock = _make(manager, "clock", preset)

    with mock.patch.object(
        overlay_base, "build_theme_snapshot", wraps=overlay_base.build_theme_snapshot
    ) as built:
        clock._template_color_alias_map()

    assert built.call_count == 1


# --------------------------------------------------------------------------- date card


def test_date_card_mini_grid_and_week_strip_use_the_theme_accent(manager):
    card = _make(manager, "date_card")
    card._set("dc_template", "")
    card._set("display_style", "mini_grid")
    card._apply_and_resize()
    assert card._grid_widget._accent_color.name() == "#ff7a1a"

    card._set("display_style", "week_strip")
    card._apply_and_resize()
    styles = [cell.styleSheet().lower() for cell in card._ws_cells]
    assert any("color:#ff7a1a; font-weight:bold" in style for style in styles)
    assert not any(_DEFAULT_ACCENT in style for style in styles)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_week_strip_weekdays_keep_light_text_on_light_text_cards(manager, host, theme):
    # Under a light theme the plain weekday cells must not turn dark on a dark card.
    _use_theme(host, theme)
    card = _make(manager, "date_card", _LIGHT_TEXT)
    card._set("dc_template", "")
    card._set("display_style", "week_strip")
    card._apply_and_resize()

    plain = [
        cell.styleSheet()
        for index, cell in enumerate(card._ws_cells)
        if index < 5 and "font-weight:normal" in cell.styleSheet()
    ]
    assert plain
    assert all("color:#f4f7fb;" in style for style in plain), plain


def test_dark_text_cards_get_readable_reading_roles_under_a_dark_theme(manager, host):
    # Pearl Mist and Paper Ivory draw dark text on a light card: the dark theme's
    # near-white muted text and weekday letters were close to invisible there.
    _use_theme(host, "dark")
    clock = _make(manager, "clock", _DARK_TEXT)
    muted = parse_css_color(clock._template_color_alias_map()["muted"])
    assert muted.lightnessF() < 0.5

    card = _make(manager, "date_card", _DARK_TEXT)
    card._set("dc_template", "")
    card._set("display_style", "week_strip")
    card._apply_and_resize()
    plain = [
        cell.styleSheet()
        for index, cell in enumerate(card._ws_cells)
        if index < 5 and "font-weight:normal" in cell.styleSheet()
    ]
    assert plain
    assert "color:#f4f7fb;" not in " ".join(plain)


def test_date_card_without_stored_colours_takes_the_theme_pair(manager):
    card = _make(manager, "date_card", preset=None)
    for key in ("appearance_preset", "text_color_rgba", "bg_color_rgba", "border_color_rgba"):
        card._s().remove(f"{card._pref()}_{key}")
    card._set("appearance_preset", "custom")

    assert card.border_color_rgba() == "#48ff7a1a"
    assert card.bg_color_rgba() == "#d614261f"


# --------------------------------------------------------------------------- weather


def test_weather_status_caption_keeps_its_fixed_size(manager, host):
    host.settings.setValue("font_size", 24)
    weather = _make(manager, "weather")
    weather._weather_data = dict(_SAMPLE_WEATHER, error="network")
    weather._apply_and_resize()

    assert "font-size: 14px;" in weather._status_label.styleSheet()


# --------------------------------------------------------------------------- refresh_theme


def test_refresh_theme_redraws_built_widgets_without_a_tick(manager, host):
    clock = _make(manager, "clock")
    clock._set("clock_template", "{time:%H:%M|size=30|color=accent}")
    clock._apply_and_resize()
    card = _make(manager, "date_card")
    card._set("dc_template", "")
    card._set("display_style", "mini_grid")
    card._apply_and_resize()
    geometries = (clock.geometry(), card.geometry())

    host.settings.setValue("theme_color", "#2fb8a0")
    manager.refresh_theme()

    assert "#2fb8a0" in clock._template_label.text().lower()
    assert card._grid_widget._accent_color.name() == "#2fb8a0"
    assert (clock.geometry(), card.geometry()) == geometries


def test_refresh_theme_keeps_going_after_a_failing_widget(manager, host, caplog):
    first = _make(manager, "clock")
    second = _make(manager, "clock")
    second._set("clock_template", "{time:%H:%M|color=accent}")
    second._apply_and_resize()
    host.settings.setValue("theme_color", "#2fb8a0")

    with mock.patch.object(first, "_apply_appearance", side_effect=RuntimeError("deleted")):
        manager.refresh_theme()

    assert "#2fb8a0" in second._template_label.text().lower()
    assert "Overlay theme refresh failed" in caplog.text


def test_refresh_theme_keeps_live_values_in_text_templates(manager, host):
    # A Text widget's _apply_appearance resolves its template without app data; the
    # theme refresh must not leave "0 tasks" up until the 60 s slow timer.
    manager.set_app_data_provider(lambda: {"task_count": 12, "next_event": "Standup"})
    text = _make(manager, "text")
    text._set("label_text", "{task_count|color=accent} tasks / {next_event}")
    manager.show_instance(text._overlay_inst_id)
    manager.refresh_all_texts(tier="slow")
    assert ">12<" in text._text_label.text()
    geometry = text.geometry()

    host.settings.setValue("theme_color", "#2fb8a0")
    manager.refresh_theme()

    html = text._text_label.text()
    assert ">12<" in html and "Standup" in html, html
    assert "#2fb8a0" in html.lower()
    assert text.geometry() == geometry


def test_refresh_theme_builds_no_hidden_widget_and_stops_after_shutdown(tmp_path, monkeypatch):
    holder = QWidget()
    holder.settings = _settings_for(tmp_path / "saved.ini", "dark")
    holder.settings.setValue(
        "overlay_instances",
        '[{"id": "clock_0", "type": "clock", "name": "Clock", "enabled": false}]',
    )
    mgr = OverlayWidgetManager(holder)
    try:
        mgr.restore_all()
        created = []
        monkeypatch.setattr(mgr, "_create_widget", lambda *args: created.append(args))
        mgr.refresh_theme()
        assert created == []
        assert mgr.live_instances() == []
    finally:
        mgr.shutdown()

    applied = []
    mgr._widgets["late"] = SimpleNamespace(_apply_appearance=lambda: applied.append(1))
    mgr.refresh_theme()
    assert applied == []
    holder.deleteLater()


def test_refresh_theme_restyles_a_resized_loop_mixer_in_place(tmp_path, monkeypatch):
    class ForbiddenDevice:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("A widget regression must not open an audio device")

    class DeviceFreeMixer(loop_mixer_audio.LoopMixer):
        def __init__(self):
            super().__init__(backend_factory=ForbiddenDevice, threaded=False)

    monkeypatch.setattr(loop_mixer_audio, "LoopMixer", DeviceFreeMixer)
    desktop = SimpleNamespace(
        geometry=lambda: QRect(0, 0, 1920, 1080),
        availableGeometry=lambda: QRect(0, 0, 1920, 1080),
    )
    monkeypatch.setattr(OverlayLoopDeckWidget, "screen", lambda self: desktop)
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [desktop]))
    monkeypatch.setattr(app_paths, "LOOP_MIXER_DIR", str(tmp_path / "loop-mixer"))
    previous = _APP.property(EXITING_PROPERTY)
    _APP.setProperty(EXITING_PROPERTY, False)
    holder = QWidget()
    holder.resize(1200, 900)
    holder.settings = _settings_for(tmp_path / "mixer.ini", "dark")
    mgr = OverlayWidgetManager(holder)
    try:
        mixer = mgr.get_widget(mgr.add_instance("loop_deck", "Mixer"))
        mixer.resize(mixer.width() + 120, mixer.height() + 60)
        _APP.processEvents()
        geometry = mixer.geometry()

        holder.settings.setValue("theme_color", "#2fb8a0")
        mgr.refresh_theme()
        _APP.processEvents()

        assert mixer.geometry() == geometry
        assert "47, 184, 160" in mixer.face.styleSheet()
    finally:
        mgr.shutdown()
        for _iid, _name, _kind, widget in mgr.live_instances():
            widget.deleteLater()
        holder.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _APP.setProperty(EXITING_PROPERTY, previous)
