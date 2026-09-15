# -*- coding: utf-8 -*-
"""Overlay preset grammar and widget-kind mapping regressions."""

import json
from pathlib import Path

from calendar_app.presentation.widgets import overlay_base
from calendar_app.presentation.widgets.overlay_base import (
    _PRESET_FALLBACK,
    _apply_span,
    _get_widget_presets,
)
from calendar_app.presentation.widgets.overlay_template_utils import _scale_template_html
from calendar_app.presentation.widgets.overlay_template_validation import (
    normalize_widget_template_kind,
    validate_widget_template,
)


def test_all_shipped_json_and_fallback_presets_follow_widget_grammar():
    path = Path("calendar_app/presentation/widgets/widget_presets.json")
    sources = [json.loads(path.read_text(encoding="utf-8", errors="strict")), _PRESET_FALLBACK]

    failures = []
    for source_name, source in zip(("json", "fallback"), sources, strict=True):
        for kind, entries in source.items():
            if kind.startswith("$"):
                continue
            for index, entry in enumerate(entries):
                issues = validate_widget_template(
                    kind,
                    entry.get("template", ""),
                    allow_default_sentinel=True,
                )
                if issues:
                    failures.append(
                        (source_name, kind, index, [issue.summary() for issue in issues])
                    )

    assert failures == []


def test_json_and_fallback_preset_catalogs_stay_in_sync():
    path = Path("calendar_app/presentation/widgets/widget_presets.json")
    shipped = json.loads(path.read_text(encoding="utf-8", errors="strict"))

    assert shipped == _PRESET_FALLBACK


def test_date_card_prefix_maps_to_the_shipped_datecard_presets():
    assert normalize_widget_template_kind("overlay_date_card") == "datecard"
    presets = _get_widget_presets("date_card", lambda _key, fallback: fallback)
    assert len(presets) == 13
    assert presets[0][0] == "Default"


def test_invalid_shipped_catalog_uses_the_complete_widget_fallback(monkeypatch):
    monkeypatch.setattr(
        overlay_base,
        "_load_widget_presets_json",
        lambda: {
            "$schema_version": 1,
            "clock": [
                {
                    "label_key": "broken",
                    "label_default": "Broken",
                    "template": "{elapsed}",
                }
            ],
        },
    )

    presets = _get_widget_presets("clock", lambda _key, fallback: fallback)

    assert len(presets) == len(_PRESET_FALLBACK["clock"])
    assert all(label != "Broken" for label, _template in presets)


def test_validator_rejects_wrong_widget_variables_and_broken_conditions():
    unknown = validate_widget_template("clock", "{elapsed|size=32|bold}")
    broken = validate_widget_template("text", "{if task_count > 0}Tasks")
    nested = validate_widget_template(
        "text",
        "{if task_count > 0}{if task_count > 1}Many{/if}{/if}",
    )

    assert {issue.code for issue in unknown} == {"unknown_variable"}
    assert "unclosed_condition" in {issue.code for issue in broken}
    assert "nested_condition" in {issue.code for issue in nested}


def test_validator_rejects_invalid_style_hints_and_accepts_supported_forms():
    invalid = validate_widget_template(
        "clock",
        "{time:%H:%M|size=huge|color=javascript:bad|shadow}",
    )
    valid = validate_widget_template(
        "text",
        "{align=right}{time:tz=UTC+9:%H:%M|size=150%|bold|color=accent|lh=1.4}",
    )

    assert {issue.code for issue in invalid} == {
        "invalid_size",
        "invalid_color",
        "unknown_hint",
    }
    assert valid == ()


def test_validator_accepts_documented_dday_instance_condition():
    issues = validate_widget_template(
        "text",
        "{if dday:dday_0 == D-0}Today{/if}",
    )

    assert issues == ()


def test_line_height_units_validate_and_render_consistently():
    ratio = _scale_template_html(_apply_span("A", ["lh=1.4x"]), 20)
    percent = _scale_template_html(_apply_span("B", ["line=150%"]), 20)
    points = _scale_template_html(_apply_span("C", ["line_height=24pt"]), 20)

    assert "line-height:1.4" in ratio
    assert "line-height:1.5" in percent
    assert "line-height:20pt" in points
