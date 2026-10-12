# -*- coding: utf-8 -*-
"""Saved typography hints remain safe even when old data bypasses validation."""

import math
import re

import pytest

from calendar_app.presentation.widgets.overlay_base import _apply_span
from calendar_app.presentation.widgets.overlay_template_utils import (
    _extract_global_lh,
    _scale_template_html,
)


@pytest.mark.parametrize(
    "kind,value,base,expected",
    [
        ("REF", "36", 20, 30),
        ("RATIO", "1.5", 20, 30),
        ("DELTA", "8", 20, 28),
        ("DELTA", "-4", 20, 16),
        ("REF", "56", 12, 28),
        ("RATIO", "1", 24, 24),
        ("REF", "0", 24, 6),
    ],
)
def test_normal_font_markers_keep_their_size_contract(kind, value, base, expected):
    source = f"<span style='font-size:{kind}:{value}_TMPLREF_pt'>A</span>"
    assert _scale_template_html(source, base) == f"<span style='font-size:{expected}pt'>A</span>"


@pytest.mark.parametrize("kind", ["REF", "RATIO", "DELTA"])
@pytest.mark.parametrize("value,expected", [("1e308", 100_000), ("-1e308", 6)])
def test_finite_hints_that_overflow_during_scaling_are_bounded(kind, value, expected):
    source = f"font-size:{kind}:{value}_TMPLREF_pt"
    assert _scale_template_html(source, 100_000) == f"font-size:{expected}pt"


@pytest.mark.parametrize("kind", ["REF", "RATIO", "DELTA"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "broken", "9" * 500])
def test_unreadable_or_nonfinite_font_markers_use_the_current_font(kind, value):
    source = f"font-size:{kind}:{value}_TMPLREF_pt"
    assert _scale_template_html(source, 24) == "font-size:24pt"


@pytest.mark.parametrize("base", [0, -5, float("inf"), float("nan"), 10**500, None])
def test_invalid_legacy_base_sizes_use_the_reference_font(base):
    assert _scale_template_html("font-size:RATIO:1_TMPLREF_pt", base) == "font-size:24pt"


def test_finite_but_excessive_base_font_size_is_bounded():
    assert _scale_template_html("font-size:RATIO:1_TMPLREF_pt", 1e308) == "font-size:100000pt"


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("RATIO", "1.4", "1.4"),
        ("REF", "36", "30pt"),
        ("REF", "1e308", "100000pt"),
        ("RATIO", "1e308", "5000.0"),
        ("RATIO", "nan", "1.0"),
        ("RATIO", "inf", "1.0"),
        ("RATIO", "-1", "1.0"),
        ("RATIO", "0", "1.0"),
        ("REF", "nan", "20pt"),
        ("REF", "inf", "20pt"),
        ("REF", "9" * 500, "20pt"),
    ],
)
def test_inline_line_height_never_emits_nonfinite_or_unbounded_css(kind, value, expected):
    source = f"line-height:{kind}:{value}_TMPLREF_lh"
    assert _scale_template_html(source, 20) == "line-height:" + expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.4x", "1.4"),
        ("150%", "1.5"),
        ("36pt", "30pt"),
        ("1.4", "1.4"),
        ("2x", "2"),
        ("1.40x", "1.40"),
        ("2", "2"),
        ("1e308pt", "100000pt"),
        ("1e308x", "5000.0"),
        ("1e308%", "5000.0"),
    ],
)
def test_global_line_height_removes_the_control_and_keeps_safe_values(value, expected):
    assert _extract_global_lh(f"<lh {value}>A", 20) == ("A", expected)


@pytest.mark.parametrize(
    "value",
    [
        "nan",
        "inf",
        "-inf",
        "0",
        "-2",
        "broken",
        "infpt",
        "nanx",
        "1e999pt",
        "9" * 500 + "%",
    ],
)
def test_invalid_global_line_height_is_ignored_without_leaking_into_css(value):
    assert _extract_global_lh(f"<lh {value}>A", 20) == ("A", "")


@pytest.mark.parametrize(
    "hints",
    [
        ["size=" + "9" * 308],
        ["size=" + "9" * 308 + "x"],
        ["size=+" + "9" * 308],
        ["size=-" + "9" * 308],
        ["size=+" + "9" * 500],
        ["size=-" + "9" * 500],
        ["lh=" + "9" * 308],
        ["lh=" + "9" * 500],
        ["line_height=" + "9" * 308 + "pt"],
    ],
)
def test_previously_saved_extreme_hints_can_run_through_the_full_text_render_path(hints):
    rendered = _scale_template_html(_apply_span("Still visible", hints), 100_000)
    assert "Still visible" in rendered and "TMPLREF" not in rendered
    assert "inf" not in rendered and "nan" not in rendered
    for raw in re.findall(r"(?:font-size|line-height):([0-9.e+-]+)(pt)?", rendered):
        number, unit = raw
        assert math.isfinite(float(number))
        assert float(number) <= 100_000 if unit else float(number) <= 1.0
