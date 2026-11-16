# -*- coding: utf-8 -*-
"""Template colour aliases build their theme map only when the HTML uses one.

``_template_color_alias_map`` takes a full theme snapshot (about 150 settings reads),
and clock, stopwatch and text widgets resolve aliases on every tick although their
default templates use none. The resolver must stay byte-identical to the old eager
version for templates with and without aliases.
"""

from unittest import mock

from PyQt6.QtCore import QDateTime, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.widgets import overlay_base
from calendar_app.presentation.widgets.overlay_base import (
    _PRESET_FALLBACK,
    _TEMPLATE_COLOR_ALIAS_RE,
    _TEMPLATE_COLOR_ALIASES,
    _BaseOverlayWidget,
    _extract_global_lh,
    _scale_template_html,
)
from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget

_CLASSES = {
    "clock": OverlayClockWidget,
    "stopwatch": OverlayStopwatchWidget,
    "countdown": OverlayCountdownWidget,
    "datecard": OverlayDateCardWidget,
    "dday": OverlayDDayWidget,
    "text": OverlayTextWidget,
    "weather": OverlayWeatherWidget,
}
_NOW = QDateTime.fromString("2026-10-07T18:47:09", Qt.DateFormat.ISODate)
_RENDERERS = {
    "clock": lambda w, tmpl: w._resolve_clock_template(tmpl, _NOW, "KST"),
    "stopwatch": lambda w, tmpl: w._resolve_sw_template(tmpl, 754500, False),
    "countdown": lambda w, tmpl: w._resolve_cd_template(tmpl, "02:03:04", _NOW.addSecs(7384)),
    "datecard": lambda w, tmpl: w._resolve_dc_template(tmpl, _NOW),
    "dday": lambda w, tmpl: w._resolve_dd_template(
        tmpl, "D-14", "프로젝트 발표", _NOW.date().addDays(14)
    ),
    "text": lambda w, tmpl: w.resolve_template(
        override_text=tmpl,
        app_data={"task_count": 3, "next_event": "검토", "custom_var": "집중"},
    ),
    "weather": lambda w, tmpl: w._resolve_weather_template(
        tmpl,
        {
            "city": "서울",
            "temp": "18.2",
            "unit": "°C",
            "desc": "흐림",
            "humidity": "72",
            "wind": "2.8",
            "_wmo": 3,
            "error": "",
        },
    ),
}
_TAILS = (";", '"', "'")
_NON_ALIAS_VALUES = (
    "color:red",
    "color:Red",
    "color:#1e90ff",
    "color:mutedx",
    "color:accent-2",
    "color:text_primary",
    "color:rgba(1,2,3,0.5)",
)


def _eager_resolve(widget, html: str) -> str:
    """Reference copy of the resolver before the lazy map: one snapshot per call."""
    alias_map = widget._template_color_alias_map()

    def _replace(match):
        alias = match.group(1).lower()
        resolved = alias_map.get(alias)
        return f"color:{resolved}" if resolved else match.group(0)

    return _TEMPLATE_COLOR_ALIAS_RE.sub(_replace, html)


class _CountingSettings(QSettings):
    """INI settings that record every key read through ``value``."""

    def __init__(self, path):
        super().__init__(str(path), QSettings.Format.IniFormat)
        self.reads: list[str] = []

    def value(self, key, *args, **kwargs):
        self.reads.append(str(key))
        return super().value(key, *args, **kwargs)


@pytest.fixture
def owner(tmp_path):
    app = QApplication.instance() or QApplication([])
    holder = QWidget()
    holder.settings = _CountingSettings(tmp_path / "overlay.ini")
    yield holder
    holder.close()
    app.processEvents()


@pytest.fixture
def clock(owner):
    widget = OverlayClockWidget(owner)
    widget._set_runtime_active(False)
    yield widget
    widget.close()


def _case_variants(alias: str) -> list[str]:
    alternating = "".join(ch.upper() if index % 2 else ch for index, ch in enumerate(alias))
    return sorted({alias, alias.upper(), alias.capitalize(), alternating})


def _styled(value: str, tail: str) -> str:
    # The alias regex needs ';', '"' or "'" right after the name.
    if tail == ";":
        return f'<span style="{value};font-weight:bold">x</span>'
    if tail == '"':
        return f'<span style="font-weight:bold;{value}">x</span>'
    return f"<span style='font-weight:bold;{value}'>x</span>"


def _spy_alias_map():
    return mock.patch.object(
        _BaseOverlayWidget,
        "_template_color_alias_map",
        autospec=True,
        side_effect=_BaseOverlayWidget._template_color_alias_map,
    )


def test_alias_map_is_not_built_for_html_without_a_known_alias(clock):
    html = "".join(_styled(value, ";") for value in _NON_ALIAS_VALUES) + "<b>12:34</b>"

    with _spy_alias_map() as built:
        assert clock._resolve_template_color_aliases(html) == html
        assert clock._resolve_template_color_aliases("plain 12:34") == "plain 12:34"

    assert built.call_count == 0


def test_alias_map_keys_are_exactly_the_known_aliases(clock):
    # The lazy resolver skips names outside _TEMPLATE_COLOR_ALIASES without building the
    # map, so a map key missing from that set would silently stop resolving.
    assert set(clock._template_color_alias_map()) == set(_TEMPLATE_COLOR_ALIASES)


