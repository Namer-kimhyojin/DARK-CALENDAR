# -*- coding: utf-8 -*-
"""Real renderer regressions for timer and weather content presets."""

from html import unescape
import json
from pathlib import Path
import re

from PyQt6.QtCore import QDateTime, QSettings, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QTextDocument
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets import overlay_countdown
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.weather_template import render_weather_template


@pytest.fixture
def widgets(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "presets.ini"), QSettings.Format.IniFormat)
    stopwatch = OverlayStopwatchWidget(owner)
    countdown = OverlayCountdownWidget(owner)
    stopwatch._set_runtime_active(False)
    countdown._set_runtime_active(False)
    yield stopwatch, countdown
    stopwatch.close()
    countdown.close()
    owner.close()
    app.processEvents()


def _catalog():
    return json.loads(
        Path("calendar_app/presentation/widgets/widget_presets.json").read_text(
            encoding="utf-8", errors="strict"
        )
    )


def _preset(kind, suffix):
    return next(
        entry["template"] for entry in _catalog()[kind] if entry["label_key"].endswith(suffix)
    )


def _plain(html):
    document = QTextDocument()
    document.setHtml(html)
    return document.toPlainText()


@pytest.mark.parametrize("elapsed, expected", [(754_500, "12:34.5"), (3_754_500, "1:02:34.5")])
def test_tenths_focus_shows_one_fraction_below_and_above_one_hour(widgets, elapsed, expected):
    stopwatch, _countdown = widgets
    rendered = stopwatch._resolve_sw_template(_preset("stopwatch", "preset_tenths"), elapsed, False)

    assert _plain(rendered).splitlines()[0] == expected
    assert _plain(rendered).count(".5") == 1


def test_timer_digits_pad_seconds_without_changing_numeric_condition_context(widgets):
    stopwatch, _countdown = widgets
    rendered = stopwatch._resolve_sw_template(
        "{if seconds == 4}{minutes}:{seconds}.{tenths}{else}wrong{/if}", 64_500, False
    )

    assert _plain(rendered) == "01:04.5"


def test_stopwatch_large_colon_and_fraction_separator_follow_digit_size(widgets):
    stopwatch, _countdown = widgets
    rendered = stopwatch._resolve_sw_template(_preset("stopwatch", "preset_split"), 64_500, False)
    stopwatch._set_template_label(rendered, base_size=24)
    html = stopwatch._template_label.text()

    assert 'font-size:40pt;font-weight:bold">:</span>' in html
    assert 'font-size:40pt;font-weight:bold">.</span>' in html
    assert _plain(html) == "01:04.5"


def test_stopwatch_semantic_colors_are_resolved_in_actual_label(widgets):
    stopwatch, _countdown = widgets
    rendered = stopwatch._resolve_sw_template(_preset("stopwatch", "preset_tenths"), 64_500, False)
    stopwatch._set_template_label(rendered, base_size=24)
    html = stopwatch._template_label.text()

    assert "color:accent" not in html
    assert "color:muted" not in html
    assert stopwatch._template_color_alias_map()["accent"] in html
    assert stopwatch._template_color_alias_map()["muted"] in html


@pytest.mark.parametrize(
    "elapsed, running, glyph", [(0, True, "▶"), (64_500, False, "Ⅱ"), (0, False, "■")]
)
def test_stopwatch_transport_glyphs_use_supported_ui_font(widgets, elapsed, running, glyph):
    stopwatch, _countdown = widgets
    rendered = stopwatch._resolve_sw_template("{status_icon|size=18} {status}", elapsed, running)
    font_match = re.search(r"font-family:'([^']+)'", rendered)
    assert font_match is not None
    font = QFont(unescape(font_match.group(1)))
    font.setStyleStrategy(QFont.StyleStrategy.NoFontMerging)

    assert _plain(rendered).startswith(glyph + " ")
    assert QFontMetrics(font).inFontUcs4(ord(glyph))
    assert "⏹" not in rendered and "⏸" not in rendered
    assert f"font-family:'{font.family()}'" in rendered


