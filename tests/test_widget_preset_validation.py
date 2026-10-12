# -*- coding: utf-8 -*-
"""Preset validation follows actual overlay rendering without losing legacy grammar."""

import re
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.widgets import overlay_text
from calendar_app.presentation.widgets.overlay_base import _BaseOverlayWidget
from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.overlay_template_validation import validate_widget_template
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from calendar_app.presentation.widgets.weather_template import render_weather_template

CLASSES = {
    "clock": OverlayClockWidget,
    "stopwatch": OverlayStopwatchWidget,
    "countdown": OverlayCountdownWidget,
    "datecard": OverlayDateCardWidget,
    "dday": OverlayDDayWidget,
    "text": OverlayTextWidget,
    "weather": OverlayWeatherWidget,
}
_WHEN = QDateTime.fromString("2026-10-06T12:34:56", "yyyy-MM-ddTHH:mm:ss")


@pytest.fixture(autouse=True, scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _context(font_size=24):
    return SimpleNamespace(
        _process_conditionals=_BaseOverlayWidget._process_conditionals,
        _finite_nonnegative=OverlayStopwatchWidget._finite_nonnegative,
        _RE_UTC_OFFSET=OverlayTextWidget._RE_UTC_OFFSET,
        _selected_dialog_asset_pack=lambda: "air_moments",
        _selected_dialog_moment=lambda: "birthday",
        font_size=lambda: font_size,
        _template_render_font_size=lambda: font_size,
    )


def _render(kind, template, *, font_size=24):
    context = _context(font_size)
    if kind == "clock":
        return OverlayClockWidget._resolve_clock_template(context, template, _WHEN, "KST")
    if kind == "stopwatch":
        return OverlayStopwatchWidget._resolve_sw_template(context, template, 3_661_500, True)
    if kind == "countdown":
        return OverlayCountdownWidget._resolve_cd_template(context, template, "01:02:03", _WHEN)
    if kind == "dday":
        return OverlayDDayWidget._resolve_dd_template(
            context, template, "D-0", "Release", _WHEN.date()
        )
    if kind == "datecard":
        return OverlayDateCardWidget._resolve_dc_template(context, template, _WHEN)
    if kind == "weather":
        return render_weather_template(
            template,
            {
                "city": "Seoul",
                "temp": "23",
                "unit": "°C",
                "desc": "Clear",
                "humidity": "65",
                "wind": "3.2",
                "error": "Offline",
                "_wmo": 0,
            },
            base_font_size=font_size,
        )
    registry = {
        "dday_0": SimpleNamespace(get_dday_text=lambda: "D-0"),
        "countdown_0": SimpleNamespace(get_remaining_text=lambda: "01:02:03"),
        "stopwatch_0": SimpleNamespace(get_elapsed_text=lambda: "00:10.0"),
    }
    return OverlayTextWidget.resolve_template(
        context,
        countdown_remaining="01:02:03",
        stopwatch_text="00:10.0",
        app_data={
            "task_count": 2,
            "directive_count": 1,
            "next_event": "Meeting",
            "custom_var": "Note",
        },
        widget_registry=registry,
        override_text=template,
    )


@pytest.mark.parametrize("kind", CLASSES)
def test_actual_widget_defaults_pass_preset_validation(kind):
    template = getattr(CLASSES[kind], "_DEFAULT_TEMPLATE", "__DEFAULT__")
    assert not validate_widget_template(kind, template, allow_default_sentinel=True)
    if template != "__DEFAULT__":
        rendered = _render(kind, template)
        assert rendered and "{" not in rendered and "}" not in rendered


@pytest.mark.parametrize(
    "kind,template,expected",
    [
        (
            "clock",
            "{time:%H:%M}|{date:%Y-%m-%d}|{weekday:short}|{tz_label}",
            ("12:34", "2026-10-06", "KST"),
        ),
        (
            "stopwatch",
            "{elapsed}|{hours}|{minutes}|{seconds}|{tenths}|{status}|{status_icon}",
            ("01:01:01", "5"),
        ),
        (
            "countdown",
            "{remaining}|{days}|{hours}|{minutes}|{seconds}|{target:%Y-%m-%d}",
            ("01:02:03", "2026-10-06"),
        ),
        (
            "datecard",
            "{weekday:en}|{day}|{date}|{month}|{year}|{doy}|{week_num}|{quarter}|{days_left_month}|{days_in_month}|{yesterday}|{tomorrow}",
            ("Tue", "2026.10.06", "Q4", "2026.10.05", "2026.10.07"),
        ),
        (
            "dday",
            "{dday}|{days}|{sign}|{label}|{date}|{date_short}|{date:%Y-%m-%d}",
            ("D-0", "Release", "2026.10.06", "2026-10-06"),
        ),
        (
            "weather",
            "{city}|{temp}|{unit}|{desc}|{icon}|{humidity}|{wind}|{error}",
            ("Seoul", "23", "°C", "Offline", "data:image/png;base64,"),
        ),
        (
            "text",
            "{time:%H:%M}|{date:%Y}|{weekday:en}|{day_of_year}|{dday:dday_0}|{countdown:countdown_0:hm}|{stopwatch:stopwatch_0}|{task_count}|{directive_count}|{next_event}|{custom_var}",
            ("D-0", "01:02", "00:10.0", "Meeting", "Note"),
        ),
    ],
)
def test_supported_variables_and_modifiers_are_valid_and_produce_real_values(
    kind, template, expected
):
    assert not validate_widget_template(kind, template)
    rendered = _render(kind, template)
    for value in expected:
        assert value in rendered


@pytest.mark.parametrize(
    "kind,template",
    [
        ("clock", "{elapsed}"),
        ("clock", "{weekday:en}"),
        ("clock", "{art}"),
        ("stopwatch", "{elapsed:%H:%M}"),
        ("countdown", "{target:}"),
        ("datecard", "{weekday:fr}"),
        ("dday", "{week_num}"),
        ("weather", "{precipitation}"),
        ("weather", "{art}"),
        ("weather", "{_wmo}"),
        ("text", "{weather}"),
        ("text", "{day_of_year:short}"),
    ],
)
def test_genuinely_unsupported_widget_tokens_still_fail_validation(kind, template):
    assert "unknown_variable" in {issue.code for issue in validate_widget_template(kind, template)}


@pytest.mark.parametrize("kind", ["datecard", "dday"])
@pytest.mark.parametrize(
    "hint,font_size,expected",
    [
        ("56", 24, 56),
        ("56", 12, 28),
        ("base", 24, 24),
        ("1.5x", 24, 36),
        ("150%", 24, 36),
        ("+8", 24, 32),
        ("-4", 24, 20),
    ],
)
def test_moment_art_accepts_shared_size_forms_and_renders_the_requested_size(
    kind, hint, font_size, expected
):
    template = "{art|size=" + hint + "}"
    assert not validate_widget_template(kind, template)
    rendered = _render(kind, template, font_size=font_size)
    assert "data:image/png;base64," in rendered
    assert re.search(r'width="' + str(expected) + r'"', rendered)
    assert re.search(r'height="' + str(expected) + r'"', rendered)


@pytest.mark.parametrize("kind", ["datecard", "dday"])
def test_new_art_variable_is_not_an_unimplemented_condition_variable(kind):
    template = "{if art == birthday}{art}{/if}"
    assert "invalid_condition_variable" in {
        issue.code for issue in validate_widget_template(kind, template)
    }
    assert not validate_widget_template(kind, "{art|bold|italic|color=accent|lh=1.4|size=56}")


@pytest.mark.parametrize("separator", [" ", "\t", "\n"])
def test_condition_whitespace_matches_the_shared_renderers(separator):
    template = "{if" + separator + "task_count > 0}Busy{else}Free{/if}"
    assert not validate_widget_template("text", template)
    assert _render("text", template) == "Busy"


def test_weather_error_variable_can_also_drive_a_supported_condition():
    template = "{if error == Offline}{error|color=warning}{else}Ready{/if}"
    assert not validate_widget_template("weather", template)
    assert "Offline" in _render("weather", template)
    assert "Ready" not in _render("weather", template)


@pytest.mark.parametrize("value,expected", [("D-0", "Today D-0"), ("D-8", "Later D-8")])
def test_plain_dday_condition_and_display_share_the_first_widget_snapshot(value, expected):
    getter = Mock(return_value=value)
    registry = {"dday_0": SimpleNamespace(get_dday_text=getter)}
    template = "{if dday == D-0}Today{else}Later{/if} {dday}"
    assert not validate_widget_template("text", template)
    assert (
        OverlayTextWidget.resolve_template(
            _context(), widget_registry=registry, override_text=template
        )
        == expected
    )
    getter.assert_called_once_with()


def test_dday_plain_and_instance_conditions_do_not_re_read_a_changing_getter():
    getter = Mock(side_effect=["D-0", "D+1"])
    registry = {"dday_0": SimpleNamespace(get_dday_text=getter)}
    template = "{if dday == D-0}Today{/if}:{dday}|{if dday:dday_0 == D-0}Today{/if}:{dday:dday_0}"
    assert not validate_widget_template("text", template)
    assert (
        OverlayTextWidget.resolve_template(
            _context(), widget_registry=registry, override_text=template
        )
        == "Today:D-0|Today:D-0"
    )
    getter.assert_called_once_with()


@pytest.mark.parametrize(
    "registry",
    [
        {},
        {"clock_0": object()},
        {"dday_0": SimpleNamespace(get_dday_text=lambda: None)},
        {
            "dday_0": SimpleNamespace(
                get_dday_text=Mock(side_effect=RuntimeError("deleted Qt object"))
            )
        },
    ],
)
def test_missing_or_unreadable_dday_has_the_same_safe_condition_and_display_fallback(registry):
    template = "{if dday == D-?}Unknown{else}Known{/if}:{dday}:{dday:missing_0}"
    assert not validate_widget_template("text", template)
    assert (
        OverlayTextWidget.resolve_template(
            _context(), widget_registry=registry, override_text=template
        )
        == "Unknown:D-?:D-?"
    )


def test_text_variable_outer_whitespace_matches_existing_validator_contract():
    template = "{ task_count |size=base} { dday }"
    assert not validate_widget_template("text", template)
    rendered = OverlayTextWidget.resolve_template(
        _context(), app_data={"task_count": 2}, override_text=template
    )
    assert ">2</span> D-?" in rendered


@pytest.mark.parametrize(
    "hint", ["size=" + "9" * 400, "size=" + "9" * 400 + "x", "lh=" + "9" * 400 + "pt"]
)
def test_numeric_overflow_is_rejected_before_it_can_reach_a_renderer(hint):
    issues = validate_widget_template("clock", "{time|" + hint + "}")
    assert {issue.code for issue in issues} in ({"invalid_size"}, {"invalid_line_height"})


def test_existing_relative_sizes_colors_and_conditions_keep_their_validation_contract():
    template = "{align=right}{lh=150%}{time:tz=UTC+9:%H:%M|size=150%|bold|italic|color=#fff|lh=1.4x}\n{if countdown:countdown_0 < 1h}{countdown:countdown_0:hm|size=+8}{else}{custom_var:note|size=-4|color=muted}{/if}"
    assert not validate_widget_template("text", template)


@pytest.mark.parametrize(
    "template,tier",
    [
        ("{task_count|size=32|bold}", "slow"),
        ("{directive_count|color=accent}", "slow"),
        ("{next_event|size=base}", "slow"),
        ("{custom_var:note|italic}", "slow"),
        ("{ weekday:short |size=18}", "slow"),
        ("{ day_of_year |size=24}", "slow"),
        ("{if task_count > 0}Busy{else}Free{/if}", "slow"),
        ("{if countdown:countdown_0 < 1h}Soon{/if}", "med"),
        ("{ countdown:countdown_0 |bold}", "med"),
        ("{ stopwatch:stopwatch_0 |size=28}", "fast"),
        ("{ time:tz=UTC+9:%H:%M |size=48}", "fast"),
        ("{task_count|size=32} {time:%H:%M}", "fast"),
    ],
)
def test_styled_and_spaced_variables_and_conditions_request_the_correct_refresh_tier(
    template, tier
):
    context = SimpleNamespace(
        _label_text=lambda: template,
        _template_variables=OverlayTextWidget._template_variables,
        _FAST_VARS=OverlayTextWidget._FAST_VARS,
        _MED_VARS=OverlayTextWidget._MED_VARS,
        _SLOW_VARS=OverlayTextWidget._SLOW_VARS,
        _CONDITION_START_RE=OverlayTextWidget._CONDITION_START_RE,
    )
    assert OverlayTextWidget._is_template(context)
    assert OverlayTextWidget.refresh_tier(context) == tier


@pytest.mark.parametrize("literal", ["My tasks", "{task_counter}", "{timer}", "{custom_variable}"])
def test_literal_text_and_unknown_prefixes_do_not_start_dynamic_refresh(literal):
    context = SimpleNamespace(
        _label_text=lambda: literal,
        _template_variables=OverlayTextWidget._template_variables,
        _FAST_VARS=OverlayTextWidget._FAST_VARS,
        _MED_VARS=OverlayTextWidget._MED_VARS,
        _SLOW_VARS=OverlayTextWidget._SLOW_VARS,
        _CONDITION_START_RE=OverlayTextWidget._CONDITION_START_RE,
    )
    assert not OverlayTextWidget._is_template(context)
    assert OverlayTextWidget.refresh_tier(context) == "none"


def test_styled_app_variables_update_the_actual_text_refresh_path():
    context = _context()
    context._is_template = lambda: True
    context.resolve_template = lambda *args: OverlayTextWidget.resolve_template(
        context,
        *args,
        override_text="{task_count|size=32|bold}:{directive_count|color=accent}",
    )
    context._resolve_template_color_aliases = lambda value: value.replace(
        "TMPLCOLOR:accent", "#45a3ff"
    )
    context._text_label = SimpleNamespace(setText=Mock())
    context._force_resize = Mock()
    OverlayTextWidget.refresh_template(context, app_data={"task_count": 3, "directive_count": 2})
    rendered = context._text_label.setText.call_args.args[0]
    assert "{task_count" not in rendered and "{directive_count" not in rendered
    assert ">3</span>" in rendered and ">2</span>" in rendered
    assert "font-size:32pt" in rendered
    context._force_resize.assert_called_once_with()


@pytest.mark.parametrize(
    "token,key",
    [
        ("next_event", "next_event"),
        ("custom_var", "custom_var"),
        ("custom_var:note", "custom_var_note"),
    ],
)
def test_external_app_text_is_visible_literal_text_inside_styled_variables(token, key):
    literal = '<수료> & <b>Meeting</b> "Notes"'
    rendered = OverlayTextWidget.resolve_template(
        _context(),
        app_data={key: literal},
        override_text="{" + token + "|size=24|bold}",
    )
    assert "&lt;수료&gt; &amp; &lt;b&gt;Meeting&lt;/b&gt;" in rendered
    doc = QTextDocument()
    doc.setHtml(rendered)
    assert doc.toPlainText() == literal


@pytest.mark.parametrize(
    "kind,getter_name,fallback",
    [
        ("countdown", "get_remaining_text", "--:--:--"),
        ("stopwatch", "get_elapsed_text", "00:00.0"),
    ],
)
def test_countdown_and_stopwatch_conditions_and_display_share_one_safe_snapshot(
    kind, getter_name, fallback
):
    getter = Mock(side_effect=RuntimeError("deleted Qt object"))
    inst_id = kind + "_0"
    registry = {inst_id: SimpleNamespace(**{getter_name: getter})}
    template = (
        "{if "
        + kind
        + ":"
        + inst_id
        + " == "
        + fallback
        + "}Unknown{/if}:{"
        + kind
        + ":"
        + inst_id
        + "}"
    )
    assert not validate_widget_template("text", template)
    result = OverlayTextWidget.resolve_template(
        _context(), widget_registry=registry, override_text=template
    )
    assert result == "Unknown:" + fallback
    getter.assert_called_once_with()


def test_spaced_condition_control_tokens_match_validation_and_rendering():
    template = "{ if task_count > 0 }Busy{ else }Free{ /if }"
    assert not validate_widget_template("text", template)
    assert _render("text", template) == "Busy"


@pytest.mark.parametrize(
    "timezone",
    ["UTC+99999999999999", "UTC+9:999999999", "UTC+14:01", "UTC+15", "UTC-" + "9" * 5000],
)
def test_invalid_timezone_offsets_use_a_safe_local_time_fallback(timezone):
    template = "{time:tz=" + timezone + ":%H:%M}"
    assert not validate_widget_template("text", template)
    rendered = _render("text", template)
    assert re.fullmatch(r"\d{2}:\d{2}", rendered)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("{time:tz=UTC:%I:%M %p}", "01:34 PM"),
        ("{time:tz=UTC+9:30:%H:%M}", "23:04"),
        ("{time:tz=UTC-5:30:%I:%M %p}", "08:04 AM"),
    ],
)
def test_timezone_minutes_and_twelve_hour_formats_have_real_values(monkeypatch, token, expected):
    fixed = QDateTime.fromString("2026-10-06T13:34:56Z", Qt.DateFormat.ISODate)
    monkeypatch.setattr(overlay_text, "QDateTime", SimpleNamespace(currentDateTime=lambda: fixed))
    assert not validate_widget_template("text", token)
    assert _render("text", token) == expected