def test_alias_map_is_built_once_per_call_for_html_with_aliases(clock):
    html = (
        '<span style="color:muted;">a</span>'
        '<span style="color:ACCENT;">b</span>'
        "<span style='color:red;'>c</span>"
        '<span style="color:Muted">d</span>'
    )

    with _spy_alias_map() as built:
        resolved = clock._resolve_template_color_aliases(html)

    assert built.call_count == 1
    alias_map = clock._template_color_alias_map()
    assert resolved == (
        f'<span style="color:{alias_map["muted"]};">a</span>'
        f'<span style="color:{alias_map["accent"]};">b</span>'
        "<span style='color:red;'>c</span>"
        f'<span style="color:{alias_map["muted"]}">d</span>'
    )


@pytest.mark.parametrize("alias", sorted(_TEMPLATE_COLOR_ALIASES))
def test_every_alias_case_and_tail_matches_the_eager_resolver(clock, alias):
    for variant in _case_variants(alias):
        for tail in _TAILS:
            html = _styled(f"color:{variant}", tail)
            resolved = clock._resolve_template_color_aliases(html)
            assert resolved == _eager_resolve(clock, html), (variant, tail)
            assert f"color:{variant}" not in resolved, (variant, tail)


@pytest.mark.parametrize("value", _NON_ALIAS_VALUES)
def test_unknown_names_and_hex_colours_match_the_eager_resolver(clock, value):
    for tail in _TAILS:
        html = _styled(value, tail)
        assert clock._resolve_template_color_aliases(html) == _eager_resolve(clock, html) == html


def test_mixed_template_matches_the_eager_resolver(clock):
    pieces = [_styled(value, ";") for value in _NON_ALIAS_VALUES]
    for index, alias in enumerate(sorted(_TEMPLATE_COLOR_ALIASES)):
        pieces.append(_styled(f"color:{alias.upper()}", _TAILS[index % len(_TAILS)]))
    pieces.append('<span style="background-color:muted;">bg</span>')
    pieces.append('<span style="color:muted ">no tail</span>')
    html = "\n".join(pieces)

    assert clock._resolve_template_color_aliases(html) == _eager_resolve(clock, html)


@pytest.mark.parametrize("kind", sorted(_CLASSES))
def test_shipped_templates_resolve_byte_identically(owner, monkeypatch, kind):
    monkeypatch.setattr(OverlayWeatherWidget, "request_update", lambda _self: None)
    widget = _CLASSES[kind](owner)
    try:
        # The text widget has no built-in default template (its settings use "").
        default = getattr(widget, "_DEFAULT_TEMPLATE", "")
        templates = [entry["template"] for entry in _PRESET_FALLBACK[kind]]
        templates = [default if tmpl == "__DEFAULT__" else tmpl for tmpl in templates]
        if default:
            templates.append(default)
        seen = {"alias": 0, "plain": 0}
        for template in templates:
            html, _lh = _extract_global_lh(_RENDERERS[kind](widget, template), 24)
            scaled = _scale_template_html(html, 24)
            uses_alias = any(
                match.group(1).lower() in _TEMPLATE_COLOR_ALIASES
                for match in _TEMPLATE_COLOR_ALIAS_RE.finditer(scaled)
            )
            seen["alias" if uses_alias else "plain"] += 1
            resolved = widget._resolve_template_color_aliases(scaled)
            assert resolved == _eager_resolve(widget, scaled), (kind, template)
            if not uses_alias:
                assert resolved == scaled, (kind, template)
        # Every kind ships templates with and without colour aliases.
        assert seen["alias"] > 0 and seen["plain"] > 0, (kind, seen)
    finally:
        widget.close()


@pytest.mark.parametrize(
    "template",
    [
        OverlayStopwatchWidget._DEFAULT_TEMPLATE,
        "{elapsed|size=36|bold|color=accent}\n{status|size=11|color=muted}",
    ],
    ids=["default", "aliases"],
)
def test_stopwatch_label_html_is_byte_identical(owner, monkeypatch, template):
    stopwatch = OverlayStopwatchWidget(owner)
    stopwatch._set_runtime_active(False)
    try:
        rendered = stopwatch._resolve_sw_template(template, 64_500, False)
        stopwatch._set_template_label(rendered, base_size=24)
        lazy_html = stopwatch._template_label.text()
        monkeypatch.setattr(_BaseOverlayWidget, "_resolve_template_color_aliases", _eager_resolve)
        stopwatch._set_template_label(rendered, base_size=24)

        assert lazy_html == stopwatch._template_label.text()
    finally:
        stopwatch.close()


def _tick_theme_cost(widget):
    reads = widget._s().reads
    with mock.patch.object(
        overlay_base, "get_ui_tokens", wraps=overlay_base.get_ui_tokens
    ) as tokens:
        del reads[:]
        widget._tick()
    return tokens.call_count, sum(key.startswith("dialog_token") for key in reads)


def test_default_clock_tick_takes_no_theme_snapshot(clock):
    assert clock._widget_template() == OverlayClockWidget._DEFAULT_TEMPLATE
    assert clock._is_template_mode()

    token_calls, token_reads = _tick_theme_cost(clock)

    assert clock._template_label.text()
    assert (token_calls, token_reads) == (0, 0)


def test_alias_clock_tick_takes_one_theme_snapshot(clock):
    # Guards the counters themselves: an alias template still resolves its colours.
    clock._set(clock._TEMPLATE_KEY, "{time:%H:%M|size=36|bold}\n{date:%Y.%m.%d|color=muted}")

    token_calls, token_reads = _tick_theme_cost(clock)

    assert token_calls == 1
    assert token_reads > 0
    assert "color:muted" not in clock._template_label.text()