@pytest.mark.parametrize("remaining", [None, "", "--:--:--", "∞"])
def test_unset_countdown_presets_show_placeholder_and_setup_hint(widgets, remaining):
    _stopwatch, countdown = widgets
    rendered = countdown._resolve_cd_template(
        "{if days == 0}{days}|{hours}:{minutes}:{seconds}|{remaining}|{target:%Y}{else}wrong{/if}",
        remaining,
        None,
    )
    plain = _plain(rendered)

    assert plain == f"--|--:--:--|--:--:--|{t('widget.countdown.set_target', 'Set target')}"


def test_invalid_countdown_target_uses_setup_hint_instead_of_completed_zero(widgets):
    _stopwatch, countdown = widgets
    invalid = QDateTime()
    remaining, hint = countdown._cd_remaining(invalid)
    rendered = countdown._resolve_cd_template("{days} {remaining} {target}", remaining, invalid)

    assert remaining == "--:--:--"
    assert hint == t("widget.countdown.no_target_hint", "Right-click -> Set target")
    assert _plain(rendered) == f"-- --:--:-- {t('widget.countdown.set_target', 'Set target')}"


def test_countdown_padding_and_large_separators_keep_numeric_condition_values(widgets, monkeypatch):
    _stopwatch, countdown = widgets
    now = QDateTime.fromString("2026-10-07T13:00:00", Qt.DateFormat.ISODate)
    target = now.addSecs(3_845)

    class FixedClock:
        @staticmethod
        def currentDateTime():
            return now

    monkeypatch.setattr(overlay_countdown, "QDateTime", FixedClock)
    rendered = countdown._resolve_cd_template(
        "{if hours == 1}" + _preset("countdown", "preset_flip") + "{else}wrong{/if}",
        "01:04:05",
        target,
    )
    countdown._set_template_label(rendered, base_size=24)
    html = countdown._template_label.text()

    assert _plain(html) == "01:04:05"
    assert html.count('font-size:32pt;font-weight:bold">:</span>') == 2


def test_countdown_target_12_hour_format_uses_real_target_hour(widgets):
    _stopwatch, countdown = widgets
    target = QDateTime.fromString("2026-10-07T18:35:00", Qt.DateFormat.ISODate)
    rendered = countdown._resolve_cd_template("{target:%I:%M %p}", "00:00:00", target)

    assert _plain(rendered) == "06:35 PM"


def test_weather_metric_presets_supply_units_without_unsupported_emoji(widgets):
    data = {
        "_wmo": 3,
        "city": "Seoul",
        "desc": "Cloudy",
        "temp": "18.2",
        "unit": "°C",
        "humidity": "65",
        "wind": "3.4",
    }
    for entry in _catalog()["weather"]:
        template = entry["template"]
        rendered = render_weather_template(template, data, asset_pack_id="classic")
        plain = _plain(rendered)
        assert "💧" not in template
        assert "💨" not in template
        if "{humidity" in template:
            assert "65%" in plain, entry["label_key"]
        if "{wind" in template:
            assert "3.4 m/s" in plain, entry["label_key"]


def test_tomorrow_preset_does_not_pair_future_date_with_current_weekday():
    template = _preset("datecard", "preset_tomorrow")
    assert "{tomorrow" in template
    assert "{weekday" not in template


def test_catalog_preserves_all_76_named_entries():
    catalog = _catalog()
    expected_counts = {
        "clock": 8,
        "stopwatch": 8,
        "countdown": 7,
        "dday": 8,
        "datecard": 13,
        "text": 12,
        "weather": 20,
    }
    assert {kind: len(catalog[kind]) for kind in expected_counts} == expected_counts
    for kind in expected_counts:
        keys = [entry["label_key"] for entry in catalog[kind]]
        assert len(keys) == len(set(keys))
